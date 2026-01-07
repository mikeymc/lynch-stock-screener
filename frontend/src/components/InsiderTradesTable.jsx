import React, { useState } from 'react'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

export default function InsiderTradesTable({ trades }) {
    const [showDetails, setShowDetails] = useState(false)
    const [showAllTypes, setShowAllTypes] = useState(false)

    if (!trades || trades.length === 0) {
        return (
            <p className="p-4 text-slate-400 italic">
                No insider transactions found.
            </p>
        )
    }

    const formatCurrency = (val) => {
        if (!val || val === 0) return '$0'
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val)
    }

    const formatDate = (dateString) => {
        if (!dateString) return '-'
        return new Date(dateString).toLocaleDateString()
    }

    // Transaction code to color class mapping
    const getCodeClass = (code) => {
        const classes = {
            'P': 'text-green-400',  // Purchase
            'S': 'text-red-400',    // Sale
            'M': 'text-amber-400',  // Option Exercise
            'A': 'text-blue-400',   // Award/Grant
            'F': 'text-slate-400',  // Tax Withholding
            'G': 'text-violet-400', // Gift
            'D': 'text-red-400',    // Disposition
            'C': 'text-blue-400',   // Conversion
            'X': 'text-amber-400',  // Exercise In-the-Money
        }
        return classes[code] || 'text-slate-300'
    }

    const getTypeClass = (type) => {
        if (type === 'Buy') return 'text-green-400'
        if (type === 'Sell') return 'text-red-400'
        return 'text-amber-400'  // Other
    }

    const getBgClass = (colorClass) => {
        return colorClass.replace('text-', 'bg-') + '/20'
    }

    // Transaction code to human-readable label
    const codeToLabel = {
        'P': 'Open Market Purchase',
        'S': 'Open Market Sale',
        'M': 'Option Exercise',
        'A': 'Award/Grant',
        'F': 'Tax Withholding',
        'G': 'Gift',
        'D': 'Disposition',
        'C': 'Conversion',
        'X': 'Exercise ITM',
        'J': 'Other',
    }

    // Filter trades based on showAllTypes toggle
    // Default: only show Open Market (P/S) transactions - the real signal
    // Filter out legacy data (missing transaction_code) which causes duplicates/aggregates
    const cleanTrades = trades.filter(t => t.transaction_code)

    // Filter trades based on showAllTypes toggle
    // Default: only show Open Market (P/S) transactions - the real signal
    const filteredTrades = showAllTypes
        ? cleanTrades
        : cleanTrades.filter(t => t.transaction_code === 'P' || t.transaction_code === 'S' ||
            t.transaction_type === 'Buy' || t.transaction_type === 'Sell')

    // Count how many "other" transactions we're hiding
    const hiddenCount = cleanTrades.length - filteredTrades.length
    const hasOtherTypes = hiddenCount > 0
    // 4. De-dupe transactions
    // We might have duplicates if names vary in casing (e.g. "McKnight" vs "MCKNIGHT") since they are unique in DB
    const uniqueTradesMap = new Map()
    filteredTrades.forEach(trade => {
        // Normalize name for de-duping
        let normalizedNameKey = trade.name.toLowerCase().replace(/[.,]/g, ' ').trim().replace(/\s+/g, ' ')
        const parts = normalizedNameKey.split(' ')
        if (parts.length >= 2) {
            normalizedNameKey = `${parts[0]} ${parts[1]}`
        }

        // Create a unique key for the transaction event
        // value + date + code + shares should be unique enough
        const dedupKey = `${trade.transaction_date}|${normalizedNameKey}|${trade.transaction_code}|${trade.shares}|${trade.price_per_share}`

        if (uniqueTradesMap.has(dedupKey)) {
            const existing = uniqueTradesMap.get(dedupKey)
            // If current trade has ownership data and existing doesn't, swap it!
            // Or if existing has no footnotes and current does, swap it.
            // Prefer the "richer" data.
            const currentScore = (trade.ownership_change_pct ? 2 : 0) + ((trade.footnotes || []).length > 0 ? 1 : 0)
            const existingScore = (existing.ownership_change_pct ? 2 : 0) + ((existing.footnotes || []).length > 0 ? 1 : 0)

            if (currentScore > existingScore) {
                uniqueTradesMap.set(dedupKey, trade)
            }
        } else {
            uniqueTradesMap.set(dedupKey, trade)
        }
    })

    // Use de-duped trades for everything downstream
    const uniqueTrades = Array.from(uniqueTradesMap.values())

    // Check if we have hidden types (non-open market)
    // Note: This logic might need to rely on the ORIGINAL full list for "hasOtherTypes"
    // But since we are only filtering visible ones here, let's just use uniqueTrades length vs total?
    // Actually, hiddenCount was calculated from trades vs filteredTrades.
    // Let's re-calculate hiddenCount based on unique trades if needed, but for now filtering is fine.

    // Group trades by person (using unique filtered trades for summary)
    // Normalize names to handle case differences in Form 4 filings
    const groupedByPerson = {}
    uniqueTrades.forEach(trade => {
        // Normalize key: lowercase, remove periods/commas, trim
        // Use first two words to handle middle initials (e.g. "Hession David" vs "Hession David M.")
        let normalizedKey = trade.name.toLowerCase().replace(/[.,]/g, ' ').trim().replace(/\s+/g, ' ')
        const parts = normalizedKey.split(' ')
        if (parts.length >= 2) {
            normalizedKey = `${parts[0]} ${parts[1]}`
        }

        if (!groupedByPerson[normalizedKey]) {
            groupedByPerson[normalizedKey] = {
                name: trade.name,
                position: trade.position,
                totalBought: 0,
                totalSold: 0,
                buyCount: 0,
                sellCount: 0,
                has10b51: false,
                // Track transaction types for summary display
                typeBreakdown: {},
                // Track total ownership percentage sold/bought
                totalPctSold: 0,
                totalPctBought: 0
            }
        } else {
            // Prefer Title Case name over ALL CAPS (Title Case usually has mixed case)
            const currentName = groupedByPerson[normalizedKey].name
            const hasUpperLower = (s) => /[a-z]/.test(s) && /[A-Z]/.test(s)
            if (!hasUpperLower(currentName) && hasUpperLower(trade.name)) {
                groupedByPerson[normalizedKey].name = trade.name
            }
            // Also update position if current one is generic (like "Officer")
            if (groupedByPerson[normalizedKey].position === 'Officer' && trade.position !== 'Officer') {
                groupedByPerson[normalizedKey].position = trade.position
            }
        }
        if (trade.transaction_type === 'Buy' || trade.transaction_code === 'P') {
            groupedByPerson[normalizedKey].totalBought += trade.value || 0
            groupedByPerson[normalizedKey].buyCount++
            // Track as Purchase for Types display
            groupedByPerson[normalizedKey].typeBreakdown['P'] = (groupedByPerson[normalizedKey].typeBreakdown['P'] || 0) + 1
        } else if (trade.transaction_type === 'Sell' || trade.transaction_code === 'S') {
            groupedByPerson[normalizedKey].totalSold += trade.value || 0
            groupedByPerson[normalizedKey].sellCount++
            // Track as Sale for Types display
            groupedByPerson[normalizedKey].typeBreakdown['S'] = (groupedByPerson[normalizedKey].typeBreakdown['S'] || 0) + 1
        }
        if (trade.is_10b51_plan) {
            groupedByPerson[normalizedKey].has10b51 = true
        }
        // Track accumulated ownership percentage
        if (trade.ownership_change_pct != null) {
            if (trade.transaction_type === 'Sell' || trade.transaction_code === 'S') {
                groupedByPerson[normalizedKey].totalPctSold += trade.ownership_change_pct
            } else if (trade.transaction_type === 'Buy' || trade.transaction_code === 'P') {
                groupedByPerson[normalizedKey].totalPctBought += trade.ownership_change_pct
            }
        }
    })

    const summaryData = Object.values(groupedByPerson)
        .filter(person => person.totalBought > 0 || person.totalSold > 0)
        .sort((a, b) => {
            const netA = a.totalBought - a.totalSold
            const netB = b.totalBought - b.totalSold
            return Math.abs(netB) - Math.abs(netA)
        })

    // Override global th styles
    const thStyle = {
        position: 'sticky',
        top: 0,
        zIndex: 10,
        backgroundColor: '#0f172a',
        padding: '12px 8px',
        textAlign: 'left',
        fontWeight: '600',
        borderBottom: '2px solid #475569',
        cursor: 'default'
    }

    // 10b5-1 Indicator
    const PlanBadge = () => (
        <span
            title="Executed under a 10b5-1 pre-scheduled trading plan (often less bearish than spontaneous sales)"
            className="ml-1.5 inline-flex items-center justify-center text-muted-foreground hover:text-blue-400 cursor-help transition-colors"
        >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
                <polyline points="10 9 9 9 8 9"></polyline>
            </svg>
        </span>
    )

    return (
        <div>
            {/* Type Filter Toggle */}
            {hasOtherTypes && (
                <div className="mb-3">
                    <Button
                        variant={showAllTypes ? "default" : "outline"}
                        size="sm"
                        onClick={() => setShowAllTypes(!showAllTypes)}
                        className={showAllTypes ? "bg-amber-500/20 text-amber-500 border-amber-500 hover:bg-amber-500/30" : "text-muted-foreground"}
                    >
                        {showAllTypes ? '✓ Showing All Types' : `Show All Types (+${hiddenCount})`}
                    </Button>
                    <span className="ml-3 text-xs text-muted-foreground">
                        {showAllTypes ? 'Including option exercises, awards, gifts' : 'Open market only'}
                    </span>
                </div>
            )}

            {/* Summary View */}
            <div className="mb-4 rounded-md border">
                <Table>
                    <TableHeader>
                        <TableRow className="bg-muted/50">
                            <TableHead className="w-[200px]">Insider</TableHead>
                            <TableHead>Types</TableHead>
                            <TableHead className="text-right text-green-400">Bought</TableHead>
                            <TableHead className="text-right text-red-400">Sold</TableHead>
                            <TableHead className="text-right">Total %</TableHead>
                            <TableHead className="text-right">Net</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {summaryData.map((person, idx) => {
                            const net = person.totalBought - person.totalSold
                            const netColorClass = net > 0 ? 'text-green-400' : net < 0 ? 'text-red-400' : 'text-muted-foreground'

                            // Render type breakdown as compact badges
                            const typeBadges = Object.entries(person.typeBreakdown).map(([code, count]) => {
                                const label = codeToLabel[code] || code
                                const shortLabel = {
                                    'P': 'Purchase',
                                    'S': 'Sale',
                                    'M': 'Option',
                                    'A': 'Award',
                                    'F': 'Tax',
                                    'G': 'Gift',
                                    'D': 'Disp.',
                                    'C': 'Conv.',
                                    'X': 'Exercise',
                                    'J': 'Other'
                                }[code] || label

                                const colorClass = getCodeClass(code)
                                const bgClass = getBgClass(colorClass)

                                return (
                                    <span
                                        key={code}
                                        title={`${count} ${label}`}
                                        className={`inline-block text-[10px] px-1.5 py-0.5 mr-1 mb-0.5 rounded ${bgClass} ${colorClass}`}
                                    >
                                        {count}× {shortLabel}
                                    </span>
                                )
                            })

                            return (
                                <TableRow key={idx}>
                                    <TableCell className="font-medium align-top">
                                        <div className="font-bold">
                                            {person.name}
                                            {person.has10b51 && <PlanBadge />}
                                        </div>
                                        <div className="text-xs text-muted-foreground">{person.position}</div>
                                    </TableCell>
                                    <TableCell className="align-top">
                                        {typeBadges}
                                    </TableCell>
                                    <TableCell className="text-right align-top text-green-400">
                                        {person.buyCount > 0 ? `${formatCurrency(person.totalBought)} (${person.buyCount})` : '-'}
                                    </TableCell>
                                    <TableCell className="text-right align-top text-red-400">
                                        {person.sellCount > 0 ? `${formatCurrency(person.totalSold)} (${person.sellCount})` : '-'}
                                    </TableCell>
                                    <TableCell className="text-right align-top">
                                        {person.totalPctSold > 0 ? (
                                            <span
                                                className={person.totalPctSold > 20 ? 'text-red-400 font-bold' : 'text-red-400'}
                                                title={`Sold ${person.totalPctSold.toFixed(1)}% of holdings cumulative`}
                                            >
                                                -{person.totalPctSold.toFixed(1)}%
                                            </span>
                                        ) : person.totalPctBought > 0 ? (
                                            <span
                                                className="text-green-400"
                                                title={`Bought equivalent of ${person.totalPctBought.toFixed(1)}% of current holdings`}
                                            >
                                                +{person.totalPctBought.toFixed(1)}%
                                            </span>
                                        ) : '-'}
                                    </TableCell>
                                    <TableCell className={`text-right align-top font-bold ${netColorClass}`}>
                                        {net > 0 ? '+' : ''}{formatCurrency(net)}
                                    </TableCell>
                                </TableRow>
                            )
                        })}
                    </TableBody>
                </Table>
            </div>


            {/* Toggle for detailed view */}
            < Button
                variant="ghost"
                size="sm"
                onClick={() => setShowDetails(!showDetails)
                }
                className="mb-2 text-muted-foreground w-full justify-start"
            >
                {showDetails ? '▼ Hide Details' : '▶ Show All Transactions'}({filteredTrades.length})
            </Button >

            {/* Detailed View */}
            {
                showDetails && (
                    <div className="rounded-md border max-h-[400px] overflow-y-auto">
                        <Table>
                            <TableHeader>
                                <TableRow className="bg-muted/50 sticky top-0 z-10">
                                    <TableHead>Date</TableHead>
                                    <TableHead>Name</TableHead>
                                    <TableHead>Type</TableHead>
                                    <TableHead className="text-right">Value</TableHead>
                                    <TableHead className="text-right">% Holdings</TableHead>
                                    <TableHead>Notes</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {uniqueTrades.map((trade, idx) => {
                                    const typeLabel = trade.transaction_type_label ||
                                        codeToLabel[trade.transaction_code] ||
                                        trade.transaction_type
                                    const typeClass = trade.transaction_code
                                        ? getCodeClass(trade.transaction_code)
                                        : getTypeClass(trade.transaction_type)

                                    // Get footnotes if available
                                    const footnotes = trade.footnotes || []
                                    const hasFootnotes = footnotes.length > 0

                                    // Format ownership change percentage
                                    const ownershipPct = trade.ownership_change_pct
                                    const isSale = trade.transaction_code === 'S' || trade.transaction_code === 'F' || trade.transaction_code === 'D'

                                    // Get canonical name from grouping map
                                    let normalizedKey = trade.name.toLowerCase().replace(/[.,]/g, ' ').trim().replace(/\s+/g, ' ')
                                    const parts = normalizedKey.split(' ')
                                    if (parts.length >= 2) {
                                        normalizedKey = `${parts[0]} ${parts[1]}`
                                    }
                                    const displayName = groupedByPerson[normalizedKey] ? groupedByPerson[normalizedKey].name : trade.name

                                    const pctColorClass = ownershipPct > 50 ? 'text-red-400 font-bold' : ownershipPct > 20 ? 'text-amber-400 font-bold' : 'text-muted-foreground'

                                    return (
                                        <TableRow key={idx}>
                                            <TableCell className="whitespace-nowrap">
                                                {formatDate(trade.transaction_date)}
                                            </TableCell>
                                            <TableCell>
                                                {displayName}
                                                {trade.is_10b51_plan && <PlanBadge />}
                                            </TableCell>
                                            <TableCell className={`font-bold ${typeClass}`}>
                                                {typeLabel}
                                            </TableCell>
                                            <TableCell className={`text-right ${typeClass}`}>
                                                {formatCurrency(trade.value)}
                                            </TableCell>
                                            <TableCell className={`text-right ${pctColorClass}`}>
                                                {ownershipPct != null ? (
                                                    <span title={`${isSale ? 'Sold' : 'Bought'} ${ownershipPct}% of holdings`}>
                                                        {ownershipPct.toFixed(1)}%
                                                    </span>
                                                ) : '-'}
                                            </TableCell>
                                            <TableCell className="text-xs text-muted-foreground max-w-[250px]">
                                                {hasFootnotes ? (
                                                    <span
                                                        title={footnotes.join('\n\n')}
                                                        className="cursor-help block truncate"
                                                    >
                                                        📝 {footnotes[0].substring(0, 60)}{footnotes[0].length > 60 ? '...' : ''}
                                                    </span>
                                                ) : (
                                                    <span>-</span>
                                                )}
                                            </TableCell>
                                        </TableRow>
                                    )
                                })}
                            </TableBody>
                        </Table>
                    </div>
                )
            }
        </div>
    )
}
