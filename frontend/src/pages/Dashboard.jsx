// ABOUTME: Dashboard landing page with market overview and personalized user data
// ABOUTME: Combines index charts, market movers, portfolio/watchlist summaries, and earnings calendar

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Badge } from "@/components/ui/badge"
import {
    TrendingUp,
    TrendingDown,
    Briefcase,
    Star,
    Bell,
    Zap,
    Calendar,
    Newspaper,
    Plus,
    ArrowRight,
    ExternalLink,
    RefreshCw
} from 'lucide-react'
import IndexChart from '@/components/dashboard/IndexChart'
import MarketMovers from '@/components/dashboard/MarketMovers'
import PortfolioSummaryCard from '@/components/dashboard/PortfolioSummaryCard'
import WatchlistQuickView from '@/components/dashboard/WatchlistQuickView'
import AlertsSummary from '@/components/dashboard/AlertsSummary'
import StrategiesSummary from '@/components/dashboard/StrategiesSummary'
import EarningsCalendar from '@/components/dashboard/EarningsCalendar'
import NewsFeed from '@/components/dashboard/NewsFeed'
import { useAuth } from '@/context/AuthContext'

const AUTO_REFRESH_INTERVAL = 5 * 60 * 1000 // 5 minutes

export default function Dashboard() {
    const { user } = useAuth()
    const navigate = useNavigate()
    const [dashboardData, setDashboardData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [lastRefresh, setLastRefresh] = useState(null)

    const fetchDashboardData = useCallback(async () => {
        try {
            setError(null)
            const response = await fetch('/api/dashboard', {
                credentials: 'include'
            })
            if (response.ok) {
                const data = await response.json()
                setDashboardData(data)
                setLastRefresh(new Date())
            } else if (response.status === 401) {
                setError('Please log in to view your dashboard')
            } else {
                throw new Error('Failed to load dashboard data')
            }
        } catch (err) {
            console.error('Error fetching dashboard:', err)
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchDashboardData()

        // Auto-refresh every 5 minutes
        const interval = setInterval(fetchDashboardData, AUTO_REFRESH_INTERVAL)
        return () => clearInterval(interval)
    }, [fetchDashboardData])

    if (loading) {
        return <DashboardSkeleton />
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center h-64 gap-4">
                <p className="text-muted-foreground">{error}</p>
                <Button onClick={fetchDashboardData} variant="outline">
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Try Again
                </Button>
            </div>
        )
    }

    const {
        portfolios = [],
        watchlist = [],
        alerts = {},
        strategies = [],
        upcoming_earnings = [],
        news = []
    } = dashboardData || {}

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
                    <p className="text-sm text-muted-foreground">
                        Welcome back{user?.name ? `, ${user.name.split(' ')[0]}` : ''}
                    </p>
                </div>
                {lastRefresh && (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={fetchDashboardData}
                        className="text-muted-foreground"
                    >
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Updated {formatTimeAgo(lastRefresh)}
                    </Button>
                )}
            </div>

            {/* Row 1: Market Overview */}
            <div className="grid gap-6 md:grid-cols-2">
                <IndexChart />
                <MarketMovers />
            </div>

            {/* Row 2: Personal Overview */}
            <div className="grid gap-6 md:grid-cols-2">
                <PortfolioSummaryCard
                    portfolios={portfolios}
                    onNavigate={() => navigate('/portfolios')}
                />
                <WatchlistQuickView
                    watchlist={watchlist}
                    onNavigate={() => navigate('/')}
                />
            </div>

            {/* Row 3: Activity & Strategy */}
            <div className="grid gap-6 md:grid-cols-2">
                <AlertsSummary
                    alerts={alerts}
                    onNavigate={() => navigate('/alerts')}
                />
                <StrategiesSummary
                    strategies={strategies}
                    onNavigate={() => navigate('/strategies')}
                />
            </div>

            {/* Row 4: Earnings & News */}
            <div className="grid gap-6 md:grid-cols-2">
                <EarningsCalendar earnings={upcoming_earnings} />
                <NewsFeed articles={news} />
            </div>
        </div>
    )
}

function DashboardSkeleton() {
    return (
        <div className="space-y-6">
            <div>
                <Skeleton className="h-8 w-48 mb-2" />
                <Skeleton className="h-4 w-32" />
            </div>

            <div className="grid gap-6 md:grid-cols-2">
                <Card>
                    <CardHeader>
                        <Skeleton className="h-5 w-32" />
                    </CardHeader>
                    <CardContent>
                        <Skeleton className="h-48 w-full" />
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader>
                        <Skeleton className="h-5 w-32" />
                    </CardHeader>
                    <CardContent>
                        <Skeleton className="h-48 w-full" />
                    </CardContent>
                </Card>
            </div>

            <div className="grid gap-6 md:grid-cols-2">
                <Card>
                    <CardHeader>
                        <Skeleton className="h-5 w-32" />
                    </CardHeader>
                    <CardContent>
                        <Skeleton className="h-24 w-full" />
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader>
                        <Skeleton className="h-5 w-32" />
                    </CardHeader>
                    <CardContent>
                        <Skeleton className="h-24 w-full" />
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}

function formatTimeAgo(date) {
    const seconds = Math.floor((new Date() - date) / 1000)
    if (seconds < 60) return 'just now'
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ago`
    const hours = Math.floor(minutes / 60)
    return `${hours}h ago`
}
