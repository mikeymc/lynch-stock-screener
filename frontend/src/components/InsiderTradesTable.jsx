import React, { useState } from 'react'

export default function InsiderTradesTable({ trades }) {
    const [showDetails, setShowDetails] = useState(false)
    const [showAllTypes, setShowAllTypes] = useState(false)

    if (!trades || trades.length === 0) {
        return (
            <p style={{ padding: '1rem', color: '#94a3b8', fontStyle: 'italic' }}>
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

    // Transaction code to color mapping
    const getCodeColor = (code) => {
        const colors = {
            'P': '#4ade80',  // Purchase - green
            'S': '#f87171',  // Sale - red
            'M': '#fbbf24',  // Option Exercise - amber/yellow
            'A': '#60a5fa',  // Award/Grant - blue
            'F': '#94a3b8',  // Tax Withholding - gray
            'G': '#a78bfa',  // Gift - purple
            'D': '#f87171',  // Disposition - red
            'C': '#60a5fa',  // Conversion - blue
            'X': '#fbbf24',  // Exercise In-the-Money - amber
        }
        return colors[code] || '#cbd5e1'
    }

    const getTypeColor = (type) => {
        if (type === 'Buy') return '#4ade80'
        if (type === 'Sell') return '#f87171'
        return '#fbbf24'  // Other - amber for option exercises etc.
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
    const filteredTrades = showAllTypes
        ? trades
        : trades.filter(t => t.transaction_code === 'P' || t.transaction_code === 'S' ||
            t.transaction_type === 'Buy' || t.transaction_type === 'Sell')

    // Count how many "other" transactions we're hiding
    const hiddenCount = trades.length - filteredTrades.length
    const hasOtherTypes = hiddenCount > 0

    // Group trades by person (using filtered trades for summary)
    // Normalize names to handle case differences in Form 4 filings
    const groupedByPerson = {}
    filteredTrades.forEach(trade => {
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
                // Track max ownership percentage for any transaction
                maxOwnershipPct: null
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
        // Track max ownership percentage
        if (trade.ownership_change_pct != null) {
            const current = groupedByPerson[normalizedKey].maxOwnershipPct
            if (current == null || trade.ownership_change_pct > current) {
                groupedByPerson[normalizedKey].maxOwnershipPct = trade.ownership_change_pct
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

    // 10b5-1 Badge component
    const PlanBadge = () => (
        <span style={{
            fontSize: '0.7rem',
            backgroundColor: 'rgba(96, 165, 250, 0.2)',
            color: '#60a5fa',
            padding: '2px 6px',
            borderRadius: '4px',
            marginLeft: '6px',
            whiteSpace: 'nowrap'
        }}>
            📋 10b5-1
        </span>
    )

    return (
        <div>
            {/* Type Filter Toggle */}
            {hasOtherTypes && (
                <div style={{ marginBottom: '0.75rem' }}>
                    <button
                        onClick={() => setShowAllTypes(!showAllTypes)}
                        style={{
                            background: showAllTypes ? 'rgba(251, 191, 36, 0.2)' : 'transparent',
                            border: `1px solid ${showAllTypes ? '#fbbf24' : '#475569'}`,
                            color: showAllTypes ? '#fbbf24' : '#94a3b8',
                            padding: '0.4rem 0.8rem',
                            borderRadius: '0.25rem',
                            cursor: 'pointer',
                            fontSize: '0.8rem'
                        }}
                    >
                        {showAllTypes ? '✓ Showing All Types' : `Show All Types (+${hiddenCount})`}
                    </button>
                    <span style={{ marginLeft: '0.75rem', fontSize: '0.75rem', color: '#64748b' }}>
                        {showAllTypes ? 'Including option exercises, awards, gifts' : 'Open market only'}
                    </span>
                </div>
            )}

            {/* Summary View */}
            <div style={{ marginBottom: '1rem' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
                    <thead>
                        <tr style={{ backgroundColor: '#0f172a' }}>
                            <th style={{ ...thStyle, position: 'static' }}>Insider</th>
                            <th style={{ ...thStyle, position: 'static' }}>Types</th>
                            <th style={{ ...thStyle, position: 'static', textAlign: 'right', color: '#4ade80' }}>Bought</th>
                            <th style={{ ...thStyle, position: 'static', textAlign: 'right', color: '#f87171' }}>Sold</th>
                            <th style={{ ...thStyle, position: 'static', textAlign: 'right' }}>Max %</th>
                            <th style={{ ...thStyle, position: 'static', textAlign: 'right' }}>Net</th>
                        </tr>
                    </thead>
                    <tbody>
                        {summaryData.map((person, idx) => {
                            const net = person.totalBought - person.totalSold
                            const netColor = net > 0 ? '#4ade80' : net < 0 ? '#f87171' : '#cbd5e1'

                            // Render type breakdown as compact badges
                            const typeBadges = Object.entries(person.typeBreakdown).map(([code, count]) => {
                                const label = codeToLabel[code] || code
                                // Use short labels for compact display
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

                                return (
                                    <span
                                        key={code}
                                        title={`${count} ${label}`}
                                        style={{
                                            display: 'inline-block',
                                            fontSize: '0.7rem',
                                            padding: '2px 6px',
                                            marginRight: '4px',
                                            marginBottom: '2px',
                                            borderRadius: '3px',
                                            backgroundColor: `${getCodeColor(code)}20`,
                                            color: getCodeColor(code),
                                            whiteSpace: 'nowrap'
                                        }}
                                    >
                                        {count}× {shortLabel}
                                    </span>
                                )
                            })

                            return (
                                <tr key={idx} style={{ borderBottom: '1px solid #334155' }}>
                                    <td style={{ padding: '10px 8px' }}>
                                        <div style={{ fontWeight: 'bold' }}>
                                            {person.name}
                                            {person.has10b51 && <PlanBadge />}
                                        </div>
                                        <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>{person.position}</div>
                                    </td>
                                    <td style={{ padding: '10px 8px' }}>
                                        {typeBadges}
                                    </td>
                                    <td style={{ padding: '10px 8px', textAlign: 'right', color: '#4ade80' }}>
                                        {person.buyCount > 0 ? `${formatCurrency(person.totalBought)} (${person.buyCount})` : '-'}
                                    </td>
                                    <td style={{ padding: '10px 8px', textAlign: 'right', color: '#f87171' }}>
                                        {person.sellCount > 0 ? `${formatCurrency(person.totalSold)} (${person.sellCount})` : '-'}
                                    </td>
                                    <td style={{
                                        padding: '10px 8px',
                                        textAlign: 'right',
                                        color: person.maxOwnershipPct > 50 ? '#f87171' : person.maxOwnershipPct > 20 ? '#fbbf24' : '#94a3b8',
                                        fontWeight: person.maxOwnershipPct > 20 ? 'bold' : 'normal'
                                    }}>
                                        {person.maxOwnershipPct != null ? (
                                            <span title={`Max single transaction was ${person.maxOwnershipPct.toFixed(1)}% of holdings`}>
                                                {person.maxOwnershipPct.toFixed(1)}%
                                            </span>
                                        ) : '-'}
                                    </td>
                                    <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 'bold', color: netColor }}>
                                        {net > 0 ? '+' : ''}{formatCurrency(net)}
                                    </td>
                                </tr>
                            )
                        })}
                    </tbody>
                </table>
            </div>

            {/* Toggle for detailed view */}
            <button
                onClick={() => setShowDetails(!showDetails)}
                style={{
                    background: 'transparent',
                    border: '1px solid #475569',
                    color: '#94a3b8',
                    padding: '0.5rem 1rem',
                    borderRadius: '0.25rem',
                    cursor: 'pointer',
                    fontSize: '0.85rem',
                    marginBottom: '0.5rem'
                }}
            >
                {showDetails ? '▼ Hide Details' : '▶ Show All Transactions'} ({filteredTrades.length})
            </button>

            {/* Detailed View */}
            {showDetails && (
                <div style={{ maxHeight: '300px', overflowY: 'auto', marginTop: '0.5rem' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                        <thead>
                            <tr>
                                <th style={thStyle}>Date</th>
                                <th style={thStyle}>Name</th>
                                <th style={thStyle}>Type</th>
                                <th style={{ ...thStyle, textAlign: 'right' }}>Value</th>
                                <th style={{ ...thStyle, textAlign: 'right' }}>% Holdings</th>
                                <th style={thStyle}>Notes</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredTrades.map((trade, idx) => {
                                const typeLabel = trade.transaction_type_label ||
                                    codeToLabel[trade.transaction_code] ||
                                    trade.transaction_type
                                const typeColor = trade.transaction_code
                                    ? getCodeColor(trade.transaction_code)
                                    : getTypeColor(trade.transaction_type)

                                // Get footnotes if available
                                const footnotes = trade.footnotes || []
                                const hasFootnotes = footnotes.length > 0

                                // Format ownership change percentage
                                const ownershipPct = trade.ownership_change_pct
                                const isSale = trade.transaction_code === 'S' || trade.transaction_code === 'F' || trade.transaction_code === 'D'

                                return (
                                    <tr key={idx} style={{ borderBottom: '1px solid #334155' }}>
                                        <td style={{ padding: '8px', whiteSpace: 'nowrap' }}>
                                            {formatDate(trade.transaction_date)}
                                        </td>
                                        <td style={{ padding: '8px' }}>
                                            {trade.name}
                                            {trade.is_10b51_plan && <PlanBadge />}
                                        </td>
                                        <td style={{ padding: '8px', color: typeColor, fontWeight: 'bold' }}>
                                            {typeLabel}
                                        </td>
                                        <td style={{ padding: '8px', textAlign: 'right', color: typeColor }}>
                                            {formatCurrency(trade.value)}
                                        </td>
                                        <td style={{
                                            padding: '8px',
                                            textAlign: 'right',
                                            color: ownershipPct > 50 ? '#f87171' : ownershipPct > 20 ? '#fbbf24' : '#94a3b8',
                                            fontWeight: ownershipPct > 20 ? 'bold' : 'normal'
                                        }}>
                                            {ownershipPct != null ? (
                                                <span title={`${isSale ? 'Sold' : 'Bought'} ${ownershipPct}% of holdings`}>
                                                    {ownershipPct.toFixed(1)}%
                                                </span>
                                            ) : '-'}
                                        </td>
                                        <td style={{ padding: '8px', fontSize: '0.75rem', color: '#94a3b8', maxWidth: '250px' }}>
                                            {hasFootnotes ? (
                                                <span
                                                    title={footnotes.join('\n\n')}
                                                    style={{
                                                        cursor: 'help',
                                                        display: 'block',
                                                        overflow: 'hidden',
                                                        textOverflow: 'ellipsis',
                                                        whiteSpace: 'nowrap'
                                                    }}
                                                >
                                                    📝 {footnotes[0].substring(0, 60)}{footnotes[0].length > 60 ? '...' : ''}
                                                </span>
                                            ) : (
                                                <span style={{ color: '#475569' }}>-</span>
                                            )}
                                        </td>
                                    </tr>
                                )
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    )
}
