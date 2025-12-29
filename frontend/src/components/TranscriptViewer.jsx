// ABOUTME: Displays earnings call transcripts as inline page content (not modal)
// ABOUTME: Includes AI summary generation with toggle between summary and full transcript

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
    const parseTranscript = (text) => {
        if (!text) return []

        const speakerPattern = /([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+([A-Za-z\s]+?)\s+at\s+([A-Za-z\s]+?)\s+(\d{2}:\d{2}:\d{2})/g

        const turns = []
        let lastIndex = 0
        let match

        while ((match = speakerPattern.exec(text)) !== null) {
            if (match.index > lastIndex && turns.length > 0) {
                const prevContent = text.substring(lastIndex, match.index).trim()
                if (prevContent && turns.length > 0) {
                    turns[turns.length - 1].content += ' ' + prevContent
                }
            }

            turns.push({
                name: match[1],
                title: match[2].trim(),
                company: match[3].trim(),
                timestamp: match[4],
                content: ''
            })

            lastIndex = match.index + match[0].length
        }

        if (lastIndex < text.length && turns.length > 0) {
            turns[turns.length - 1].content = text.substring(lastIndex).trim()
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

            const isQA = turn.content.includes('?') || turn.title.toLowerCase().includes('analyst')

            return (
                <div key={i} className={`transcript-turn ${isQA ? 'qa-turn' : ''}`}>
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
        return <div className="loading">Loading transcript...</div>
    }

    if (error) {
        return <div className="error-message">{error}</div>
    }

    if (!transcript) {
        return <div className="empty-state">No transcript available</div>
    }

    return (
        <div className="transcript-page">
            {/* Header with metadata */}
            <div className="transcript-header">
                <h2>Earnings Call Transcript</h2>
                <div className="transcript-meta">
                    <span><strong>Period:</strong> {transcript.quarter} {transcript.fiscal_year}</span>
                    <span><strong>Date:</strong> {transcript.earnings_date}</span>
                </div>
            </div>

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
            {viewMode === 'summary' && summary ? (
                <div className="brief-analysis-container">
                    <div className="section-item">
                        <div className="section-content">
                            {/* Hidden spacer to prevent :only-child centering rule */}
                            <div style={{ display: 'none' }} />
                            <div className="section-summary">
                                <div className="summary-content">
                                    <ReactMarkdown>{summary}</ReactMarkdown>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            ) : (
                <div className="transcript-text">
                    {renderTranscript(transcript.transcript_text)}
                </div>
            )}
        </div>
    )
}
