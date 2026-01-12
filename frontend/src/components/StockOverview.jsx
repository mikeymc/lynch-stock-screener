import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import StatusBar from "./StatusBar"

// Character-specific metric configurations for stock overview
const CHARACTER_METRICS = {
  lynch: {
    valuation: [
      { key: 'pe_ratio', label: 'P/E Ratio', format: 'number', decimals: 2, goodWhen: v => v < 15 },
      { key: 'peg_ratio', label: 'PEG Ratio', format: 'number', decimals: 2, goodWhen: v => v < 1 },
      { key: 'debt_to_equity', label: 'Debt/Equity', format: 'number', decimals: 2, goodWhen: v => v < 1 },
      { key: 'dividend_yield', label: 'Div Yield', format: 'percent', decimals: 2 },
    ],
    growth: [
      { key: 'institutional_ownership', label: 'Inst. Ownership', format: 'percent_decimal', decimals: 1, colSpan: 'col-span-2 sm:col-span-1' },
      { key: 'revenue_cagr', label: '5Y Rev Growth', format: 'percent', decimals: 1, goodWhen: v => v > 10 },
      { key: 'earnings_cagr', label: '5Y Inc Growth', format: 'percent', decimals: 1, goodWhen: v => v > 10 },
    ]
  },
  buffett: {
    valuation: [
      { key: 'pe_ratio', label: 'P/E Ratio', format: 'number', decimals: 2, goodWhen: v => v < 15 },
      { key: 'roe', label: 'ROE', format: 'percent', decimals: 2, goodWhen: v => v > 15 },
      { key: 'debt_to_earnings', label: 'Debt/Earnings', format: 'years', decimals: 2, goodWhen: v => v < 4 },
      { key: 'dividend_yield', label: 'Div Yield', format: 'percent', decimals: 2 },
    ],
    growth: [
      { key: 'owner_earnings', label: 'Owner Earnings', format: 'currency', decimals: 1, colSpan: 'col-span-2 sm:col-span-1' },
      { key: 'revenue_cagr', label: '5Y Rev Growth', format: 'percent', decimals: 1, goodWhen: v => v > 10 },
      { key: 'earnings_cagr', label: '5Y Inc Growth', format: 'percent', decimals: 1, goodWhen: v => v > 10 },
    ]
  }
};

const formatValue = (value, format, decimals) => {
  if (typeof value !== 'number') return '-';

  switch (format) {
    case 'percent':
      return `${value.toFixed(decimals)}%`;
    case 'percent_decimal':
      return `${(value * 100).toFixed(decimals)}%`;
    case 'currency':
      // Convert to billions if >= 1000M, otherwise keep in millions
      if (value >= 1000) {
        return `$${(value / 1000).toFixed(2)}B`;
      }
      return `$${value.toFixed(1)}M`;
    case 'years':
      return `${value.toFixed(decimals)} yrs`;
    case 'number':
    default:
      return value.toFixed(decimals);
  }
};

export default function StockOverview({ stock, activeCharacter = 'lynch' }) {
    const metrics = CHARACTER_METRICS[activeCharacter] || CHARACTER_METRICS.lynch;

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
                            {metrics.valuation.map(metric => {
                                const value = stock[metric.key];
                                const isGood = metric.goodWhen && typeof value === 'number' && metric.goodWhen(value);
                                return (
                                    <div key={metric.key}>
                                        <div className="text-sm text-muted-foreground mb-1">{metric.label}</div>
                                        <div className={`text-2xl font-bold ${isGood ? "text-green-500" : ""}`}>
                                            {formatValue(value, metric.format, metric.decimals)}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </CardContent>
                </Card>

                {/* Growth & Ownership */}
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-lg font-medium text-muted-foreground">Growth & Performance</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-2 gap-y-6 gap-x-4">
                            {metrics.growth.map(metric => {
                                const value = stock[metric.key];
                                const isGood = metric.goodWhen && typeof value === 'number' && metric.goodWhen(value);
                                return (
                                    <div key={metric.key} className={metric.colSpan || ''}>
                                        <div className="text-sm text-muted-foreground mb-1">{metric.label}</div>
                                        <div className={`text-2xl font-bold ${isGood ? 'text-green-500' : ''}`}>
                                            {formatValue(value, metric.format, metric.decimals)}
                                        </div>
                                    </div>
                                );
                            })}
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
