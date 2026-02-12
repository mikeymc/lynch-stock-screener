// ABOUTME: Summary of active investment strategies for dashboard
// ABOUTME: Shows strategy status and last run info or CTA to create strategy

import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Zap, Plus, ArrowRight } from 'lucide-react'

export default function StrategiesSummary({ onNavigate }) {
    const [strategies, setStrategies] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        const fetchStrategies = async () => {
            try {
                setLoading(true)
                const response = await fetch('/api/dashboard/strategies')
                if (response.ok) {
                    const data = await response.json()
                    setStrategies(data.strategies || [])
                } else {
                    setError('Failed to load strategies')
                }
            } catch (err) {
                console.error('Error fetching strategies:', err)
                setError('Failed to load strategies')
            } finally {
                setLoading(false)
            }
        }

        fetchStrategies()
    }, [])

    const hasStrategies = strategies.length > 0

    return (
        <Card>
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                        <Zap className="h-4 w-4" />
                        Strategies
                    </CardTitle>
                    <Button variant="ghost" size="sm" onClick={onNavigate}>
                        Manage <ArrowRight className="h-4 w-4 ml-1" />
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
                ) : hasStrategies ? (
                    <div className="space-y-2">
                        {strategies.slice(0, 4).map(strategy => (
                            <StrategyRow key={strategy.id} strategy={strategy} />
                        ))}
                        {strategies.length > 4 && (
                            <p className="text-xs text-muted-foreground text-center pt-1">
                                +{strategies.length - 4} more strategies
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

function StrategyRow({ strategy }) {
    const isPositive = strategy.portfolio_return_pct >= 0

    return (
        <div className="flex items-center justify-between py-2 px-2 rounded bg-muted/50">
            <div className="flex items-center gap-2 min-w-0">
                <div className={`h-2 w-2 rounded-full ${strategy.enabled ? 'bg-green-500' : 'bg-muted-foreground/50'}`} title={strategy.enabled ? 'Active' : 'Paused'} />
                <span className="font-medium text-sm truncate">{strategy.name}</span>
            </div>
            <div className="flex items-center gap-4">
                <div className="flex flex-col items-end">
                    <span className={`text-sm font-medium ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
                        {isPositive ? '+' : ''}{strategy.portfolio_return_pct?.toFixed(2)}%
                    </span>
                    <span className="text-[10px] text-muted-foreground uppercase font-semibold">Return</span>
                </div>
                <div className="flex flex-col items-end min-w-[80px]">
                    <span className="text-sm font-medium">
                        ${strategy.portfolio_value?.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                    </span>
                    <span className="text-[10px] text-muted-foreground uppercase font-semibold">Value</span>
                </div>
            </div>
        </div>
    )
}


function EmptyState({ onNavigate }) {
    return (
        <div className="flex flex-col items-center justify-center py-6 text-center">
            <Zap className="h-8 w-8 text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground mb-3">
                Automate your investment rules with strategies
            </p>
            <Button onClick={onNavigate} size="sm">
                <Plus className="h-4 w-4 mr-1" />
                Create Strategy
            </Button>
        </div>
    )
}
