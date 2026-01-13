// ABOUTME: Displays earnings call transcripts with AI summary toggle
// ABOUTME: Shows parsed speaker turns in a chat-like format

import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Sparkles, FileText, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

export default function TranscriptViewer({ symbol }) {
    const [transcript, setTranscript] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [viewMode, setViewMode] = useState('full') // 'full' or 'summary'
    const [summary, setSummary] = useState(null)
    const [summaryLoading, setSummaryLoading] = useState(false)
    const [summaryError, setSummaryError] = useState(null)

    useEffect(() => {
        const fetchTranscript = async () => {
            try {
                const response = await fetch(`/api/stock/${symbol}/transcript`)
                if (response.ok) {
                    const data = await response.json()
                    setTranscript(data)
                    if (data.summary) {
                        setSummary(data.summary)
                    }
                } else {
                    setError('No transcript available for this stock.')
                }
            } catch (err) {
                setError('Failed to load transcript.')
                console.error(err)
            } finally {
                setLoading(false)
            }
        }

        fetchTranscript()
    }, [symbol])

    const generateSummary = async () => {
        setSummaryLoading(true)
        setSummaryError(null)

        try {
            const response = await fetch(`/api/stock/${symbol}/transcript/summary`, {
                method: 'POST'
            })

            if (response.ok) {
                const data = await response.json()
                setSummary(data.summary)
                setViewMode('summary')
            } else {
                const errorData = await response.json()
                setSummaryError(errorData.error || 'Failed to generate summary')
            }
        } catch (err) {
            setSummaryError('Failed to generate summary')
            console.error(err)
        } finally {
            setSummaryLoading(false)
        }
    }

    // Parse transcript into speaker turns for chat-like display
    // Tries multiple strategies: bracketed timestamps, or line-based speaker detection
    const parseTranscript = (text) => {
        if (!text) return []

        const turns = []

        // Strategy 1: Try bracketed timestamp format [HH:MM:SS] Speaker (Title)\nContent
        const bracketedParts = text.split(/(?=\[\d{2}:\d{2}:\d{2}\])/)

        if (bracketedParts.length > 1) {
            for (const part of bracketedParts) {
                const trimmed = part.trim()
                if (!trimmed) continue

                const newlineIndex = trimmed.indexOf('\n')
                if (newlineIndex === -1) continue

                const headerLine = trimmed.substring(0, newlineIndex)
                const content = trimmed.substring(newlineIndex + 1).trim()

                const headerMatch = headerLine.match(/^\[(\d{2}:\d{2}:\d{2})\]\s+(.+?)(?:\s+\((.+?)\))?$/)

                if (headerMatch) {
                    const timestamp = headerMatch[1]
                    const name = headerMatch[2].trim()
                    const title = headerMatch[3] ? headerMatch[3].trim() : ''

                    if (name && content) {
                        turns.push({ name, title, timestamp, content })
                    }
                }
            }

            if (turns.length > 0) return turns
        }

        // Strategy 2: Parse line-by-line format (Name\nTitle\nTimestamp\nContent pattern)
        const lines = text.split('\n').map(l => l.trim()).filter(l => l)
        let i = 0

        while (i < lines.length) {
            const line = lines[i]

            // Look for timestamp pattern (HH:MM:SS or H:MM:SS)
            const timestampMatch = line.match(/^(\d{1,2}:\d{2}:\d{2})$/)

            if (timestampMatch && i >= 2) {
                // This is a timestamp - look back for name and title
                const timestamp = timestampMatch[1].padStart(8, '0')
                const title = lines[i - 1] || ''
                const name = lines[i - 2] || ''

                // Collect content lines until next speaker block
                const contentLines = []
                i++

                while (i < lines.length) {
                    const nextLine = lines[i]
                    // Check if this starts a new speaker block
                    // (next line after this could be a title, then timestamp)
                    if (i + 2 < lines.length && lines[i + 2].match(/^\d{1,2}:\d{2}:\d{2}$/)) {
                        break
                    }
                    // Or check if current line is a timestamp (end of content)
                    if (nextLine.match(/^\d{1,2}:\d{2}:\d{2}$/)) {
                        break
                    }
                    contentLines.push(nextLine)
                    i++
                }

                if (name && contentLines.length > 0) {
                    turns.push({
                        name,
                        title: title.includes('at ') || title.includes('of ') ? title : '',
                        timestamp,
                        content: contentLines.join(' ')
                    })
                }
            } else {
                i++
            }
        }

        return turns
    }

    const renderTranscript = (text) => {
        const turns = parseTranscript(text)

        if (turns.length === 0) {
            if (text === 'NO_TRANSCRIPT_AVAILABLE') {
                return <div className="whitespace-pre-wrap text-muted-foreground italic text-center py-8">No transcript available</div>
            }
            return <div className="whitespace-pre-wrap text-foreground">{text}</div>
        }

        const speakerColors = {}
        const colorPalette = [
            'text-blue-600', 'text-emerald-600', 'text-amber-600',
            'text-rose-600', 'text-violet-600', 'text-pink-600', 'text-cyan-600'
        ]
        let colorIndex = 0

        return turns.map((turn, i) => {
            if (!speakerColors[turn.name]) {
                speakerColors[turn.name] = colorPalette[colorIndex % colorPalette.length]
                colorIndex++
            }

            return (
                <div key={i} className="p-4 mb-3 rounded-lg bg-muted/50 border-l-4 border-primary/20">
                    <div className="flex items-baseline gap-3 mb-2 flex-wrap">
                        <span className={`font-semibold text-base ${speakerColors[turn.name]}`}>
                            {turn.name}
                        </span>
                        {turn.title && (
                            <span className="text-muted-foreground text-sm">{turn.title}</span>
                        )}
                        <span className="text-muted-foreground/60 text-xs font-mono ml-auto">{turn.timestamp}</span>
                    </div>
                    <div className="text-foreground leading-relaxed">
                        {turn.content}
                    </div>
                </div>
            )
        })
    }

    if (loading) {
        return (
            <div className="p-10 text-center text-muted-foreground flex items-center justify-center gap-2">
                <Loader2 className="h-5 w-5 animate-spin" />
                Loading transcript...
            </div>
        )
    }

    if (error || !transcript) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle>Earnings Call Transcript</CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-center text-muted-foreground py-8">
                        {error || 'No transcript available for this stock.'}
                    </p>
                </CardContent>
            </Card>
        )
    }

    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
                <div className="flex flex-col gap-1">
                    <CardTitle className="text-xl">Earnings Call Transcript</CardTitle>
                    <div className="text-sm text-primary font-medium">
                        {transcript.quarter} {transcript.fiscal_year} • {transcript.earnings_date}
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                {/* View Mode Toggle */}
                <div className="inline-flex bg-muted rounded-lg p-1 gap-1 mb-6">
                    <button
                        className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${viewMode === 'summary'
                            ? 'bg-primary text-primary-foreground shadow-sm'
                            : 'text-muted-foreground hover:text-foreground hover:bg-muted/80'
                            }`}
                        onClick={() => {
                            if (summary) {
                                setViewMode('summary')
                            } else {
                                generateSummary()
                            }
                        }}
                        disabled={summaryLoading || transcript?.transcript_text === 'NO_TRANSCRIPT_AVAILABLE'}
                    >
                        {summaryLoading ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Sparkles className="h-4 w-4" />
                        )}
                        {summaryLoading ? 'Generating...' : 'AI Summary'}
                    </button>
                    <button
                        className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${viewMode === 'full'
                            ? 'bg-primary text-primary-foreground shadow-sm'
                            : 'text-muted-foreground hover:text-foreground hover:bg-muted/80'
                            }`}
                        onClick={() => setViewMode('full')}
                    >
                        <FileText className="h-4 w-4" />
                        Full Transcript
                    </button>
                </div>

                {summaryError && (
                    <div className="bg-destructive/10 border border-destructive/20 text-destructive p-4 rounded-lg mb-4">
                        {summaryError}
                    </div>
                )}

                {/* Content */}
                <div className="min-h-[400px]">
                    {viewMode === 'summary' && summary ? (
                        <div className="prose prose-sm dark:prose-invert max-w-none">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{summary}</ReactMarkdown>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {renderTranscript(transcript.transcript_text)}
                        </div>
                    )}
                </div>
            </CardContent>
        </Card>
    )
}
