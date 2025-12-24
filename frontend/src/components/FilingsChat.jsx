// ABOUTME: Chat component for SEC filings allowing Q&A about 10-K/10-Q content
// ABOUTME: Reuses existing chat backend with RAG context for filing sections

import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'

const API_BASE = '/api'

function SourceCitation({ sources }) {
    if (!sources || sources.length === 0) return null

    const sourceLabels = {
        'business': 'Business Description',
        'risk_factors': 'Risk Factors',
        'mda': "Management's Discussion & Analysis",
        'market_risk': 'Market Risk Disclosures'
    }

    return (
        <div className="filings-chat-sources">
            📚 Sources: {sources.map((s, i) => (
                <span key={s}>
                    {sourceLabels[s] || s}{i < sources.length - 1 ? ', ' : ''}
                </span>
            ))}
        </div>
    )
}

export default function FilingsChat({ symbol }) {
    const [messages, setMessages] = useState([])
    const [inputMessage, setInputMessage] = useState('')
    const [chatLoading, setChatLoading] = useState(false)
    const [conversationId, setConversationId] = useState(null)
    const [streamingMessage, setStreamingMessage] = useState('')
    const [streamingSources, setStreamingSources] = useState([])

    const messagesEndRef = useRef(null)

    // Auto-scroll to bottom when new messages arrive
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages, streamingMessage])

    const sendMessage = async () => {
        const userMessage = inputMessage.trim()
        if (!userMessage || chatLoading) return

        setInputMessage('')
        setMessages(prev => [...prev, { role: 'user', content: userMessage }])
        setChatLoading(true)
        setStreamingMessage('')
        setStreamingSources([])

        try {
            const response = await fetch(`${API_BASE}/chat/${symbol}/message/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    message: userMessage,
                    conversation_id: conversationId
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
                                sources: sources
                            }])
                            setStreamingMessage('')
                            setStreamingSources([])
                            setChatLoading(false)
                        } else if (data.type === 'error') {
                            setMessages(prev => [...prev, {
                                role: 'error',
                                content: `Error: ${data.data}`
                            }])
                            setStreamingMessage('')
                            setChatLoading(false)
                        }
                    }
                }
            }

        } catch (error) {
            console.error('Error sending message:', error)
            setMessages(prev => [...prev, {
                role: 'error',
                content: 'Sorry, there was an error. Please try again.'
            }])
            setStreamingMessage('')
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
        <div className="filings-chat-container">
            <div className="filings-chat-header">
                <h4>💬 Ask about these filings</h4>
            </div>

            {/* Messages */}
            {messages.length > 0 && (
                <div className="filings-chat-messages">
                    {messages.map((msg, idx) => (
                        <div key={idx} className={`filings-chat-message ${msg.role}`}>
                            <div className="filings-chat-message-header">
                                {msg.role === 'user' ? '👤 You' : msg.role === 'assistant' ? '📊 Analyst' : '⚠️'}
                            </div>
                            <div className="filings-chat-message-content">
                                <ReactMarkdown>{msg.content}</ReactMarkdown>
                            </div>
                            {msg.role === 'assistant' && <SourceCitation sources={msg.sources} />}
                        </div>
                    ))}

                    {/* Streaming message */}
                    {chatLoading && (
                        <div className="filings-chat-message assistant streaming">
                            <div className="filings-chat-message-header">📊 Thinking...</div>
                            <div className="filings-chat-message-content">
                                {streamingMessage ? (
                                    <ReactMarkdown>{streamingMessage}</ReactMarkdown>
                                ) : (
                                    <span className="typing-dots">●●●</span>
                                )}
                            </div>
                            {streamingSources.length > 0 && <SourceCitation sources={streamingSources} />}
                        </div>
                    )}

                    <div ref={messagesEndRef} />
                </div>
            )}

            {/* Input */}
            <div className="filings-chat-input-container">
                <textarea
                    className="filings-chat-input"
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder="Ask a question about the filings..."
                    rows="2"
                    disabled={chatLoading}
                />
                <button
                    className="filings-chat-send"
                    onClick={sendMessage}
                    disabled={chatLoading || !inputMessage.trim()}
                >
                    {chatLoading ? '...' : 'Send'}
                </button>
            </div>
        </div>
    )
}
