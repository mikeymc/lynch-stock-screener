// ABOUTME: Economy dashboard page displaying FRED macroeconomic indicators
// ABOUTME: Shows 8 key indicators with current values, changes, and mini charts

import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
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

// Category display order and colors
const CATEGORY_CONFIG = {
  output: { label: 'Economic Output', color: 'rgb(59, 130, 246)' },
  employment: { label: 'Employment', color: 'rgb(34, 197, 94)' },
  inflation: { label: 'Inflation', color: 'rgb(249, 115, 22)' },
  interest_rates: { label: 'Interest Rates', color: 'rgb(168, 85, 247)' },
  volatility: { label: 'Market Volatility', color: 'rgb(239, 68, 68)' }
}

function formatValue(value, units, seriesId) {
  if (value === null || value === undefined) return 'N/A'

  // Format based on series type
  if (seriesId === 'GDPC1') {
    return `$${(value / 1000).toFixed(1)}T`
  }
  if (seriesId === 'ICSA') {
    return `${(value / 1000).toFixed(0)}K`
  }
  if (units === 'Percent' || units === 'Index') {
    return value.toFixed(2)
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function formatChange(change, changePercent, seriesId) {
  if (change === null || change === undefined) return null

  const isPositive = change > 0
  const arrow = isPositive ? '↑' : '↓'

  // For percentage-based metrics, show absolute change
  if (seriesId === 'UNRATE' || seriesId === 'FEDFUNDS' || seriesId === 'DGS10' || seriesId === 'T10Y2Y') {
    return { text: `${arrow} ${Math.abs(change).toFixed(2)}pp`, isPositive }
  }

  // For others, show percent change if available
  if (changePercent !== null && changePercent !== undefined) {
    return { text: `${arrow} ${Math.abs(changePercent).toFixed(1)}%`, isPositive }
  }

  return { text: `${arrow} ${Math.abs(change).toFixed(2)}`, isPositive }
}

function IndicatorCard({ indicator, onClick, isSelected }) {
  const categoryConfig = CATEGORY_CONFIG[indicator.category] || { color: 'rgb(107, 114, 128)' }
  const change = formatChange(indicator.change, indicator.change_percent, indicator.series_id)

  // Mini chart data
  const chartData = {
    labels: indicator.observations?.map(o => o.date) || [],
    datasets: [{
      data: indicator.observations?.map(o => o.value) || [],
      borderColor: categoryConfig.color,
      backgroundColor: `${categoryConfig.color}33`,
      fill: true,
      tension: 0.3,
      pointRadius: 0,
      borderWidth: 2,
    }]
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: { enabled: false }
    },
    scales: {
      x: { display: false },
      y: { display: false }
    },
    interaction: { enabled: false }
  }

  return (
    <Card
      className={`cursor-pointer transition-all hover:shadow-lg ${isSelected ? 'ring-2 ring-primary' : ''}`}
      onClick={() => onClick(indicator)}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            {indicator.name}
          </CardTitle>
          <Badge variant="outline" className="text-xs">
            {indicator.frequency}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex items-end justify-between mb-2">
          <div>
            <div className="text-2xl font-bold">
              {formatValue(indicator.current_value, indicator.units, indicator.series_id)}
            </div>
            {change && (
              <div className={`text-sm ${change.isPositive ? 'text-green-500' : 'text-red-500'}`}>
                {change.text}
              </div>
            )}
          </div>
          <div className="text-xs text-muted-foreground">
            {indicator.current_date}
          </div>
        </div>
        <div className="h-16">
          <Line data={chartData} options={chartOptions} />
        </div>
      </CardContent>
    </Card>
  )
}

function DetailChart({ indicator }) {
  if (!indicator) return null

  const categoryConfig = CATEGORY_CONFIG[indicator.category] || { color: 'rgb(107, 114, 128)' }

  const chartData = {
    labels: indicator.observations?.map(o => {
      const date = new Date(o.date)
      return date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
    }) || [],
    datasets: [{
      label: indicator.name,
      data: indicator.observations?.map(o => o.value) || [],
      borderColor: categoryConfig.color,
      backgroundColor: `${categoryConfig.color}33`,
      fill: true,
      tension: 0.3,
      pointRadius: 2,
      pointHoverRadius: 6,
      borderWidth: 2,
    }]
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (context) => {
            return `${formatValue(context.raw, indicator.units, indicator.series_id)} ${indicator.units}`
          }
        }
      }
    },
    scales: {
      x: {
        grid: { color: 'rgba(255, 255, 255, 0.1)' },
        ticks: { color: 'rgba(255, 255, 255, 0.7)' }
      },
      y: {
        grid: { color: 'rgba(255, 255, 255, 0.1)' },
        ticks: {
          color: 'rgba(255, 255, 255, 0.7)',
          callback: (value) => formatValue(value, indicator.units, indicator.series_id)
        }
      }
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>{indicator.name}</CardTitle>
            <p className="text-sm text-muted-foreground mt-1">{indicator.description}</p>
          </div>
          <Badge>{indicator.series_id}</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-80">
          <Line data={chartData} options={chartOptions} />
        </div>
      </CardContent>
    </Card>
  )
}

