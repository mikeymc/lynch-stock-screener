// ABOUTME: Material events component for displaying SEC 8-K filings
// ABOUTME: Two-column layout: filings list left (2/3), chat sidebar right (1/3)
// ABOUTME: Displays AI-generated summaries for high-value events (earnings, M&A, etc.)

import { useRef, useState, useEffect } from 'react'
import AnalysisChat from './AnalysisChat'

// Item codes that get AI summaries
const SUMMARIZABLE_CODES = ['2.02', '2.01', '1.01', '1.05', '2.06', '4.02']

// Check if an event should have a summary
const isSummarizable = (itemCodes) => {
    if (!itemCodes || itemCodes.length === 0) return false
    return itemCodes.some(code => SUMMARIZABLE_CODES.includes(code))
}

export default function MaterialEvents({ eventsData, loading, symbol }) {
    const chatRef = useRef(null)
    const [summaries, setSummaries] = useState({})
    const [loadingSummaries, setLoadingSummaries] = useState(false)
    const [summaryError, setSummaryError] = useState(null)

    // Fetch summaries when events data changes
    useEffect(() => {
        const fetchSummaries = async () => {
            if (!eventsData?.events || eventsData.events.length === 0) return

            // Find events that should have summaries
            const summarizableEvents = eventsData.events.filter(e =>
                isSummarizable(e.sec_item_codes)
            )

            if (summarizableEvents.length === 0) return

            setLoadingSummaries(true)
            setSummaryError(null)

            try {
                const response = await fetch(`/api/stock/${symbol}/material-event-summaries`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                })

                if (!response.ok) {
                    throw new Error(`Failed to fetch summaries: ${response.status}`)
                }

                const data = await response.json()

                // Convert string keys to numbers for easier lookup
                const summaryMap = {}
                if (data.summaries) {
                    for (const [id, value] of Object.entries(data.summaries)) {
                        summaryMap[parseInt(id)] = value.summary
                    }
                }

                setSummaries(summaryMap)
            } catch (err) {
                console.error('Error fetching event summaries:', err)
                setSummaryError(err.message)
            } finally {
                setLoadingSummaries(false)
            }
        }

        fetchSummaries()
    }, [eventsData, symbol])

    if (loading) {
        return (
            <div className="loading" style={{ padding: '40px', textAlign: 'center' }}>
                Loading material events...
            </div>
        )
    }

    const events = eventsData?.events || []

    if (events.length === 0) {
        return (
            <div className="reports-layout">
                <div className="reports-main-column">
                    <div className="section-item">
                        <div className="section-header-simple">
                            <span className="section-title">Material Event Filings</span>
                        </div>
                        <div className="section-content">
                            <div className="section-summary">
                                <p style={{ textAlign: 'center', color: '#94a3b8', margin: '2rem 0' }}>
                                    No material events (SEC 8-K filings) available for this stock.
                                </p>
                                <p style={{ fontSize: '13px', textAlign: 'center', color: '#64748b' }}>
                                    Material events include significant corporate announcements like earnings releases,
                                    acquisitions, leadership changes, and other important disclosures.
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
                <div className="reports-chat-sidebar">
                    <div className="chat-sidebar-content">
                        <AnalysisChat ref={chatRef} symbol={symbol} chatOnly={true} contextType="events" />
                    </div>
                </div>
            </div>
        )
    }

    // Calculate date range from events
    const sortedDates = events
        .map(e => e.filing_date ? new Date(e.filing_date) : null)
        .filter(d => d !== null)
        .sort((a, b) => a - b)

    const formatShortDate = (date) => date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
    const dateRange = sortedDates.length > 0
        ? `${formatShortDate(sortedDates[0])} – ${formatShortDate(sortedDates[sortedDates.length - 1])}`
        : null

    return (
        <div className="reports-layout">
            {/* Left Column - Events Content (2/3) */}
            <div className="reports-main-column">
                <div className="section-item">
                    <div className="section-header-simple">
                        <span className="section-title">{events.length} Filings</span>
                        {dateRange && <span className="section-metadata">({dateRange})</span>}
                    </div>
                    <div className="section-content">
                        <div className="section-summary">
                            <div className="events-list">
                                {events.map((event, index) => {
                                    const filingDate = event.filing_date
                                        ? new Date(event.filing_date).toLocaleDateString('en-US', {
                                            year: 'numeric',
                                            month: 'short',
                                            day: 'numeric'
                                        })
                                        : 'Unknown date'

                                    const hasSummary = isSummarizable(event.sec_item_codes)
                                    const summary = summaries[event.id]

                                    return (
                                        <div key={event.id || index} className="material-event" style={{
                                            borderBottom: '1px solid rgba(71, 85, 105, 0.5)',
                                            paddingBottom: '16px',
                                            marginBottom: '16px'
                                        }}>
                                            {/* Header with SEC badge and date */}
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                                                <span style={{
                                                    backgroundColor: '#2563eb',
                                                    color: '#fff',
                                                    padding: '2px 8px',
                                                    borderRadius: '4px',
                                                    fontSize: '11px',
                                                    fontWeight: '600',
                                                    letterSpacing: '0.5px'
                                                }}>
                                                    SEC 8-K
                                                </span>
                                                <span style={{ fontSize: '13px', color: '#94a3b8' }}>
                                                    Filed: {filingDate}
                                                </span>
                                            </div>

                                            {/* Headline */}
                                            <h3 style={{ margin: '0 0 8px 0', fontSize: '16px', lineHeight: '1.4', fontWeight: '600' }}>
                                                {event.url ? (
                                                    <a
                                                        href={event.url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        style={{ color: '#60a5fa', textDecoration: 'none' }}
                                                    >
                                                        {event.headline || 'No headline'}
                                                    </a>
                                                ) : (
                                                    <span style={{ color: '#f1f5f9' }}>{event.headline || 'No headline'}</span>
                                                )}
                                            </h3>

                                            {/* AI Summary - always visible for summarizable events */}
                                            {hasSummary && (
                                                <div className="event-summary">
                                                    {loadingSummaries && !summary ? (
                                                        <div className="summary-loading">
                                                            <span className="loading-dot">●</span> Generating AI summary...
                                                        </div>
                                                    ) : summary ? (
                                                        <p className="summary-text">{summary}</p>
                                                    ) : summaryError ? (
                                                        <div className="summary-error">
                                                            Unable to generate summary
                                                        </div>
                                                    ) : null}
                                                </div>
                                            )}

                                            {/* Item codes as badges */}
                                            {event.sec_item_codes && event.sec_item_codes.length > 0 && (
                                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
                                                    {event.sec_item_codes.map((code, idx) => (
                                                        <span key={idx} style={{
                                                            backgroundColor: SUMMARIZABLE_CODES.includes(code) ? '#1e3a5f' : '#374151',
                                                            color: SUMMARIZABLE_CODES.includes(code) ? '#93c5fd' : '#d1d5db',
                                                            padding: '2px 8px',
                                                            borderRadius: '4px',
                                                            fontSize: '11px',
                                                            fontWeight: '500'
                                                        }}>
                                                            Item {code}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}

                                            {/* Accession number */}
                                            {event.sec_accession_number && (
                                                <div style={{ marginTop: '8px', fontSize: '11px', color: '#64748b' }}>
                                                    Accession: {event.sec_accession_number}
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
                    <AnalysisChat ref={chatRef} symbol={symbol} chatOnly={true} contextType="events" />
                </div>
            </div>
        </div>
    )
}
