// ABOUTME: Wall Street Sentiment page with analyst consensus and forward indicators
import React, { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const API_BASE = '/api'

export default function WallStreetSentiment({ symbol }) {
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

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

    return (
        <div className="w-full space-y-6">
            {/* ROW 1: Wall Street Consensus + Next Earnings */}
            {(analyst_consensus?.rating || short_interest?.short_percent_float || metrics?.next_earnings_date) && (
                <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                    {/* Wall Street Consensus Card */}
                    {(analyst_consensus?.rating || short_interest?.short_percent_float) && (
                        <Card className="lg:col-span-3">
                            <CardHeader>
                                <CardTitle>Wall Street Consensus</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                                    {/* Analyst Rating */}
                                    {analyst_consensus?.rating && (
                                        <div>
                                            <div className="text-sm text-muted-foreground mb-3">
                                                Analyst Rating ({analystCount} analysts)
                                            </div>
                                            <div className="flex items-center gap-4 mb-2">
                                                <div className="flex-1 h-3 bg-muted rounded-full overflow-hidden">
                                                    <div
                                                        className={`h-full ${ratingBgClass} rounded-full transition-all`}
                                                        style={{ width: `${ratingPercent}%` }}
                                                    />
                                                </div>
                                                <div className={`font-bold min-w-[80px] ${ratingColorClass}`}>
                                                    {ratingText}
                                                </div>
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
                                        <div>
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
                                        <div>
                                            <div className="text-sm text-muted-foreground mb-3">
                                                Short Interest
                                            </div>
                                            <div className="flex items-baseline gap-2 mb-1">
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

                    {/* Next Earnings Date Card */}
                    {metrics?.next_earnings_date && (() => {
                        const earningsDate = new Date(metrics.next_earnings_date)
                        const today = new Date()
                        today.setHours(0, 0, 0, 0)
                        earningsDate.setHours(0, 0, 0, 0)
                        const diffDays = Math.ceil((earningsDate - today) / (1000 * 60 * 60 * 24))

                        if (diffDays < 0) return null

                        let relativeText
                        if (diffDays === 0) relativeText = 'Today'
                        else if (diffDays === 1) relativeText = 'Tomorrow'
                        else if (diffDays <= 7) relativeText = `In ${diffDays} days`
                        else if (diffDays <= 14) relativeText = 'In ~2 weeks'
                        else if (diffDays <= 30) relativeText = `In ${Math.round(diffDays / 7)} weeks`
                        else relativeText = `In ${Math.round(diffDays / 30)} months`

                        return (
                            <Card>
                                <CardHeader>
                                    <CardTitle>Next Earnings Date</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="text-3xl font-bold mb-2">
                                        {earningsDate.toLocaleDateString('en-US', {
                                            month: 'short',
                                            day: 'numeric',
                                            year: 'numeric'
                                        })}
                                    </div>
                                    <div className="text-sm text-muted-foreground">
                                        {relativeText}
                                    </div>
                                </CardContent>
                            </Card>
                        )
                    })()}
                </div>
            )}



            {/* ROW 2: Forward Indicators */}
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
                            <div className={`text-sm mt-1 ${pegColorClass}`}>{pegStatus}</div>
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
        </div>
    )
}
