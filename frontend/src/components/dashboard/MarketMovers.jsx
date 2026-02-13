// ABOUTME: Shows top gainers and losers from screened stocks
// ABOUTME: Supports period toggles for Today, Week, Month, Year

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { TrendingUp, TrendingDown } from 'lucide-react'
import { Badge } from "@/components/ui/badge"

const PERIODS = [
    { value: '1d', label: 'Today' },
    { value: '1w', label: 'Week' },
    { value: '1m', label: 'Month' },
    { value: 'ytd', label: 'YTD' }
]

export default function MarketMovers() {
    const navigate = useNavigate()
    const [period, setPeriod] = useState('1d')
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        const fetchMovers = async () => {
            setLoading(true)
            setError(null)
            try {
                const response = await fetch(`/api/market/movers?period=${period}&limit=5`)
                if (response.ok) {
                    const result = await response.json()
                    setData(result)
                } else {
                    setError('Failed to load market movers')
                }
            } catch (err) {
                console.error('Error fetching movers:', err)
                setError('Failed to load market movers')
            } finally {
                setLoading(false)
            }
        }

        fetchMovers()
    }, [period])

    return (
        <Card>
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-medium">Movers</CardTitle>
                    <div className="flex gap-1">
                        {PERIODS.map(p => (
                            <Button
                                key={p.value}
                                variant={period === p.value ? 'secondary' : 'ghost'}
                                size="sm"
                                className="h-7 px-2 text-xs"
                                onClick={() => setPeriod(p.value)}
                            >
                                {p.label}
                            </Button>
                        ))}
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <div className="space-y-3">
                        {[...Array(5)].map((_, i) => (
                            <Skeleton key={i} className="h-8 w-full" />
                        ))}
                    </div>
                ) : error ? (
                    <div className="h-48 flex items-center justify-center text-muted-foreground">
                        {error}
                    </div>
                ) : (
                    <div className="space-y-4">
                        {/* Gainers */}
                        <div>
                            <div className="flex items-center gap-1 text-xs text-muted-foreground mb-2">
                                <TrendingUp className="h-3 w-3 text-green-500" />
                                Top Gainers
                            </div>
                            <div className="space-y-1">
                                {data?.gainers?.map(stock => (
                                    <MoverRow
                                        key={stock.symbol}
                                        stock={stock}
                                        isGainer={true}
                                        onClick={() => navigate(`/stock/${stock.symbol}`)}
                                    />
                                ))}
                                {(!data?.gainers || data.gainers.length === 0) && (
                                    <p className="text-xs text-muted-foreground py-2">No data</p>
                                )}
                            </div>
                        </div>

                        {/* Losers */}
                        <div>
                            <div className="flex items-center gap-1 text-xs text-muted-foreground mb-2">
                                <TrendingDown className="h-3 w-3 text-red-500" />
                                Top Losers
                            </div>
                            <div className="space-y-1">
                                {data?.losers?.map(stock => (
                                    <MoverRow
                                        key={stock.symbol}
                                        stock={stock}
                                        isGainer={false}
                                        onClick={() => navigate(`/stock/${stock.symbol}`)}
                                    />
                                ))}
                                {(!data?.losers || data.losers.length === 0) && (
                                    <p className="text-xs text-muted-foreground py-2">No data</p>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

function MoverRow({ stock, isGainer, onClick }) {
    const changePct = stock.change_pct?.toFixed(2)
    const pe = stock.pe_ratio ? stock.pe_ratio.toFixed(1) : 'N/A'

    return (
        <button
            onClick={onClick}
            className="w-full flex items-center justify-between py-1 px-2 rounded hover:bg-accent transition-colors text-left"
        >
            <div className="flex items-center gap-2 min-w-0 flex-1 mr-2">
                <span className="font-medium text-sm shrink-0 w-12">{stock.symbol}</span>
                <span className="text-xs text-muted-foreground truncate">{stock.company_name}</span>
            </div>

            <div className="flex items-center gap-3 shrink-0">
                <div className="flex flex-col items-end w-10">
                    <span className="text-[10px] text-muted-foreground leading-none">P/E</span>
                    <span className="text-xs font-medium">{pe}</span>
                </div>

                <div className="flex items-center justify-end w-16">
                    <Badge
                        variant="default"
                        className={`text-[10px] px-1.5 py-0 ${stock.overall_status === 'Excellent' || stock.overall_status === 'STRONG_BUY'
                            ? 'bg-green-600 hover:bg-green-700'
                            : stock.overall_status === 'Good' || stock.overall_status === 'BUY'
                                ? 'bg-blue-600 hover:bg-blue-700'
                                : stock.overall_status === 'Fair' || stock.overall_status === 'HOLD'
                                    ? 'bg-yellow-600 hover:bg-yellow-700'
                                    : stock.overall_status === 'Weak' || stock.overall_status === 'CAUTION'
                                        ? 'bg-orange-600 hover:bg-orange-700'
                                        : stock.overall_status === 'Poor' || stock.overall_status === 'AVOID'
                                            ? 'bg-red-600 hover:bg-red-700'
                                            : 'bg-zinc-600 hover:bg-zinc-700'
                            } text-white whitespace-nowrap min-w-[50px] justify-center`}
                    >
                        {stock.overall_status === 'STRONG_BUY' ? 'Excellent' :
                            stock.overall_status === 'BUY' ? 'Good' :
                                stock.overall_status === 'HOLD' ? 'Fair' :
                                    stock.overall_status === 'CAUTION' ? 'Weak' :
                                        stock.overall_status === 'AVOID' ? 'Poor' :
                                            stock.overall_status || 'N/A'}
                    </Badge>
                </div>

                <div className={`flex items-center gap-1 text-sm font-medium w-16 justify-end ${isGainer ? 'text-green-500' : 'text-red-500'}`}>
                    {isGainer && '+'}{changePct}%
                </div>
            </div>
        </button>
    )
}
