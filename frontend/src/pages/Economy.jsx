// ABOUTME: Economy dashboard page displaying FRED macroeconomic indicators
// ABOUTME: Shows detailed trend charts organized by economic theme

import { useState, useEffect } from 'react'
import { Line } from 'react-chartjs-2'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

const API_BASE = '/api'

// Configuration for the 3 distinct sections
const DASHBOARD_SECTIONS = [
  {
    id: 'consumer',
    title: 'Consumer Engine',
    description: 'The heartbeat of the economy (Lynch Focus)',
    color: 'rgb(236, 72, 153)', // Pink
    series: ['RSXFS', 'TOTALSA', 'UMCSENT', 'HOUST', 'PSAVERT', 'DRCCLACBS', 'ICSA']
  },
  {
    id: 'corporate',
    title: 'Corporate & Output',
    description: 'Production, profits, and liquidity (Buffett Focus)',
    color: 'rgb(139, 92, 246)', // Purple
    series: ['GDP', 'CP', 'TSIFRGHT', 'RETAILIRSA', 'M2SL', 'UNRATE']
  },
  {
    id: 'rates',
    title: 'Rates & Inflation',
    description: 'The cost of capital and currency purchasing power',
    color: 'rgb(20, 184, 166)', // Teal
    series: ['FEDFUNDS', 'DGS10', 'BAA10Y', 'CPIAUCSL', 'PPIACO', 'T10Y2Y', 'VIXCLS']
  }
]

function formatValue(value, units, seriesId) {
  if (value === null || value === undefined) return 'N/A'

  // Format based on series type
  if (seriesId === 'GDPC1' || seriesId === 'GDP') {
    return `$${(value / 1000).toFixed(1)}T`
  }
  if (seriesId === 'RSXFS' || seriesId === 'CP' || seriesId === 'M2SL') {
    if (seriesId === 'M2SL') {
      return `$${(value / 1000).toFixed(1)}T`
    }
    return `$${(value / 1000).toFixed(1)}B`
  }
  if (seriesId === 'TOTALSA' || seriesId === 'HOUST') {
    if (seriesId === 'HOUST') {
      return `${(value / 1000).toFixed(2)}M`
    }
    return `${value.toFixed(1)}M`
  }
  if (seriesId === 'ICSA') {
    return `${(value / 1000).toFixed(0)}K`
  }

  // Percentages and Indices
  if (units === 'Percent' || units === 'Index' || units.includes('Index')) {
    return value.toFixed(2)
  }

  return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function formatChange(change, changePercent, seriesId) {
  if (change === null || change === undefined) return null

  const isPositive = change > 0
  const arrow = isPositive ? '↑' : '↓'

  // For percentage-based metrics (rates, unrate), show absolute change in pp
  if (['UNRATE', 'FEDFUNDS', 'DGS10', 'T10Y2Y', 'BAA10Y', 'PSAVERT'].includes(seriesId)) {
    return { text: `${arrow} ${Math.abs(change).toFixed(2)}pp`, isPositive }
  }

  // For others, show percent change if available
  if (changePercent !== null && changePercent !== undefined) {
    return { text: `${arrow} ${Math.abs(changePercent).toFixed(1)}%`, isPositive }
  }

  return { text: `${arrow} ${Math.abs(change).toFixed(2)}`, isPositive }
}


function TrendChart({ indicator, sectionColor }) {
  if (!indicator) return null

  // Prepare data
  const observations = indicator.observations || []
  const labels = observations.map(o => o.date)
  const dataPoints = observations.map(o => o.value)

  // Calculate display values
  const currentValue = formatValue(indicator.current_value, indicator.units, indicator.series_id)
  const change = formatChange(indicator.change, indicator.change_percent, indicator.series_id)

  // Helper to get RGBA with opacity from RGB string
  // Input: "rgb(236, 72, 153)" -> Output: "rgba(236, 72, 153, 0.2)"
  const getTransparentColor = (rgbString, opacity = 0.2) => {
    return rgbString.replace('rgb', 'rgba').replace(')', `, ${opacity})`)
  }

  const chartData = {
    labels,
    datasets: [{
      label: indicator.name,
      data: dataPoints,
      borderColor: sectionColor,
      backgroundColor: (context) => {
        const ctx = context.chart.ctx;
        const gradient = ctx.createLinearGradient(0, 0, 0, 200);
        gradient.addColorStop(0, getTransparentColor(sectionColor, 0.4));
        gradient.addColorStop(1, getTransparentColor(sectionColor, 0.05));
        return gradient;
      },
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 4,
      fill: true,
      tension: 0.2
    }]
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index',
      intersect: false,
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: 'rgba(15, 23, 42, 0.9)', // slate-900
        padding: 12,
        titleColor: '#e2e8f0', // slate-200
        bodyColor: '#e2e8f0',
        borderColor: 'rgba(148, 163, 184, 0.1)',
        borderWidth: 1,
        displayColors: false,
        callbacks: {
          label: (ctx) => `${formatValue(ctx.raw, indicator.units, indicator.series_id)}`
        }
      }
    },
    scales: {
      x: {
        display: true,
        grid: {
          display: true,
          color: 'rgba(148, 163, 184, 0.1)'
        },
        ticks: {
          maxRotation: 0,
          autoSkip: true,
          maxTicksLimit: 8, // Increased slightly to allow more density if space permits
          color: '#94a3b8', // slate-400
          font: { size: 10 },
          callback: function (val, index) {
            const label = this.getLabelForValue(val)
            const date = new Date(label)
            // Format as "Jan '24" for compactness
            return date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
          }
        }
      },
      y: {
        display: true,
        position: 'right', // Put axis on right for financial look
        grid: {
          color: 'rgba(148, 163, 184, 0.1)'
        },
        ticks: {
          color: '#94a3b8',
          font: { size: 10 },
          callback: (val) => {
            // Simplify large numbers for axis
            if (val >= 1000 && (indicator.series_id === 'GDP' || indicator.series_id === 'M2SL')) return `$${val / 1000}T`
            if (val >= 1000) return `${val / 1000}k`
            return val
          }
        }
      }
    }
  }

  return (
    <Card className="flex flex-col h-full overflow-hidden hover:shadow-md transition-shadow">
      <CardHeader className="pb-2 pt-4 px-4 space-y-0">
        <div className="flex justify-between items-start">
          <div>
            <CardTitle className="text-sm font-medium text-muted-foreground mr-2 leading-tight">
              {indicator.name}
            </CardTitle>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-xl font-bold text-foreground">
                {currentValue}
              </span>
              {change && (
                <span className={`text-xs font-medium ${change.isPositive ? 'text-green-500' : 'text-red-500'}`}>
                  {change.text}
                </span>
              )}
            </div>
          </div>
          <Badge variant="secondary" className="text-[10px] h-5 px-1.5 font-normal opacity-70">
            {indicator.frequency === 'monthly' ? 'Monthly' : indicator.frequency === 'quarterly' ? 'Quarterly' : 'Daily'}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 pt-0 pb-4 px-0">
        <div className="h-48 w-full">
          <Line data={chartData} options={options} />
        </div>
      </CardContent>
    </Card>
  )
}

