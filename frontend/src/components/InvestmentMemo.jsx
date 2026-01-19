
import { useState, useEffect, useRef } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Loader2, RefreshCw, AlertTriangle } from 'lucide-react'
import ChartNarrativeRenderer from './ChartNarrativeRenderer'

export default function InvestmentMemo({ symbol, historyData, isQuarterly = false }) {
    const [narrative, setNarrative] = useState('')
    const [loading, setLoading] = useState(false)
    const [streaming, setStreaming] = useState(false)
    const [error, setError] = useState(null)
    const [metaAttributes, setMetaAttributes] = useState(null)

    const abortControllerRef = useRef(null)

    const fetchMemo = async (forceRefresh = false) => {
        // Cancel previous request if active
        if (abortControllerRef.current) {
            abortControllerRef.current.abort()
        }

        setLoading(true)
        setStreaming(true)
        setError(null)
        setNarrative('')

        abortControllerRef.current = new AbortController()

        try {
            const response = await fetch(`/api/stock/${symbol}/investment-memo`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    force_refresh: forceRefresh,
                    model: 'gemini-3-pro-preview' // Default model
                }),
                signal: abortControllerRef.current.signal
            })

            if (!response.ok) {
                if (response.status === 404) {
                    throw new Error("Investment Memo feature is not enabled or data not found.")
                }
                throw new Error(`Failed to fetch Investment Memo: ${response.statusText}`)
            }

            // Handle non-streaming cached response (JSON)
            const contentType = response.headers.get('content-type')
            if (contentType && contentType.includes('application/json')) {
                const data = await response.json()
                if (data.narrative) {
                    setNarrative(data.narrative)
                    setMetaAttributes({ generated_at: data.generated_at, cached: true })
                    setLoading(false)
                    setStreaming(false)
                    return
                }
            }

            // Handle streaming response (SSE)
            const reader = response.body.getReader()
            const decoder = new TextDecoder()
            let buffer = ''

            while (true) {
                const { done, value } = await reader.read()
                if (done) break

                const chunk = decoder.decode(value, { stream: true })
                buffer += chunk

                const lines = buffer.split('\n\n')
                buffer = lines.pop() // Keep the last incomplete line in buffer

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6))

                            if (data.type === 'metadata') {
                                setMetaAttributes({
                                    generated_at: data.generated_at,
                                    cached: data.cached
                                })
                            } else if (data.type === 'chunk') {
                                setNarrative(prev => prev + data.content)
                            } else if (data.type === 'error') {
                                throw new Error(data.message)
                            } else if (data.type === 'done') {
                                setStreaming(false)
                            }
                        } catch (e) {
                            console.warn("Failed to parse SSE message:", line)
                        }
                    }
                }
            }

        } catch (err) {
            if (err.name !== 'AbortError') {
                setError(err.message)
                console.error("Error fetching investment memo:", err)
            }
        } finally {
            setLoading(false)
            setStreaming(false)
            abortControllerRef.current = null
        }
    }

    // Initial fetch on mount
    useEffect(() => {
        fetchMemo()
        return () => {
            if (abortControllerRef.current) {
                abortControllerRef.current.abort()
            }
        }
    }, [symbol])

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            {/* Header / Meta / Actions */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">Investment Memo</h2>
                    <p className="text-sm text-muted-foreground mt-1">
                        AI-generated thesis and financial analysis based on Peter Lynch's principles.
                        {metaAttributes?.generated_at && (
                            <span className="ml-2 inline-block">
                                Last updated: {new Date(metaAttributes.generated_at).toLocaleDateString()}
                            </span>
                        )}
                    </p>
                </div>

                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => fetchMemo(true)}
                    disabled={loading || streaming}
                    className="gap-2"
                >
                    {loading || streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                    {loading || streaming ? 'Generating...' : 'Refresh Analysis'}
                </Button>
            </div>

            {/* Error state */}
            {error && (
                <Card className="border-destructive/50 bg-destructive/10">
                    <CardContent className="pt-6 flex items-start gap-4 text-destructive">
                        <AlertTriangle className="h-5 w-5 shrink-0" />
                        <div>
                            <h3 className="font-semibold">Analysis Failed</h3>
                            <p className="text-sm mt-1">{error}</p>
                            <Button variant="link" className="p-0 h-auto mt-2 text-destructive underline" onClick={() => fetchMemo(true)}>
                                Try Again
                            </Button>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Narrative Content */}
            <div className={streaming ? "opacity-90 transition-opacity" : ""}>
                <ChartNarrativeRenderer
                    narrative={narrative}
                    historyData={historyData}
                    isQuarterly={isQuarterly}
                />
            </div>

            {/* Loading Skeleton / Placeholder if empty and loading */}
            {loading && !narrative && (
                <div className="space-y-8">
                    {[1, 2, 3].map(i => (
                        <Card key={i} className="animate-pulse">
                            <div className="h-12 bg-muted/50 border-b border-border/50" />
                            <CardContent className="p-6 space-y-4">
                                <div className="h-4 bg-muted/50 rounded w-3/4" />
                                <div className="h-4 bg-muted/50 rounded w-full" />
                                <div className="h-4 bg-muted/50 rounded w-5/6" />
                                <div className="h-64 bg-muted/30 rounded-xl mt-6" />
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}
        </div>
    )
}
