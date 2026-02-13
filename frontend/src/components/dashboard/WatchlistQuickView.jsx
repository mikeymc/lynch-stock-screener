// ABOUTME: Quick view of watchlist stocks with prices and daily change
// ABOUTME: Shows CTA to add stocks if watchlist is empty

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Star, Plus, ArrowRight, TrendingUp, TrendingDown } from 'lucide-react'

export default function WatchlistQuickView({ onNavigate }) {
    const navigate = useNavigate()
    const [watchlist, setWatchlist] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        const fetchWatchlist = async () => {
            try {
                setLoading(true)
                const response = await fetch('/api/dashboard/watchlist')
                if (response.ok) {
                    const data = await response.json()
                    setWatchlist(data.watchlist || [])
                } else {
                    setError('Failed to load watchlist')
                }
            } catch (err) {
                console.error('Error fetching watchlist:', err)
                setError('Failed to load watchlist')
            } finally {
                setLoading(false)
            }
        }

        fetchWatchlist()
    }, [])

    const hasItems = watchlist.length > 0

    return (
        <Card>
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                        <Star className="h-4 w-4" />
                        Watchlist
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
                ) : hasItems ? (
                    <div className="space-y-0">
                        {watchlist.slice(0, 5).map(stock => (
                            <WatchlistRow
                                key={stock.symbol}
                                stock={stock}
                                onClick={() => navigate(`/stock/${stock.symbol}`)}
                            />
                        ))}
                        {watchlist.length > 5 && (
                            <p className="text-xs text-muted-foreground text-center pt-2">
                                +{watchlist.length - 5} more stocks
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

function WatchlistRow({ stock, onClick }) {
    const isPositive = (stock.price_change_pct || 0) >= 0
    const changePct = stock.price_change_pct?.toFixed(2) || '0.00'

    return (
        <button
            onClick={onClick}
            className="w-full flex items-center justify-between py-0.5 px-2 rounded hover:bg-accent transition-colors text-left"
        >
            <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{stock.symbol}</span>
                    <span className="text-xs text-muted-foreground truncate">
                        {stock.company_name}
                    </span>
                </div>
            </div>
            <div className="flex items-center gap-3">
                <div className="flex flex-col items-end min-w-[75px]">
                    <span className="text-sm font-bold">
                        ${stock.price?.toFixed(2) || '—'}
                    </span>
                    <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">Price</span>
                </div>
                <div className="flex flex-col items-end min-w-[60px]">
                    <div className={`flex items-center gap-1 text-sm font-bold ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
                        {isPositive ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                        {isPositive && '+'}{changePct}%
                    </div>
                    <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">Change</span>
                </div>
            </div>
        </button>
    )
}

function EmptyState({ onNavigate }) {
    return (
        <div className="flex flex-col items-center justify-center py-6 text-center">
            <Star className="h-8 w-8 text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground mb-3">
                Add stocks to track their performance
            </p>
            <Button onClick={onNavigate} size="sm">
                <Plus className="h-4 w-4 mr-1" />
                Browse Stocks
            </Button>
        </div>
    )
}
