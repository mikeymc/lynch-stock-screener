import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import StatusBar from "./StatusBar"

export default function StockOverview({ stock }) {
    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            {/* Top Row: Financial & Growth Metrics */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">

                {/* Valuation & Financial Health */}
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-lg font-medium text-muted-foreground">Valuation & Financials</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-2 gap-y-6 gap-x-4">
                            <div>
                                <div className="text-sm text-muted-foreground mb-1">P/E Ratio</div>
                                <div className={`text-2xl font-bold ${stock.pe_ratio < 15 ? "text-green-500" : ""}`}>
                                    {typeof stock.pe_ratio === 'number' ? stock.pe_ratio.toFixed(2) : '-'}
                                </div>
                            </div>
                            <div>
                                <div className="text-sm text-muted-foreground mb-1">PEG Ratio</div>
                                <div className={`text-2xl font-bold ${stock.peg_ratio < 1 ? "text-green-500" : ""}`}>
                                    {typeof stock.peg_ratio === 'number' ? stock.peg_ratio.toFixed(2) : '-'}
                                </div>
                            </div>
                            <div>
                                <div className="text-sm text-muted-foreground mb-1">Debt/Equity</div>
                                <div className={`text-2xl font-bold ${stock.debt_to_equity < 1 ? "text-green-500" : ""}`}>
                                    {typeof stock.debt_to_equity === 'number' ? stock.debt_to_equity.toFixed(2) : '-'}
                                </div>
                            </div>
                            <div>
                                <div className="text-sm text-muted-foreground mb-1">Div Yield</div>
                                <div className="text-2xl font-bold">
                                    {typeof stock.dividend_yield === 'number' ? `${stock.dividend_yield.toFixed(2)}%` : '-'}
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Growth & Ownership */}
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-lg font-medium text-muted-foreground">Growth & Ownership</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-2 gap-y-6 gap-x-4">
                            <div className="col-span-2 sm:col-span-1">
                                <div className="text-sm text-muted-foreground mb-1">Inst. Ownership</div>
                                <div className="text-2xl font-bold">
                                    {typeof stock.institutional_ownership === 'number'
                                        ? `${(stock.institutional_ownership * 100).toFixed(1)}%`
                                        : '-'}
                                </div>
                            </div>
                            <div>
                                <div className="text-sm text-muted-foreground mb-1">5Y Rev Growth</div>
                                <div className={`text-2xl font-bold ${stock.revenue_cagr > 10 ? 'text-green-500' : ''}`}>
                                    {typeof stock.revenue_cagr === 'number' ? `${stock.revenue_cagr.toFixed(1)}%` : '-'}
                                </div>
                            </div>
                            <div>
                                <div className="text-sm text-muted-foreground mb-1">5Y Inc Growth</div>
                                <div className={`text-2xl font-bold ${stock.earnings_cagr > 10 ? 'text-green-500' : ''}`}>
                                    {typeof stock.earnings_cagr === 'number' ? `${stock.earnings_cagr.toFixed(1)}%` : '-'}
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Bottom Row: Performance Consistency */}
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-6">
                <Card>
                    <CardContent className="pt-6">
                        <div className="text-sm font-medium text-muted-foreground mb-4">P/E Range (52W)</div>
                        <div className="h-4 mb-2">
                            <StatusBar
                                metricType="pe_range"
                                score={stock.pe_52_week_position || 0}
                                status="Current Position"
                                value={`${stock.pe_52_week_position?.toFixed(0)}%`}
                            />
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">
                            Position within 52-week P/E range. Lower is generally better.
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardContent className="pt-6">
                        <div className="text-sm font-medium text-muted-foreground mb-4">Revenue Consistency</div>
                        <div className="h-4 mb-2">
                            <StatusBar
                                metricType="revenue_consistency"
                                score={stock.revenue_consistency_score || 0}
                                status="Consistency Score"
                                value={`${stock.revenue_consistency_score?.toFixed(0)}%`}
                            />
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">
                            Based on steady 5-year growth trajectory.
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardContent className="pt-6">
                        <div className="text-sm font-medium text-muted-foreground mb-4">Income Consistency</div>
                        <div className="h-4 mb-2">
                            <StatusBar
                                metricType="income_consistency"
                                score={stock.income_consistency_score || 0}
                                status="Consistency Score"
                                value={`${stock.income_consistency_score?.toFixed(0)}%`}
                            />
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">
                            Based on steady 5-year earnings growth.
                        </p>
                    </CardContent>
                </Card>
            </div>

            {/* Sector Info */}
            <Card>
                <CardContent className="pt-6 flex items-center gap-4 text-sm">
                    <span className="text-muted-foreground">Sector:</span>
                    <span className="font-medium bg-muted px-2 py-1 rounded">{stock.sector || 'N/A'}</span>
                    <span className="text-muted-foreground ml-4">Industry:</span>
                    <span className="font-medium bg-muted px-2 py-1 rounded">{stock.industry || 'N/A'}</span>
                </CardContent>
            </Card>
        </div>
    )
}
