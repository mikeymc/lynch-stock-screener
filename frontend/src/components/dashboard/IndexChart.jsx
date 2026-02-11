// ABOUTME: Market index chart with selector for S&P 500, Nasdaq, Dow Jones
// ABOUTME: Shows price history with period toggles (1D, 1W, 1M, 3M, YTD, 1Y)

import { useState, useEffect, useMemo } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { TrendingUp, TrendingDown, Check } from 'lucide-react'
import { Line } from 'react-chartjs-2'
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Tooltip,
    Filler,
    Legend
} from 'chart.js'

ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Tooltip,
    Filler,
    Legend
)

// Plugin to draw a dashed zero line
const zeroLinePlugin = {
    id: 'zeroLine',
    beforeDraw: (chart) => {
        const ctx = chart.ctx;
        const yAxis = chart.scales.y;
        const xAxis = chart.scales.x;

        // Check if 0 is visible on the y-axis
        if (yAxis && yAxis.min <= 0 && yAxis.max >= 0) {
            const y = yAxis.getPixelForValue(0);

            ctx.save();
            ctx.beginPath();
            ctx.moveTo(xAxis.left, y);
            ctx.lineTo(xAxis.right, y);
            ctx.lineWidth = 1;
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
            ctx.setLineDash([6, 4]);
            ctx.stroke();
            ctx.restore();
        }
    }
};

const INDICES = [
    { symbol: '^GSPC', name: 'S&P 500', color: '#22c55e' },
    { symbol: '^IXIC', name: 'Nasdaq', color: '#3b82f6' },
    { symbol: '^DJI', name: 'Dow Jones', color: '#f97316' }
]

const PERIODS = [
    { value: '1d', label: '1D' },
    { value: '5d', label: '1W' },
    { value: '1mo', label: '1M' },
    { value: '3mo', label: '3M' },
    { value: 'ytd', label: 'YTD' },
    { value: '1y', label: '1Y' }
]

