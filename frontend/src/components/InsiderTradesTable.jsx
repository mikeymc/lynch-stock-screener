import React, { useState } from 'react'

export default function InsiderTradesTable({ trades }) {
    const [showDetails, setShowDetails] = useState(false)

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

    const getTypeColor = (type) => {
        if (type === 'Buy') return '#4ade80'
        if (type === 'Sell') return '#f87171'
        return '#cbd5e1'
    }

    // Group trades by person
    const groupedByPerson = {}
    trades.forEach(trade => {
        const key = trade.name
        if (!groupedByPerson[key]) {
            groupedByPerson[key] = {
                name: trade.name,
                position: trade.position,
                totalBought: 0,
                totalSold: 0,
                buyCount: 0,
                sellCount: 0
            }
        }
        if (trade.transaction_type === 'Buy') {
            groupedByPerson[key].totalBought += trade.value || 0
            groupedByPerson[key].buyCount++
        } else if (trade.transaction_type === 'Sell') {
            groupedByPerson[key].totalSold += trade.value || 0
            groupedByPerson[key].sellCount++
        }
    })

    const summaryData = Object.values(groupedByPerson)
        // Only show insiders who have actual buy/sell activity with value
        .filter(person => person.totalBought > 0 || person.totalSold > 0)
        .sort((a, b) => {
            // Sort by net activity (biggest movers first)
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

    return (
        <div>
            {/* Summary View */}
            <div style={{ marginBottom: '1rem' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
                    <thead>
                        <tr style={{ backgroundColor: '#0f172a' }}>
                            <th style={{ ...thStyle, position: 'static' }}>Insider</th>
                            <th style={{ ...thStyle, position: 'static', textAlign: 'right', color: '#4ade80' }}>Bought</th>
                            <th style={{ ...thStyle, position: 'static', textAlign: 'right', color: '#f87171' }}>Sold</th>
                            <th style={{ ...thStyle, position: 'static', textAlign: 'right' }}>Net</th>
                        </tr>
                    </thead>
                    <tbody>
                        {summaryData.map((person, idx) => {
                            const net = person.totalBought - person.totalSold
                            const netColor = net > 0 ? '#4ade80' : net < 0 ? '#f87171' : '#cbd5e1'
                            return (
                                <tr key={idx} style={{ borderBottom: '1px solid #334155' }}>
                                    <td style={{ padding: '10px 8px' }}>
                                        <div style={{ fontWeight: 'bold' }}>{person.name}</div>
                                        <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>{person.position}</div>
                                    </td>
                                    <td style={{ padding: '10px 8px', textAlign: 'right', color: '#4ade80' }}>
                                        {person.buyCount > 0 ? `${formatCurrency(person.totalBought)} (${person.buyCount})` : '-'}
                                    </td>
                                    <td style={{ padding: '10px 8px', textAlign: 'right', color: '#f87171' }}>
                                        {person.sellCount > 0 ? `${formatCurrency(person.totalSold)} (${person.sellCount})` : '-'}
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
                {showDetails ? '▼ Hide Details' : '▶ Show All Transactions'} ({trades.length})
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
                            </tr>
                        </thead>
                        <tbody>
                            {trades.map((trade, idx) => (
                                <tr key={idx} style={{ borderBottom: '1px solid #334155' }}>
                                    <td style={{ padding: '8px', whiteSpace: 'nowrap' }}>
                                        {formatDate(trade.transaction_date)}
                                    </td>
                                    <td style={{ padding: '8px' }}>{trade.name}</td>
                                    <td style={{ padding: '8px', color: getTypeColor(trade.transaction_type), fontWeight: 'bold' }}>
                                        {trade.transaction_type}
                                    </td>
                                    <td style={{ padding: '8px', textAlign: 'right', color: getTypeColor(trade.transaction_type) }}>
                                        {formatCurrency(trade.value)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    )
}
