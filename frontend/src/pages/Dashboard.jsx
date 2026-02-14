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
import EarningsCalendar from '@/components/dashboard/EarningsCalendar'
import NewsFeed from '@/components/dashboard/NewsFeed'
import NewTheses from '@/components/dashboard/NewTheses'
import { useAuth } from '@/context/AuthContext'

const AUTO_REFRESH_INTERVAL = 5 * 60 * 1000 // 5 minutes

export default function Dashboard({ activeCharacter }) {
    const navigate = useNavigate()

    return (
        <div className="space-y-6">
            {/* Row 1: Market Overview & Portfolios */}
            <div className="grid gap-6 md:grid-cols-2">
                <IndexChart />
                <PortfolioSummaryCard onNavigate={() => navigate('/portfolios')} />
            </div>

            {/* Row 2: Watchlist & Alerts */}
            <div className="grid gap-6 md:grid-cols-2">
                <WatchlistQuickView onNavigate={() => navigate('/')} />
                <AlertsSummary onNavigate={() => navigate('/alerts')} />
            </div>

            {/* Row 3: Earnings & Recent Theses */}
            <div className="grid gap-6 md:grid-cols-2">
                <EarningsCalendar />
                <NewTheses />
                {/* <NewsFeed /> */}
            </div>

            {/* Row 4: Market Movers */}
            <div className="grid gap-6">
                <MarketMovers activeCharacter={activeCharacter} />
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
