import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, TrendingUp, TrendingDown, Activity, Calendar, PlayCircle, Folder } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { format } from 'date-fns'

import StrategyWizard from '@/components/strategies/StrategyWizard'

function Strategies() {
    const navigate = useNavigate()
    const [strategies, setStrategies] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [showWizard, setShowWizard] = useState(false)

    const fetchStrategies = async () => {
        try {
            const response = await fetch('/api/strategies')
            if (!response.ok) {
                throw new Error('Failed to fetch strategies')
            }
            const data = await response.json()
            setStrategies(data)
        } catch (err) {
            console.error(err)
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchStrategies()
    }, [])

    if (loading) {
        return (
            <div className="space-y-6">
                <div className="flex items-center justify-between">
                    <Skeleton className="h-8 w-48" />
                    <Skeleton className="h-10 w-32" />
                </div>
                <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                    {[1, 2, 3].map((i) => (
                        <Skeleton key={i} className="h-64 w-full" />
                    ))}
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="p-6 text-center text-red-500 bg-red-50 rounded-lg">
                <p>Error loading strategies: {error}</p>
            </div>
        )
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Investment Strategies</h1>
                    <p className="text-muted-foreground">Manage your autonomous investment agents</p>
                </div>
                <Button onClick={() => setShowWizard(true)} className="flex items-center gap-2">
                    <Plus className="h-4 w-4" /> Create Strategy
                </Button>
            </div>

            {strategies.length === 0 ? (
                <div className="rounded-lg border bg-card text-card-foreground shadow-sm p-12 text-center">
                    <div className="mx-auto w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
                        <Activity className="h-6 w-6 text-muted-foreground" />
                    </div>
                    <h3 className="text-lg font-medium mb-2">No strategies defined</h3>
                    <p className="text-muted-foreground mb-6 max-w-sm mx-auto">
                        There are no active investment strategies linked to your account.
                    </p>
                    <Button onClick={() => setShowWizard(true)}>
                        <Plus className="h-4 w-4 mr-2" /> Create Your First Strategy
                    </Button>
                </div>
            ) : (
                <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                    {strategies.map((strategy) => (
                        <StrategyCard key={strategy.id} strategy={strategy} />
                    ))}
                </div>
            )}

            {showWizard && (
                <StrategyWizard
                    onClose={() => setShowWizard(false)}
                    onSuccess={(newStrategy) => {
                        setShowWizard(false)
                        fetchStrategies()
                    }}
                />
            )}
        </div>
    )
}

function StrategyCard({ strategy }) {
    const navigate = useNavigate()

    // Format percentages
    const formatPct = (val) => {
        if (val === null || val === undefined) return 'N/A'
        const num = parseFloat(val)
        return (num > 0 ? '+' : '') + num.toFixed(2) + '%'
    }

    const alpha = strategy.alpha || 0
    const alphaColor = alpha > 0 ? 'text-green-600' : alpha < 0 ? 'text-red-600' : 'text-muted-foreground'

    return (
        <Card
            className="cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => navigate(`/strategies/${strategy.id}`)}
        >
            <CardHeader className="pb-3">
                <div className="flex justify-between items-start">
                    <div>
                        <CardTitle className="text-lg font-semibold">{strategy.name}</CardTitle>
                        <CardDescription className="flex items-center gap-1 mt-1">
                            <Folder className="h-3 w-3" />
                            {strategy.portfolio_name}
                        </CardDescription>
                    </div>
                    <Badge variant={strategy.enabled ? "success" : "secondary"}>
                        {strategy.enabled ? 'Active' : 'Paused'}
                    </Badge>
                </div>
            </CardHeader>
            <CardContent>
                <div className="space-y-4">
                    {/* Performance Summary */}
                    <div className="grid grid-cols-2 gap-4 text-sm">
                        <div className="space-y-1">
                            <span className="text-muted-foreground text-xs">Returns</span>
                            <div className="font-medium flex items-center">
                                {formatPct(strategy.portfolio_return_pct)}
                            </div>
                        </div>
                        <div className="space-y-1">
                            <span className="text-muted-foreground text-xs">Alpha vs SPY</span>
                            <div className={`font-medium flex items-center ${alphaColor}`}>
                                {alpha > 0 ? <TrendingUp className="h-3 w-3 mr-1" /> : <TrendingDown className="h-3 w-3 mr-1" />}
                                {formatPct(alpha)}
                            </div>
                        </div>
                    </div>

                    <div className="pt-2 border-t flex flex-col gap-2">
                        <div className="flex justify-between text-xs">
                            <span className="text-muted-foreground">Last Run</span>
                            <span className="font-medium">
                                {strategy.last_run_date
                                    ? format(new Date(strategy.last_run_date), 'MMM d, h:mm a')
                                    : 'Never'}
                            </span>
                        </div>
                        {strategy.last_run_status && (
                            <div className="flex justify-between text-xs">
                                <span className="text-muted-foreground">Status</span>
                                <Badge variant="outline" className="text-[10px] h-5 capitalize">
                                    {strategy.last_run_status}
                                </Badge>
                            </div>
                        )}
                    </div>
                </div>
            </CardContent>
            <CardFooter className="bg-muted/30 p-3">
                <Button
                    variant="ghost"
                    className="w-full h-8 text-xs text-muted-foreground hover:text-primary"
                >
                    View Details
                </Button>
            </CardFooter>
        </Card>
    )
}

export default Strategies
