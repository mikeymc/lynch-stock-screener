
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { TrendingUp, TrendingDown, Trash2, Bot, User } from 'lucide-react'

// Format currency with commas and 2 decimal places
const formatCurrency = (value) => {
    if (value === null || value === undefined) return '$0.00'
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value)
}

// Format percentage with sign
const formatPercent = (value) => {
    if (value === null || value === undefined) return '0.00%'
    const sign = value >= 0 ? '+' : ''
    return `${sign}${value.toFixed(2)}%`
}

export default function PortfolioCard({ portfolio, onClick, onDelete }) {
    // Use pre-computed values from backend (now includes live prices)
    const totalValue = portfolio.total_value || portfolio.initial_cash || 100000
    const initialCash = portfolio.initial_cash || 100000
    const gainLoss = portfolio.gain_loss ?? (totalValue - initialCash)
    const gainLossPercent = portfolio.gain_loss_percent ?? (initialCash > 0 ? (gainLoss / initialCash) * 100 : 0)
    const isPositive = gainLoss >= 0

    return (
        <Card
            className="cursor-pointer transition-all hover:shadow-md hover:border-primary/30 group relative"
            onClick={onClick}
        >
            {onDelete && (
                <Button
                    variant="ghost"
                    size="icon"
                    className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity h-8 w-8 text-muted-foreground hover:text-destructive z-10"
                    onClick={(e) => {
                        e.stopPropagation()
                        onDelete()
                    }}
                >
                    <Trash2 className="h-4 w-4" />
                </Button>
            )}
            <CardHeader className="pb-2">
                <CardTitle className="text-lg font-semibold truncate pr-8">
                    {portfolio.name}
                </CardTitle>
                <CardDescription className="text-xs flex flex-col gap-1">
                    <span>Created {new Date(portfolio.created_at).toLocaleDateString()}</span>
                    {portfolio.user_email && (
                        <span className="text-muted-foreground/80 font-medium">User: {portfolio.user_email}</span>
                    )}
                    {portfolio.strategy_id ? (
                        <div className="flex items-center gap-1.5 mt-1">
                            <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-primary/30 text-primary font-medium flex items-center gap-1">
                                <Bot className="h-2.5 w-2.5" />
                                Autonomous
                            </Badge>
                            <Button
                                variant="link"
                                className="p-0 h-auto text-[10px] text-primary"
                                onClick={(e) => {
                                    e.stopPropagation()
                                    window.location.href = `/strategies/${portfolio.strategy_id}`
                                }}
                            >
                                Strategy Detail
                            </Button>
                        </div>
                    ) : (
                        <div className="flex items-center gap-1.5 mt-1">
                            <Badge variant="outline" className="text-[10px] h-4 px-1.5 text-muted-foreground font-medium flex items-center gap-1">
                                <User className="h-2.5 w-2.5" />
                                Self-Directed
                            </Badge>
                        </div>
                    )}
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="space-y-3">
                    <div>
                        <p className="text-2xl font-bold tracking-tight">
                            {formatCurrency(totalValue)}
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        <Badge
                            variant={isPositive ? "default" : "destructive"}
                            className={`${isPositive
                                ? 'bg-emerald-500/10 text-emerald-600 hover:bg-emerald-500/20 dark:bg-emerald-500/20 dark:text-emerald-400'
                                : 'bg-red-500/10 text-red-600 hover:bg-red-500/20 dark:bg-red-500/20 dark:text-red-400'
                                }`}
                        >
                            {isPositive ? (
                                <TrendingUp className="h-3 w-3 mr-1" />
                            ) : (
                                <TrendingDown className="h-3 w-3 mr-1" />
                            )}
                            {formatPercent(gainLossPercent)}
                        </Badge>
                        <span className={`text-sm ${isPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                            {formatCurrency(gainLoss)}
                        </span>
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}
