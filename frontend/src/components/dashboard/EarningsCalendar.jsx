// ABOUTME: Upcoming earnings calendar for stocks in watchlist and portfolios
// ABOUTME: Shows next 10 earnings dates within 2-week lookahead window

import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Calendar, Clock, Zap } from 'lucide-react'
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip"

export default function EarningsCalendar() {
    const navigate = useNavigate()
    const [earningsData, setEarningsData] = useState({ earnings: [], total_count: 0 })
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        const fetchEarnings = async () => {
            try {
                setLoading(true)
                const response = await fetch('/api/dashboard/earnings')
                if (response.ok) {
                    const data = await response.json()
                    setEarningsData(data.upcoming_earnings || { earnings: [], total_count: 0 })
                } else {
                    setError('Failed to load earnings calendar')
                }
            } catch (err) {
                console.error('Error fetching earnings:', err)
                setError('Failed to load earnings calendar')
            } finally {
                setLoading(false)
            }
        }

        fetchEarnings()
    }, [])

    const { earnings = [], total_count = 0 } = earningsData
    const moreCount = total_count - earnings.length

    return (
        <Card>
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                        <Calendar className="h-4 w-4" />
                        Earnings Calendar
                    </CardTitle>
                    <Link
                        to="/earnings"
                        className="text-xs text-primary hover:underline flex items-center gap-1 transition-colors"
                    >
                        view calendar
                        <span className="text-[10px]">→</span>
                    </Link>
                </div>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <Skeleton className="h-24 w-full" />
                ) : error ? (
                    <div className="h-24 flex items-center justify-center text-sm text-muted-foreground border border-dashed rounded-lg bg-muted/20">
                        {error}
                    </div>
                ) : earnings.length > 0 ? (
                    <div className="space-y-0">
                        {earnings.map(item => (
                            <EarningsRow
                                key={item.symbol}
                                item={item}
                                onClick={() => navigate(`/stock/${item.symbol}`)}
                            />
                        ))}
                        {moreCount > 0 && (
                            <div className="pt-2 pb-1 text-center border-t border-border mt-1">
                                <span className="text-xs text-muted-foreground italic">
                                    +{moreCount} more in the next two weeks
                                </span>
                            </div>
                        )}
                    </div>
                ) : (
                    <EmptyState />
                )}
            </CardContent>
        </Card>
    )
}

function EarningsRow({ item, onClick }) {
    const daysUntil = item.days_until
    const isToday = daysUntil === 0
    const isTomorrow = daysUntil === 1
    const isThisWeek = daysUntil <= 7

    return (
        <button
            onClick={onClick}
            className="w-full flex items-center justify-between py-0.5 px-2 rounded hover:bg-accent transition-colors text-left"
        >
            <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{item.symbol}</span>
                    <span className="text-xs text-muted-foreground truncate">
                        {item.company_name}
                    </span>
                    {item.has_8k && (
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <div className="flex items-center">
                                        <Zap className="h-3 w-3 text-amber-500 fill-amber-500 animate-pulse" />
                                    </div>
                                </TooltipTrigger>
                                <TooltipContent>
                                    <p>8-K (Item 2.02) filed on earnings date - Fresh data available</p>
                                </TooltipContent>
                            </Tooltip>
                        </TooltipProvider>
                    )}
                </div>
            </div>
            <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">
                    {formatDate(item.earnings_date)}
                </span>
                <Badge
                    variant={isToday ? 'destructive' : isTomorrow ? 'default' : isThisWeek ? 'secondary' : 'outline'}
                    className="text-xs"
                >
                    {isToday ? 'Today' : isTomorrow ? 'Tomorrow' : `${daysUntil}d`}
                </Badge>
            </div>
        </button>
    )
}

function formatDate(dateStr) {
    if (!dateStr) return ''
    const [year, month, day] = dateStr.split('-').map(Number)
    const date = new Date(year, month - 1, day)
    return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric'
    })
}

function EmptyState() {
    return (
        <div className="flex flex-col items-center justify-center py-6 text-center">
            <Calendar className="h-8 w-8 text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground">
                No upcoming earnings in the next 2 weeks
            </p>
            <p className="text-xs text-muted-foreground mt-1">
                Add stocks to your watchlist or portfolios to see their earnings dates
            </p>
        </div>
    )
}
