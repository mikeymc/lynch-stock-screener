// ABOUTME: Word on the Street component for displaying Reddit sentiment
// ABOUTME: Full-width layout: Reddit posts list with theme-aware styling

import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { RefreshCw, MessageCircle, ArrowUp, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

const API_BASE = '/api'

export default function WordOnTheStreet({ symbol }) {
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

    // Helper to get sentiment display
    const getSentimentDisplay = (score) => {
        if (score > 0.2) return { label: 'Bullish', variant: 'success' }
        if (score < -0.2) return { label: 'Bearish', variant: 'destructive' }
        return { label: 'Neutral', variant: 'secondary' }
    }

    // Helper to format date
    const formatDate = (isoDate) => {
        if (!isoDate) return 'Unknown'
        const date = new Date(isoDate)
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    }

    if (loading) {
        return (
            <div className="p-10 text-center text-muted-foreground flex items-center justify-center gap-2">
                <Loader2 className="h-5 w-5 animate-spin" />
                Loading Reddit discussions...
            </div>
        )
    }

    if (error) {
        return (
            <div className="p-10 text-center text-muted-foreground">
                <p>{error}</p>
            </div>
        )
    }

    if (posts.length === 0) {
        return (
            <Card>
                <CardContent className="py-10 text-center text-muted-foreground">
                    <p>No Reddit discussions found for {symbol}.</p>
                    <p className="text-sm mt-2">
                        Try checking back later or verify the stock is commonly discussed.
                    </p>
                </CardContent>
            </Card>
        )
    }

    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
                <CardTitle className="text-lg">
                    {posts.length} discussions from Reddit
                    {source === 'database' && (
                        <span className="text-sm text-muted-foreground font-normal ml-2">(cached)</span>
                    )}
                </CardTitle>
                <Button
                    variant="default"
                    size="sm"
                    onClick={() => fetchSentiment(true)}
                    disabled={refreshing}
                >
                    {refreshing ? (
                        <>
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            Refreshing...
                        </>
                    ) : (
                        <>
                            <RefreshCw className="h-4 w-4 mr-2" />
                            Refresh
                        </>
                    )}
                </Button>
            </CardHeader>
            <CardContent className="space-y-6">
                {posts.map((post, index) => {
                    const sentiment = getSentimentDisplay(post.sentiment_score || 0)

                    return (
                        <div
                            key={post.id || index}
                            className="pb-6 border-b border-border last:border-b-0 last:pb-0"
                        >
                            {/* Post Header */}
                            <div className="flex items-center gap-3 mb-2 text-sm flex-wrap">
                                {/* Subreddit */}
                                <span className="text-orange-500 font-semibold">
                                    r/{post.subreddit}
                                </span>

                                {/* Score */}
                                <span className="flex items-center gap-1 text-orange-400">
                                    <ArrowUp className="h-3 w-3" />
                                    {formatScore(post.score)}
                                </span>

                                {/* Comments */}
                                <span className="flex items-center gap-1 text-muted-foreground">
                                    <MessageCircle className="h-3 w-3" />
                                    {post.num_comments}
                                </span>

                                {/* Time */}
                                <span className="text-muted-foreground">{formatDate(post.published_at || post.created_at)}</span>

                                {/* Sentiment */}
                                <Badge
                                    variant={sentiment.variant}
                                    className="ml-auto"
                                >
                                    {sentiment.label}
                                </Badge>
                            </div>

                            {/* Post Title */}
                            <h3 className="font-semibold text-base mb-2 leading-snug">
                                {post.url ? (
                                    <a
                                        href={post.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-primary hover:underline"
                                    >
                                        {post.title}
                                    </a>
                                ) : (
                                    <span>{post.title}</span>
                                )}
                            </h3>

                            {/* Post Body */}
                            {post.selftext && (
                                <div className="text-sm text-muted-foreground leading-relaxed mb-2 prose prose-sm dark:prose-invert max-w-none [&>p]:mb-2 [&>ul]:mb-2 [&>ol]:mb-2">
                                    <ReactMarkdown>{post.selftext}</ReactMarkdown>
                                </div>
                            )}

                            {/* Author */}
                            <div className="text-xs text-muted-foreground/70">
                                Posted by u/{post.author}
                            </div>

                            {/* Top Comments Section */}
                            {post.conversation?.comments?.length > 0 && (
                                <div className="mt-4 p-4 bg-muted/50 rounded-lg border-l-4 border-orange-500">
                                    <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wide mb-3">
                                        💬 Top Comments ({post.conversation.count})
                                    </div>

                                    <div className="space-y-4">
                                        {post.conversation.comments.map((comment, commentIdx) => (
                                            <div
                                                key={comment.id || commentIdx}
                                                className="pb-3 border-b border-border/50 last:border-b-0 last:pb-0"
                                            >
                                                <div className="flex items-center gap-2 mb-1 text-xs">
                                                    <span className="text-orange-400 font-semibold flex items-center gap-1">
                                                        <ArrowUp className="h-3 w-3" />
                                                        {formatScore(comment.score)}
                                                    </span>
                                                    <span className="text-muted-foreground/70">
                                                        u/{comment.author}
                                                    </span>
                                                </div>
                                                <div className="text-sm leading-relaxed prose prose-sm dark:prose-invert max-w-none [&>p]:mb-1">
                                                    <ReactMarkdown>{comment.body}</ReactMarkdown>
                                                </div>

                                                {/* Nested Replies */}
                                                {comment.replies?.length > 0 && (
                                                    <div className="mt-3 ml-4 pl-3 border-l-2 border-border/30 space-y-2">
                                                        {comment.replies.map((reply, replyIdx) => (
                                                            <div key={reply.id || replyIdx}>
                                                                <div className="flex items-center gap-2 mb-1 text-xs">
                                                                    <span className="text-orange-400 flex items-center gap-1">
                                                                        <ArrowUp className="h-2.5 w-2.5" />
                                                                        {formatScore(reply.score)}
                                                                    </span>
                                                                    <span className="text-muted-foreground/70">
                                                                        u/{reply.author}
                                                                    </span>
                                                                </div>
                                                                <div className="text-sm text-muted-foreground leading-relaxed prose prose-sm dark:prose-invert max-w-none [&>p]:mb-1">
                                                                    <ReactMarkdown>{reply.body}</ReactMarkdown>
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )
                })}
            </CardContent>
        </Card>
    )
}
