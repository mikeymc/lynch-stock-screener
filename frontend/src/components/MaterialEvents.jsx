// ABOUTME: Material events component for displaying SEC 8-K filings
// ABOUTME: Displays AI-generated summaries for high-value events (earnings, M&A, etc.)

import { useState, useEffect } from 'react'
import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

// Item codes that get AI summaries
const SUMMARIZABLE_CODES = ['2.02', '2.01', '1.01', '1.05', '2.06', '4.02']

// Check if an event should have a summary
const isSummarizable = (itemCodes) => {
    if (!itemCodes || itemCodes.length === 0) return false
    return itemCodes.some(code => SUMMARIZABLE_CODES.includes(code))
}

export default function MaterialEvents({ eventsData, loading, symbol }) {
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
            <div className="loading p-10 text-center">
                Loading material events...
            </div>
        )
    }

    const events = eventsData?.events || []

    if (events.length === 0) {
        return (
            <div className="w-full">
                <div className="section-item">
                    <div className="section-header-simple">
                        <span className="section-title">Material Event Filings</span>
                    </div>
                    <div className="section-content">
                        <div className="section-summary">
                            <p className="text-center text-slate-400 my-8">
                                No material events (SEC 8-K filings) available for this stock.
                            </p>
                            <p className="text-[13px] text-center text-slate-500">
                                Material events include significant corporate announcements like earnings releases,
                                acquisitions, leadership changes, and other important disclosures.
                            </p>
                        </div>
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
        <div className="w-full">
            <div className="section-item">
                <div className="section-header-simple">
                    <span className="section-title">{events.length} Filings</span>
                    {dateRange && <span className="section-metadata">({dateRange})</span>}
                </div>
                <div className="section-content">
                    <div className="section-summary">
                        <div className="events-list space-y-4">
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
                                    <Card key={event.id || index}>
                                        <CardHeader className="pb-3">
                                            <div className="flex items-center gap-2 mb-2">
                                                <Badge className="bg-blue-600 hover:bg-blue-700">SEC 8-K</Badge>
                                                <span className="text-sm text-muted-foreground">Filed: {filingDate}</span>
                                            </div>
                                            <CardTitle className="text-base leading-snug">
                                                {event.url ? (
                                                    <a
                                                        href={event.url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="text-blue-400 hover:underline hover:text-blue-300"
                                                    >
                                                        {event.headline || 'No headline'}
                                                    </a>
                                                ) : (
                                                    <span className="text-foreground">{event.headline || 'No headline'}</span>
                                                )}
                                            </CardTitle>
                                        </CardHeader>
                                        <CardContent>
                                            {/* AI Summary */}
                                            {hasSummary && (
                                                <div className="mb-4 bg-muted/30 p-3 rounded-md border border-border/50">
                                                    {loadingSummaries && !summary ? (
                                                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                                            <span className="animate-pulse">●</span> Generating AI summary...
                                                        </div>
                                                    ) : summary ? (
                                                        <p className="text-sm leading-relaxed text-muted-foreground">{summary}</p>
                                                    ) : summaryError ? (
                                                        <div className="text-sm text-red-400">
                                                            Unable to generate summary
                                                        </div>
                                                    ) : null}
                                                </div>
                                            )}

                                            {/* Item codes */}
                                            {event.sec_item_codes && event.sec_item_codes.length > 0 && (
                                                <div className="flex flex-wrap gap-2 mb-2">
                                                    {event.sec_item_codes.map((code, idx) => (
                                                        <Badge
                                                            key={idx}
                                                            variant="outline"
                                                            className={SUMMARIZABLE_CODES.includes(code) ? "border-blue-500/50 text-blue-400 bg-blue-500/10" : "text-muted-foreground"}
                                                        >
                                                            Item {code}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            )}

                                            {/* Accession */}
                                            {event.sec_accession_number && (
                                                <div className="text-xs text-muted-foreground mt-2">
                                                    Accession: {event.sec_accession_number}
                                                </div>
                                            )}
                                        </CardContent>
                                    </Card>
                                )
                            })}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
