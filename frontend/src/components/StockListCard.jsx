import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useNavigate } from "react-router-dom"
import StatusBar from "./StatusBar"

export default function StockListCard({ stock, toggleWatchlist, watchlist }) {
    const navigate = useNavigate()
    const isWatchlisted = watchlist?.has(stock.symbol)

    return (
        <Card
            className="cursor-pointer hover:border-primary/50 transition-colors w-full"
            onClick={() => navigate(`/stock/${stock.symbol}`)}
        >
            <CardContent className="p-4">
                <div className="grid gap-4">
                    {/* Row 1: Header - Symbol, Name, Watchlist */}
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3 overflow-hidden">
                            <h3 className="text-xl font-bold min-w-[3.5rem]">{stock.symbol}</h3>
                            <span className="text-sm text-muted-foreground truncate max-w-[200px] md:max-w-[400px]" title={stock.company_name}>
                                {stock.company_name || stock.company}
                            </span>
                        </div>
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 -mr-2 shrink-0 hover:bg-transparent"
                            onClick={(e) => {
                                e.stopPropagation()
                                toggleWatchlist(stock.symbol)
                            }}
                        >
                            <span className={`text-lg ${isWatchlisted ? 'opacity-100' : 'opacity-30 hover:opacity-100'}`}>
                                {isWatchlisted ? '⭐' : '☆'}
                            </span>
                        </Button>
                    </div>

                    {/* Row 2: Primary Metrics - Price, Market Cap, Sector, Status */}
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 pb-2 border-b">
                        <div>
                            <div className="text-xs text-muted-foreground">Price</div>
                            <div className="font-semibold text-base">${stock.price?.toFixed(2) ?? 'N/A'}</div>
                        </div>
                        <div>
                            <div className="text-xs text-muted-foreground">Market Cap</div>
                            <div className="font-semibold text-base">
                                {typeof stock.market_cap === 'number'
                                    ? `$${(stock.market_cap / 1e9).toFixed(2)}B`
                                    : (stock.market_cap || 'N/A')}
                            </div>
                        </div>
                        <div>
                            <div className="text-xs text-muted-foreground">Sector</div>
                            <div className="font-medium text-sm truncate" title={stock.sector}>{stock.sector || 'N/A'}</div>
                        </div>
                        <div className="flex items-center lg:justify-end">
                            <Badge
                                variant="default"
                                className={
                                    stock.overall_status === 'Excellent' || stock.overall_status === 'STRONG_BUY'
                                        ? 'bg-green-600 hover:bg-green-700 text-white'
                                        : stock.overall_status === 'Good' || stock.overall_status === 'BUY'
                                            ? 'bg-blue-600 hover:bg-blue-700 text-white'
                                            : stock.overall_status === 'Fair' || stock.overall_status === 'HOLD'
                                                ? 'bg-yellow-600 hover:bg-yellow-700 text-white'
                                                : stock.overall_status === 'Weak' || stock.overall_status === 'CAUTION'
                                                    ? 'bg-orange-600 hover:bg-orange-700 text-white'
                                                    : stock.overall_status === 'Poor' || stock.overall_status === 'AVOID'
                                                        ? 'bg-red-600 hover:bg-red-700 text-white'
                                                        : 'bg-zinc-600 hover:bg-zinc-700 text-white'
                                }
                            >
                                {stock.overall_status === 'STRONG_BUY' ? 'Excellent' :
                                    stock.overall_status === 'BUY' ? 'Good' :
                                        stock.overall_status === 'HOLD' ? 'Fair' :
                                            stock.overall_status === 'CAUTION' ? 'Weak' :
                                                stock.overall_status === 'AVOID' ? 'Poor' :
                                                    stock.overall_status || 'N/A'}
                            </Badge>
                        </div>
                    </div>

                    {/* Row 3: Valuation & Financials */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                            <div className="text-xs text-muted-foreground">P/E Ratio</div>
                            <div className={stock.pe_ratio < 15 ? "text-green-600 font-medium" : ""}>
                                {typeof stock.pe_ratio === 'number' ? stock.pe_ratio.toFixed(2) : '-'}
                            </div>
                        </div>
                        <div>
                            <div className="text-xs text-muted-foreground">PEG Ratio</div>
                            <div className={stock.peg_ratio < 1 ? "text-green-600 font-medium" : ""}>
                                {typeof stock.peg_ratio === 'number' ? stock.peg_ratio.toFixed(2) : '-'}
                            </div>
                        </div>
                        <div>
                            <div className="text-xs text-muted-foreground">Debt/Equity</div>
                            <div className={stock.debt_to_equity < 1 ? "text-green-600 font-medium" : ""}>
                                {typeof stock.debt_to_equity === 'number' ? stock.debt_to_equity.toFixed(2) : '-'}
                            </div>
                        </div>
                        <div>
                            <div className="text-xs text-muted-foreground">Div Yield</div>
                            <div className="font-medium">
                                {typeof stock.dividend_yield === 'number' ? `${stock.dividend_yield.toFixed(2)}%` : '-'}
                            </div>
                        </div>
                    </div>

                    {/* Row 4: Growth & Ownership */}
                    <div className="grid grid-cols-3 gap-4 border-b pb-2">
                        <div>
                            <div className="text-xs text-muted-foreground">Inst. Own</div>
                            <div className="font-medium">
                                {typeof stock.institutional_ownership === 'number'
                                    ? `${(stock.institutional_ownership * 100).toFixed(1)}%`
                                    : '-'}
                            </div>
                        </div>
                        <div>
                            <div className="text-xs text-muted-foreground">5Y Rev Growth</div>
                            <div className={`font-medium ${stock.revenue_cagr > 10 ? 'text-green-600' : ''}`}>
                                {typeof stock.revenue_cagr === 'number' ? `${stock.revenue_cagr.toFixed(1)}%` : '-'}
                            </div>
                        </div>
                        <div>
                            <div className="text-xs text-muted-foreground">5Y Inc Growth</div>
                            <div className={`font-medium ${stock.earnings_cagr > 10 ? 'text-green-600' : ''}`}>
                                {typeof stock.earnings_cagr === 'number' ? `${stock.earnings_cagr.toFixed(1)}%` : '-'}
                            </div>
                        </div>
                    </div>

                    {/* Row 5: Charts (StatusBar) */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-1">
                        <div>
                            <div className="text-xs text-muted-foreground mb-1">P/E Range (TTM)</div>
                            <div className="h-2">
                                <StatusBar
                                    metricType="pe_range"
                                    score={stock.pe_52_week_position || 0}
                                    status="Current P/E Position"
                                    value={`${stock.pe_52_week_position?.toFixed(0)}%`}
                                />
                            </div>
                        </div>
                        <div>
                            <div className="text-xs text-muted-foreground mb-1">Rev Consistency (5Y)</div>
                            <div className="h-2">
                                <StatusBar
                                    metricType="revenue_consistency"
                                    score={stock.revenue_consistency_score || 0}
                                    status="Revenue Consistency"
                                    value={`${stock.revenue_consistency_score?.toFixed(0)}%`}
                                />
                            </div>
                        </div>
                        <div>
                            <div className="text-xs text-muted-foreground mb-1">Inc Consistency (5Y)</div>
                            <div className="h-2">
                                <StatusBar
                                    metricType="income_consistency"
                                    score={stock.income_consistency_score || 0}
                                    status="Income Consistency"
                                    value={`${stock.income_consistency_score?.toFixed(0)}%`}
                                />
                            </div>
                        </div>
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}
