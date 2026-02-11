// ABOUTME: Dashboard landing page with market overview and personalized user data
// ABOUTME: Combines index charts, market movers, portfolio/watchlist summaries, and earnings calendar

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from "@/components/ui/button"
import { RefreshCw } from 'lucide-react'
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

            {/* Inline error banner */}
            {error && (
                <div className="flex items-center justify-between rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-2 text-sm text-destructive">
                    <span>{error}</span>
                    <Button variant="ghost" size="sm" onClick={fetchDashboardData} className="h-auto p-0 text-destructive hover:text-destructive">
                        Try again
                    </Button>
                </div>
            )}

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
                    loading={loading}
                />
                <WatchlistQuickView
                    watchlist={watchlist}
                    onNavigate={() => navigate('/')}
                    loading={loading}
                />
            </div>

            {/* Row 3: Activity & Strategy */}
            <div className="grid gap-6 md:grid-cols-2">
                <AlertsSummary
                    alerts={alerts}
                    onNavigate={() => navigate('/alerts')}
                    loading={loading}
                />
                <StrategiesSummary
                    strategies={strategies}
                    onNavigate={() => navigate('/strategies')}
                    loading={loading}
                />
            </div>

            {/* Row 4: Earnings & News */}
            <div className="grid gap-6 md:grid-cols-2">
                <EarningsCalendar earnings={upcoming_earnings} loading={loading} />
                <NewsFeed articles={news} loading={loading} />
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
