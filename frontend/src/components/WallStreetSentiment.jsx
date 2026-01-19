// ABOUTME: Wall Street Sentiment page with analyst consensus and forward indicators
import React, { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Bar, Line } from 'react-chartjs-2'
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    BarElement,
    Title,
    Tooltip,
    Legend,
    Filler
} from 'chart.js'

ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    BarElement,
    Title,
    Tooltip,
    Legend,
    Filler
)

const API_BASE = '/api'

export default function WallStreetSentiment({ symbol }) {
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    // Get computed CSS color values for charts
    const getChartColors = () => {
        if (typeof window === 'undefined') return { text: '#888', border: '#333' }
        const styles = getComputedStyle(document.documentElement)
        const mutedFg = styles.getPropertyValue('--muted-foreground').trim()
        const borderColor = styles.getPropertyValue('--border').trim()
        return {
            text: mutedFg ? `hsl(${mutedFg})` : '#888',
            border: borderColor ? `hsl(${borderColor})` : '#333'
        }
    }
    const chartColors = getChartColors()

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
                    if (active) setError("Failed to load sentiment data")
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

    if (loading) return <div className="p-8 text-muted-foreground">Loading sentiment data...</div>
    if (error) return <div className="p-8 text-destructive">Error: {error}</div>
    if (!data) return null

    const { metrics, analyst_consensus, short_interest, current_price } = data

    // --- Formatters ---
    const formatCurrency = (val) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val)
    const formatCurrencyDecimal = (val) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(val)
    const formatNumber = (val) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(val)
    const formatPercent = (val) => new Intl.NumberFormat('en-US', { style: 'percent', maximumFractionDigits: 2 }).format(val)

    // --- Analyst count helpers ---
    const analystEstimates = data.analyst_estimates || {}
    const getAnalystCount = (periods, type) => {
        const key = `${type}_num_analysts`
        const counts = periods.map(p => analystEstimates[p]?.[key]).filter(c => c != null)
        if (counts.length === 0) return null
        return Math.max(...counts)
    }

    // --- Helper for PEG ---
    const peg = metrics?.forward_peg_ratio
    let pegStatus = 'N/A'
    let pegColorClass = 'text-muted-foreground'
    if (peg) {
        if (peg < 1.0) { pegColorClass = 'text-green-600'; pegStatus = 'Undervalued (< 1.0)' }
        else if (peg < 1.5) { pegColorClass = 'text-cyan-500'; pegStatus = 'Fair Value' }
        else { pegColorClass = 'text-red-500'; pegStatus = 'Overvalued (> 1.5)' }
    }

    // --- Analyst Rating Helpers ---
    const ratingScore = analyst_consensus?.rating_score
    const ratingText = analyst_consensus?.rating?.toUpperCase() || 'N/A'
    const analystCount = analyst_consensus?.analyst_count || 0
    const ratingPercent = ratingScore ? ((5 - ratingScore) / 4) * 100 : 50

    let ratingColorClass = 'text-muted-foreground'
    let ratingBgClass = 'bg-muted'
    if (ratingScore) {
        if (ratingScore <= 1.5) { ratingColorClass = 'text-green-600'; ratingBgClass = 'bg-green-600' }
        else if (ratingScore <= 2.5) { ratingColorClass = 'text-green-500'; ratingBgClass = 'bg-green-500' }
        else if (ratingScore <= 3.5) { ratingColorClass = 'text-yellow-500'; ratingBgClass = 'bg-yellow-500' }
        else if (ratingScore <= 4.5) { ratingColorClass = 'text-orange-500'; ratingBgClass = 'bg-orange-500' }
        else { ratingColorClass = 'text-red-500'; ratingBgClass = 'bg-red-500' }
    }

    // Price target calculations
    const targetLow = analyst_consensus?.price_target_low
    const targetHigh = analyst_consensus?.price_target_high
    const targetMean = analyst_consensus?.price_target_mean
    const priceNow = current_price || 0

    let pricePosition = 50
    if (targetLow && targetHigh && priceNow && targetHigh !== targetLow) {
        pricePosition = ((priceNow - targetLow) / (targetHigh - targetLow)) * 100
        pricePosition = Math.max(0, Math.min(100, pricePosition))
    }
    const upside = targetMean && priceNow ? ((targetMean - priceNow) / priceNow) : null

    // Short interest helpers
    const shortRatio = short_interest?.short_ratio
    const shortPercentFloat = short_interest?.short_percent_float
    let shortColorClass = 'text-muted-foreground'
    let shortStatus = 'Normal'
    if (shortPercentFloat) {
        if (shortPercentFloat > 0.20) { shortColorClass = 'text-red-500'; shortStatus = 'Very High (>20%)' }
        else if (shortPercentFloat > 0.10) { shortColorClass = 'text-orange-500'; shortStatus = 'Elevated (>10%)' }
        else if (shortPercentFloat > 0.05) { shortColorClass = 'text-yellow-500'; shortStatus = 'Moderate (>5%)' }
        else { shortColorClass = 'text-green-500'; shortStatus = 'Low' }
    }

    // --- Chart Data: Recommendation History (Stacked Bar) ---
    const recHistory = data.recommendation_history || []
    const sortedRecHistory = recHistory
        .slice(0, 4)
        .sort((a, b) => {
            const aVal = parseInt(a.period) || 0
            const bVal = parseInt(b.period) || 0
            return aVal - bVal
        })
    const recChartData = {
        labels: sortedRecHistory.map(r => r.period),
        datasets: [
            {
                label: 'Strong Sell',
                data: sortedRecHistory.map(r => r.strong_sell || 0),
                backgroundColor: 'rgb(239, 68, 68)',
                borderRadius: 2,
            },
            {
                label: 'Sell',
                data: sortedRecHistory.map(r => r.sell || 0),
                backgroundColor: 'rgb(249, 115, 22)',
                borderRadius: 2,
            },
            {
                label: 'Hold',
                data: sortedRecHistory.map(r => r.hold || 0),
                backgroundColor: 'rgb(234, 179, 8)',
                borderRadius: 2,
            },
            {
                label: 'Buy',
                data: sortedRecHistory.map(r => r.buy || 0),
                backgroundColor: 'rgb(34, 197, 94)',
                borderRadius: 2,
            },
            {
                label: 'Strong Buy',
                data: sortedRecHistory.map(r => r.strong_buy || 0),
                backgroundColor: 'rgb(22, 163, 74)',
                borderRadius: 2,
            },
        ]
    }

    const recChartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { position: 'top', labels: { color: chartColors.text, boxWidth: 12, padding: 10 } },
            title: { display: false }
        },
        scales: {
            x: { stacked: true, grid: { display: false }, ticks: { color: chartColors.text } },
            y: { stacked: true, grid: { color: chartColors.border }, ticks: { color: chartColors.text } }
        }
    }

    // --- Chart Data: Revenue & EPS Trends (Line Charts showing current vs 30d ago) ---
    const epsTrends = data.eps_trends || {}

    // Helper to format period labels
    const formatPeriodLabel = (period, estimate) => {
        // Preference: Use exact period end date if available (e.g. "12/25")
        if (estimate?.period_end_date) {
            const date = new Date(estimate.period_end_date)
            const month = date.getMonth() + 1
            const year = date.getFullYear() % 100 // Last 2 digits
            return `${month}/${year}`
        }

        // Fallback to old format
        const baseLabelMap = { '0q': 'Current Q', '+1q': 'Next Q', '0y': 'Current Y', '+1y': 'Next Y' }
        return baseLabelMap[period] || period
    }

    // Quarterly EPS periods
    const quarterlyPeriods = ['0q', '+1q'].filter(p => epsTrends[p]?.current)
    const quarterlyEpsChartData = {
        labels: quarterlyPeriods.map(p => formatPeriodLabel(p, analystEstimates[p])),
        datasets: [
            // High estimate (upper bound of range band)
            {
                label: 'Estimate Range',
                data: quarterlyPeriods.map(p => analystEstimates[p]?.eps_high || 0),
                borderColor: 'rgba(59, 130, 246, 0.3)',
                backgroundColor: 'rgba(59, 130, 246, 0.15)',
                borderWidth: 1,
                pointRadius: 0,
                fill: {
                    target: '+1',
                    above: 'rgba(59, 130, 246, 0.15)',
                },
                tension: 0.3,
            },
            // Low estimate (lower bound of range band)
            {
                label: 'Estimate Low',
                data: quarterlyPeriods.map(p => analystEstimates[p]?.eps_low || 0),
                borderColor: 'rgba(59, 130, 246, 0.3)',
                backgroundColor: 'transparent',
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
                tension: 0.3,
            },
            // Current estimate (main line)
            {
                label: 'Current Estimate',
                data: quarterlyPeriods.map(p => epsTrends[p]?.current || 0),
                borderColor: 'rgb(59, 130, 246)',
                backgroundColor: 'transparent',
                borderWidth: 2,
                tension: 0.3,
                pointRadius: 6,
                pointBackgroundColor: 'rgb(59, 130, 246)',
            },
            // 30 days ago comparison
            {
                label: '30 Days Ago',
                data: quarterlyPeriods.map(p => epsTrends[p]?.['30_days_ago'] || 0),
                borderColor: 'rgb(148, 163, 184)',
                backgroundColor: 'transparent',
                borderWidth: 2,
                tension: 0.3,
                pointRadius: 4,
                pointBackgroundColor: 'rgb(148, 163, 184)',
                borderDash: [5, 5],
            },
        ]
    }

    // Annual EPS periods
    const annualPeriods = ['0y', '+1y'].filter(p => epsTrends[p]?.current)
    const annualEpsChartData = {
        labels: annualPeriods.map(p => formatPeriodLabel(p, analystEstimates[p])),
        datasets: [
            // High estimate (upper bound of range band)
            {
                label: 'Estimate Range',
                data: annualPeriods.map(p => analystEstimates[p]?.eps_high || 0),
                borderColor: 'rgba(59, 130, 246, 0.3)',
                backgroundColor: 'rgba(59, 130, 246, 0.15)',
                borderWidth: 1,
                pointRadius: 0,
                fill: {
                    target: '+1',
                    above: 'rgba(59, 130, 246, 0.15)',
                },
                tension: 0.3,
            },
            // Low estimate (lower bound of range band)
            {
                label: 'Estimate Low',
                data: annualPeriods.map(p => analystEstimates[p]?.eps_low || 0),
                borderColor: 'rgba(59, 130, 246, 0.3)',
                backgroundColor: 'transparent',
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
                tension: 0.3,
            },
            // Current estimate (main line)
            {
                label: 'Current Estimate',
                data: annualPeriods.map(p => epsTrends[p]?.current || 0),
                borderColor: 'rgb(59, 130, 246)',
                backgroundColor: 'transparent',
                borderWidth: 2,
                tension: 0.3,
                pointRadius: 6,
                pointBackgroundColor: 'rgb(59, 130, 246)',
            },
            // 30 days ago comparison
            {
                label: '30 Days Ago',
                data: annualPeriods.map(p => epsTrends[p]?.['30_days_ago'] || 0),
                borderColor: 'rgb(148, 163, 184)',
                backgroundColor: 'transparent',
                borderWidth: 2,
                tension: 0.3,
                pointRadius: 4,
                pointBackgroundColor: 'rgb(148, 163, 184)',
                borderDash: [5, 5],
            },
        ]
    }

    // Quarterly Revenue periods
    const quarterlyRevenuePeriods = ['0q', '+1q'].filter(p => analystEstimates[p]?.revenue_avg)
    const quarterlyRevenueChartData = {
        labels: quarterlyRevenuePeriods.map(p => formatPeriodLabel(p, analystEstimates[p])),
        datasets: [
            // High estimate (upper bound of range band)
            {
                label: 'Estimate Range',
                data: quarterlyRevenuePeriods.map(p => (analystEstimates[p]?.revenue_high || 0) / 1e9),
                borderColor: 'rgba(34, 197, 94, 0.3)',
                backgroundColor: 'rgba(34, 197, 94, 0.15)',
                borderWidth: 1,
                pointRadius: 0,
                fill: {
                    target: '+1',
                    above: 'rgba(34, 197, 94, 0.15)',
                },
                tension: 0.3,
            },
            // Low estimate (lower bound of range band)
            {
                label: 'Estimate Low',
                data: quarterlyRevenuePeriods.map(p => (analystEstimates[p]?.revenue_low || 0) / 1e9),
                borderColor: 'rgba(34, 197, 94, 0.3)',
                backgroundColor: 'transparent',
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
                tension: 0.3,
            },
            // Average estimate (main line)
            {
                label: 'Avg Estimate',
                data: quarterlyRevenuePeriods.map(p => (analystEstimates[p]?.revenue_avg || 0) / 1e9),
                borderColor: 'rgb(34, 197, 94)',
                backgroundColor: 'transparent',
                borderWidth: 2,
                tension: 0.3,
                pointRadius: 6,
                pointBackgroundColor: 'rgb(34, 197, 94)',
            },
        ]
    }

    // Annual Revenue periods
    const annualRevenuePeriods = ['0y', '+1y'].filter(p => analystEstimates[p]?.revenue_avg)
    const annualRevenueChartData = {
        labels: annualRevenuePeriods.map(p => formatPeriodLabel(p, analystEstimates[p])),
        datasets: [
            // High estimate (upper bound of range band)
            {
                label: 'Estimate Range',
                data: annualRevenuePeriods.map(p => (analystEstimates[p]?.revenue_high || 0) / 1e9),
                borderColor: 'rgba(34, 197, 94, 0.3)',
                backgroundColor: 'rgba(34, 197, 94, 0.15)',
                borderWidth: 1,
                pointRadius: 0,
                fill: {
                    target: '+1',
                    above: 'rgba(34, 197, 94, 0.15)',
                },
                tension: 0.3,
            },
            // Low estimate (lower bound of range band)
            {
                label: 'Estimate Low',
                data: annualRevenuePeriods.map(p => (analystEstimates[p]?.revenue_low || 0) / 1e9),
                borderColor: 'rgba(34, 197, 94, 0.3)',
                backgroundColor: 'transparent',
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
                tension: 0.3,
            },
            // Average estimate (main line)
            {
                label: 'Avg Estimate',
                data: annualRevenuePeriods.map(p => (analystEstimates[p]?.revenue_avg || 0) / 1e9),
                borderColor: 'rgb(34, 197, 94)',
                backgroundColor: 'transparent',
                borderWidth: 2,
                tension: 0.3,
                pointRadius: 6,
                pointBackgroundColor: 'rgb(34, 197, 94)',
            },
        ]
    }

    const epsChartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: 'top',
                labels: {
                    color: chartColors.text,
                    filter: (item) => !item.text.includes('Range') && !item.text.includes('Low')
                }
            },
            title: { display: false }
        },
        scales: {
            y: {
                grid: { color: chartColors.border },
                ticks: { color: chartColors.text, callback: (val) => `$${val.toFixed(2)}` }
            },
            x: { grid: { display: false }, ticks: { color: chartColors.text } }
        }
    }

    const revenueChartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: 'top',
                labels: {
                    color: chartColors.text,
                    filter: (item) => !item.text.includes('Range') && !item.text.includes('Low')
                }
            },
            title: { display: false }
        },
        scales: {
            y: {
                grid: { color: chartColors.border },
                ticks: { color: chartColors.text, callback: (val) => `$${val.toFixed(1)}B` }
            },
            x: { grid: { display: false }, ticks: { color: chartColors.text } }
        }
    }

    // --- Calculate Revision Momentum Summary ---
    const epsRevisions = data.eps_revisions || {}
    let totalUp = 0, totalDown = 0
    Object.values(epsRevisions).forEach(rev => {
        totalUp += rev.up_30d || 0
        totalDown += rev.down_30d || 0
    })
    const netRevisions = totalUp - totalDown
    const revisionSentiment = netRevisions > 0 ? 'Bullish' : netRevisions < 0 ? 'Bearish' : 'Neutral'

    return (
        <div className="w-full space-y-6">
            {/* ROW 1: Wall Street Consensus + Fiscal Calendar */}
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">

                {/* Wall Street Consensus (Left, 3/4 width) */}
                {(analyst_consensus?.rating || short_interest?.short_percent_float) && (
                    <Card className="lg:col-span-3 h-full">
                        <CardHeader>
                            <CardTitle>Wall Street Consensus</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
                                {/* Analyst Rating */}
                                {analyst_consensus?.rating && (
                                    <div className="text-center">
                                        <div className="text-sm text-muted-foreground mb-3">
                                            Analyst Rating ({analystCount} analysts)
                                        </div>
                                        <div className="h-3 bg-muted rounded-full overflow-hidden mb-3">
                                            <div
                                                className={`h-full ${ratingBgClass} rounded-full transition-all`}
                                                style={{ width: `${ratingPercent}%` }}
                                            />
                                        </div>
                                        <div className={`font-bold text-lg mb-1 ${ratingColorClass}`}>
                                            {ratingText}
                                        </div>
                                        {ratingScore && (
                                            <div className="text-xs text-muted-foreground">
                                                Score: {formatNumber(ratingScore)} (1 = Strong Buy, 5 = Sell)
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Price Target */}
                                {targetLow && targetHigh && (
                                    <div className="text-center">
                                        <div className="text-sm text-muted-foreground mb-3">
                                            Price Target Range
                                        </div>
                                        <div className="relative mb-4">
                                            <div className="flex justify-between text-xs text-muted-foreground mb-1">
                                                <span>{formatCurrencyDecimal(targetLow)}</span>
                                                <span>{formatCurrencyDecimal(targetHigh)}</span>
                                            </div>
                                            <div className="h-2 bg-muted rounded relative">
                                                {/* Mean target marker */}
                                                {targetMean && (
                                                    <div
                                                        className="absolute top-[-2px] w-1 h-[12px] bg-blue-500 rounded"
                                                        style={{ left: `${((targetMean - targetLow) / (targetHigh - targetLow)) * 100}%`, transform: 'translateX(-50%)' }}
                                                    />
                                                )}
                                                {/* Current price marker */}
                                                <div
                                                    className="absolute top-[-4px] w-3 h-[16px] bg-green-500 rounded border-2 border-background"
                                                    style={{ left: `${pricePosition}%`, transform: 'translateX(-50%)' }}
                                                />
                                            </div>
                                            <div className="flex justify-center gap-8 mt-3">
                                                <div className="text-center">
                                                    <div className="text-xs text-muted-foreground">Current</div>
                                                    <div className="font-bold text-green-600">{formatCurrencyDecimal(priceNow)}</div>
                                                </div>
                                                {targetMean && (
                                                    <div className="text-center">
                                                        <div className="text-xs text-muted-foreground">Mean Target</div>
                                                        <div className="font-bold text-blue-600">
                                                            {formatCurrencyDecimal(targetMean)}
                                                            {upside !== null && (
                                                                <span className={`ml-2 text-sm ${upside >= 0 ? 'text-green-500' : 'text-red-500'}`}>
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
                                    <div className="text-center">
                                        <div className="text-sm text-muted-foreground mb-3">
                                            Short Interest
                                        </div>
                                        <div className="flex items-baseline justify-center gap-2 mb-1">
                                            <span className={`text-3xl font-bold ${shortColorClass}`}>
                                                {formatPercent(shortPercentFloat)}
                                            </span>
                                            <span className="text-muted-foreground">of float</span>
                                        </div>
                                        <div className={`text-sm ${shortColorClass} mb-2`}>
                                            {shortStatus}
                                        </div>
                                        {shortRatio && (
                                            <div className="text-xs text-muted-foreground">
                                                Days to cover: {formatNumber(shortRatio)}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Fiscal Calendar (Right, 1/4 width) */}
                {(data.fiscal_calendar || metrics?.next_earnings_date) && (() => {
                    const fc = data.fiscal_calendar
                    const currentQ = fc?.current_quarter
                    const currentFY = fc?.current_fiscal_year
                    const reportingQ = fc?.reporting_quarter
                    const reportingFY = fc?.reporting_fiscal_year
                    const earningsDate = (fc?.next_earnings_date || metrics?.next_earnings_date) ? new Date(fc?.next_earnings_date || metrics.next_earnings_date) : null

                    if (!earningsDate && !currentQ) return null

                    return (
                        <Card className="h-full">
                            <CardHeader>
                                <CardTitle>Fiscal Calendar</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-6">
                                    {/* Current Quarter */}
                                    {currentQ && currentFY && (
                                        <div className="text-center">
                                            <div className="text-xs text-muted-foreground mb-1">Current Quarter</div>
                                            <div className="text-2xl font-bold">Q{currentQ} {2000 + currentFY}</div>
                                        </div>
                                    )}

                                    {/* Next Earnings Date */}
                                    {earningsDate && (
                                        <div className="text-center">
                                            <div className="text-xs text-muted-foreground mb-1">
                                                {reportingQ ? `Q${reportingQ} Earnings` : 'Next Earnings'}
                                            </div>
                                            <div className="text-2xl font-bold">
                                                {earningsDate.toLocaleDateString('en-US', {
                                                    month: 'short',
                                                    day: 'numeric'
                                                })}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </CardContent>
                        </Card>
                    )
                })()}
            </div>



            {/* ROW 3: Forward Indicators */}
            <Card>
                <CardHeader>
                    <CardTitle>Forward Indicators</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {/* PEG Box */}
                        <div className="text-center p-6 bg-muted/50 rounded-lg">
                            <div className="text-sm text-muted-foreground mb-2">Forward PEG Ratio</div>
                            <div className={`text-3xl font-bold ${pegColorClass}`}>
                                {peg ? formatNumber(peg) : 'N/A'}
                            </div>
                        </div>

                        {/* Forward PE Box */}
                        <div className="text-center p-6 bg-muted/50 rounded-lg">
                            <div className="text-sm text-muted-foreground mb-2">Forward P/E</div>
                            <div className="text-3xl font-bold">
                                {metrics?.forward_pe ? formatNumber(metrics.forward_pe) : 'N/A'}
                            </div>
                        </div>

                        {/* Forward EPS Box */}
                        <div className="text-center p-6 bg-muted/50 rounded-lg">
                            <div className="text-sm text-muted-foreground mb-2">Forward EPS</div>
                            <div className="text-3xl font-bold">
                                {metrics?.forward_eps ? formatCurrency(metrics.forward_eps) : 'N/A'}
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* ROW 4: Revenue Estimate Charts */}
            {(quarterlyRevenuePeriods.length > 0 || annualRevenuePeriods.length > 0) && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Quarterly Revenue Trends */}
                    {quarterlyRevenuePeriods.length > 0 && (() => {
                        const count = getAnalystCount(quarterlyRevenuePeriods, 'revenue')
                        return (
                            <Card>
                                <CardHeader>
                                    <CardTitle className="flex items-baseline gap-2">
                                        Quarterly Revenue Estimates
                                        {count && <span className="text-sm font-normal text-muted-foreground">({count} analysts)</span>}
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="h-[250px]">
                                        <Line data={quarterlyRevenueChartData} options={revenueChartOptions} />
                                    </div>
                                </CardContent>
                            </Card>
                        )
                    })()}

                    {/* Annual Revenue Trends */}
                    {annualRevenuePeriods.length > 0 && (() => {
                        const count = getAnalystCount(annualRevenuePeriods, 'revenue')
                        return (
                            <Card>
                                <CardHeader>
                                    <CardTitle className="flex items-baseline gap-2">
                                        Annual Revenue Estimates
                                        {count && <span className="text-sm font-normal text-muted-foreground">({count} analysts)</span>}
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="h-[250px]">
                                        <Line data={annualRevenueChartData} options={revenueChartOptions} />
                                    </div>
                                </CardContent>
                            </Card>
                        )
                    })()}
                </div>
            )}

            {/* ROW 5: EPS Estimate Charts */}
            {(quarterlyPeriods.length > 0 || annualPeriods.length > 0) && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Quarterly EPS Trends */}
                    {quarterlyPeriods.length > 0 && (() => {
                        const count = getAnalystCount(quarterlyPeriods, 'eps')
                        return (
                            <Card>
                                <CardHeader>
                                    <CardTitle className="flex items-baseline gap-2">
                                        Quarterly EPS Estimate Trends
                                        {count && <span className="text-sm font-normal text-muted-foreground">({count} analysts)</span>}
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="h-[250px]">
                                        <Line data={quarterlyEpsChartData} options={epsChartOptions} />
                                    </div>
                                </CardContent>
                            </Card>
                        )
                    })()}

                    {/* Annual EPS Trends */}
                    {annualPeriods.length > 0 && (() => {
                        const count = getAnalystCount(annualPeriods, 'eps')
                        return (
                            <Card>
                                <CardHeader>
                                    <CardTitle className="flex items-baseline gap-2">
                                        Annual EPS Estimate Trends
                                        {count && <span className="text-sm font-normal text-muted-foreground">({count} analysts)</span>}
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="h-[250px]">
                                        <Line data={annualEpsChartData} options={epsChartOptions} />
                                    </div>
                                </CardContent>
                            </Card>
                        )
                    })()}
                </div>
            )}

            {/* ROW 6: Revision Momentum */}
            {(totalUp > 0 || totalDown > 0) && (
                <Card>
                    <CardHeader>
                        <CardTitle>Estimate Revision Momentum</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-sm text-muted-foreground mb-4">
                            Net upward vs downward revisions in the last 30 days.
                        </p>
                        <div className="flex items-center justify-center gap-8 py-8">
                            <div className="text-center">
                                <div className="text-5xl font-bold text-green-500">↑{totalUp}</div>
                                <div className="text-sm text-muted-foreground mt-2">Upward</div>
                            </div>
                            <div className="text-center">
                                <div className="text-5xl font-bold text-red-500">↓{totalDown}</div>
                                <div className="text-sm text-muted-foreground mt-2">Downward</div>
                            </div>
                            <div className="text-center border-l pl-8">
                                <div className={`text-5xl font-bold ${netRevisions > 0 ? 'text-green-500' : netRevisions < 0 ? 'text-red-500' : 'text-muted-foreground'}`}>
                                    {netRevisions > 0 ? '+' : ''}{netRevisions}
                                </div>
                                <div className={`text-sm font-medium mt-2 ${netRevisions > 0 ? 'text-green-500' : netRevisions < 0 ? 'text-red-500' : 'text-muted-foreground'}`}>
                                    {revisionSentiment}
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* ROW 7: Recommendation History Chart */}
            {recHistory.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle>Analyst Recommendation Trend</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-sm text-muted-foreground mb-4">
                            Distribution of analyst recommendations over the past months.
                        </p>
                        <div className="h-[280px]">
                            <Bar data={recChartData} options={recChartOptions} />
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    )
}
