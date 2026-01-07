// ABOUTME: Business Health page combining Insider Trading and Business Trends
import React, { useState, useEffect } from 'react'
import InsiderTradesTable from './InsiderTradesTable'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Line } from 'react-chartjs-2'
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend
} from 'chart.js'

ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend
)

const API_BASE = '/api'

export default function BusinessHealth({ symbol }) {
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        let active = true
        const fetchData = async () => {
            setLoading(true)
            try {
                // Fetch from outlook endpoint which has extensive data including health checks
                const res = await fetch(`${API_BASE}/stock/${symbol}/outlook`)
                if (res.ok) {
                    const json = await res.json()
                    if (active) setData(json)
                } else {
                    if (active) setError("Failed to load business health data")
                }
            } catch (err) {
                if (active) setError(err.message)
            } finally {
                if (active) setLoading(false)
            }
        }
        fetchData()
        return () => { active = false }
    }, [symbol])

    if (loading) return <div className="p-8 text-muted-foreground">Loading business health indicators...</div>
    if (error) return <div className="p-8 text-destructive">Error: {error}</div>
    if (!data) return null

    const { metrics, insider_trades, inventory_vs_revenue, gross_margin_history } = data

    // --- Formatters ---
    const formatCurrency = (val) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val)

    // --- Helper for Net Insider Buying ---
    const netBuying = metrics?.insider_net_buying_6m || 0
    const netBuyingText = netBuying > 0 ? 'Net Buying' : (netBuying < 0 ? 'Net Selling' : 'Neutral')

    // --- Chart Data ---
    const inventoryChartData = {
        labels: inventory_vs_revenue?.map(d => d.year) || [],
        datasets: [
            {
                label: 'Revenue ($B)',
                data: inventory_vs_revenue?.map(d => d.revenue) || [],
                borderColor: 'rgb(59, 130, 246)',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                fill: true,
                tension: 0.2,
                yAxisID: 'y'
            },
            {
                label: 'Inventory ($B)',
                data: inventory_vs_revenue?.map(d => d.inventory) || [],
                borderColor: 'rgb(249, 115, 22)',
                backgroundColor: 'rgba(249, 115, 22, 0.1)',
                fill: true,
                tension: 0.2,
                yAxisID: 'y1'
            }
        ]
    }

    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
            legend: { position: 'top', labels: { color: 'hsl(var(--foreground))' } },
            title: { display: false }
        },
        scales: {
            y: {
                type: 'linear',
                position: 'left',
                grid: { color: 'hsl(var(--border))' },
                title: { display: true, text: 'Revenue ($B)', color: 'rgb(59, 130, 246)' },
                ticks: { color: 'rgb(59, 130, 246)' }
            },
            y1: {
                type: 'linear',
                position: 'right',
                grid: { display: false },
                title: { display: true, text: 'Inventory ($B)', color: 'rgb(249, 115, 22)' },
                ticks: { color: 'rgb(249, 115, 22)' }
            },
            x: { grid: { color: 'hsl(var(--border))' }, ticks: { color: 'hsl(var(--foreground))' } }
        }
    }

    const marginChartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
            legend: { display: false },
            title: { display: false }
        },
        scales: {
            y: {
                grid: { color: 'hsl(var(--border))' },
                title: { display: true, text: 'Margin (%)', color: 'hsl(var(--foreground))' },
                ticks: { color: 'hsl(var(--foreground))' }
            },
            x: { grid: { color: 'hsl(var(--border))' }, ticks: { color: 'hsl(var(--foreground))' } }
        }
    }

    return (
        <div className="w-full space-y-6">
            {/* ROW 1: Insider Trading */}
            <Card>
                <CardHeader>
                    <CardTitle>Insider Trading Activity</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center gap-4 mb-6 p-4 bg-muted/30 rounded-lg border border-border/50">
                        <div>
                            <div className="text-sm text-muted-foreground mb-1">Net Insider Activity (6m)</div>
                            <div className="flex items-baseline gap-3">
                                <span className={`text-3xl font-bold ${netBuying > 0 ? 'text-green-500' : netBuying < 0 ? 'text-red-500' : 'text-muted-foreground'}`}>
                                    {netBuying > 0 ? '+' : ''}{formatCurrency(netBuying)}
                                </span>
                                <span className="text-lg text-muted-foreground font-medium">
                                    {netBuyingText}
                                </span>
                            </div>
                        </div>
                    </div>

                    <InsiderTradesTable trades={insider_trades} />
                    <div className="mt-4 text-xs text-muted-foreground italic">
                        * Only open market transactions shown. 10b5-1 plans are pre-scheduled trades.
                    </div>
                </CardContent>
            </Card>

            {/* ROW 2: Business Health Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Inventory Check */}
                <Card>
                    <CardHeader>
                        <CardTitle>Inventory vs Revenue Trends</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-sm text-muted-foreground mb-4">
                            Warning Sign: If Inventory (Orange) is growing faster than Revenue (Blue).
                        </p>
                        <div className="h-[250px]">
                            {inventory_vs_revenue && inventory_vs_revenue.length > 0 ? (
                                <Line data={inventoryChartData} options={chartOptions} />
                            ) : (
                                <div className="flex items-center justify-center h-full text-muted-foreground">
                                    Insufficient data for Inventory check.
                                </div>
                            )}
                        </div>
                    </CardContent>
                </Card>

                {/* Moat Stability */}
                <Card>
                    <CardHeader>
                        <CardTitle>Gross Margin Trend</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-sm text-muted-foreground mb-4">
                            Stable or expanding gross margins indicate pricing power and a durable moat.
                        </p>
                        <div className="h-[250px]">
                            {gross_margin_history && gross_margin_history.length > 0 ? (
                                <Line
                                    data={{
                                        labels: gross_margin_history.map(d => d.year),
                                        datasets: [{
                                            label: 'Gross Margin (%)',
                                            data: gross_margin_history.map(d => d.value),
                                            borderColor: 'rgb(34, 197, 94)',
                                            backgroundColor: 'rgba(34, 197, 94, 0.1)',
                                            fill: true,
                                            tension: 0.2
                                        }]
                                    }}
                                    options={marginChartOptions}
                                />
                            ) : (
                                <div className="flex items-center justify-center h-full text-muted-foreground">
                                    No Gross Margin history available.
                                </div>
                            )}
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
