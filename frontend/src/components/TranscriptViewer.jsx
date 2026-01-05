// ABOUTME: Displays earnings call transcripts with full-width layout
// ABOUTME: AI summary/full transcript toggle

import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import '../App.css'

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
    // Format: [00:00:00] Speaker Name (Title)\nContent\n[00:00:31] Next Speaker...
    const parseTranscript = (text) => {
        if (!text) return []

        const turns = []

        // Split by the [timestamp] pattern at the start of each turn
        // Use lookahead to split while keeping the delimiter
        const parts = text.split(/(?=\[\d{2}:\d{2}:\d{2}\])/)

        for (const part of parts) {
            const trimmed = part.trim()
            if (!trimmed) continue

            // Find first newline to separate header from content
            const newlineIndex = trimmed.indexOf('\n')
            if (newlineIndex === -1) continue // No content

            const headerLine = trimmed.substring(0, newlineIndex)
            const content = trimmed.substring(newlineIndex + 1).trim()

            // Parse header: [00:00:00] Speaker Name (Title)
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

        return turns
    }

    const renderTranscript = (text) => {
        const turns = parseTranscript(text)

        if (turns.length === 0) {
            return <div className="transcript-fallback">{text}</div>
        }

        const speakerColors = {}
        const colorPalette = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4']
        let colorIndex = 0

        return turns.map((turn, i) => {
            if (!speakerColors[turn.name]) {
                speakerColors[turn.name] = colorPalette[colorIndex % colorPalette.length]
                colorIndex++
            }

            return (
                <div key={i} className="transcript-turn">
                    <div className="turn-header">
                        <span className="speaker-name" style={{ color: speakerColors[turn.name] }}>
                            {turn.name}
                        </span>
                        <span className="speaker-title">{turn.title}</span>
                        <span className="speaker-timestamp">{turn.timestamp}</span>
                    </div>
                    <div className="turn-content">
                        {turn.content}
                    </div>
                </div>
            )
        })
    }

    if (loading) {
        return (
            <div className="loading" style={{ padding: '40px', textAlign: 'center' }}>
                Loading transcript...
            </div>
        )
    }

    if (error || !transcript) {
        return (
            <div className="reports-layout">
                <div className="reports-main-column">
                    <div className="section-item">
                        <div className="section-header-simple">
                            <span className="section-title">Earnings Call Transcript</span>
                        </div>
                        <div className="section-content">
                            <div className="section-summary">
                                <p style={{ textAlign: 'center', color: '#94a3b8', margin: '2rem 0' }}>
                                    {error || 'No transcript available for this stock.'}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="reports-layout">
            {/* Left Column - Transcript Content (2/3) */}
            <div className="reports-main-column">
                <div className="section-item">
                    <div className="section-header-simple">
                        <span className="section-title">Earnings Call Transcript</span>
                        <span className="section-metadata">
                            {transcript.quarter} {transcript.fiscal_year} • {transcript.earnings_date}
                        </span>
                    </div>
                    <div className="section-content">
                        {/* View Mode Toggle - Segmented Control */}
                        <div className="transcript-toggle">
                            <button
                                className={`toggle-segment ${viewMode === 'summary' ? 'active' : ''}`}
                                onClick={() => {
                                    if (summary) {
                                        setViewMode('summary')
                                    } else {
                                        generateSummary()
                                    }
                                }}
                                disabled={summaryLoading}
                            >
                                <span className="toggle-icon">✨</span>
                                {summaryLoading ? 'Generating...' : 'AI Summary'}
                            </button>
                            <button
                                className={`toggle-segment ${viewMode === 'full' ? 'active' : ''}`}
                                onClick={() => setViewMode('full')}
                            >
                                <span className="toggle-icon">📜</span>
                                Full Transcript
                            </button>
                        </div>

                        {summaryError && (
                            <div className="error-message" style={{ margin: '1rem 0' }}>
                                {summaryError}
                            </div>
                        )}

                        {/* Content */}
                        <div className="section-summary">
                            {viewMode === 'summary' && summary ? (
                                <div className="summary-content">
                                    <ReactMarkdown>{summary}</ReactMarkdown>
                                </div>
                            ) : (
                                <div className="transcript-text">
                                    {renderTranscript(transcript.transcript_text)}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
