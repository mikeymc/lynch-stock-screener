// ABOUTME: Compact portfolio overview card for dashboard
// ABOUTME: Shows total value, gain/loss, top holdings or CTA to create portfolio

import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Briefcase, Plus, ArrowRight, TrendingUp, TrendingDown } from 'lucide-react'

export default function PortfolioSummaryCard({ onNavigate }) {
    const [portfolios, setPortfolios] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        const fetchPortfolios = async () => {
            try {
                setLoading(true)
                const response = await fetch('/api/dashboard/portfolios')
                if (response.ok) {
                    const data = await response.json()
                    setPortfolios(data.portfolios || [])
                } else {
                    setError('Failed to load portfolios')
                }
            } catch (err) {
                console.error('Error fetching portfolios:', err)
                setError('Failed to load portfolios')
            } finally {
                setLoading(false)
            }
        }

        fetchPortfolios()
    }, [])

    const hasPortfolios = portfolios.length > 0

    // Calculate totals across all portfolios
    const totalValue = portfolios.reduce((sum, p) => sum + (p.total_value || 0), 0)
    const totalGainLoss = portfolios.reduce((sum, p) => sum + (p.total_gain_loss || 0), 0)
    const totalGainLossPct = totalValue > 0 ? (totalGainLoss / (totalValue - totalGainLoss)) * 100 : 0
    const isPositive = totalGainLoss >= 0

    return (
        <Card>
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                        <Briefcase className="h-4 w-4" />
                        Portfolios
                    </CardTitle>
                    <Button variant="ghost" size="sm" onClick={onNavigate}>
                        View all <ArrowRight className="h-4 w-4 ml-1" />
                    </Button>
                </div>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <Skeleton className="h-24 w-full" />
                ) : error ? (
                    <div className="h-24 flex items-center justify-center text-sm text-muted-foreground border border-dashed rounded-lg bg-muted/20">
                        {error}
                    </div>
                ) : hasPortfolios ? (
                    <div className="space-y-4">
                        {/* Summary row */}
                        <div className="flex items-end justify-between">
                            <div>
                                <p className="text-2xl font-bold">
                                    {formatCurrency(totalValue)}
                                </p>
                                <p className="text-sm text-muted-foreground">
                                    Total across {portfolios.length} portfolio{portfolios.length > 1 ? 's' : ''}
                                </p>
                            </div>
                            <div className={`flex items-center gap-1 text-sm ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
                                {isPositive ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                                {formatCurrency(Math.abs(totalGainLoss))} ({isPositive ? '+' : ''}{totalGainLossPct.toFixed(2)}%)
                            </div>
                        </div>

                        {/* Top holdings from all portfolios */}
                        {portfolios.some(p => p.top_holdings?.length > 0) && (
                            <div>
                                <p className="text-xs text-muted-foreground mb-2">Top Holdings</p>
                                <div className="flex flex-wrap gap-1">
                                    {getTopHoldings(portfolios).slice(0, 5).map(holding => (
                                        <Badge key={holding.symbol} variant="secondary" className="text-xs">
                                            {holding.symbol}
                                        </Badge>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                ) : (
                    <EmptyState onNavigate={onNavigate} />
                )}
            </CardContent>
        </Card>
    )
}

function EmptyState({ onNavigate }) {
    return (
        <div className="flex flex-col items-center justify-center py-6 text-center">
            <Briefcase className="h-8 w-8 text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground mb-3">
                Track your investments with paper trading portfolios
            </p>
            <Button onClick={onNavigate} size="sm">
                <Plus className="h-4 w-4 mr-1" />
                Create Portfolio
            </Button>
        </div>
    )
}

function getTopHoldings(portfolios) {
    // Aggregate holdings across portfolios and sort by frequency
    const holdingCounts = {}
    portfolios.forEach(p => {
        (p.top_holdings || []).forEach(h => {
            holdingCounts[h.symbol] = (holdingCounts[h.symbol] || 0) + 1
        })
    })
    return Object.entries(holdingCounts)
        .sort((a, b) => b[1] - a[1])
        .map(([symbol]) => ({ symbol }))
}

function formatCurrency(value) {
    if (value === null || value === undefined) return '$0.00'
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value)
}
