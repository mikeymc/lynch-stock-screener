import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Calendar, Clock, Zap, ArrowLeft, Search } from 'lucide-react'
import { Input } from "@/components/ui/input"
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip"

export default function EarningsCalendarPage() {
    const navigate = useNavigate()
    const [earningsData, setEarningsData] = useState({ earnings: [], total_count: 0 })
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [searchQuery, setSearchQuery] = useState('')
    const [scope, setScope] = useState('user') // 'user' or 'all'

    useEffect(() => {
        const fetchEarnings = async () => {
            try {
                setLoading(true)
                // Fetch next 90 days of earnings with scope
                const response = await fetch(`/api/dashboard/earnings?days=90&scope=${scope}`)
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
    }, [scope])

    const filteredEarnings = earningsData.earnings.filter(item =>
        item.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.company_name.toLowerCase().includes(searchQuery.toLowerCase())
    )

    return (
        <div className="container mx-auto py-8 max-w-4xl space-y-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-6">
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight">Earnings Calendar</h1>
                        <p className="text-muted-foreground">Upcoming earnings (Next 90 Days)</p>
                    </div>
                </div>

                <div className="flex items-center gap-4">
                    <div className="flex bg-muted rounded-md p-1 min-w-fit">
                        <button
                            onClick={() => setScope('user')}
                            className={`px-3 py-1.5 text-xs font-medium rounded-sm transition-all ${scope === 'user'
                                    ? 'bg-background text-foreground shadow-sm'
                                    : 'text-muted-foreground hover:text-foreground'
                                }`}
                        >
                            My List
                        </button>
                        <button
                            onClick={() => setScope('all')}
                            className={`px-3 py-1.5 text-xs font-medium rounded-sm transition-all ${scope === 'all'
                                    ? 'bg-background text-foreground shadow-sm'
                                    : 'text-muted-foreground hover:text-foreground'
                                }`}
                        >
                            All Stocks
                        </button>
                    </div>

                    <div className="relative w-64">
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input
                            type="search"
                            placeholder="Search ticker or company..."
                            className="pl-8 bg-background"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                        />
                    </div>
                </div>
            </div>

            <Card className="border-none shadow-md bg-card/50 backdrop-blur-sm">
                <CardContent className="p-0">
                    {loading ? (
                        <div className="p-8 space-y-4">
                            {[1, 2, 3, 4, 5].map(i => (
                                <Skeleton key={i} className="h-12 w-full" />
                            ))}
                        </div>
                    ) : error ? (
                        <div className="p-12 text-center text-muted-foreground italic">
                            {error}
                        </div>
                    ) : filteredEarnings.length > 0 ? (
                        <div className="divide-y divide-border">
                            {/* Header Row */}
                            <div className="grid grid-cols-12 gap-4 px-6 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider bg-muted/30">
                                <div className="col-span-2">Ticker</div>
                                <div className="col-span-6">Company</div>
                                <div className="col-span-4 text-right">Earnings Date</div>
                            </div>

                            {/* Earnings Rows */}
                            {filteredEarnings.map(item => (
                                <button
                                    key={item.symbol}
                                    onClick={() => navigate(`/stock/${item.symbol}`)}
                                    className="grid grid-cols-12 gap-4 px-6 py-4 w-full items-center hover:bg-accent/50 transition-colors text-left group"
                                >
                                    <div className="col-span-2 font-bold text-primary group-hover:underline">
                                        {item.symbol}
                                    </div>
                                    <div className="col-span-6 flex items-center gap-2">
                                        <span className="truncate">{item.company_name}</span>
                                        {item.has_8k && (
                                            <TooltipProvider>
                                                <Tooltip>
                                                    <TooltipTrigger asChild>
                                                        <Zap className="h-3.5 w-3.5 text-amber-500 fill-amber-500 animate-pulse" />
                                                    </TooltipTrigger>
                                                    <TooltipContent>
                                                        <p>8-K (Item 2.02) filed - Results available</p>
                                                    </TooltipContent>
                                                </Tooltip>
                                            </TooltipProvider>
                                        )}
                                    </div>
                                    <div className="col-span-4 flex items-center justify-end gap-3 text-right">
                                        <span className="text-sm">
                                            {formatDate(item.earnings_date)}
                                        </span>
                                        <Badge
                                            variant={getVariant(item.days_until)}
                                            className="min-w-[80px] justify-center"
                                        >
                                            {formatDaysUntil(item.days_until)}
                                        </Badge>
                                    </div>
                                </button>
                            ))}
                        </div>
                    ) : (
                        <div className="p-12 text-center flex flex-col items-center gap-3">
                            <Calendar className="h-12 w-12 text-muted-foreground/30" />
                            <p className="text-muted-foreground">No earnings found for the current search/filters.</p>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}

function getVariant(days) {
    if (days === 0) return 'destructive'
    if (days === 1) return 'default'
    if (days <= 7) return 'secondary'
    return 'outline'
}

function formatDaysUntil(days) {
    if (days === 0) return 'Today'
    if (days === 1) return 'Tomorrow'
    return `In ${days} days`
}

function formatDate(dateStr) {
    if (!dateStr) return ''
    const [year, month, day] = dateStr.split('-').map(Number)
    const date = new Date(year, month - 1, day)
    return date.toLocaleDateString('en-US', {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        year: 'numeric'
    })
}