export default function IndexChart() {
    const [selectedSymbols, setSelectedSymbols] = useState(['^GSPC'])
    const [selectedPeriod, setSelectedPeriod] = useState('1mo')
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const toggleSymbol = (symbol) => {
        setSelectedSymbols(prev => {
            if (prev.includes(symbol)) {
                if (prev.length === 1) return prev // Keep at least one
                return prev.filter(s => s !== symbol)
            }
            return [...prev, symbol]
        })
    }

    useEffect(() => {
        const controller = new AbortController()

        const fetchIndexData = async () => {
            if (selectedSymbols.length === 0) {
                setData(null)
                setLoading(false)
                return
            }

            setLoading(true)
            setError(null)
            try {
                const symbols = INDICES.map(idx => idx.symbol).join(',')
                const response = await fetch(`/api/market/index/${symbols}?period=${selectedPeriod}`, {
                    signal: controller.signal
                })
                if (response.ok) {
                    const result = await response.json()
                    setData(result)
                } else {
                    const err = await response.json()
                    setError(err.error || 'Failed to load index data')
                }
            } catch (err) {
                if (err.name === 'AbortError') return
                console.error('Error fetching index:', err)
                setError('Failed to load index data')
            } finally {
                if (!controller.signal.aborted) setLoading(false)
            }
        }

        fetchIndexData()
        return () => controller.abort()
    }, [selectedSymbols, selectedPeriod])

    const chartData = useMemo(() => {
        if (!data) return null

        // Detect data shape: single symbol vs multi-symbol dictionary
        const isSingleSymbolResponse = data && typeof data === 'object' && 'symbol' in data
        const datasetsMap = isSingleSymbolResponse
            ? { [data.symbol]: data }
            : data

        // Only process keys that are selected AND have valid data
        const symbols = Object.keys(datasetsMap).filter(s =>
            selectedSymbols.includes(s) &&
            datasetsMap[s] &&
            !datasetsMap[s].error &&
            Array.isArray(datasetsMap[s].data)
        )

        if (symbols.length === 0) return null

        // Use the first symbol's data for labels
        const firstSymbol = symbols[0]
        const labels = datasetsMap[firstSymbol].data.map(d => formatLabel(d.timestamp, selectedPeriod))

        const datasets = symbols.map(symbol => {
            const indexInfo = INDICES.find(i => i.symbol === symbol)
            const symbolData = datasetsMap[symbol]
            const rawData = symbolData.data.map(d => d.close)

            // Normalize if we have multiple indices
            const isMulti = symbols.length > 1
            const firstVal = rawData[0] || 1
            const processedData = isMulti
                ? rawData.map(v => ((v - firstVal) / firstVal) * 100)
                : rawData

            return {
                label: indexInfo.name,
                data: processedData,
                borderColor: indexInfo.color,
                backgroundColor: `${indexInfo.color}1a`, // 10% opacity
                fill: !isMulti, // Only fill if single index for cleaner view
                tension: 0.1,
                pointRadius: 0,
                pointHoverRadius: 5,
                borderWidth: 1.5
            }
        })

        return { labels, datasets }
    }, [data, selectedSymbols, selectedPeriod])

    const chartOptions = useMemo(() => ({
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: false // We'll show our own legend via checkboxes
            },
            tooltip: {
                mode: 'index',
                intersect: false,
                callbacks: {
                    label: (context) => {
                        const isMulti = selectedSymbols.length > 1
                        const val = context.raw
                        if (isMulti) {
                            return `${context.dataset.label}: ${val >= 0 ? '+' : ''}${val.toFixed(2)}%`
                        }
                        return `${context.dataset.label}: $${val?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                    }
                }
            }
        },
        scales: {
            x: {
                display: true,
                grid: {
                    color: 'rgba(100, 116, 139, 0.1)'
                },
                ticks: {
                    maxTicksLimit: 6,
                    font: { size: 10 },
                    color: '#64748b'
                }
            },
            y: {
                display: true,
                position: 'right',
                grid: {
                    color: 'rgba(100, 116, 139, 0.1)'
                },
                ticks: {
                    font: { size: 10 },
                    color: '#64748b',
                    callback: (value) => {
                        const isMulti = selectedSymbols.length > 1
                        if (isMulti) return `${value >= 0 ? '+' : ''}${value}%`
                        return value.toLocaleString()
                    }
                }
            }
        },
        interaction: {
            mode: 'index',
            intersect: false
        }
    }), [selectedSymbols])

    return (
        <Card className="h-full">
            <CardHeader className="pb-2 space-y-0">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                        Market Indices
                    </CardTitle>

                    <div className="flex gap-1">
                        {PERIODS.map(p => (
                            <Button
                                key={p.value}
                                variant={selectedPeriod === p.value ? 'secondary' : 'ghost'}
                                size="sm"
                                className="h-7 px-2 text-xs"
                                onClick={() => setSelectedPeriod(p.value)}
                            >
                                {p.label}
                            </Button>
                        ))}
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <div className="h-48 w-full flex flex-col gap-2">
                        <Skeleton className="h-full w-full rounded-xl" />
                    </div>
                ) : error ? (
                    <div className="h-48 flex items-center justify-center text-sm text-muted-foreground bg-muted/20 rounded-xl border border-dashed">
                        {error}
                    </div>
                ) : chartData ? (
                    <div className="h-48">
                        <Line data={chartData} options={chartOptions} plugins={[zeroLinePlugin]} />
                    </div>
                ) : (
                    <div className="h-48 flex items-center justify-center text-sm text-muted-foreground bg-muted/20 rounded-xl border border-dashed">
                        No data available
                    </div>
                )}

                <div className="mt-4 flex flex-col">
                    {INDICES.map(idx => {
                        const isSelected = selectedSymbols.includes(idx.symbol)
                        const symbolData = data && !loading && !data.error ? data[idx.symbol] : null

                        return (
                            <div key={idx.symbol} className="flex items-center justify-between h-8 px-1 rounded-md hover:bg-accent/50 transition-colors">
                                <button
                                    onClick={() => toggleSymbol(idx.symbol)}
                                    className={`flex items-center gap-2 text-xs font-medium transition-colors hover:text-foreground text-left ${isSelected ? 'text-foreground' : 'text-muted-foreground'}`}
                                >
                                    <div
                                        className={`w-4 h-4 rounded border flex items-center justify-center transition-all ${isSelected ? 'border-none' : 'border-muted'}`}
                                        style={{ backgroundColor: isSelected ? idx.color : 'transparent' }}
                                    >
                                        {isSelected && <Check className="h-3 w-3 text-white" />}
                                    </div>
                                    {idx.name}
                                </button>

                                {symbolData && !symbolData.error && (
                                    <div className="flex items-center gap-3 text-xs font-medium">
                                        <span className="text-foreground">
                                            {symbolData.current_price?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                        </span>
                                        <span className={`flex items-center ${symbolData.change >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                                            {symbolData.change >= 0 ? <TrendingUp className="h-3 w-3 mr-0.5" /> : <TrendingDown className="h-3 w-3 mr-0.5" />}
                                            {symbolData.change_pct}%
                                        </span>
                                    </div>
                                )}
                            </div>
                        )
                    })}
                </div>
            </CardContent>
        </Card>
    )
}

function formatLabel(timestamp, period) {
    const date = new Date(timestamp)
    if (period === '1d') {
        return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    } else if (period === '5d') {
        const day = date.toLocaleDateString('en-US', { weekday: 'short' })
        const time = date.toLocaleTimeString('en-US', { hour: 'numeric' })
        return `${day} ${time}`
    } else {
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    }
}