export default function Economy() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [dashboardData, setDashboardData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedIndicator, setSelectedIndicator] = useState(null)

  // Get selected category from URL
  const selectedCategory = searchParams.get('category') || null

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        setLoading(true)
        const response = await fetch(`${API_BASE}/fred/dashboard`, {
          credentials: 'include'
        })

        if (!response.ok) {
          const data = await response.json()
          throw new Error(data.error || 'Failed to fetch economic data')
        }

        const data = await response.json()
        setDashboardData(data)

        // Select first indicator by default
        if (data.indicators?.length > 0 && !selectedIndicator) {
          setSelectedIndicator(data.indicators[0])
        }
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchDashboard()
  }, [])

  const handleIndicatorClick = (indicator) => {
    setSelectedIndicator(indicator)
  }

  const handleCategoryClick = (category) => {
    if (category === selectedCategory) {
      setSearchParams({})
    } else {
      setSearchParams({ category })
    }
  }

  // Filter indicators by category if selected
  const filteredIndicators = selectedCategory
    ? dashboardData?.indicators?.filter(i => i.category === selectedCategory) || []
    : dashboardData?.indicators || []

  if (loading) {
    return (
      <div className="flex flex-col w-full min-h-full p-6 space-y-6">
        <div className="flex items-center justify-between">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-32" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(8)].map((_, i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col w-full min-h-full p-6">
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="flex flex-col w-full min-h-full p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Economic Indicators</h1>
          <p className="text-muted-foreground">
            Federal Reserve Economic Data (FRED)
          </p>
        </div>
        {dashboardData?.fetched_at && (
          <div className="text-sm text-muted-foreground">
            Updated: {new Date(dashboardData.fetched_at).toLocaleString()}
          </div>
        )}
      </div>

      {/* Category filters */}
      <div className="flex flex-wrap gap-2">
        {Object.entries(CATEGORY_CONFIG).map(([key, config]) => (
          <Badge
            key={key}
            variant={selectedCategory === key ? 'default' : 'outline'}
            className="cursor-pointer"
            onClick={() => handleCategoryClick(key)}
          >
            {config.label}
          </Badge>
        ))}
      </div>

      {/* Indicator grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {filteredIndicators.map((indicator) => (
          <IndicatorCard
            key={indicator.series_id}
            indicator={indicator}
            onClick={handleIndicatorClick}
            isSelected={selectedIndicator?.series_id === indicator.series_id}
          />
        ))}
      </div>

      {/* Detail chart */}
      {selectedIndicator && (
        <DetailChart indicator={selectedIndicator} />
      )}
    </div>
  )
}
