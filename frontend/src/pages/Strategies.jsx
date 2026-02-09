import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, TrendingUp, TrendingDown, Activity, Calendar, PlayCircle, Folder } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { format } from 'date-fns'

import StrategyWizard from '@/components/strategies/StrategyWizard'
import StrategyCard from '@/components/StrategyCard'

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

export default Strategies
