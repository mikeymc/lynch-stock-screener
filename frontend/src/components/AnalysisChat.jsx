// ABOUTME: Brief page component with AI-generated stock analysis and chat interface
// ABOUTME: Two-column layout in full mode (analysis left, chat right); chatOnly mode for sidebar use

import { useState, useEffect, useRef, forwardRef, useImperativeHandle, memo, useCallback, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ChatChart from './ChatChart'

const API_BASE = '/api'

const LOADING_MESSAGES = [
  "Scanning earnings reports...",
  "Reading latest news coverage...",
  "Processing earnings call transcripts...",
  "Analyzing insider trading patterns...",
  "Reviewing financial statements...",
  "Checking material event filings...",
  "Synthesizing market context...",
  "Generating investment insights..."
]

function SourceCitation({ sources }) {
  const [expanded, setExpanded] = useState(false)

  if (!sources || sources.length === 0) return null

  const sourceLabels = {
    'business': 'Business Description',
    'risk_factors': 'Risk Factors',
    'mda': "Management's Discussion & Analysis",
    'market_risk': 'Market Risk Disclosures'
  }

  return (
    <div className="chat-message-sources">
      <button
        className="sources-toggle"
        onClick={() => setExpanded(!expanded)}
      >
        📚 Sources ({sources.length}) {expanded ? '▼' : '▶'}
      </button>
      {expanded && (
        <ul className="sources-list">
          {sources.map((source, idx) => (
            <li key={idx}>{sourceLabels[source] || source}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

// Custom markdown components for chart rendering
const markdownComponents = {
  code({ node, inline, className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || '')
    const language = match ? match[1] : ''

    // Render chart blocks with ChatChart component
    if (language === 'chart' && !inline) {
      return <ChatChart chartJson={String(children).replace(/\n$/, '')} />
    }

    // Default code block rendering
    return (
      <code className={className} {...props}>
        {children}
      </code>
    )
  }
}

// Memoized ChatMessage component - only re-renders when content changes
const ChatMessage = memo(function ChatMessage({ role, content, sources }) {
  const roleLabel = role === 'user' ? '👤 You' : role === 'assistant' ? '📊 Analyst' : '⚠️ Error'

  return (
    <div className={`chat-message ${role} analysis-message`}>
      <div className="chat-message-header">{roleLabel}</div>
      <div className="chat-message-content markdown-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {content}
        </ReactMarkdown>
      </div>
      {role === 'assistant' && <SourceCitation sources={sources} />}
    </div>
  )
})

const AnalysisChat = forwardRef(function AnalysisChat({ symbol, stockName, chatOnly = false, contextType = 'brief' }, ref) {
  // Analysis state
  const [analysis, setAnalysis] = useState(null)
  const [analysisLoading, setAnalysisLoading] = useState(true)
  const [analysisError, setAnalysisError] = useState(null)
  const [generatedAt, setGeneratedAt] = useState(null)
  const [cached, setCached] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [selectedModel, setSelectedModel] = useState('gemini-3-flash-preview')

  // Chat state
  const [messages, setMessages] = useState([])
  // Note: inputMessage removed - using uncontrolled textarea via ref for performance
  const [chatLoading, setChatLoading] = useState(false)
  const [conversationId, setConversationId] = useState(null)
  const [streamingMessage, setStreamingMessage] = useState('')
  const [streamingSources, setStreamingSources] = useState([])
  const [loadingHistory, setLoadingHistory] = useState(true)
  const [showScrollIndicator, setShowScrollIndicator] = useState(false)
  const [loadingMessageIndex, setLoadingMessageIndex] = useState(0)
  const [agentMode, setAgentMode] = useState(() => {
    // Persist agent mode toggle across page navigations
    const saved = localStorage.getItem('agentModeEnabled')
    return saved === 'true'
  })
  const [agentThinking, setAgentThinking] = useState('')
  const [agentModeEnabled, setAgentModeEnabled] = useState(false)
  const [showScrollDown, setShowScrollDown] = useState(false)
  const [isNearBottom, setIsNearBottom] = useState(true)

  // Start a new chat session (clears messages and resets conversation)
  const startNewChat = useCallback(() => {
    setMessages([])
    setConversationId(null)
    setStreamingMessage('')
    setStreamingSources([])
    setAgentThinking('')
    // Focus input after reset
    setTimeout(() => inputRef.current?.focus(), 100)
  }, [])

  const messagesEndRef = useRef(null)
  const messagesContainerRef = useRef(null)
  const inputRef = useRef(null)

  // Expose sendMessage to parent via ref for batch review
  useImperativeHandle(ref, () => ({
    sendMessage: (message, options) => sendMessage(message, options)
  }))

  // Track scroll position to show/hide scroll indicator and down arrow (debounced)
  const scrollTimeoutRef = useRef(null)
  const handleScroll = useCallback(() => {
    // Debounce scroll handling
    if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current)
    scrollTimeoutRef.current = setTimeout(() => {
      const container = messagesContainerRef.current
      if (!container) return

      const { scrollTop, scrollHeight, clientHeight } = container
      const hasMoreContent = scrollHeight > clientHeight
      const isNearTop = scrollTop < 50
      const distanceFromBottom = scrollHeight - scrollTop - clientHeight
      const nearBottom = distanceFromBottom < 100

      setShowScrollIndicator(hasMoreContent && isNearTop)
      setIsNearBottom(nearBottom)
      setShowScrollDown(!nearBottom && scrollHeight > clientHeight)
    }, 50)  // 50ms debounce
  }, [])

  // Check for scroll indicator on content changes
  useEffect(() => {
    handleScroll()
  }, [analysis, messages, analysisLoading])

  // When a new message is added, scroll appropriately:
  // - User messages: scroll to bottom (so user sees their message)
  // - Assistant messages: scroll to show the START of the message (so user can read from beginning)
  const prevMessagesLengthRef = useRef(messages.length)

  useEffect(() => {
    const container = messagesContainerRef.current
    if (!container) return

    // Check if a new message was added
    if (messages.length > prevMessagesLengthRef.current) {
      const lastMessage = messages[messages.length - 1]

      if (lastMessage?.role === 'user') {
        // User message: scroll to bottom to show their message
        container.scrollTop = container.scrollHeight
      } else if (lastMessage?.role === 'assistant') {
        // Assistant message: scroll the USER's question to the TOP
        // so both the question and response are visible
        const allMessages = container.querySelectorAll('.chat-message')
        if (allMessages.length >= 2) {
          // Get the second-to-last message (the user's question)
          const userQuestionEl = allMessages[allMessages.length - 2]
          // Use offsetTop instead of scrollIntoView to avoid scrolling the page
          container.scrollTop = userQuestionEl.offsetTop - container.offsetTop
        }
      }
    }

    prevMessagesLengthRef.current = messages.length
    handleScroll()
  }, [messages.length])

  // Restore focus to input after chat response completes
  useEffect(() => {
    if (!chatLoading && inputRef.current) {
      inputRef.current.focus()
    }
  }, [chatLoading])

  // Fetch Agent Mode feature flag
  useEffect(() => {
    const fetchAgentModeFlag = async () => {
      try {
        const response = await fetch(`${API_BASE}/settings`)
        if (response.ok) {
          const settings = await response.json()
          setAgentModeEnabled(
            settings.feature_agent_mode_enabled?.value === true ||
            settings.feature_agent_mode_enabled?.value === 'true'
          )
        }
      } catch (err) {
        console.error('Error fetching agent mode flag:', err)
      }
    }

    fetchAgentModeFlag()
  }, [])

  // Load agent conversation when agent mode is active
  useEffect(() => {
    if (!agentMode) return

    const loadAgentConversation = async () => {
      try {
        // Fetch recent agent conversations
        const response = await fetch(`${API_BASE}/agent/conversations`)
        if (!response.ok) {
          console.error('Failed to fetch agent conversations')
          return
        }

        const data = await response.json()

        if (data.conversations && data.conversations.length > 0) {
          // Load most recent conversation
          const conv = data.conversations[0]
          setConversationId(conv.id)

          // Load messages
          const msgResponse = await fetch(`${API_BASE}/agent/conversation/${conv.id}/messages`)
          if (msgResponse.ok) {
            const msgData = await msgResponse.json()
            console.log('[Agent] Loaded messages from DB:', msgData.messages)
            setMessages(msgData.messages || [])
            // Scroll to bottom after messages load
            setTimeout(() => {
              const container = messagesContainerRef.current
              if (container) {
                container.scrollTop = container.scrollHeight
              }
            }, 100)
          }
        } else {
          // Create new conversation
          const createResponse = await fetch(`${API_BASE}/agent/conversations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
          })

          if (createResponse.ok) {
            const createData = await createResponse.json()
            setConversationId(createData.conversation_id)
            setMessages([])  // Start with empty messages
          }
        }
      } catch (error) {
        console.error('Error loading agent conversation:', error)
      }
    }

    loadAgentConversation()
  }, [agentMode])  // Only re-run when agentMode changes

  // Cycle loading messages during brief generation with random timing
  useEffect(() => {
    if ((analysisLoading || isGenerating) && !analysis) {
      let timeoutId
      const cycleMessage = () => {
        setLoadingMessageIndex(prev => (prev + 1) % LOADING_MESSAGES.length)
        const randomDelay = 1500 + Math.random() * 1500 // 1.5-3 seconds
        timeoutId = setTimeout(cycleMessage, randomDelay)
      }
      const initialDelay = 1500 + Math.random() * 1500
      timeoutId = setTimeout(cycleMessage, initialDelay)
      return () => clearTimeout(timeoutId)
    } else {
      setLoadingMessageIndex(0)
    }
  }, [analysisLoading, isGenerating, analysis])

  // Fetch analysis
  const fetchAnalysis = async (forceRefresh = false, signal = null, onlyCached = false) => {
    try {
      if (forceRefresh) {
        setRefreshing(true)
      } else {
        setAnalysisLoading(true)
      }
      setAnalysisError(null)
      setIsGenerating(true)

      let baseUrl = forceRefresh
        ? `${API_BASE}/stock/${symbol}/lynch-analysis/refresh`
        : `${API_BASE}/stock/${symbol}/lynch-analysis`

      // Handle simple check for cached data (no streaming)
      if (onlyCached && !forceRefresh) {
        const url = `${baseUrl}?only_cached=true&model=${selectedModel}`
        const response = await fetch(url, { signal })
        if (!response.ok) throw new Error(response.statusText)
        const data = await response.json()
        setAnalysis(data.analysis)
        setGeneratedAt(data.generated_at)
        setCached(data.cached)
        return
      }

      // Prepare request for streaming
      let url = baseUrl
      const options = {
        method: forceRefresh ? 'POST' : 'GET',
        signal
      }

      if (forceRefresh) {
        options.headers = { 'Content-Type': 'application/json' }
        options.body = JSON.stringify({ model: selectedModel, stream: true })
      } else {
        url += `?model=${selectedModel}&stream=true`
      }

      const response = await fetch(url, options)

      if (!response.ok) {
        throw new Error(`Failed to fetch analysis: ${response.statusText}`)
      }

      // Handle streaming response
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      // Start with empty string if not using cached data effectively (or if we want to show it building up)
      // If we are refreshing, definitely clear. If loading fresh, clear.
      setAnalysis('')

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))

              if (data.type === 'metadata') {
                setCached(data.cached)
                setGeneratedAt(data.generated_at)
              } else if (data.type === 'chunk') {
                // Filter out debug metadata lines like [Prompt: 0.00s, 17,448 chars]
                let content = data.content
                // Robust regex replacement instead of startswith check
                content = content.replace(/\[Prompt:[^\]]*\]/g, '')
                if (content) {
                  setAnalysis(prev => (prev || '') + content)
                }
              } else if (data.type === 'error') {
                throw new Error(data.message)
              }
            } catch (e) {
              console.error('Error parsing stream:', e)
            }
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        console.log('Fetch aborted')
        return
      }
      console.error('Error fetching analysis:', err)
      setAnalysisError(err.message)
    } finally {
      setAnalysisLoading(false)
      setRefreshing(false)
      setIsGenerating(false)
    }
  }

  // Load conversation history (skip if agent mode is active - agent has its own context)
  useEffect(() => {
    // Don't load regular chat history if starting in agent mode
    if (agentMode) {
      setLoadingHistory(false)
      return
    }

    const loadConversationHistory = async () => {
      try {
        setLoadingHistory(true)
        const response = await fetch(`${API_BASE}/chat/${symbol}/conversations`)

        if (response.ok) {
          const data = await response.json()
          const conversations = data.conversations || []

          if (conversations.length > 0) {
            const recentConversation = conversations[0]
            setConversationId(recentConversation.id)

            const messagesResponse = await fetch(`${API_BASE}/chat/conversation/${recentConversation.id}/messages`)
            if (messagesResponse.ok) {
              const messagesData = await messagesResponse.json()
              setMessages(messagesData.messages || [])
            }
          }
        }
      } catch (error) {
        console.error('Error loading conversation history:', error)
      } finally {
        setLoadingHistory(false)
      }
    }

    loadConversationHistory()
  }, [symbol]) // Note: intentionally not including agentMode as dep to prevent refetch on toggle


  // Auto-fetch analysis on mount (cache only) - skip in chatOnly mode
  useEffect(() => {
    if (chatOnly) {
      setAnalysisLoading(false)
      return
    }
    const controller = new AbortController()
    fetchAnalysis(false, controller.signal, true)
    return () => controller.abort()
  }, [symbol, selectedModel, chatOnly])

  const formatDate = (isoString) => {
    if (!isoString) return ''
    const date = new Date(isoString)
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const handleRefresh = () => {
    fetchAnalysis(true)
  }

  const handleGenerate = () => {
    fetchAnalysis(false)
  }

  // Helper to save agent messages to database
  const saveAgentMessage = async (role, content, toolCalls = null) => {
    console.log('[Agent] saveAgentMessage called:', { role, contentLength: content?.length, agentMode, conversationId })

    if (!agentMode || !conversationId) {
      console.warn('[Agent] Skipping save - agentMode:', agentMode, 'conversationId:', conversationId)
      return
    }

    try {
      const response = await fetch(`${API_BASE}/agent/conversation/${conversationId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, content, tool_calls: toolCalls })
      })

      if (!response.ok) {
        console.error('[Agent] Failed to save message:', await response.text())
      } else {
        console.log('[Agent] Message saved successfully:', role)
      }
    } catch (error) {
      console.error('Error saving agent message:', error)
    }
  }

  const sendMessage = async (messageText = null, options = {}) => {
    const userMessage = (messageText || inputRef.current?.value || '').trim()
    if (!userMessage || chatLoading) return

    // Clear input via DOM (uncontrolled)
    if (inputRef.current) inputRef.current.value = ''
    // Only show user message bubble if not hidden (for comment reviews)
    if (!options.hideUserMessage) {
      setMessages(prev => [...prev, { role: 'user', content: userMessage }])
      // Save user message to database (agent mode only)
      saveAgentMessage('user', userMessage)
    }
    setChatLoading(true)
    setStreamingMessage('')
    setStreamingSources([])
    setAgentThinking('')

    try {
      // Choose endpoint based on agent mode
      const endpoint = agentMode
        ? `${API_BASE}/chat/${symbol}/agent`
        : `${API_BASE}/chat/${symbol}/message/stream`

      const body = agentMode
        ? { message: userMessage, history: messages.map(m => ({ role: m.role, content: m.content })) }
        : { message: userMessage, conversation_id: conversationId, lynch_analysis: analysis || null, context_type: contextType }

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let fullMessage = ''
      let sources = []
      let toolCalls = []

      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          // Process any remaining data in buffer when stream ends
          if (buffer.trim()) {
            const remainingLines = buffer.split('\n')
            for (const line of remainingLines) {
              if (line.startsWith('data: ')) {
                try {
                  const data = JSON.parse(line.slice(6))
                  if (data.type === 'done') {
                    setMessages(prev => [...prev, {
                      role: 'assistant',
                      content: fullMessage,
                      sources: sources,
                      toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
                      message_id: data.data?.message_id
                    }])
                    // Save assistant message to database (agent mode only)
                    saveAgentMessage('assistant', fullMessage, toolCalls.length > 0 ? toolCalls : null)
                    setStreamingMessage('')
                    setStreamingSources([])
                    setAgentThinking('')
                    setChatLoading(false)
                  }
                } catch (e) {
                  console.error('Error parsing final buffer:', e)
                }
              }
            }
          }
          // Ensure we finalize if we have a message but never got 'done'
          if (fullMessage && chatLoading) {
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: fullMessage,
              sources: sources,
              toolCalls: toolCalls.length > 0 ? toolCalls : undefined
            }])
            // Save assistant message to database (agent mode only)
            saveAgentMessage('assistant', fullMessage, toolCalls.length > 0 ? toolCalls : null)
            setStreamingMessage('')
            setStreamingSources([])
            setAgentThinking('')
            setChatLoading(false)
          }
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6))

            if (data.type === 'conversation_id') {
              setConversationId(data.data)
            } else if (data.type === 'sources') {
              sources = data.data
              setStreamingSources(data.data)
            } else if (data.type === 'token') {
              let content = data.data
              // Filter out debug metadata lines if they slip through
              content = content.replace(/\[Prompt:[^\]]*\]/g, '')
              fullMessage += content
              setStreamingMessage(fullMessage)
              setAgentThinking('')  // Clear thinking when we start getting response
            } else if (data.type === 'thinking') {
              // Agent mode: show what the agent is doing
              setAgentThinking(data.data)
            } else if (data.type === 'tool_call') {
              // Agent mode: track tool calls
              toolCalls.push(data.data)
              setAgentThinking(`Calling ${data.data.tool}...`)
            } else if (data.type === 'done') {
              setMessages(prev => [...prev, {
                role: 'assistant',
                content: fullMessage,
                sources: sources,
                toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
                message_id: data.data?.message_id
              }])
              // Save assistant message to database (agent mode only)
              saveAgentMessage('assistant', fullMessage, toolCalls.length > 0 ? toolCalls : null)
              setStreamingMessage('')
              setStreamingSources([])
              setAgentThinking('')
              setChatLoading(false)
            } else if (data.type === 'error') {
              console.error('Stream error:', data.data)
              setMessages(prev => [...prev, {
                role: 'error',
                content: `Error: ${data.data}`
              }])
              setStreamingMessage('')
              setStreamingSources([])
              setAgentThinking('')
              setChatLoading(false)
            }
          }
        }
      }

    } catch (error) {
      console.error('Error sending message:', error)
      setMessages(prev => [...prev, {
        role: 'error',
        content: 'Sorry, there was an error. Please check that the backend server is running and try again.'
      }])
      setStreamingMessage('')
      setStreamingSources([])
      setAgentThinking('')
      setChatLoading(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  // Analysis content (for left column in two-column mode)
  const analysisContent = (
    <div className="brief-analysis-container">
      <div className="section-item">
        <div className="section-content">
          {(analysisLoading || isGenerating) && !analysis ? (
            <div className="section-summary">
              <div className="brief-generating">
                <div className="generating-spinner"></div>
                <div className="generating-text">
                  <span className="generating-title">Generating brief...</span>
                  <span className="generating-subtitle" key={loadingMessageIndex}>{LOADING_MESSAGES[loadingMessageIndex]}</span>
                </div>
              </div>
            </div>
          ) : analysisError ? (
            <div className="section-summary">
              <p>Failed to load analysis: {analysisError}</p>
              <button onClick={() => fetchAnalysis(false, null, true)} className="retry-button">
                Retry
              </button>
            </div>
          ) : !analysis ? (
            <div className="section-summary">
              <p>No brief generated yet for {stockName}.</p>
              <button onClick={handleGenerate} className="generate-button" style={{ marginTop: '1rem' }}>
                ✨ Generate
              </button>
            </div>
          ) : (
            <>
              <div className="brief-controls">
                <span className="brief-metadata">
                  {cached ? '📦 Cached' : '✨ Fresh'} · {formatDate(generatedAt)}
                </span>
                <button
                  onClick={handleRefresh}
                  disabled={refreshing}
                  className="generate-button"
                >
                  {refreshing ? '...' : '🔄 Regenerate'}
                </button>
              </div>
              <div className="section-summary">
                <div className="summary-content">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{analysis}</ReactMarkdown>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )

  // Chat content (for right column or standalone)
  const chatContent = (
    <div className="unified-chat-container">
      <div
        className="unified-chat-messages"
        ref={messagesContainerRef}
        onScroll={handleScroll}
      >
        {/* Loading history indicator */}
        {loadingHistory && (
          <div className="chat-loading-history">
            <div className="loading">Loading conversation history...</div>
          </div>
        )}

        {/* Chat messages - using memoized component for performance */}
        {messages.map((msg, idx) => (
          <ChatMessage
            key={msg.message_id || idx}
            role={msg.role}
            content={msg.content}
            sources={msg.sources}
          />
        ))}

        {/* Streaming message */}
        {chatLoading && (
          <div className="chat-message assistant streaming">
            <div className="chat-message-header">
              {agentMode ? '🤖 Agent' : '📊 Analyst'}{agentThinking ? ` - ${agentThinking}` : ' Thinking...'}
            </div>
            <div className="chat-message-content markdown-content">
              {streamingMessage ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{streamingMessage}</ReactMarkdown>
              ) : (
                <div className="chat-loading">
                  <span className="typing-indicator">●</span>
                  <span className="typing-indicator">●</span>
                  <span className="typing-indicator">●</span>
                </div>
              )}
            </div>
            {streamingMessage && (
              <div className="streaming-cursor">▊</div>
            )}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Scroll indicator arrow - shows when not at bottom */}
      {(showScrollIndicator || showScrollDown) && (
        <div
          className="scroll-indicator"
          onClick={() => {
            const container = messagesContainerRef.current
            if (container) {
              container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' })
            }
          }}
        >
          <span>↓</span>
        </div>
      )}

      {/* Chat input - always visible at bottom */}
      <div className="unified-chat-input-container">
        {/* Agent Mode Toggle and New Chat - only show if feature flag is enabled */}
        {agentModeEnabled && (
          <div className="agent-mode-controls">
            {agentMode && (
              <button
                className="new-chat-button"
                onClick={startNewChat}
                disabled={chatLoading || messages.length === 0}
                title="Start a new conversation"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                New Chat
              </button>
            )}
            <div className="agent-mode-toggle">
              <label className="toggle-label">
                <input
                  type="checkbox"
                  checked={agentMode}
                  onChange={(e) => {
                    const newValue = e.target.checked
                    setAgentMode(newValue)
                    localStorage.setItem('agentModeEnabled', newValue.toString())
                  }}
                  disabled={chatLoading}
                />
                <span className="toggle-slider"></span>
                <span className="toggle-text">🤖 Agent Mode {agentMode ? '(Beta)' : ''}</span>
              </label>
            </div>
          </div>
        )}
        <div className="chat-input-wrapper">
          <textarea
            ref={inputRef}
            className="chat-input"
            defaultValue=""
            onKeyDown={handleKeyPress}
            placeholder={agentMode ? "Ask complex questions (e.g., 'Compare to peers')" : "Ask anything"}
            rows="2"
            disabled={chatLoading}
          />
          <button
            className="chat-send-button"
            onClick={() => sendMessage()}
            disabled={chatLoading}
          >
            {chatLoading ? '...' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )

  // In chatOnly mode, just render the chat
  if (chatOnly) {
    return chatContent
  }

  // In full mode, use two-column layout
  return (
    <div className="reports-layout">
      {/* Left Column - Analysis Content (2/3) */}
      <div className="reports-main-column">
        {analysisContent}
      </div>

      {/* Right Column - Chat Sidebar (1/3) */}
      <div className="reports-chat-sidebar">
        <div className="chat-sidebar-content">
          {chatContent}
        </div>
      </div>
    </div>
  )
}
)

export default AnalysisChat
