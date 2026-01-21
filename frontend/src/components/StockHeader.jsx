import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { formatLargeCurrency } from "../utils/formatters"

export default function StockHeader({ stock, toggleWatchlist, watchlist, className, onClick, flash = {} }) {
    const isWatchlisted = watchlist?.has(stock.symbol)

    return (
        <Card
            className={`w-full shrink-0 ${onClick ? 'cursor-pointer hover:bg-muted/50 transition-colors' : ''} ${className || ''}`}
            onClick={onClick}
        >
            <CardContent className="p-4 py-3 flex items-center justify-between gap-4">
                {/* Left: Identity */}
                <div className="flex items-center gap-4 min-w-0">
                    <div className="flex items-baseline gap-3 min-w-0">
                        <h1 className="text-2xl font-bold tracking-tight">{stock.symbol}</h1>
                        <span className="text-muted-foreground truncate hidden sm:inline-block" title={stock.company_name}>
                            {stock.company_name || stock.company}
                        </span>
                    </div>

                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 shrink-0 hover:bg-transparent -ml-2 text-muted-foreground hover:text-foreground"
                        onClick={(e) => {
                            e.stopPropagation()
                            toggleWatchlist(stock.symbol)
                        }}
                    >
                        <span className={`text-xl ${isWatchlisted ? 'text-yellow-500' : 'opacity-30 hover:opacity-100'}`}>
                            {isWatchlisted ? '★' : '☆'}
                        </span>
                    </Button>
                </div>

                {/* Right: Key Metrics & Status */}
                <div className="flex items-center gap-6 shrink-0">
                    <div className="text-right hidden sm:block">
                        <div className="text-sm font-medium text-muted-foreground">Price</div>
                        <div className={`font-bold text-lg leading-none rounded px-1 transition-colors duration-500 ${flash.price || ''}`}>
                            ${stock.price?.toFixed(2) ?? 'N/A'}
                        </div>
                    </div>

                    <div className="text-right hidden md:block">
                        <div className="text-sm font-medium text-muted-foreground">Market Cap</div>
                        <div className={`font-semibold leading-none rounded px-1 transition-colors duration-500 ${flash.market_cap || ''}`}>
                            {formatLargeCurrency(stock.market_cap)}
                        </div>
                    </div>

                    <Badge
                        variant="default"
                        className={`text-sm px-3 py-1 ${stock.overall_status === 'Excellent' || stock.overall_status === 'STRONG_BUY'
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
                            } text-white whitespace-nowrap`}
                    >
                        {stock.overall_status === 'STRONG_BUY' ? 'Excellent' :
                            stock.overall_status === 'BUY' ? 'Good' :
                                stock.overall_status === 'HOLD' ? 'Fair' :
                                    stock.overall_status === 'CAUTION' ? 'Weak' :
                                        stock.overall_status === 'AVOID' ? 'Poor' :
                                            stock.overall_status || 'N/A'}
                    </Badge>
                </div>
            </CardContent>
        </Card>
    )
}
