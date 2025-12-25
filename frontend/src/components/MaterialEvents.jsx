// ABOUTME: Material events component for displaying SEC 8-K filings
// ABOUTME: Two-column layout: filings list left (2/3), chat sidebar right (1/3)

import { useRef } from 'react'
import AnalysisChat from './AnalysisChat'

export default function MaterialEvents({ eventsData, loading, symbol }) {
    const chatRef = useRef(null)

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
            <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>
                <p>No material events (SEC 8-K filings) available for this stock.</p>
                <p style={{ fontSize: '13px', marginTop: '10px' }}>
                    Material events include significant corporate announcements like earnings releases,
                    acquisitions, leadership changes, and other important disclosures.
                </p>
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

                                            {/* Description */}
                                            {event.description && (
                                                <p style={{ margin: '0 0 8px 0', lineHeight: '1.5', color: '#e2e8f0', fontSize: '14px' }}>
                                                    {event.description}
                                                </p>
                                            )}

                                            {/* Item codes as badges */}
                                            {event.sec_item_codes && event.sec_item_codes.length > 0 && (
                                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
                                                    {event.sec_item_codes.map((code, idx) => (
                                                        <span key={idx} style={{
                                                            backgroundColor: '#374151',
                                                            color: '#d1d5db',
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
                    <AnalysisChat ref={chatRef} symbol={symbol} chatOnly={true} />
                </div>
            </div>
        </div>
    )
}
