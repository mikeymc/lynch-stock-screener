
import React from 'react'
import { Line } from 'react-chartjs-2'
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Tooltip,
} from 'chart.js'

ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Tooltip
)

export default function Sparkline({ data, labels, color, height = 50, width = 150 }) {
    if (!data || data.length === 0) return null

    // Determine trend color if not provided
    const trendColor = color || (data[data.length - 1] >= data[0] ? '#22c55e' : '#ef4444')

    const options = {
        responsive: false, // Fixed size for sparkline
        maintainAspectRatio: false,
        plugins: {
            legend: { display: false },
            title: { display: false },
            tooltip: {
                enabled: true,
                intersect: false,
                mode: 'index',
            }
        },
        layout: {
            padding: 5
        },
        scales: {
            x: {
                display: false, // No axis
            },
            y: {
                display: false, // No axis
                min: Math.min(...data) * 0.95,
                max: Math.max(...data) * 1.05
            }
        },
        elements: {
            point: {
                radius: 0, // No points usually
                hoverRadius: 4
            },
            line: {
                borderWidth: 2,
                tension: 0.3 // Smooth curves
            }
        }
    }

    const chartData = {
        labels: labels || data.map((_, i) => i),
        datasets: [
            {
                data: data,
                borderColor: trendColor,
                backgroundColor: 'transparent',
                fill: false,
            }
        ]
    }

    return (
        <div style={{ width: width, height: height }}>
            <Line data={chartData} options={options} height={height} width={width} />
        </div>
    )
}
