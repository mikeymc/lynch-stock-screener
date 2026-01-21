// ABOUTME: Displays stock data in card format with character-specific metrics
// ABOUTME: Swaps displayed metrics based on active character (Lynch vs Buffett)

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useNavigate } from "react-router-dom"
import StatusBar from "./StatusBar"
import { formatLargeCurrency } from "../utils/formatters"
import { useState, useEffect } from 'react'

// Metric configurations for each character
const CHARACTER_METRICS = {
    lynch: {
        row3: [
            { key: 'pe_ratio', label: 'P/E Ratio', format: 'ratio', goodWhen: v => v !== null && v < 15 },
            { key: 'peg_ratio', label: 'PEG Ratio', format: 'ratio', goodWhen: v => v !== null && v < 1 },
            { key: 'debt_to_equity', label: 'Debt/Equity', format: 'ratio', goodWhen: v => v !== null && v < 1 },
            { key: 'dividend_yield', label: 'Div Yield', format: 'percent' },
        ],
        row4: [
            { key: 'institutional_ownership', label: 'Inst. Own', format: 'ownership_percent' },
            { key: 'revenue_cagr', label: '5Y Rev Growth', format: 'percent', goodWhen: v => v !== null && v > 10 },
            { key: 'earnings_cagr', label: '5Y Inc Growth', format: 'percent', goodWhen: v => v !== null && v > 10 },
        ]
    },
    buffett: {
        row3: [
            { key: 'pe_ratio', label: 'P/E Ratio', format: 'ratio', goodWhen: v => v !== null && v < 15 },
            { key: 'roe', label: 'ROE', format: 'percent', goodWhen: v => v !== null && v > 15 },
            { key: 'debt_to_earnings', label: 'Debt/Earn (yrs)', format: 'years', goodWhen: v => v !== null && v < 4 },
            { key: 'dividend_yield', label: 'Div Yield', format: 'percent' },
        ],
        row4: [
            { key: 'gross_margin', label: 'Gross Margin', format: 'percent', goodWhen: v => v !== null && v > 40 },
            {
                key: 'owner_earnings',
                label: (
                    <>
                        <span className="hidden md:inline">Owner Earnings</span>
                        <span className="md:hidden">Owner Earn.</span>
                    </>
                ),
                format: 'currency_large'
            },
            { key: 'revenue_cagr', label: '5Y Rev Growth', format: 'percent', goodWhen: v => v !== null && v > 10 },
            { key: 'earnings_cagr', label: '5Y Inc Growth', format: 'percent', goodWhen: v => v !== null && v > 10 },
        ]
    }
}

// Format a metric value based on its type
function formatMetricValue(value, format) {
    if (value === null || value === undefined) return '-'

    switch (format) {
        case 'ratio':
            return typeof value === 'number' ? value.toFixed(2) : '-'
        case 'percent':
            return typeof value === 'number' ? `${value.toFixed(1)}%` : '-'
        case 'ownership_percent':
            // institutional_ownership comes as 0-1, needs *100
            return typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '-'
        case 'years':
            return typeof value === 'number' ? value.toFixed(1) : '-'
        case 'currency':
            return typeof value === 'number' ? `$${value.toFixed(2)}` : '-'
        case 'currency_large':
            return formatLargeCurrency(value)
        default:
            return typeof value === 'number' ? value.toFixed(2) : String(value)
    }
}

export default function StockListCard({ stock: initialStock, toggleWatchlist, watchlist, activeCharacter = 'lynch' }) {
    const navigate = useNavigate()
    const isWatchlisted = watchlist?.has(initialStock.symbol)

    // Local state to handle real-time updates
    const [stock, setStock] = useState(initialStock)
    const [flash, setFlash] = useState({}) // { price: 'animate-flash-green', ... }

    // Sync prop changes (e.g. parent re-render or new search)
    useEffect(() => {
        setStock(initialStock)
    }, [initialStock])

    // Listen for real-time updates
    useEffect(() => {
        const handleUpdate = (e) => {
            const updates = e.detail?.updates
            if (!updates) return

            // Find update for this stock
            const update = updates.find(u => u.symbol === stock.symbol)
            if (update) {
                // Determine which fields changed and set flash
                const newFlash = {}
                let hasChanges = false

                // Fields to check and animate
                const fieldsToCheck = ['price', 'pe_ratio', 'dividend_yield', 'market_cap', 'peg_ratio', 'forward_pe', 'forward_peg_ratio']

                fieldsToCheck.forEach(field => {
                    const newValue = update[field]
                    const oldValue = stock[field]

                    // Simple equality check, can be improved for floats
                    if (newValue !== undefined && newValue !== null && newValue !== oldValue) {
                        // Determine color based on diff (only for price mainly)
                        if (field === 'price') {
                            newFlash[field] = (newValue > oldValue) ? 'animate-flash-green' : 'animate-flash-red'
                        } else {
                            newFlash[field] = 'animate-flash-green'
                        }
                        hasChanges = true
                    }
                })

                if (hasChanges) {
                    setStock(prev => ({ ...prev, ...update }))
                    setFlash(newFlash)

                    // Clear flash after animation
                    setTimeout(() => setFlash({}), 2000)
                }
            }
        }

        window.addEventListener('price-updates', handleUpdate)
        return () => window.removeEventListener('price-updates', handleUpdate)
    }, [stock.symbol, stock]) // Dependency on stock needed for oldValue compariso

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
                            <div className={`font-semibold text-base px-1 rounded transition-colors ${flash.price || ''}`}>${stock.price?.toFixed(2) ?? 'N/A'}</div>
                        </div>
                        <div>
                            <div className="text-xs text-muted-foreground">Market Cap</div>
                            <div className={`font-semibold text-base px-1 rounded transition-colors ${flash.market_cap || ''}`}>
                                {formatLargeCurrency(stock.market_cap)}
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

                    {/* Row 3: Character-specific metrics */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        {CHARACTER_METRICS[activeCharacter]?.row3.map(metric => (
                            <div key={metric.key}>
                                <div className="text-xs text-muted-foreground">{metric.label}</div>
                                <div className={`${metric.goodWhen?.(stock[metric.key]) ? "text-green-600 font-medium" : "font-medium"} px-1 rounded transition-colors ${flash[metric.key] || ''}`}>
                                    {formatMetricValue(stock[metric.key], metric.format)}
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Row 4: Character-specific secondary metrics */}
                    <div className={`grid gap-4 border-b pb-2 ${activeCharacter === 'buffett' ? 'grid-cols-2 md:grid-cols-4' : 'grid-cols-3'}`}>
                        {CHARACTER_METRICS[activeCharacter]?.row4.map(metric => (
                            <div key={metric.key}>
                                <div className="text-xs text-muted-foreground">{metric.label}</div>
                                <div className={metric.goodWhen?.(stock[metric.key]) ? "text-green-600 font-medium" : "font-medium"}>
                                    {formatMetricValue(stock[metric.key], metric.format)}
                                </div>
                            </div>
                        ))}
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
