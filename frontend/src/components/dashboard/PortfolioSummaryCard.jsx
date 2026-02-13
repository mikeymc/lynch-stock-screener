// ABOUTME: Compact portfolio overview card for dashboard
// ABOUTME: Shows total value, gain/loss, top holdings or CTA to create portfolio

import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Briefcase, Plus, ArrowRight, TrendingUp, TrendingDown, Bot, User, ArrowUpRight, ArrowDownRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

export default function PortfolioSummaryCard({ onNavigate }) {
    const navigate = useNavigate()
    const [portfolios, setPortfolios] = useState([])
    const [totalCount, setTotalCount] = useState(0)
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
                    setTotalCount(data.total_count || data.portfolios?.length || 0)
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
                    <div className="space-y-0">
                        {portfolios.slice(0, 5).map(portfolio => (
                            <PortfolioRow key={portfolio.id} portfolio={portfolio} onClick={() => navigate(`/portfolios/${portfolio.id}`)} />
                        ))}
                        {totalCount > 5 && (
                            <p className="text-xs text-muted-foreground text-center pt-2">
                                +{totalCount - 5} more portfolios
                            </p>
                        )}
                    </div>
                ) : (
                    <EmptyState onNavigate={onNavigate} />
                )}
            </CardContent>
        </Card>
    )
}

function PortfolioRow({ portfolio, onClick }) {
    const isPositive = (portfolio.total_gain_loss || 0) >= 0
    const isAutonomous = !!portfolio.strategy_id

    return (
        <div
            className="flex items-center justify-between py-1.5 px-0 rounded-lg bg-muted/30 hover:bg-muted/50 cursor-pointer transition-colors"
            onClick={onClick}
        >
            <div className="flex items-center gap-3 min-w-0">
                <div className={`p-2 rounded-full ${isAutonomous ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'}`}>
                    {isAutonomous ? <Bot className="h-4 w-4" /> : <User className="h-4 w-4" />}
                </div>
                <div className="min-w-0">
                    <p className="font-semibold text-sm truncate">{portfolio.name}</p>
                    <div className="flex items-center gap-2">
                        <Badge variant="outline" className={`text-[10px] h-4 px-1.5 font-medium ${isAutonomous ? 'border-primary/30 text-primary' : 'text-muted-foreground'}`}>
                            {isAutonomous ? 'Autonomous' : 'Self-Directed'}
                        </Badge>
                    </div>
                </div>
            </div>
            <div className="flex items-center gap-3">
                <div className="flex flex-col items-end">
                    <div className={`flex items-center gap-1 text-sm font-bold ${isPositive ? 'text-emerald-500' : 'text-red-500'}`}>
                        {isPositive ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                        {(portfolio.total_gain_loss_pct || 0).toFixed(2)}%
                    </div>
                    <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">Return</span>
                </div>
                <div className="flex flex-col items-end min-w-[75px]">
                    <span className="text-sm font-bold">
                        {formatCurrency(portfolio.total_value)}
                    </span>
                    <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">Value</span>
                </div>
            </div>
        </div>
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
    if (value === null || value === undefined) return '$0'
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(value)
}
