// ABOUTME: Word on the Street component for displaying Reddit sentiment
// ABOUTME: Two-column layout: Reddit posts left (2/3), chat sidebar right (1/3)

import { useState, useEffect, useRef } from 'react'
import AnalysisChat from './AnalysisChat'

const API_BASE = '/api'

export default function WordOnTheStreet({ symbol }) {
    const chatRef = useRef(null)
    const [posts, setPosts] = useState([])
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState(null)
    const [source, setSource] = useState(null)

    const fetchSentiment = async (forceRefresh = false) => {
        if (forceRefresh) {
            setRefreshing(true)
        } else {
            setLoading(true)
        }
        setError(null)

        try {
            const url = forceRefresh
                ? `${API_BASE}/stock/${symbol}/reddit?refresh=true`
                : `${API_BASE}/stock/${symbol}/reddit`
            const response = await fetch(url)
            if (response.ok) {
                const data = await response.json()
                setPosts(data.posts || [])
                setSource(data.source)
            } else {
                setError('Failed to load Reddit data')
            }
        } catch (err) {
            console.error('Error fetching Reddit sentiment:', err)
            setError('Failed to load Reddit data')
        } finally {
            setLoading(false)
            setRefreshing(false)
        }
    }

    useEffect(() => {
        fetchSentiment()
    }, [symbol])

    // Helper to format score
    const formatScore = (score) => {
        if (score >= 1000) {
            return `${(score / 1000).toFixed(1)}k`
        }
        return score.toString()
    }

    // Helper to get sentiment color and icon
    const getSentimentDisplay = (score) => {
        if (score > 0.2) return { icon: '🟢', label: 'Bullish', color: '#22c55e' }
        if (score < -0.2) return { icon: '🔴', label: 'Bearish', color: '#ef4444' }
        return { icon: '⚪', label: 'Neutral', color: '#94a3b8' }
    }

    // Helper to format date
    const formatDate = (isoDate) => {
        if (!isoDate) return 'Unknown'
        const date = new Date(isoDate)
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    }

    if (loading) {
        return (
            <div className="loading" style={{ padding: '40px', textAlign: 'center' }}>
                Loading Reddit discussions...
            </div>
        )
    }

    if (error) {
        return (
            <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>
                <p>{error}</p>
            </div>
        )
    }

    if (posts.length === 0) {
        return (
            <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>
                <p>No Reddit discussions found for {symbol}.</p>
                <p style={{ fontSize: '13px', marginTop: '8px' }}>
                    Try checking back later or verify the stock is commonly discussed.
                </p>
            </div>
        )
    }

    return (
        <div className="reports-layout">
            {/* Left Column - Reddit Posts (2/3) */}
            <div className="reports-main-column">
                <div className="section-item">
                    <div className="section-header-simple" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span className="section-title">
                            {posts.length} discussions from Reddit
                            {source === 'database' && <span style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 'normal', marginLeft: '8px' }}>(cached)</span>}
                        </span>
                        <button
                            onClick={() => fetchSentiment(true)}
                            disabled={refreshing}
                            style={{
                                padding: '6px 12px',
                                fontSize: '12px',
                                backgroundColor: refreshing ? 'rgba(255, 69, 0, 0.3)' : 'rgba(255, 69, 0, 0.1)',
                                border: '1px solid #ff4500',
                                borderRadius: '6px',
                                color: '#ff4500',
                                cursor: refreshing ? 'wait' : 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px',
                                transition: 'all 0.2s'
                            }}
                        >
                            {refreshing ? (
                                <>
                                    <span style={{ animation: 'spin 1s linear infinite' }}>🔄</span>
                                    Refreshing...
                                </>
                            ) : (
                                <>🔄 Refresh Live</>
                            )}
                        </button>
                    </div>
                    <div className="section-content">
                        <div className="section-summary">
                            <div className="reddit-posts-list">
                                {posts.map((post, index) => {
                                    const sentiment = getSentimentDisplay(post.sentiment_score || 0)

                                    return (
                                        <div
                                            key={post.id || index}
                                            className="reddit-post"
                                            style={{
                                                borderBottom: '1px solid rgba(71, 85, 105, 0.5)',
                                                paddingBottom: '16px',
                                                marginBottom: '16px'
                                            }}
                                        >
                                            {/* Post Header */}
                                            <div style={{
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: '12px',
                                                marginBottom: '8px',
                                                fontSize: '13px',
                                                color: '#94a3b8'
                                            }}>
                                                {/* Subreddit */}
                                                <span style={{
                                                    color: '#ff4500',
                                                    fontWeight: '600'
                                                }}>
                                                    r/{post.subreddit}
                                                </span>

                                                {/* Score */}
                                                <span style={{
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    gap: '4px',
                                                    color: '#f97316'
                                                }}>
                                                    ⬆ {formatScore(post.score)}
                                                </span>

                                                {/* Comments */}
                                                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                                    💬 {post.num_comments}
                                                </span>

                                                {/* Time */}
                                                <span>{formatDate(post.created_at)}</span>

                                                {/* Sentiment */}
                                                <span style={{
                                                    color: sentiment.color,
                                                    fontWeight: '500',
                                                    marginLeft: 'auto'
                                                }}>
                                                    {sentiment.icon} {sentiment.label}
                                                </span>
                                            </div>

                                            {/* Post Title */}
                                            <h3 style={{
                                                margin: '0 0 8px 0',
                                                fontSize: '16px',
                                                lineHeight: '1.4',
                                                fontWeight: '600'
                                            }}>
                                                {post.url ? (
                                                    <a
                                                        href={post.url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        style={{ color: '#60a5fa', textDecoration: 'none' }}
                                                    >
                                                        {post.title}
                                                    </a>
                                                ) : (
                                                    <span style={{ color: '#f1f5f9' }}>{post.title}</span>
                                                )}
                                            </h3>

                                            {/* Post Body - Full text */}
                                            {post.selftext && (
                                                <p style={{
                                                    margin: '0',
                                                    lineHeight: '1.6',
                                                    color: '#cbd5e1',
                                                    fontSize: '14px',
                                                    whiteSpace: 'pre-wrap'
                                                }}>
                                                    {post.selftext}
                                                </p>
                                            )}

                                            {/* Author */}
                                            <div style={{
                                                marginTop: '8px',
                                                fontSize: '12px',
                                                color: '#64748b'
                                            }}>
                                                Posted by u/{post.author}
                                            </div>

                                            {/* Top Conversations - Shows all comments with 30+ upvotes */}
                                            {post.conversation && post.conversation.comments && post.conversation.comments.length > 0 && (
                                                <div style={{
                                                    marginTop: '16px',
                                                    padding: '12px',
                                                    backgroundColor: 'rgba(30, 41, 59, 0.6)',
                                                    borderRadius: '8px',
                                                    borderLeft: '3px solid #ff4500'
                                                }}>
                                                    <div style={{
                                                        fontSize: '11px',
                                                        color: '#94a3b8',
                                                        marginBottom: '12px',
                                                        fontWeight: '600',
                                                        textTransform: 'uppercase',
                                                        letterSpacing: '0.5px'
                                                    }}>
                                                        💬 Top Comments ({post.conversation.count})
                                                    </div>

                                                    {/* All quality comments */}
                                                    {post.conversation.comments.map((comment, commentIdx) => (
                                                        <div
                                                            key={comment.id || commentIdx}
                                                            style={{
                                                                marginBottom: commentIdx < post.conversation.comments.length - 1 ? '16px' : 0,
                                                                paddingBottom: commentIdx < post.conversation.comments.length - 1 ? '12px' : 0,
                                                                borderBottom: commentIdx < post.conversation.comments.length - 1 ? '1px solid rgba(71, 85, 105, 0.3)' : 'none'
                                                            }}
                                                        >
                                                            <div style={{
                                                                display: 'flex',
                                                                alignItems: 'center',
                                                                gap: '8px',
                                                                marginBottom: '4px',
                                                                fontSize: '12px'
                                                            }}>
                                                                <span style={{ color: '#f97316', fontWeight: '600' }}>
                                                                    ⬆ {formatScore(comment.score)}
                                                                </span>
                                                                <span style={{ color: '#64748b' }}>
                                                                    u/{comment.author}
                                                                </span>
                                                            </div>
                                                            <p style={{
                                                                margin: 0,
                                                                fontSize: '14px',
                                                                lineHeight: '1.6',
                                                                color: '#e2e8f0',
                                                                whiteSpace: 'pre-wrap'
                                                            }}>
                                                                {comment.body}
                                                            </p>

                                                            {/* Nested replies */}
                                                            {comment.replies && comment.replies.length > 0 && (
                                                                <div style={{
                                                                    marginTop: '12px',
                                                                    marginLeft: '16px',
                                                                    paddingLeft: '12px',
                                                                    borderLeft: '2px solid rgba(148, 163, 184, 0.3)'
                                                                }}>
                                                                    {comment.replies.map((reply, replyIdx) => (
                                                                        <div key={reply.id || replyIdx} style={{
                                                                            marginBottom: replyIdx < comment.replies.length - 1 ? '10px' : 0
                                                                        }}>
                                                                            <div style={{
                                                                                display: 'flex',
                                                                                alignItems: 'center',
                                                                                gap: '8px',
                                                                                marginBottom: '2px',
                                                                                fontSize: '11px'
                                                                            }}>
                                                                                <span style={{ color: '#f97316' }}>
                                                                                    ⬆ {formatScore(reply.score)}
                                                                                </span>
                                                                                <span style={{ color: '#64748b' }}>
                                                                                    u/{reply.author}
                                                                                </span>
                                                                            </div>
                                                                            <p style={{
                                                                                margin: 0,
                                                                                fontSize: '13px',
                                                                                lineHeight: '1.5',
                                                                                color: '#cbd5e1',
                                                                                whiteSpace: 'pre-wrap'
                                                                            }}>
                                                                                {reply.body}
                                                                            </p>
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            )}
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    )
                                })}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Right Column - Chat Sidebar (1/3) */}
            <div className="reports-chat-sidebar">
                <div className="chat-sidebar-content">
                    <AnalysisChat
                        ref={chatRef}
                        symbol={symbol}
                        chatOnly={true}
                        contextType="reddit"
                    />
                </div>
            </div>
        </div>
    )
}
