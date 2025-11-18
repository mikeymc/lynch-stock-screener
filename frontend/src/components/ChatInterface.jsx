// ABOUTME: Chat interface component for conversing with Peter Lynch about stocks
// ABOUTME: Displays message history and handles user input with streaming API integration

import { useState, useEffect, useRef } from 'react'

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

export default function ChatInterface({ symbol, lynchAnalysis }) {
  const [messages, setMessages] = useState([])
  const [inputMessage, setInputMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [conversationId, setConversationId] = useState(null)
  const [streamingMessage, setStreamingMessage] = useState('')
  const [streamingSources, setStreamingSources] = useState([])
  const [loadingHistory, setLoadingHistory] = useState(true)
  const messagesEndRef = useRef(null)
  const eventSourceRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, streamingMessage])

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
    }
  }, [])

  // Load conversation history on mount
  useEffect(() => {
    const loadConversationHistory = async () => {
      try {
        setLoadingHistory(true)
        const response = await fetch(`${API_BASE}/chat/${symbol}/conversations`)

        if (response.ok) {
          const data = await response.json()
          const conversations = data.conversations || []

          if (conversations.length > 0) {
            // Load most recent conversation
            const recentConversation = conversations[0]
            setConversationId(recentConversation.id)

            // Load messages for this conversation
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

  const startNewConversation = () => {
    setMessages([])
    setConversationId(null)
    setInputMessage('')
    setStreamingMessage('')
    setStreamingSources([])
  }

  const sendMessage = async (messageText = null) => {
    const userMessage = (messageText || inputMessage).trim()
    if (!userMessage || loading) return

    setInputMessage('')
    setMessages(prev => [...prev, { role: 'user', content: userMessage }])
    setLoading(true)
    setStreamingMessage('')
    setStreamingSources([])

    try {
      const response = await fetch(`${API_BASE}/chat/${symbol}/message/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: userMessage,
          conversation_id: conversationId,
          lynch_analysis: lynchAnalysis || null
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

        if (done) break

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
              setLoading(false)
            } else if (data.type === 'error') {
              console.error('Stream error:', data.data)
              setMessages(prev => [...prev, {
                role: 'error',
                content: `Error: ${data.data}`
              }])
              setStreamingMessage('')
              setStreamingSources([])
              setLoading(false)
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
      setLoading(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="chat-container">
      <div className="chat-header">
        <div className="chat-header-content">
          <div>
            <h3>💬 Ask Questions</h3>
            <p className="chat-subtitle">Discuss the analysis with Peter Lynch</p>
          </div>
          {messages.length > 0 && (
            <button
              className="new-conversation-button"
              onClick={startNewConversation}
              disabled={loading}
            >
              ➕ New Conversation
            </button>
          )}
        </div>
      </div>

      <div className="chat-messages">
        {loadingHistory && (
          <div className="chat-loading-history">
            <div className="loading">Loading conversation history...</div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} className={`chat-message ${msg.role}`}>
            <div className="chat-message-header">
              {msg.role === 'user' ? '👤 You' : msg.role === 'assistant' ? '🎩 Peter Lynch' : '⚠️ Error'}
            </div>
            <div className="chat-message-content">
              {msg.content}
            </div>
            {msg.role === 'assistant' && (
              <SourceCitation sources={msg.sources} />
            )}
          </div>
        ))}

        {loading && (
          <div className="chat-message assistant streaming">
            <div className="chat-message-header">🎩 Peter Lynch</div>
            <div className="chat-message-content">
              {streamingMessage || (
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

      <div className="chat-input-container">
        <textarea
          className="chat-input"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Ask Peter Lynch a question..."
          rows="2"
          disabled={loading}
        />
        <button
          className="chat-send-button"
          onClick={() => sendMessage()}
          disabled={loading || !inputMessage.trim()}
        >
          {loading ? 'Sending...' : 'Send'}
        </button>
      </div>
    </div>
  )
}
