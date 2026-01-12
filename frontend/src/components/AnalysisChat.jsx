// ABOUTME: Brief page component with AI-generated stock analysis and chat interface
// ABOUTME: Two-column layout in full mode (analysis left, chat right); chatOnly mode for sidebar use

import { useState, useEffect, useRef, forwardRef, useImperativeHandle, memo, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { RefreshCw, Sparkles, Bot } from 'lucide-react'
import ChatChart from './ChatChart'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Card } from '@/components/ui/card'
import { useChatContext } from '@/context/ChatContext'
import { useAuth } from '@/context/AuthContext'

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

const TOOL_DESCRIPTIONS = {
  get_financial_metric: "Analyzing financial metrics",
  get_financials: "Gathering financial statements",
  get_stock_price: "Fetching real-time quote",
  get_peers: "Finding competitors",
  search_news: "Scanning latest headlines",
  get_earnings_transcript: "Reading earnings call transcripts",
  get_price_history: "Analyzing price trends",
  get_growth_rates: "Calculating growth metrics",
  get_dividend_analysis: "Checking dividend safety",
  compare_stocks: "Comparing against peers",
  search_company: "Finding ticker symbol",
  screen_stocks: "Screening the market",
  get_earnings_history: "Reviewing earnings history",
  get_sector_comparison: "Benchmarking against sector",
  get_analyst_estimates: "Checking analyst forecasts",
  find_similar_stocks: "Finding similar companies",
  get_material_events: "Checking SEC filings",
  get_stock_metrics: "Analyzing key metrics",
  get_historical_pe: "Analyzing valuation history"
}

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
    <div className="mt-2 text-xs border-t border-border/50 pt-2">
      <button
        className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors font-medium"
        onClick={() => setExpanded(!expanded)}
      >
        📚 Sources ({sources.length}) {expanded ? '▼' : '▶'}
      </button>
      {expanded && (
        <ul className="list-disc list-inside mt-2 pl-1 text-muted-foreground space-y-1">
          {sources.map((source, idx) => (
            <li key={idx} className="truncate">{sourceLabels[source] || source}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

// Custom markdown components
const MarkdownComponents = ({ navigate }) => useMemo(() => ({
  h1: (props) => (
    <h1 className="scroll-m-20 text-2xl font-semibold tracking-tight mb-4" {...props} />
  ),
  h2: (props) => (
    <h2 className="scroll-m-20 border-b pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0 mb-4 mt-8" {...props} />
  ),
  h3: (props) => (
    <h3 className="scroll-m-20 text-lg font-semibold tracking-tight mb-2 mt-6" {...props} />
  ),
  p: (props) => (
    <p className="leading-7 [&:not(:first-child)]:mt-6 mb-4" {...props} />
  ),
  ul: (props) => (
    <ul className="my-6 ml-6 list-disc [&>li]:mt-2" {...props} />
  ),
  ol: (props) => (
    <ol className="my-6 ml-6 list-decimal [&>li]:mt-2" {...props} />
  ),
  li: (props) => (
    <li className="leading-7" {...props} />
  ),
  blockquote: (props) => (
    <blockquote className="mt-6 border-l-2 pl-6 italic text-muted-foreground" {...props} />
  ),
  strong: (props) => (
    <strong className="font-bold text-foreground" {...props} />
  ),
  pre: (props) => (
    <pre className="overflow-x-auto w-full p-2 my-2 bg-muted/50 rounded-lg whitespace-pre-wrap break-words max-w-full" {...props} />
  ),
  code({ node, inline, className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || '')
    const language = match ? match[1] : ''

    // Render chart blocks with ChatChart component
    if (language === 'chart' && !inline) {
      return <ChatChart chartJson={String(children).replace(/\n$/, '')} />
    }

    // Default code block rendering
    if (inline) {
      return <code className="relative rounded bg-muted px-[0.3rem] py-[0.2rem] font-mono text-sm font-semibold" {...props}>{children}</code>
    }

    return (
      <code className={className} {...props}>
        {children}
      </code>
    )
  },
  // Custom link renderer for client-side navigation
  a({ href, children, ...props }) {
    const handleClick = (e) => {
      // Check if it's an internal link
      if (href && (href.startsWith('/') || href.startsWith(window.location.origin))) {
        e.preventDefault()
        const path = href.startsWith(window.location.origin)
          ? href.substring(window.location.origin.length)
          : href
        navigate(path)
      }
    }

    return (
      <a href={href} onClick={handleClick} {...props} className="font-medium text-primary underline underline-offset-4 hover:text-primary/80">
        {children}
      </a>
    )
  }
}), [navigate])

// Memoized ChatMessage component - only re-renders when content changes
const ChatMessage = memo(function ChatMessage({ role, content, sources, components }) {
  const { user } = useAuth()
  const isUser = role === 'user'
  const isError = role === 'error'
  const isAssistant = role === 'assistant'

  return (
    <div className={`flex gap-3 mb-6 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {/* Avatar/Icon */}
      <div className="flex-shrink-0 mt-1">
        {isUser ? (
          <div className="h-8 w-8 rounded-full border border-border overflow-hidden bg-muted">
            {user?.picture ? (
              <img src={user.picture} alt="User" className="h-full w-full object-cover" />
            ) : (
              <div className="h-full w-full flex items-center justify-center text-xs font-medium text-muted-foreground">
                {(user?.name?.[0] || user?.email?.[0] || 'U').toUpperCase()}
              </div>
            )}
          </div>
        ) : (
          <div className="h-8 w-8 flex items-center justify-center rounded-lg border border-border bg-background shadow-sm">
            {isError ? (
              <div className="text-destructive font-bold">!</div>
            ) : (
              <Bot className="h-5 w-5 text-primary" />
            )}
          </div>
        )}
      </div>

      {/* Message Bubble */}
      <div className={`flex flex-col max-w-[85%] min-w-0 ${isUser ? 'items-end' : 'items-start'}`}>
        <div className={`rounded-lg px-4 py-3 ${isUser
          ? 'bg-primary text-primary-foreground'
          : isError
            ? 'bg-destructive/10 text-destructive border border-destructive/20'
            : 'bg-muted'
          }`}>
          <div className="text-sm break-words">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
              {content}
            </ReactMarkdown>
          </div>
          {isAssistant && <SourceCitation sources={sources} />}
        </div>
      </div>
    </div>
  )
})

const AnalysisChat = forwardRef(function AnalysisChat({ symbol, stockName, chatOnly = false, hideChat = false, contextType = 'brief' }, ref) {
  // Navigation for internal links
  const navigate = useNavigate()
  const components = MarkdownComponents({ navigate })

  // Shared chat context for sidebar integration
  const {
    agentMode,
    setAgentMode,
    conversations,
    setConversations,
    addConversation,
    updateConversationTitle,
    activeConversationId,
    setActiveConversationId
  } = useChatContext()

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
  // Local conversationId syncs with activeConversationId from context
  const [conversationId, setConversationId] = useState(null)
  const [streamingMessage, setStreamingMessage] = useState('')
  const [streamingSources, setStreamingSources] = useState([])
  const [loadingHistory, setLoadingHistory] = useState(true)
  const [showScrollIndicator, setShowScrollIndicator] = useState(false)
  const [loadingMessageIndex, setLoadingMessageIndex] = useState(0)
  const [agentThinking, setAgentThinking] = useState('')
  const [agentModeEnabled, setAgentModeEnabled] = useState(false)
  const [showScrollDown, setShowScrollDown] = useState(false)
  const [isNearBottom, setIsNearBottom] = useState(true)

  // Start a new chat session - creates a new conversation on the backend
  const startNewChat = useCallback(async () => {
    try {
      // Create new conversation on backend
      const response = await fetch(`${API_BASE}/agent/conversations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include'
      })

      if (!response.ok) {
        console.error('Failed to create new conversation')
        return
      }

      const data = await response.json()
      const newConversationId = data.conversation_id

      // Update local state
      setConversationId(newConversationId)
      setMessages([])
      setStreamingMessage('')
      setStreamingSources([])
      setAgentThinking('')

      // Update context state
      setActiveConversationId(newConversationId)
      addConversation({
        id: newConversationId,
        title: 'New Chat',
        created_at: new Date().toISOString(),
        last_message_at: new Date().toISOString()
      })

      // Focus input after reset
      setTimeout(() => inputRef.current?.focus(), 100)
    } catch (error) {
      console.error('Error creating new chat:', error)
    }
  }, [addConversation, setActiveConversationId])

  // Switch to a different conversation
  const switchConversation = useCallback(async (targetConversationId) => {
    if (targetConversationId === conversationId) return
    if (chatLoading) return  // Don't switch while streaming

    try {
      // Fetch messages for the selected conversation
      const response = await fetch(`${API_BASE}/agent/conversation/${targetConversationId}/messages`, {
        credentials: 'include'
      })

      if (!response.ok) {
        console.error('Failed to load conversation messages')
        return
      }

      const data = await response.json()

      // Update local state
      setConversationId(targetConversationId)
      setMessages(data.messages || [])
      setStreamingMessage('')
      setStreamingSources([])
      setAgentThinking('')

      // Update context state
      setActiveConversationId(targetConversationId)

      // Scroll to bottom after messages load
      setTimeout(() => {
        const container = messagesContainerRef.current
        if (container) {
          container.scrollTop = container.scrollHeight
        }
      }, 100)

      // Focus input
      setTimeout(() => inputRef.current?.focus(), 100)
    } catch (error) {
      console.error('Error switching conversation:', error)
    }
  }, [conversationId, chatLoading, setActiveConversationId])

  // Respond to conversation selection from sidebar (or deletion)
  useEffect(() => {
    if (!agentMode) return

    if (activeConversationId === null && conversationId !== null) {
      // Active conversation was deleted - start a new chat
      startNewChat()
    } else if (activeConversationId && activeConversationId !== conversationId) {
      // Switch to selected conversation
      switchConversation(activeConversationId)
    }
  }, [activeConversationId])  // Intentionally limited deps to avoid loops

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

  // Load agent conversations when agent mode is active
  useEffect(() => {
    if (!agentMode) return

    const loadAgentConversations = async () => {
      try {
        // Fetch all recent agent conversations
        const response = await fetch(`${API_BASE}/agent/conversations`, { credentials: 'include' })
        if (!response.ok) {
          console.error('Failed to fetch agent conversations')
          return
        }

        const data = await response.json()

        if (data.conversations && data.conversations.length > 0) {
          // Store all conversations for the chat history (via context)
          setConversations(data.conversations)

          // Load most recent conversation
          const conv = data.conversations[0]
          setConversationId(conv.id)
          setActiveConversationId(conv.id)

          // Load messages for the most recent conversation
          const msgResponse = await fetch(`${API_BASE}/agent/conversation/${conv.id}/messages`, { credentials: 'include' })
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
          // No conversations exist - create a new one
          setConversations([])
          const createResponse = await fetch(`${API_BASE}/agent/conversations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include'
          })

          if (createResponse.ok) {
            const createData = await createResponse.json()
            const newConv = {
              id: createData.conversation_id,
              title: 'New Chat',
              created_at: new Date().toISOString(),
              last_message_at: new Date().toISOString()
            }
            setConversationId(createData.conversation_id)
            setActiveConversationId(createData.conversation_id)
            setConversations([newConv])
            setMessages([])
          }
        }
      } catch (error) {
        console.error('Error loading agent conversations:', error)
      }
    }

    loadAgentConversations()
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

        // Clean cached content
        let cleanContent = data.analysis
        if (cleanContent) {
          cleanContent = cleanContent.replace(/\[Prompt:[^\]]*\]/g, '')
        }

        setAnalysis(cleanContent)
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
        const response = await fetch(`${API_BASE}/chat/${symbol}/conversations`, { credentials: 'include' })

        if (response.ok) {
          const data = await response.json()
          const conversations = data.conversations || []

          if (conversations.length > 0) {
            const recentConversation = conversations[0]
            setConversationId(recentConversation.id)

            const messagesResponse = await fetch(`${API_BASE}/chat/conversation/${recentConversation.id}/messages`, { credentials: 'include' })
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
        credentials: 'include',
        body: JSON.stringify({ role, content, tool_calls: toolCalls })
      })

      if (!response.ok) {
        console.error('[Agent] Failed to save message:', await response.text())
      } else {
        const data = await response.json()
        console.log('[Agent] Message saved successfully:', role)

        // If backend generated a title, update the conversation in context
        if (data.title) {
          updateConversationTitle(conversationId, data.title)
        }
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
        credentials: 'include',
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
              const friendlyName = TOOL_DESCRIPTIONS[data.data.tool] || `Calling ${data.data.tool}`
              setAgentThinking(`${friendlyName}...`)
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
    <div className="w-full h-full overflow-y-auto pr-2">
      <Card className="h-full border-0 shadow-none bg-transparent">
        <div className="h-full">
          {(analysisLoading || isGenerating) && !analysis ? (
            <div className="flex flex-col items-center justify-center h-[50vh] space-y-6 text-center text-muted-foreground">
              <div className="relative">
                <div className="h-12 w-12 rounded-full border-4 border-primary/20"></div>
                <div className="absolute top-0 left-0 h-12 w-12 rounded-full border-4 border-primary border-t-transparent animate-spin"></div>
              </div>
              <div className="space-y-2">
                <span className="block text-lg font-medium text-foreground">Generating brief...</span>
                <span className="block text-sm animate-pulse" key={loadingMessageIndex}>
                  {LOADING_MESSAGES[loadingMessageIndex]}
                </span>
              </div>
            </div>
          ) : analysisError ? (
            <div className="flex flex-col items-center justify-center h-[50vh] space-y-4 text-destructive">
              <p>Failed to load analysis: {analysisError}</p>
              <Button onClick={() => fetchAnalysis(false, null, true)} variant="outline">
                Retry
              </Button>
            </div>
          ) : !analysis ? (
            <div className="flex flex-col items-center justify-center h-[50vh] space-y-4 text-muted-foreground">
              <p>No brief generated yet for {stockName}.</p>
              <Button onClick={handleGenerate} className="mt-4">
                <Sparkles className="mr-2 h-4 w-4" /> Generate Brief
              </Button>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-6 pb-4 border-b">
                <span className="text-sm text-muted-foreground font-medium">
                  {cached ? 'Cached' : 'Fresh'} · {formatDate(generatedAt)}
                </span>
                <Button
                  onClick={handleRefresh}
                  disabled={refreshing}
                  variant="default"
                  size="sm"
                  className="gap-2 bg-slate-700 hover:bg-slate-600 text-white"
                >
                  <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
                  Re-Analyze
                </Button>
              </div>
              <div className="prose prose-sm dark:prose-invert max-w-none pb-8">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{analysis}</ReactMarkdown>
              </div>
            </>
          )}
        </div>
      </Card>
    </div>
  )

  // Chat content (for right column or standalone)
  const chatContent = (
    <div className="flex flex-col h-full bg-background">
      {/* Messages area wrapper - relative for scroll indicator positioning */}
      <div className="flex-1 relative overflow-hidden">
        <div
          className="absolute inset-0 overflow-y-auto p-4 space-y-2"
          ref={messagesContainerRef}
          onScroll={handleScroll}
        >
          {/* Loading history indicator */}
          {loadingHistory && (
            <div className="flex items-center justify-center py-4">
              <div className="text-sm text-muted-foreground">Loading conversation history...</div>
            </div>
          )}

          {/* Chat messages - using memoized component for performance */}
          {messages.map((msg, idx) => (
            <ChatMessage
              key={msg.message_id || idx}
              role={msg.role}
              content={msg.content}
              sources={msg.sources}
              components={components}
            />
          ))}

          {/* Streaming message */}
          {chatLoading && (
            <div className="flex flex-col gap-1 mb-4 items-start">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground px-2">
                <Bot className="h-3.5 w-3.5" />
                <span>{agentThinking || 'Thinking...'}</span>
              </div>
              <div className="rounded-lg px-4 py-3 max-w-[85%] bg-muted">
                {streamingMessage ? (
                  <div className="prose prose-sm max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{streamingMessage}</ReactMarkdown>
                  </div>
                ) : (
                  <div className="flex gap-1">
                    <span className="animate-pulse">●</span>
                    <span className="animate-pulse delay-100">●</span>
                    <span className="animate-pulse delay-200">●</span>
                  </div>
                )}
                {streamingMessage && (
                  <span className="inline-block animate-pulse">▊</span>
                )}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Scroll indicator arrow - shows when not at bottom */}
        {(showScrollIndicator || showScrollDown) && (
          <button
            className="absolute bottom-4 left-1/2 -translate-x-1/2 w-8 h-8 rounded-full bg-primary text-primary-foreground shadow-lg flex items-center justify-center hover:scale-110 transition-transform z-10"
            onClick={() => {
              const container = messagesContainerRef.current
              if (container) {
                container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' })
              }
            }}
          >
            <span>↓</span>
          </button>
        )}
      </div>

      {/* Chat input - always visible at bottom */}
      <div className="p-4 border-t bg-background">
        {/* Agent Mode Toggle and New Chat - only show if feature flag is enabled */}
        {agentModeEnabled && (
          <div className="flex items-center justify-between mb-3">
            {agentMode && (
              <Button
                variant="ghost"
                size="sm"
                onClick={startNewChat}
                disabled={chatLoading || messages.length === 0}
                className="text-muted-foreground"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="mr-1">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                New Chat
              </Button>
            )}
            <div className="flex items-center gap-2 ml-auto mr-8">
              <Switch
                id="agent-mode"
                checked={agentMode}
                onCheckedChange={setAgentMode}
                disabled={chatLoading}
              />
              <label htmlFor="agent-mode" className="text-sm text-muted-foreground cursor-pointer">
                Agent Mode (Beta)
              </label>
            </div>
          </div>
        )}
        <div className="flex gap-2">
          <Textarea
            ref={inputRef}
            defaultValue=""
            onKeyDown={handleKeyPress}
            placeholder={agentMode ? "Ask complex questions (e.g., 'Compare to peers')" : "Ask anything"}
            rows={2}
            disabled={chatLoading}
            className="flex-1 resize-none"
          />
          <Button
            onClick={() => sendMessage()}
            disabled={chatLoading}
            className="self-end"
          >
            {chatLoading ? '...' : 'Send'}
          </Button>
        </div>
      </div>
    </div>
  )

  // In chatOnly mode, just render the chat
  if (chatOnly) {
    return chatContent
  }

  // In hideChat mode, just render the analysis
  if (hideChat) {
    return (
      <div className="w-full">
        {analysisContent}
      </div>
    )
  }

  // In full mode, use two-column layout
  return (
    <div className="flex flex-col lg:flex-row h-[calc(100vh-140px)] gap-6">
      {/* Left Column - Analysis Content (2/3) */}
      <div className="hidden lg:flex lg:w-2/3 flex-col min-h-0">
        {analysisContent}
      </div>

      {/* Right Column - Chat Sidebar (1/3) */}
      <div className="flex-1 lg:w-1/3 flex flex-col min-h-0 border rounded-xl overflow-hidden bg-card shadow-sm">
        <div className="flex-1 flex flex-col min-h-0">
          {chatContent}
        </div>
      </div>
    </div>
  )
}
)

export default AnalysisChat
