// ABOUTME: Unified component displaying analysis as first message in chat-style conversation
// ABOUTME: Creates seamless flow from analysis to discussion like ChatGPT/Claude

import { useState, useEffect, useRef, forwardRef, useImperativeHandle } from 'react'
import ReactMarkdown from 'react-markdown'
import ModelSelector from './ModelSelector'

const API_BASE = '/api'

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

const AnalysisChat = forwardRef(function AnalysisChat({ symbol, stockName, chatOnly = false }, ref) {
  // Analysis state
  const [analysis, setAnalysis] = useState(null)
  const [analysisLoading, setAnalysisLoading] = useState(true)
  const [analysisError, setAnalysisError] = useState(null)
  const [generatedAt, setGeneratedAt] = useState(null)
  const [cached, setCached] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [selectedModel, setSelectedModel] = useState('gemini-3-flash-preview')

  // Chat state
  const [messages, setMessages] = useState([])
  const [inputMessage, setInputMessage] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [conversationId, setConversationId] = useState(null)
  const [streamingMessage, setStreamingMessage] = useState('')
  const [streamingSources, setStreamingSources] = useState([])
  const [loadingHistory, setLoadingHistory] = useState(true)
  const [showScrollIndicator, setShowScrollIndicator] = useState(false)

  const messagesEndRef = useRef(null)
  const messagesContainerRef = useRef(null)

  // Expose sendMessage to parent via ref for batch review
  useImperativeHandle(ref, () => ({
    sendMessage: (message, options) => sendMessage(message, options)
  }))

  // Track scroll position to show/hide scroll indicator
  const handleScroll = () => {
    const container = messagesContainerRef.current
    if (!container) return

    const { scrollTop, scrollHeight, clientHeight } = container
    const hasMoreContent = scrollHeight > clientHeight
    const isNearTop = scrollTop < 50

    setShowScrollIndicator(hasMoreContent && isNearTop)
  }

  // Check for scroll indicator on content changes
  useEffect(() => {
    handleScroll()
  }, [analysis, messages, analysisLoading])

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (messages.length > 0 || streamingMessage) {
      // Scroll within the container only, not the whole page
      const container = messagesContainerRef.current
      if (container) {
        container.scrollTop = container.scrollHeight
      }
    }
  }, [messages, streamingMessage])

  // Fetch analysis
  const fetchAnalysis = async (forceRefresh = false, signal = null, onlyCached = false) => {
    try {
      if (forceRefresh) {
        setRefreshing(true)
      } else {
        setAnalysisLoading(true)
      }
      setAnalysisError(null)

      let url = forceRefresh
        ? `${API_BASE}/stock/${symbol}/lynch-analysis/refresh`
        : `${API_BASE}/stock/${symbol}/lynch-analysis`

      if (onlyCached && !forceRefresh) {
        url += `?only_cached=true&model=${selectedModel}`
      } else if (!forceRefresh) {
        url += `?model=${selectedModel}`
      }

      const method = forceRefresh ? 'POST' : 'GET'

      const options = { method, signal }
      if (forceRefresh) {
        options.headers = { 'Content-Type': 'application/json' }
        options.body = JSON.stringify({ model: selectedModel })
      }

      const response = await fetch(url, options)

      if (!response.ok) {
        throw new Error(`Failed to fetch analysis: ${response.statusText}`)
      }

      const data = await response.json()
      setAnalysis(data.analysis)
      setGeneratedAt(data.generated_at)
      setCached(data.cached)
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
    }
  }

  // Load conversation history
  useEffect(() => {
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
  }, [symbol])

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

  const sendMessage = async (messageText = null, options = {}) => {
    const userMessage = (messageText || inputMessage).trim()
    if (!userMessage || chatLoading) return

    setInputMessage('')
    // Only show user message bubble if not hidden (for comment reviews)
    if (!options.hideUserMessage) {
      setMessages(prev => [...prev, { role: 'user', content: userMessage }])
    }
    setChatLoading(true)
    setStreamingMessage('')
    setStreamingSources([])

    try {
      const response = await fetch(`${API_BASE}/chat/${symbol}/message/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage,
          conversation_id: conversationId,
          lynch_analysis: analysis || null
        })
      })

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let fullMessage = ''
      let sources = []

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
                      message_id: data.data.message_id
                    }])
                    setStreamingMessage('')
                    setStreamingSources([])
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
              sources: sources
            }])
            setStreamingMessage('')
            setStreamingSources([])
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
              fullMessage += data.data
              setStreamingMessage(fullMessage)
            } else if (data.type === 'done') {
              setMessages(prev => [...prev, {
                role: 'assistant',
                content: fullMessage,
                sources: sources,
                message_id: data.data.message_id
              }])
              setStreamingMessage('')
              setStreamingSources([])
              setChatLoading(false)
            } else if (data.type === 'error') {
              console.error('Stream error:', data.data)
              setMessages(prev => [...prev, {
                role: 'error',
                content: `Error: ${data.data}`
              }])
              setStreamingMessage('')
              setStreamingSources([])
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
      setChatLoading(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="unified-chat-container">
      <div
        className="unified-chat-messages"
        ref={messagesContainerRef}
        onScroll={handleScroll}
      >
        {/* Analysis as first message - hidden in chatOnly mode */}
        {!chatOnly && (
          <>
            {analysisLoading ? (
              <div className="chat-message assistant analysis-message">
                <div className="chat-message-content">
                  <div className="chat-loading">
                    <span className="typing-indicator">●</span>
                    <span className="typing-indicator">●</span>
                    <span className="typing-indicator">●</span>
                  </div>
                  <p style={{ marginTop: '0.5rem', opacity: 0.7 }}>Loading analysis...</p>
                </div>
              </div>
            ) : analysisError ? (
              <div className="chat-message assistant analysis-message">
                <div className="chat-message-content">
                  <p>Failed to load analysis: {analysisError}</p>
                  <button onClick={() => fetchAnalysis(false, null, true)} className="retry-button">
                    Retry
                  </button>
                </div>
              </div>
            ) : !analysis ? (
              <div className="chat-message assistant analysis-message">
                <div className="chat-message-content">
                  <p>No analysis generated yet for {stockName}.</p>
                  <div style={{ display: 'flex', flexDirection: 'row', gap: '1rem', alignItems: 'center', marginTop: '1rem' }}>
                    <ModelSelector
                      selectedModel={selectedModel}
                      onModelChange={setSelectedModel}
                      storageKey="lynchAnalysisModel"
                    />
                    <button onClick={handleGenerate} className="generate-button">
                      ✨ Generate
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="chat-message assistant analysis-message">
                <div className="analysis-metadata-bar">
                  <span className="analysis-metadata">
                    {cached ? '📦 Cached' : '✨ Freshly Generated'} • Generated {formatDate(generatedAt)}
                  </span>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <ModelSelector
                      selectedModel={selectedModel}
                      onModelChange={setSelectedModel}
                      storageKey="lynchAnalysisModel"
                    />
                    <button
                      onClick={handleRefresh}
                      disabled={refreshing}
                      className="refresh-button-small"
                    >
                      {refreshing ? '...' : '🔄'}
                    </button>
                  </div>
                </div>
                <div className="chat-message-content markdown-content">
                  <ReactMarkdown>{analysis}</ReactMarkdown>
                </div>
              </div>
            )}
          </>
        )}

        {/* Loading history indicator */}
        {loadingHistory && (
          <div className="chat-loading-history">
            <div className="loading">Loading conversation history...</div>
          </div>
        )}

        {/* Chat messages */}
        {messages.map((msg, idx) => (
          <div key={idx} className={`chat-message ${msg.role} analysis-message`}>
            <div className="chat-message-header">
              {msg.role === 'user' ? '👤 You' : msg.role === 'assistant' ? '📊 Analyst' : '⚠️ Error'}
            </div>
            <div className="chat-message-content markdown-content">
              <ReactMarkdown>{msg.content}</ReactMarkdown>
            </div>
            {msg.role === 'assistant' && (
              <SourceCitation sources={msg.sources} />
            )}
          </div>
        ))}

        {/* Streaming message */}
        {chatLoading && (
          <div className="chat-message assistant streaming">
            <div className="chat-message-header">📊 Thinking...</div>
            <div className="chat-message-content markdown-content">
              {streamingMessage ? (
                <ReactMarkdown>{streamingMessage}</ReactMarkdown>
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

      {/* Scroll indicator arrow */}
      {showScrollIndicator && (
        <div className="scroll-indicator">
          <span>↓</span>
        </div>
      )}

      {/* Chat input - always visible at bottom */}
      <div className="unified-chat-input-container">
        <div className="chat-input-wrapper">
          <textarea
            className="chat-input"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask anything"
            rows="2"
            disabled={chatLoading}
          />
          <button
            className="chat-send-button"
            onClick={() => sendMessage()}
            disabled={chatLoading || !inputMessage.trim()}
          >
            {chatLoading ? '...' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )
}
)

export default AnalysisChat