export default function Economy() {
  const [dashboardData, setDashboardData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        setLoading(true)
        const response = await fetch(`${API_BASE}/fred/dashboard`, {
          credentials: 'include'
        })

        if (!response.ok) {
          throw new Error('Failed to fetch economic data')
        }

        const data = await response.json()
        setDashboardData(data)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchDashboard()
  }, [])

  if (loading) {
    return (
      <div className="flex flex-col w-full min-h-full p-6 space-y-8 max-w-[1600px] mx-auto">
        <div className="space-y-2">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-4 w-96" />
        </div>
        {[1, 2, 3].map(i => (
          <div key={i} className="space-y-4">
            <Skeleton className="h-6 w-48" />
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {[1, 2, 3].map(j => <Skeleton key={j} className="h-64" />)}
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    )
  }

  // Helper to find indicator data by ID
  const getIndicator = (id) => dashboardData?.indicators?.find(i => i.series_id === id)

  return (
    <div className="flex flex-col w-full min-h-full p-6 space-y-12 max-w-[1600px] mx-auto pb-20">

      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Economic Indicators</h1>
        <p className="text-muted-foreground mt-2 text-lg">
          Macroeconomic driver dashboard • {dashboardData?.fetched_at ? new Date(dashboardData.fetched_at).toLocaleDateString() : ''}
        </p>
      </div>

      {DASHBOARD_SECTIONS.map(section => (
        <section key={section.id} className="space-y-6">
          <div className="border-b pb-2">
            <h2 className="text-xl font-semibold flex items-center gap-2" style={{ color: section.color }}>
              {section.title}
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              {section.description}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {section.series.map(seriesId => {
              const indicator = getIndicator(seriesId)
              if (!indicator) return null
              return (
                <TrendChart
                  key={seriesId}
                  indicator={indicator}
                  sectionColor={section.color}
                />
              )
            })}
          </div>
        </section>
      ))}

    </div>
  )
}
