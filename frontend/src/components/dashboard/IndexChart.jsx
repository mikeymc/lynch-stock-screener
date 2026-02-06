// ABOUTME: Market index chart with selector for S&P 500, Nasdaq, Dow Jones
// ABOUTME: Shows price history with period toggles (1D, 1W, 1M, 3M, YTD, 1Y)

import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { TrendingUp, TrendingDown } from 'lucide-react'
import { Line } from 'react-chartjs-2'
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Tooltip,
    Filler
} from 'chart.js'

ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Tooltip,
    Filler
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
            ctx.lineWidth = 2;
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
            ctx.setLineDash([6, 4]);
            ctx.stroke();
            ctx.restore();
        }
    }
};

// Plugin to draw synchronized crosshair
const crosshairPlugin = {
    id: 'crosshair',
    afterDraw: (chart) => {
        // Get activeIndex from options
        const index = chart.config.options.plugins.crosshair?.activeIndex;

        if (index === null || index === undefined || index === -1) return;

        const ctx = chart.ctx;
        const yAxis = chart.scales.y;

        // Ensure dataset meta exists
        const meta = chart.getDatasetMeta(0);
        if (!meta || !meta.data) return;

        const point = meta.data[index];

        if (point) {
            const x = point.x;

            ctx.save();
            ctx.beginPath();
            ctx.moveTo(x, yAxis.top);
            ctx.lineTo(x, yAxis.bottom);
            ctx.lineWidth = 1;
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)'; // Bright white line
            ctx.setLineDash([5, 5]);
            ctx.stroke();
            ctx.restore();
        }
    }
};

const INDICES = [
    { symbol: '^GSPC', name: 'S&P 500' },
    { symbol: '^IXIC', name: 'Nasdaq' },
    { symbol: '^DJI', name: 'Dow Jones' }
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
    const [selectedIndex, setSelectedIndex] = useState('^GSPC')
    const [selectedPeriod, setSelectedPeriod] = useState('1mo')
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [activeIndex, setActiveIndex] = useState(null)

    const handleHover = (event, elements) => {
        if (elements && elements.length > 0) {
            setActiveIndex(elements[0].index)
        }
    }

    const handleMouseLeave = () => {
        setActiveIndex(null)
    }

    useEffect(() => {
        const fetchIndexData = async () => {
            setLoading(true)
            setError(null)
            try {
                const response = await fetch(`/api/market/index/${selectedIndex}?period=${selectedPeriod}`)
                if (response.ok) {
                    const result = await response.json()
                    setData(result)
                } else {
                    const err = await response.json()
                    setError(err.error || 'Failed to load index data')
                }
            } catch (err) {
                console.error('Error fetching index:', err)
                setError('Failed to load index data')
            } finally {
                setLoading(false)
            }
        }

        fetchIndexData()
    }, [selectedIndex, selectedPeriod])

    const isPositive = data && data.change >= 0

    const chartData = data ? {
        labels: data.data.map(d => formatLabel(d.timestamp, selectedPeriod)),
        datasets: [{
            data: data.data.map(d => d.close),
            borderColor: isPositive ? '#22c55e' : '#ef4444',
            backgroundColor: isPositive
                ? 'rgba(34, 197, 94, 0.1)'
                : 'rgba(239, 68, 68, 0.1)',
            fill: true,
            tension: 0.1,
            pointRadius: activeIndex !== null ? 3 : 0,
            pointHoverRadius: 5,
            borderWidth: 1.5
        }]
    } : null

    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        onHover: handleHover,
        plugins: {
            legend: { display: false },
            tooltip: {
                mode: 'index',
                intersect: false,
                callbacks: {
                    label: (context) => `$${context.raw?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                }
            },
            crosshair: {
                activeIndex: activeIndex
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
                    color: (context) => {
                        if (Math.abs(context.tick.value) < 0.00001) return 'transparent';
                        return 'rgba(100, 116, 139, 0.1)';
                    }
                },
                ticks: {
                    font: { size: 10 },
                    color: '#64748b',
                    callback: (value) => value.toLocaleString()
                }
            }
        },
        interaction: {
            mode: 'index',
            intersect: false
        }
    }

    return (
        <Card>
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <Select value={selectedIndex} onValueChange={setSelectedIndex}>
                            <SelectTrigger className="w-[140px] h-8">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {INDICES.map(idx => (
                                    <SelectItem key={idx.symbol} value={idx.symbol}>
                                        {idx.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                        {data && !loading && (
                            <div className="flex items-center gap-2">
                                <span className="text-lg font-semibold">
                                    {data.current_price?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </span>
                                <span className={`flex items-center text-sm ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
                                    {isPositive ? <TrendingUp className="h-4 w-4 mr-1" /> : <TrendingDown className="h-4 w-4 mr-1" />}
                                    {isPositive ? '+' : ''}{data.change_pct?.toFixed(2)}%
                                </span>
                            </div>
                        )}
                    </div>

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
                    <Skeleton className="h-48 w-full" />
                ) : error ? (
                    <div className="h-48 flex items-center justify-center text-muted-foreground">
                        {error}
                    </div>
                ) : chartData ? (
                    <div className="h-48" onMouseLeave={handleMouseLeave}>
                        <Line data={chartData} options={chartOptions} plugins={[zeroLinePlugin, crosshairPlugin]} />
                    </div>
                ) : null}
            </CardContent>
        </Card>
    )
}

function formatLabel(timestamp, period) {
    const date = new Date(timestamp)
    if (period === '1d') {
        return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    } else if (period === '5d') {
        return date.toLocaleDateString('en-US', { weekday: 'short', hour: 'numeric' })
    } else {
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    }
}
