// ABOUTME: ChatChart component for rendering inline charts in agent chat responses
// ABOUTME: Parses JSON chart data and renders using Recharts library

import React from 'react'
import {
    BarChart,
    Bar,
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
} from 'recharts'

// Color palette for multiple series
const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899']

// Custom tooltip styling
const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
        return (
            <div className="bg-background/95 border border-border p-3 rounded-lg shadow-xl text-xs backdrop-blur-sm z-[100]">
                <p className="font-semibold mb-2 text-foreground">{label}</p>
                {payload.map((entry, index) => (
                    <p key={index} style={{ color: entry.color }} className="flex items-center gap-2 mb-1">
                        <span className="font-medium">{entry.name}:</span>
                        <span>
                            {typeof entry.value === 'number'
                                ? entry.value.toLocaleString('en-US', {
                                    style: entry.unit === '$' ? 'currency' : 'decimal',
                                    currency: 'USD',
                                    maximumFractionDigits: 2,
                                    compactDisplay: 'short',
                                    notation: entry.value > 1000000 ? 'compact' : 'standard'
                                })
                                : entry.value}
                        </span>
                    </p>
                ))}
            </div>
        )
    }
    return null
}

/**
 * ChatChart - Renders charts from JSON data in agent responses
 * 
 * Expected JSON format:
 * {
 *   "type": "bar" | "line",
 *   "title": "Chart Title",
 *   "data": [
 *     { "name": "2020", "AMD": 9.76, "NVDA": 10.92 },
 *     { "name": "2021", "AMD": 16.43, "NVDA": 16.68 },
 *     ...
 *   ],
 *   "series": ["AMD", "NVDA"],  // Keys to chart (optional, auto-detected)
 *   "xKey": "name",             // X-axis key (default: "name")
 *   "yLabel": "Revenue ($B)",   // Y-axis label (optional)
 * }
 */
export default function ChatChart({ chartJson }) {
    // Don't attempt to render if we don't have any data
    if (!chartJson) return null

    // If it's a string, check if it looks like complete JSON before parsing
    // This prevents errors during streaming when we receive incomplete JSON chunks
    if (typeof chartJson === 'string') {
        const trimmed = chartJson.trim()

        // Basic validation: must start with { and end with }
        // and have balanced braces (simple heuristic)
        if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) {
            // Incomplete JSON during streaming - silently skip rendering
            return null
        }

        // Count braces to check if they're balanced
        const openBraces = (trimmed.match(/{/g) || []).length
        const closeBraces = (trimmed.match(/}/g) || []).length
        if (openBraces !== closeBraces) {
            // Incomplete JSON during streaming - silently skip rendering
            return null
        }
    }

    let chartData

    try {
        chartData = typeof chartJson === 'string' ? JSON.parse(chartJson) : chartJson
    } catch (e) {
        // Only log error if it looks like it should be complete JSON
        // (to avoid spamming console during streaming)
        if (typeof chartJson === 'string' && chartJson.trim().endsWith('}')) {
            console.error('Failed to parse chart JSON:', e)
        }
        // Silently return null - likely incomplete streaming data
        return null
    }

    const { type = 'bar', title, data, series, xKey = 'name', yLabel } = chartData

    if (!data || !Array.isArray(data) || data.length === 0) {
        return (
            <div className="chat-chart-error">
                Unable to render chart: No data provided
            </div>
        )
    }

    // Auto-detect series if not provided
    const detectedSeries = series || Object.keys(data[0]).filter(k => k !== xKey)

    // Format large numbers for Y-axis
    const formatYAxis = (value) => {
        if (value >= 1e9) return `$${(value / 1e9).toFixed(0)}B`
        if (value >= 1e6) return `$${(value / 1e6).toFixed(0)}M`
        if (value >= 1e3) return `$${(value / 1e3).toFixed(0)}K`
        return value.toLocaleString()
    }

    const renderChart = () => {
        if (type === 'line') {
            return (
                <LineChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis
                        dataKey={xKey}
                        stroke="#94a3b8"
                        tick={{ fill: '#94a3b8' }}
                    />
                    <YAxis
                        stroke="#94a3b8"
                        tick={{ fill: '#94a3b8' }}
                        tickFormatter={formatYAxis}
                        label={yLabel ? { value: yLabel, angle: -90, position: 'insideLeft', fill: '#94a3b8' } : null}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Legend />
                    {detectedSeries.map((key, idx) => (
                        <Line
                            key={key}
                            type="monotone"
                            dataKey={key}
                            stroke={COLORS[idx % COLORS.length]}
                            strokeWidth={2}
                            dot={{ fill: COLORS[idx % COLORS.length], r: 4 }}
                            activeDot={{ r: 6 }}
                        />
                    ))}
                </LineChart>
            )
        }

        // Default: Bar chart
        return (
            <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis
                    dataKey={xKey}
                    stroke="#94a3b8"
                    tick={{ fill: '#94a3b8' }}
                />
                <YAxis
                    stroke="#94a3b8"
                    tick={{ fill: '#94a3b8' }}
                    tickFormatter={formatYAxis}
                    label={yLabel ? { value: yLabel, angle: -90, position: 'insideLeft', fill: '#94a3b8' } : null}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                {detectedSeries.map((key, idx) => (
                    <Bar
                        key={key}
                        dataKey={key}
                        fill={COLORS[idx % COLORS.length]}
                        radius={[4, 4, 0, 0]}
                    />
                ))}
            </BarChart>
        )
    }

    return (
        <div className="w-full min-w-0 whitespace-normal max-w-full">
            {title && <h4 className="text-sm font-semibold mb-2 text-center text-muted-foreground">{title}</h4>}
            {/* Wrapper div with explicit width essential for ResponsiveContainer in flex layouts */}
            <div className="w-full h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                    {renderChart()}
                </ResponsiveContainer>
            </div>
        </div>
    )
}
