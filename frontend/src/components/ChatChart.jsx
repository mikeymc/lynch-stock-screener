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
            <div className="chat-chart-tooltip">
                <p className="tooltip-label">{label}</p>
                {payload.map((entry, index) => (
                    <p key={index} style={{ color: entry.color }}>
                        {entry.name}: {typeof entry.value === 'number'
                            ? entry.value.toLocaleString('en-US', {
                                style: entry.unit === '$' ? 'currency' : 'decimal',
                                currency: 'USD',
                                maximumFractionDigits: 2
                            })
                            : entry.value}
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
    let chartData

    try {
        chartData = typeof chartJson === 'string' ? JSON.parse(chartJson) : chartJson
    } catch (e) {
        console.error('Failed to parse chart JSON:', e)
        return (
            <div className="chat-chart-error">
                Unable to render chart: Invalid JSON
            </div>
        )
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
        <div className="chat-chart-container">
            {title && <h4 className="chat-chart-title">{title}</h4>}
            <ResponsiveContainer width="100%" height={300}>
                {renderChart()}
            </ResponsiveContainer>
        </div>
    )
}
