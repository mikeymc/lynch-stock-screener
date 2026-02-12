// ABOUTME: Upcoming earnings calendar for stocks in watchlist and portfolios
// ABOUTME: Shows next 10 earnings dates within 2-week lookahead window

import { useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Calendar, Clock } from 'lucide-react'

export default function EarningsCalendar({ earnings = [], totalCount = 0, loading = false }) {
    const navigate = useNavigate()
    const moreCount = totalCount - earnings.length

    return (
        <Card>
            <CardHeader className="pb-2">
                <CardTitle className="text-base font-medium flex items-center gap-2">
                    <Calendar className="h-4 w-4" />
                    Earnings Calendar
                </CardTitle>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <Skeleton className="h-24 w-full" />
                ) : earnings.length > 0 ? (
                    <div className="space-y-1">
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
            className="w-full flex items-center justify-between py-2 px-2 rounded hover:bg-accent transition-colors text-left"
        >
            <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{item.symbol}</span>
                    <span className="text-xs text-muted-foreground truncate">
                        {item.company_name}
                    </span>
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
