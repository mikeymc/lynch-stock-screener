// ABOUTME: Forward-looking metrics page with analyst consensus, insider trades, and business health indicators
// ABOUTME: Two-column layout: metrics content left (2/3), chat sidebar right (1/3)

import React, { useState, useEffect, useRef } from 'react'
import InsiderTradesTable from './InsiderTradesTable'
import Sparkline from './Sparkline'
import AnalysisChat from './AnalysisChat'
import { Line } from 'react-chartjs-2'
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend
} from 'chart.js'

ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend
)

const API_BASE = '/api'

export default function FutureOutlook({ symbol }) {
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const chatRef = useRef(null)

    useEffect(() => {
        let active = true
        const fetchData = async () => {
            setLoading(true)
            try {
                const res = await fetch(`${API_BASE}/stock/${symbol}/outlook`)
                if (res.ok) {
                    const json = await res.json()
                    if (active) setData(json)
                } else {
                    if (active) setError("Failed to load outlook data")
                }
            } catch (err) {
                if (active) setError(err.message)
            } finally {
                if (active) setLoading(false)
            }
        }
        fetchData()
        return () => { active = false }
    }, [symbol])

    if (loading) return <div className="loading" style={{ padding: '2rem' }}>Loading outlook data...</div>
    if (error) return <div className="error" style={{ padding: '2rem' }}>Error: {error}</div>
    if (!data) return null

    const { metrics, analyst_consensus, short_interest, current_price, insider_trades, inventory_vs_revenue, gross_margin_history } = data

    // --- Formatters ---
    const formatCurrency = (val) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val)
    const formatCurrencyDecimal = (val) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(val)
    const formatNumber = (val) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(val)
    const formatPercent = (val) => new Intl.NumberFormat('en-US', { style: 'percent', maximumFractionDigits: 2 }).format(val)

    // --- Styles ---
    const cardStyle = {
        backgroundColor: '#1e293b',
        borderRadius: '0.5rem',
        border: '1px solid #334155',
        padding: '1.5rem',
        marginBottom: '1.5rem'
    }

    const sectionTitleStyle = {
        fontSize: '1.2rem',
        fontWeight: 'bold',
        marginBottom: '1rem',
        color: '#e2e8f0',
        borderBottom: '1px solid #475569',
        paddingBottom: '0.5rem'
    }

    // --- Helper for Net Insider Buying Color ---
    const netBuying = metrics?.insider_net_buying_6m || 0
    const netBuyingColor = netBuying > 0 ? '#4ade80' : (netBuying < 0 ? '#f87171' : '#94a3b8')
    const netBuyingText = netBuying > 0 ? 'Net Buying' : (netBuying < 0 ? 'Net Selling' : 'Neutral')

    // --- Helper for PEG Color ---
    const peg = metrics?.forward_peg_ratio
    let pegColor = '#94a3b8'
    let pegStatus = 'N/A'
    if (peg) {
        if (peg < 1.0) { pegColor = '#4ade80'; pegStatus = 'Undervalued (< 1.0)' }
        else if (peg < 1.5) { pegColor = '#22d3ee'; pegStatus = 'Fair Value' }
        else { pegColor = '#f87171'; pegStatus = 'Overvalued (> 1.5)' }
    }

    // --- Analyst Rating Helpers ---
    const ratingScore = analyst_consensus?.rating_score
    const ratingText = analyst_consensus?.rating?.toUpperCase() || 'N/A'
    const analystCount = analyst_consensus?.analyst_count || 0

    // Rating score is 1 (Strong Buy) to 5 (Sell)
    // Invert for display: 5 - score gives us 0-4 range, then normalize to percentage
    const ratingPercent = ratingScore ? ((5 - ratingScore) / 4) * 100 : 50
    let ratingColor = '#94a3b8'
    if (ratingScore) {
        if (ratingScore <= 1.5) ratingColor = '#22c55e' // Strong Buy - green
        else if (ratingScore <= 2.5) ratingColor = '#4ade80' // Buy - light green
        else if (ratingScore <= 3.5) ratingColor = '#fbbf24' // Hold - yellow
        else if (ratingScore <= 4.5) ratingColor = '#f97316' // Underperform - orange
        else ratingColor = '#ef4444' // Sell - red
    }

    // Price target calculations
    const targetLow = analyst_consensus?.price_target_low
    const targetHigh = analyst_consensus?.price_target_high
    const targetMean = analyst_consensus?.price_target_mean
    const priceNow = current_price || 0

    // Calculate position of current price within target range
    let pricePosition = 50 // Default to middle
    if (targetLow && targetHigh && priceNow && targetHigh !== targetLow) {
        pricePosition = ((priceNow - targetLow) / (targetHigh - targetLow)) * 100
        pricePosition = Math.max(0, Math.min(100, pricePosition)) // Clamp to 0-100
    }

    // Calculate upside from mean target
    const upside = targetMean && priceNow ? ((targetMean - priceNow) / priceNow) : null

    // Short interest helpers
    const shortRatio = short_interest?.short_ratio
    const shortPercentFloat = short_interest?.short_percent_float
    let shortColor = '#94a3b8'
    let shortStatus = 'Normal'
    if (shortPercentFloat) {
        if (shortPercentFloat > 0.20) { shortColor = '#ef4444'; shortStatus = 'Very High (>20%)' }
        else if (shortPercentFloat > 0.10) { shortColor = '#f97316'; shortStatus = 'Elevated (>10%)' }
        else if (shortPercentFloat > 0.05) { shortColor = '#fbbf24'; shortStatus = 'Moderate (>5%)' }
        else { shortColor = '#4ade80'; shortStatus = 'Low' }
    }

    // --- Inventory Chart Data (Absolute values in $B) ---
    const inventoryChartData = {
        labels: inventory_vs_revenue?.map(d => d.year) || [],
        datasets: [
            {
                label: 'Revenue ($B)',
                data: inventory_vs_revenue?.map(d => d.revenue) || [],
                borderColor: '#3b82f6', // blue
                backgroundColor: 'rgba(59, 130, 246, 0.2)',
                fill: true,
                tension: 0.2,
                yAxisID: 'y'
            },
            {
                label: 'Inventory ($B)',
                data: inventory_vs_revenue?.map(d => d.inventory) || [],
                borderColor: '#f97316', // orange
                backgroundColor: 'rgba(249, 115, 22, 0.2)',
                fill: true,
                tension: 0.2,
                yAxisID: 'y1'
            }
        ]
    }

    const inventoryChartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
            legend: { position: 'top' },
            title: { display: false }
        },
        scales: {
            y: {
                type: 'linear',
                position: 'left',
                grid: { color: 'rgba(255,255,255,0.1)' },
                title: { display: true, text: 'Revenue ($B)', color: '#3b82f6' },
                ticks: { color: '#3b82f6' }
            },
            y1: {
                type: 'linear',
                position: 'right',
                grid: { display: false },
                title: { display: true, text: 'Inventory ($B)', color: '#f97316' },
                ticks: { color: '#f97316' }
            },
            x: {
                grid: { display: false }
            }
        }
    }

    return (
        <div className="reports-layout">
            {/* Left Column - Future Outlook Content (2/3) */}
            <div className="reports-main-column">
                <div className="future-outlook-container" style={{ padding: '0 1rem 1rem 1rem' }}>

                    {/* ROW 1: Wall Street Consensus */}
                    {(analyst_consensus?.rating || short_interest?.short_percent_float) && (
                        <div style={cardStyle}>
                            <h3 style={sectionTitleStyle}>Wall Street Consensus</h3>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '2rem' }}>

                                {/* Analyst Rating */}
                                {analyst_consensus?.rating && (
                                    <div>
                                        <div style={{ fontSize: '0.9rem', color: '#94a3b8', marginBottom: '0.75rem' }}>
                                            Analyst Rating ({analystCount} analysts)
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.5rem' }}>
                                            <div style={{
                                                flex: 1,
                                                height: '12px',
                                                backgroundColor: '#334155',
                                                borderRadius: '6px',
                                                overflow: 'hidden',
                                                position: 'relative'
                                            }}>
                                                <div style={{
                                                    width: `${ratingPercent}%`,
                                                    height: '100%',
                                                    background: `linear-gradient(90deg, ${ratingColor} 0%, ${ratingColor}88 100%)`,
                                                    borderRadius: '6px',
                                                    transition: 'width 0.3s ease'
                                                }} />
                                            </div>
                                            <div style={{ fontWeight: 'bold', color: ratingColor, minWidth: '80px' }}>
                                                {ratingText}
                                            </div>
                                        </div>
                                        {ratingScore && (
                                            <div style={{ fontSize: '0.85rem', color: '#64748b' }}>
                                                Score: {formatNumber(ratingScore)} (1 = Strong Buy, 5 = Sell)
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Price Target */}
                                {targetLow && targetHigh && (
                                    <div>
                                        <div style={{ fontSize: '0.9rem', color: '#94a3b8', marginBottom: '0.75rem' }}>
                                            Price Target Range
                                        </div>
                                        <div style={{ position: 'relative', marginBottom: '1rem' }}>
                                            <div style={{
                                                display: 'flex',
                                                justifyContent: 'space-between',
                                                fontSize: '0.85rem',
                                                marginBottom: '0.25rem'
                                            }}>
                                                <span style={{ color: '#94a3b8' }}>{formatCurrencyDecimal(targetLow)}</span>
                                                <span style={{ color: '#94a3b8' }}>{formatCurrencyDecimal(targetHigh)}</span>
                                            </div>
                                            <div style={{
                                                height: '8px',
                                                backgroundColor: '#334155',
                                                borderRadius: '4px',
                                                position: 'relative'
                                            }}>
                                                {/* Mean target marker */}
                                                {targetMean && (
                                                    <div style={{
                                                        position: 'absolute',
                                                        left: `${((targetMean - targetLow) / (targetHigh - targetLow)) * 100}%`,
                                                        top: '-2px',
                                                        width: '4px',
                                                        height: '12px',
                                                        backgroundColor: '#3b82f6',
                                                        borderRadius: '2px',
                                                        transform: 'translateX(-50%)'
                                                    }} />
                                                )}
                                                {/* Current price marker */}
                                                <div style={{
                                                    position: 'absolute',
                                                    left: `${pricePosition}%`,
                                                    top: '-6px',
                                                    width: '12px',
                                                    height: '20px',
                                                    backgroundColor: '#22c55e',
                                                    borderRadius: '4px',
                                                    transform: 'translateX(-50%)',
                                                    border: '2px solid #0f172a'
                                                }} />
                                            </div>
                                            <div style={{
                                                display: 'flex',
                                                justifyContent: 'center',
                                                marginTop: '0.75rem',
                                                gap: '2rem'
                                            }}>
                                                <div style={{ textAlign: 'center' }}>
                                                    <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Current</div>
                                                    <div style={{ fontWeight: 'bold', color: '#22c55e' }}>{formatCurrencyDecimal(priceNow)}</div>
                                                </div>
                                                {targetMean && (
                                                    <div style={{ textAlign: 'center' }}>
                                                        <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Mean Target</div>
                                                        <div style={{ fontWeight: 'bold', color: '#3b82f6' }}>
                                                            {formatCurrencyDecimal(targetMean)}
                                                            {upside !== null && (
                                                                <span style={{
                                                                    color: upside >= 0 ? '#4ade80' : '#f87171',
                                                                    marginLeft: '0.5rem',
                                                                    fontSize: '0.9rem'
                                                                }}>
                                                                    ({upside >= 0 ? '+' : ''}{formatPercent(upside)})
                                                                </span>
                                                            )}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {/* Short Interest */}
                                {shortPercentFloat && (
                                    <div>
                                        <div style={{ fontSize: '0.9rem', color: '#94a3b8', marginBottom: '0.75rem' }}>
                                            Short Interest
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginBottom: '0.25rem' }}>
                                            <span style={{ fontSize: '1.75rem', fontWeight: 'bold', color: shortColor }}>
                                                {formatPercent(shortPercentFloat)}
                                            </span>
                                            <span style={{ color: '#94a3b8' }}>of float</span>
                                        </div>
                                        <div style={{ fontSize: '0.85rem', color: shortColor, marginBottom: '0.5rem' }}>
                                            {shortStatus}
                                        </div>
                                        {shortRatio && (
                                            <div style={{ fontSize: '0.85rem', color: '#64748b' }}>
                                                Days to cover: {formatNumber(shortRatio)}
                                            </div>
                                        )}
                                    </div>
                                )}

                            </div>
                        </div>
                    )}

                    {/* ROW 2: Insider Signals */}
                    <div style={cardStyle}>
                        <h3 style={sectionTitleStyle}>Insider Trading</h3>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.5rem' }}>
                            <div style={{ fontSize: '2.5rem', fontWeight: 'bold', color: netBuyingColor }}>
                                {netBuying > 0 ? '+' : ''}{formatCurrency(netBuying)}
                            </div>
                            <div style={{ fontSize: '1.2rem', color: '#cbd5e1' }}>
                                ({netBuyingText})
                            </div>
                        </div>
                        <div>
                            <InsiderTradesTable trades={insider_trades} />
                        </div>
                    </div>

                    {/* ROW 3: Business Health Checks */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '1.5rem' }}>

                        {/* Inventory Check */}
                        <div style={cardStyle}>
                            <h3 style={sectionTitleStyle}>Inventory vs Revenue Trends</h3>
                            <p style={{ fontSize: '0.9rem', color: '#94a3b8', marginBottom: '1rem' }}>
                                Warning Sign: If Inventory (Orange) is growing faster than Revenue (Blue).
                            </p>
                            <div style={{ height: '250px' }}>
                                {inventory_vs_revenue && inventory_vs_revenue.length > 0 ? (
                                    <Line data={inventoryChartData} options={inventoryChartOptions} />
                                ) : (
                                    <div className="no-data">Insufficient data for Inventory check.</div>
                                )}
                            </div>
                        </div>

                        {/* Moat Stability */}
                        <div style={cardStyle}>
                            <h3 style={sectionTitleStyle}>Gross Margin Trend</h3>
                            <p style={{ fontSize: '0.9rem', color: '#94a3b8', marginBottom: '1rem' }}>
                                Stable or expanding gross margins indicate pricing power and a durable moat.
                            </p>
                            <div style={{ height: '250px' }}>
                                {gross_margin_history && gross_margin_history.length > 0 ? (
                                    <Line
                                        data={{
                                            labels: gross_margin_history.map(d => d.year),
                                            datasets: [{
                                                label: 'Gross Margin (%)',
                                                data: gross_margin_history.map(d => d.value),
                                                borderColor: '#22c55e',
                                                backgroundColor: 'rgba(34, 197, 94, 0.2)',
                                                fill: true,
                                                tension: 0.2
                                            }]
                                        }}
                                        options={{
                                            responsive: true,
                                            maintainAspectRatio: false,
                                            interaction: { mode: 'index', intersect: false },
                                            plugins: {
                                                legend: { display: false },
                                                title: { display: false }
                                            },
                                            scales: {
                                                y: {
                                                    grid: { color: 'rgba(255,255,255,0.1)' },
                                                    title: { display: true, text: 'Margin (%)' }
                                                },
                                                x: {
                                                    grid: { display: false }
                                                }
                                            }
                                        }}
                                    />
                                ) : (
                                    <div className="no-data">No Gross Margin history available.</div>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* ROW 4: Valuation Reality */}
                    <div style={cardStyle}>
                        <h3 style={sectionTitleStyle}>Forward Indicators</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '2rem' }}>

                            {/* PEG Box */}
                            <div style={{ textAlign: 'center', padding: '1rem', backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: '0.5rem' }}>
                                <div style={{ fontSize: '0.9rem', color: '#94a3b8', marginBottom: '0.5rem' }}>Forward PEG Ratio</div>
                                <div style={{ fontSize: '2rem', fontWeight: 'bold', color: pegColor }}>
                                    {peg ? formatNumber(peg) : 'N/A'}
                                </div>
                                <div style={{ color: pegColor, marginTop: '0.2rem' }}>{pegStatus}</div>
                            </div>

                            {/* Forward PE Box */}
                            <div style={{ textAlign: 'center', padding: '1rem', backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: '0.5rem' }}>
                                <div style={{ fontSize: '0.9rem', color: '#94a3b8', marginBottom: '0.5rem' }}>Forward P/E</div>
                                <div style={{ fontSize: '2rem', fontWeight: 'bold', color: '#e2e8f0' }}>
                                    {metrics?.forward_pe ? formatNumber(metrics.forward_pe) : 'N/A'}
                                </div>
                            </div>

                            {/* Forward EPS Box */}
                            <div style={{ textAlign: 'center', padding: '1rem', backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: '0.5rem' }}>
                                <div style={{ fontSize: '0.9rem', color: '#94a3b8', marginBottom: '0.5rem' }}>Forward EPS</div>
                                <div style={{ fontSize: '2rem', fontWeight: 'bold', color: '#e2e8f0' }}>
                                    {metrics?.forward_eps ? formatCurrency(metrics.forward_eps) : 'N/A'}
                                </div>
                            </div>

                        </div>
                    </div>

                </div>
            </div>

            {/* Right Column - Chat Sidebar (1/3) */}
            <div className="reports-chat-sidebar">
                <div className="chat-sidebar-content">
                    <AnalysisChat ref={chatRef} symbol={symbol} chatOnly={true} contextType="outlook" />
                </div>
            </div>
        </div>
    )
}
