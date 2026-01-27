// ABOUTME: Stock charts component displaying 10 financial metrics in 3 thematic sections
// ABOUTME: Full-width layout: charts content

import { useState, useCallback, useMemo, useEffect } from 'react'
import { Line } from 'react-chartjs-2'
import { Button } from "@/components/ui/button"
import { Sparkles, RefreshCw } from 'lucide-react'
import UnifiedChartAnalysis from './UnifiedChartAnalysis'
import ChartNarrativeRenderer from './ChartNarrativeRenderer'
import ReactMarkdown from 'react-markdown'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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

// Register ChartJS components
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

// Stateless year tick callback
const yearTickCallback = function (value, index, values) {
  const label = this.getLabelForValue(value)
  if (!label) return label

  // Extract year from date string (assumes YYYY-MM-DD or YYYY QX format)
  const year = String(label).substring(0, 4)

  // Always show first label
  if (index === 0) return year

  // Check previous label's year
  const prevValue = values[index - 1].value
  const prevLabel = this.getLabelForValue(prevValue)
  const prevYear = prevLabel ? prevLabel.substring(0, 4) : null

  // If different from previous year, show it
  if (year !== prevYear) {
    return year
  }
  return null
};

export default function StockCharts({ historyData, quarterlyHistoryData, loading, symbol, activeCharacter }) {
  const [activeIndex, setActiveIndex] = useState(null)
  const [analyses, setAnalyses] = useState({ growth: null, cash: null, valuation: null })
  const [narrative, setNarrative] = useState(null)
  const [viewMode, setViewMode] = useState('annual') // 'annual' or 'quarterly'
  // Local character selection (defaults to activeCharacter prop, or 'lynch')
  const [selectedCharacter, setSelectedCharacter] = useState(activeCharacter || 'lynch')
  // State to hold the analyze button state from child component
  const [analyzeButtonState, setAnalyzeButtonState] = useState({ loading: false, hasAnyAnalysis: false, onAnalyze: null })

  // Sync local character state when global character changes
  useEffect(() => {
    if (activeCharacter) {
      setSelectedCharacter(activeCharacter)
    }
  }, [activeCharacter])

  // Clear analyses when selected character changes (either from prop or local toggle)
  useEffect(() => {
    setAnalyses({ growth: null, cash: null, valuation: null })
    setNarrative(null)
  }, [selectedCharacter])

  const handleHover = useCallback((event, elements) => {
    if (elements && elements.length > 0) {
      const index = elements[0].index;
      setActiveIndex(index);
    }
  }, []);

  const handleMouseLeave = useCallback(() => {
    setActiveIndex(null);
  }, []);

  // Callback to receive button state from UnifiedChartAnalysis
  const handleButtonStateChange = useCallback((state) => {
    setAnalyzeButtonState(state)
  }, [])

  // Time Horizon State
  const [timeHorizon, setTimeHorizon] = useState('5y') // '3y', '5y', '10y', 'all'

  // Determine active dataset (Annual vs Quarterly)
  const rawActiveData = viewMode === 'quarterly' && quarterlyHistoryData ? quarterlyHistoryData : historyData
  const showQuarterly = viewMode === 'quarterly'

  // Apply Time Horizon Filtering
  const activeData = useMemo(() => {
    if (!rawActiveData || timeHorizon === 'all') return rawActiveData

    const years = parseInt(timeHorizon.replace('y', ''))
    // Calculate points to keep:
    // Annual: 1 point per year
    // Quarterly: 4 points per year
    const pointsToKeep = viewMode === 'quarterly' ? years * 4 : years

    const len = (rawActiveData.labels || []).length
    const startIdx = len > pointsToKeep ? len - pointsToKeep : 0
    const slice = (arr) => Array.isArray(arr) ? arr.slice(startIdx) : arr

    // Helper for time-based filtering (weekly data)
    const filterByDate = (dates, values) => {
      if (!dates || !values || dates.length === 0) return { dates, values }

      const lastDateStr = dates[dates.length - 1]
      if (!lastDateStr) return { dates, values }

      const lastDate = new Date(lastDateStr)
      const cutoffDate = new Date(lastDate)
      cutoffDate.setFullYear(lastDate.getFullYear() - years)
      const cutoffIso = cutoffDate.toISOString().split('T')[0]

      const startIndex = dates.findIndex(d => d >= cutoffIso)
      if (startIndex === -1) return { dates, values }

      return {
        dates: dates.slice(startIndex),
        values: values.slice(startIndex)
      }
    }

    // Filter weekly prices
    const wp = rawActiveData.weekly_prices || {}
    const filteredWp = wp.dates && wp.prices
      ? ((res) => ({ dates: res.dates, prices: res.values }))(filterByDate(wp.dates, wp.prices))
      : wp

    // Filter weekly dividends
    const wdy = rawActiveData.weekly_dividend_yields || {}
    const filteredWdy = wdy.dates && wdy.values
      ? filterByDate(wdy.dates, wdy.values)
      : wdy

    // Filter weekly PE
    const wpe = rawActiveData.weekly_pe_ratios || {}
    const filteredWpe = wpe.dates && wpe.values
      ? filterByDate(wpe.dates, wpe.values)
      : wpe

    return {
      ...rawActiveData,
      labels: slice(rawActiveData.labels),
      years: slice(rawActiveData.years),
      revenue: slice(rawActiveData.revenue),
      net_income: slice(rawActiveData.net_income),
      eps: slice(rawActiveData.eps),
      price: slice(rawActiveData.price),
      pe_ratio: slice(rawActiveData.pe_ratio || rawActiveData.pe_history), // Use pe_ratio or pe_history
      pe_history: slice(rawActiveData.pe_history),
      debt_to_equity: slice(rawActiveData.debt_to_equity),
      operating_cash_flow: slice(rawActiveData.operating_cash_flow),
      free_cash_flow: slice(rawActiveData.free_cash_flow),
      capital_expenditures: slice(rawActiveData.capital_expenditures),
      shareholder_equity: slice(rawActiveData.shareholder_equity),
      shares_outstanding: slice(rawActiveData.shares_outstanding),
      roe: slice(rawActiveData.roe),
      book_value_per_share: slice(rawActiveData.book_value_per_share),
      debt_to_earnings: slice(rawActiveData.debt_to_earnings),
      // Add filtered weekly/granular data
      weekly_prices: filteredWp,
      weekly_dividend_yields: filteredWdy,
      weekly_pe_ratios: filteredWpe
    }
  }, [rawActiveData, timeHorizon, viewMode])

  // Calculate Net Margin on the fly (Net Income / Revenue * 100)
  // Must be before early return to satisfy Rules of Hooks
  const netMarginData = useMemo(() => {
    if (!activeData || !activeData.net_income || !activeData.revenue) return []
    return activeData.net_income.map((ni, i) => {
      const rev = activeData.revenue[i]
      if (ni == null || rev == null || rev === 0) return null
      return (ni / rev) * 100
    })
  }, [activeData])

  if (loading || !historyData) {
    return (
      <div className="flex items-center justify-center p-12">
        <div className="text-muted-foreground">Loading chart data...</div>
      </div>
    )
  }

  // Labels and Years
  // For quarterly, labels are "YYYY QX", years are "YYYY"
  const labels = activeData?.labels || activeData?.years || []

  // Helper to extract year from label
  const getYearFromLabel = (label) => {
    if (typeof label === 'string' && label.includes(' ')) {
      // Handle "2023 Q1" -> 2023
      return parseInt(label.split(' ')[0])
    }
    return parseInt(String(label).substring(0, 4))
  }

  const lastHistoricalYear = (() => {
    const lastLabel = labels[labels.length - 1]
    return getYearFromLabel(lastLabel)
  })()

  // Estimates: use annual (next_year) or quarterly (next_quarter) based on view mode
  // Annual estimates come from historyData (always annual endpoint)
  // Quarterly estimates are returned alongside quarterly history data
  const hasAnnualEstimates = historyData?.analyst_estimates?.next_year
  const hasQuarterlyEstimates = activeData?.analyst_estimates?.next_quarter
  const hasEstimates = showQuarterly ? hasQuarterlyEstimates : hasAnnualEstimates

  // Helper to get next quarter label from last label (e.g., "2024 Q4" -> "2025 Q1 E")
  const getNextQuarterLabel = () => {
    if (!labels.length) return null
    const lastLabel = labels[labels.length - 1]
    const match = String(lastLabel).match(/^(\d{4})\s+Q(\d)$/)
    if (!match) return null

    let year = parseInt(match[1])
    let quarter = parseInt(match[2])

    // Advance to next quarter
    quarter += 1
    if (quarter > 4) {
      quarter = 1
      year += 1
    }
    return `${year} Q${quarter} E`
  }

  // Build labels with future estimate period appended if exists
  const getExtendedLabels = () => {
    const baseLabels = [...labels]

    if (hasEstimates) {
      if (showQuarterly) {
        // Quarterly: append next quarter estimate label
        const nextQLabel = getNextQuarterLabel()
        if (nextQLabel) {
          baseLabels.push(nextQLabel)
        }
      } else {
        // Annual: append next year estimate label
        const estimateYear = lastHistoricalYear + 1
        const yearExists = labels.some(l => getYearFromLabel(l) === estimateYear)
        if (!yearExists) {
          baseLabels.push(`${estimateYear}E`)
        }
      }
    }

    return baseLabels
  }


  // Build estimate data array - positioned after historical data
  const buildEstimateData = (historicalData, estimateType, scaleFactor = 1) => {
    const extLabels = getExtendedLabels()

    // Start with nulls for all positions
    const estimateData = new Array(extLabels.length).fill(null)

    if (!hasEstimates) return estimateData

    // Get appropriate estimates based on view mode
    const estimates = showQuarterly
      ? activeData?.analyst_estimates?.next_quarter
      : historyData?.analyst_estimates?.next_year

    if (!estimates) return estimateData

    // Find the estimate position (last label which ends with " E")
    const estimateIdx = extLabels.findIndex(l => String(l).endsWith(' E') || String(l).endsWith('E'))
    const connectionIdx = estimateIdx - 1

    if (estimateIdx >= 0) {
      const estValue = estimates[`${estimateType}_avg`]
      if (estValue != null) {
        estimateData[estimateIdx] = estValue / scaleFactor

        // Connect from the last historical point
        if (historicalData.length > 0 && connectionIdx >= 0) {
          const lastHistorical = historicalData[historicalData.length - 1]
          if (lastHistorical != null) {
            estimateData[connectionIdx] = lastHistorical / scaleFactor
          }
        }
      }
    }

    return estimateData
  }


  // Helper to scale data values (e.g. to Billions)
  const scaleHistoryData = (data, scaleFactor = 1) => {
    return (data || []).map(v => v != null ? v / scaleFactor : null)
  }

  // Data for charts, using activeData and estimates
  const revenueData = scaleHistoryData(activeData.revenue, 1e9)
  const netIncomeData = scaleHistoryData(activeData.net_income || [], 1e9)
  const epsData = scaleHistoryData(activeData.eps || [], 1)
  const priceData = scaleHistoryData(activeData.price || [], 1)

  // Fallback for missing debt_to_equity in quarterly?
  // If activeData lacks it, it will be empty.
  const debtToEquityData = scaleHistoryData(activeData.debt_to_equity || [], 1)

  const ocfData = scaleHistoryData(activeData.operating_cash_flow || [], 1e9)
  const fcfData = scaleHistoryData(activeData.free_cash_flow || [], 1e9)

  // CapEx is negative, take abs
  const capExData = scaleHistoryData(
    (activeData.capital_expenditures || []).map(v => v != null ? Math.abs(v) : null),
    1e9
  )

  // New Buffett Data
  const roeData = scaleHistoryData(activeData.roe || [], 1)
  const sharesData = scaleHistoryData(activeData.shares_outstanding || [], 1) // No scale needed, usu. in exact units or thousands? Usually raw in DB. Let's assume raw. Wait, Market Cap is scaled. Shares are usually huge. Let's check DB. If market cap is e.g. 3 Trillion, shares are e.g. 15 Billion. Let's scale to Billions for display if needed, or just formatted. Let's start with Billions.
  // Actually, shares are usually in full units. 15B shares = 15,000,000,000.
  // Let's scale shares to Billions.
  const sharesDataBillion = scaleHistoryData(activeData.shares_outstanding || [], 1e9)

  const bookValueData = scaleHistoryData(activeData.book_value_per_share || [], 1)

  const debtToEarningsData = scaleHistoryData(activeData.debt_to_earnings || [], 1)

  // selectedCharacter can be a string ID or an object with an id property
  const characterId = typeof selectedCharacter === 'string' ? selectedCharacter : selectedCharacter?.id
  const isBuffett = characterId === 'buffett'


  // Helper function to create chart options
  const createChartOptions = (title, yAxisLabel, isQuarterly = false) => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index',
      intersect: false,
    },
    onHover: handleHover,
    plugins: {
      title: {
        display: true,
        text: title,
        font: { size: 14, weight: '600' },
        color: '#999999' // Medium Grey for headers
      },
      legend: {
        display: false
      },
      crosshair: {
        activeIndex: activeIndex
      }
    },
    scales: {
      x: {
        ticks: {
          autoSkip: false,
          maxRotation: 45,
          minRotation: 45,
          color: '#64748b', // Slate gray for labels
          callback: function (value, index, ticks) {
            const label = this.getLabelForValue(value)
            if (!label) return label

            if (isQuarterly) {
              // For quarterly data: only show year on Q4 labels
              if (String(label).endsWith(' Q4')) {
                return label.replace(' Q4', '') // "2024 Q4" -> "2024"
              }
              // Also show estimate labels (e.g., "2025E")
              if (String(label).endsWith('E')) {
                return label
              }
              return '' // Hide Q1, Q2, Q3 labels
            }

            // For annual data: show all labels (years)
            return label
          }
        },
        grid: {
          color: 'rgba(100, 116, 139, 0.1)' // Light grid lines
        }
      },
      y: {
        title: {
          display: true,
          text: yAxisLabel,
          color: '#64748b'
        },
        ticks: {
          color: '#64748b'
        },
        grid: {
          color: (context) => {
            // Hide default zero line so we can draw our own
            if (Math.abs(context.tick.value) < 0.00001) {
              return 'transparent';
            }
            return 'rgba(100, 116, 139, 0.1)'; // Light grid for Paper theme
          }
        }
      }
    }
  })

  // Styled analysis box component
  const AnalysisBox = ({ content }) => {
    // Preprocess: convert single newlines to double newlines for proper paragraph rendering
    const processedContent = content
      ?.replace(/([^\n])\n([^\n])/g, '$1\n\n$2')  // Single newline → double newline
      || ''

    return (
      <Card className="mt-4 bg-muted/50">
        <CardContent className="pt-4">
          <div className="prose prose-sm max-w-none prose-p:mb-4 prose-p:leading-relaxed prose-headings:text-foreground prose-p:text-foreground/90 prose-strong:text-foreground prose-li:text-foreground/90 [&>p]:mb-4 [&>p]:leading-relaxed">
            <ReactMarkdown>{processedContent}</ReactMarkdown>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Custom Legend Component for external rendering
  const CustomLegend = ({ items }) => {
    if (!items || items.length === 0) return null

    return (
      <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 mt-4 px-2">
        {items.map((item, idx) => (
          <div key={idx} className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <span
              className="block"
              style={{
                width: item.type === 'rect' ? '12px' : '16px',
                height: item.type === 'rect' ? '12px' : '2px',
                borderRadius: item.type === 'rect' ? '2px' : '0',
                backgroundColor: item.color,
                border: item.border ? `1px solid ${item.borderColor}` : 'none',
                borderStyle: item.dashed ? 'dashed' : 'solid',
                borderColor: item.color // For lines, border color is same as bg
              }}
            />
            <span>{item.label}</span>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="w-full">
      <div className="flex flex-col">
        {/* Header with Toggle */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          {/* Analyze Button - positioned on the left */}
          {analyzeButtonState.onAnalyze && (
            <Button
              onClick={analyzeButtonState.onAnalyze}
              className="gap-2"
              size="sm"
              disabled={analyzeButtonState.loading}
              variant={analyzeButtonState.loading ? "secondary" : "default"}
            >
              {analyzeButtonState.loading ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  Generating
                </>
              ) : analyzeButtonState.hasAnyAnalysis ? (
                <>
                  <RefreshCw className="h-4 w-4" />
                  Re-Analyze
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Analyze
                </>
              )}
            </Button>
          )}

          {/* Toggle Controls - positioned on the right */}
          <div className="flex flex-wrap items-center gap-4">
            {/* Time Horizon Selector */}
            <div className="flex items-center space-x-1 bg-muted p-1 rounded-lg">
              {[
                { label: '3Y', value: '3y' },
                { label: '5Y', value: '5y' },
                { label: '10Y', value: '10y' },
                { label: 'All', value: 'all' },
              ].map((opt) => (
                <Button
                  key={opt.value}
                  variant={timeHorizon === opt.value ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setTimeHorizon(opt.value)}
                  className="h-8 shadow-none px-3"
                >
                  {opt.label}
                </Button>
              ))}
            </div>

            {/* View Mode Selector */}
            <div className="flex items-center space-x-2 bg-muted p-1 rounded-lg">
              <Button
                variant={viewMode === 'annual' ? "default" : "ghost"}
                size="sm"
                onClick={() => setViewMode('annual')}
                className="h-8 shadow-none"
              >
                Annual
              </Button>
              <Button
                variant={viewMode === 'quarterly' ? "default" : "ghost"}
                size="sm"
                onClick={() => setViewMode('quarterly')}
                disabled={!quarterlyHistoryData}
                className="h-8 shadow-none"
              >
                Quarterly
              </Button>
            </div>

            {/* Character Selector */}
            <div className="flex items-center space-x-2 bg-muted p-1 rounded-lg">
              <Button
                variant={selectedCharacter === 'lynch' ? "default" : "ghost"}
                size="sm"
                onClick={() => setSelectedCharacter('lynch')}
                className="h-8 shadow-none"
              >
                Lynch
              </Button>
              <Button
                variant={selectedCharacter === 'buffett' ? "default" : "ghost"}
                size="sm"
                onClick={() => setSelectedCharacter('buffett')}
                className="h-8 shadow-none"
              >
                Buffett
              </Button>
            </div>
          </div>
        </div>

        {/* Profitability & Growth */}
        <div className="stock-charts mt-6" onMouseLeave={handleMouseLeave}>
          <UnifiedChartAnalysis
            symbol={symbol}
            character={selectedCharacter}
            onAnalysisGenerated={(result) => {
              if (result.narrative) {
                setNarrative(result.narrative)
                setAnalyses({ growth: null, cash: null, valuation: null })
              } else if (result.sections) {
                setAnalyses(result.sections)
                setNarrative(null)
              } else {
                // No analysis found for this character - clear both to show regular charts
                setNarrative(null)
                setAnalyses({ growth: null, cash: null, valuation: null })
              }
            }}
            onButtonStateChange={handleButtonStateChange}
          />

          {/* Narrative mode: render ChartNarrativeRenderer */}
          {narrative && historyData && (
            <ChartNarrativeRenderer narrative={narrative} historyData={activeData} isQuarterly={showQuarterly} />
          )}

          {/* Legacy mode: render traditional chart sections */}
          {!narrative && (loading ? (
            <div className="loading">Loading historical data...</div>
          ) : !historyData ? (
            <div className="no-data">No historical data available</div>
          ) : (
            <>
              {/* SECTION 1: Profitability & Growth */}
              <Card className="mb-6">
                <CardHeader className="pb-2">
                  <CardTitle className="text-lg font-semibold" style={{ color: '#999999' }}>Profitability & Growth</CardTitle>
                </CardHeader>
                <CardContent>

                  {/* Row 1: Revenue + Net Income */}
                  <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,350px),1fr))] gap-4 mb-4">
                    {/* Revenue */}
                    {/* Revenue */}
                    <div>
                      <div className="h-64 chart-container">
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: getExtendedLabels(),
                            datasets: [
                              {
                                label: 'Revenue (Billions)',
                                data: revenueData,
                                borderColor: 'rgb(75, 192, 192)',
                                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              },
                              // Analyst estimate projection
                              ...(hasEstimates ? [{
                                label: 'Analyst Est.',
                                data: buildEstimateData(activeData.revenue, 'revenue', 1e9),
                                borderColor: 'rgba(20, 184, 166, 0.8)',
                                backgroundColor: 'transparent',
                                borderDash: [5, 5],
                                pointRadius: 4,
                                pointStyle: 'triangle',
                                pointHoverRadius: 6,
                                spanGaps: true,
                              }] : [])
                            ]
                          }}
                          options={{
                            ...createChartOptions('Revenue', 'Billions ($)', showQuarterly),
                            plugins: {
                              ...createChartOptions('Revenue', 'Billions ($)', showQuarterly).plugins,
                              legend: {
                                display: false,
                              }
                            }
                          }}
                        />
                      </div>
                      <CustomLegend items={[
                        { label: 'Revenue', color: 'rgb(75, 192, 192)' },
                        ...(hasEstimates ? [{ label: 'Analyst Est.', color: 'rgba(20, 184, 166, 0.8)', dashed: true }] : [])
                      ]} />
                    </div>

                    {/* Slot 2: EPS (Shared) */}
                    <div>
                      <div className="h-64 chart-container">
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: getExtendedLabels(),
                            datasets: [
                              {
                                label: 'EPS ($)',
                                data: epsData,
                                borderColor: 'rgb(6, 182, 212)',
                                backgroundColor: 'rgba(6, 182, 212, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              },
                              // Analyst estimate projection
                              ...(hasEstimates ? [{
                                label: 'Analyst Est.',
                                data: buildEstimateData(activeData.eps || [], 'eps', 1),
                                borderColor: 'rgba(20, 184, 166, 0.8)',
                                backgroundColor: 'transparent',
                                borderDash: [5, 5],
                                pointRadius: 4,
                                pointStyle: 'triangle',
                                pointHoverRadius: 6,
                                spanGaps: true,
                              }] : [])
                            ]
                          }}
                          options={{
                            ...createChartOptions('Earnings Per Share', 'EPS ($)', showQuarterly),
                            plugins: {
                              ...createChartOptions('Earnings Per Share', 'EPS ($)', showQuarterly).plugins,
                              legend: {
                                display: false,
                              }
                            }
                          }}
                        />
                      </div>
                      <CustomLegend items={[
                        { label: 'EPS', color: 'rgb(6, 182, 212)' },
                        ...(hasEstimates ? [{ label: 'Analyst Est.', color: 'rgba(20, 184, 166, 0.8)', dashed: true }] : [])
                      ]} />
                    </div>
                  </div>

                  {/* Row 2: Net Income/Margin + Dividend/ROE */}
                  <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,350px),1fr))] gap-4 mb-4">
                    {/* Slot 3: Net Income (Lynch) or Net Margin (Buffett) */}
                    <div className="h-64 chart-container">
                      {isBuffett ? (
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: getExtendedLabels(),
                            datasets: [{
                              label: 'Net Margin (%)',
                              data: netMarginData,
                              borderColor: 'rgb(236, 72, 153)', // Pink
                              backgroundColor: 'rgba(236, 72, 153, 0.2)',
                              pointRadius: activeIndex !== null ? 3 : 0,
                              pointHoverRadius: 5
                            }]
                          }}
                          options={createChartOptions('Net Profit Margin', 'Margin (%)', showQuarterly)}
                        />
                      ) : (
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: getExtendedLabels(),
                            datasets: [
                              {
                                label: 'Net Income (Billions)',
                                data: netIncomeData,
                                borderColor: 'rgb(153, 102, 255)',
                                backgroundColor: 'rgba(153, 102, 255, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              }
                            ]
                          }}
                          options={createChartOptions('Net Income', 'Billions ($)', showQuarterly)}
                        />
                      )}
                    </div>

                    {/* Slot 4: Dividend Yield (Lynch) or ROE (Buffett) */}
                    <div className="h-64 chart-container">
                      {isBuffett ? (
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: getExtendedLabels(),
                            datasets: [{
                              label: 'ROE (%)',
                              data: roeData,
                              borderColor: 'rgb(245, 158, 11)', // Amber
                              backgroundColor: 'rgba(245, 158, 11, 0.2)',
                              pointRadius: activeIndex !== null ? 3 : 0,
                              pointHoverRadius: 5
                            }]
                          }}
                          options={createChartOptions('Return on Equity', 'ROE (%)', showQuarterly)}
                        />
                      ) : (
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: activeData.weekly_dividend_yields?.dates || [],
                            datasets: [
                              {
                                label: 'Dividend Yield (%)',
                                data: activeData.weekly_dividend_yields?.values || [],
                                borderColor: 'rgb(255, 205, 86)',
                                backgroundColor: 'rgba(255, 205, 86, 0.2)',
                                pointRadius: 0,
                                pointHoverRadius: 3,
                                borderWidth: 1.5,
                                tension: 0.1
                              }
                            ]
                          }}
                          options={{
                            ...createChartOptions('Dividend Yield', 'Yield (%)', showQuarterly),
                            scales: {
                              ...createChartOptions('Dividend Yield', 'Yield (%)', showQuarterly).scales,
                              x: {
                                type: 'category',
                                ticks: {
                                  callback: yearTickCallback,
                                  maxRotation: 45,
                                  minRotation: 45,
                                  autoSkip: false
                                }
                              }
                            }
                          }}
                        />
                      )}
                    </div>
                  </div>

                  {analyses.growth && <AnalysisBox content={analyses.growth} />}
                </CardContent>
              </Card>

              {/* SECTION 2: Cash & Capital Efficiency */}
              <Card className="mb-6">
                <CardHeader className="pb-2">
                  <CardTitle className="text-lg font-semibold" style={{ color: '#999999' }}>Cash & Capital Efficiency</CardTitle>
                </CardHeader>
                <CardContent>

                  {/* Row 1: Operating Cash Flow + Free Cash Flow */}
                  <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,350px),1fr))] gap-4 mb-4">
                    {/* Slot 5: Operating Cash Flow (Lynch) or Free Cash Flow (Buffett - moved from slot 6) */}
                    <div className="h-64 chart-container">
                      {isBuffett ? (
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: getExtendedLabels(),
                            datasets: [
                              {
                                label: 'Free Cash Flow (Billions)',
                                data: fcfData,
                                borderColor: 'rgb(16, 185, 129)',
                                backgroundColor: 'rgba(16, 185, 129, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              },
                            ],
                          }}
                          options={createChartOptions('Free Cash Flow', 'Billions ($)', showQuarterly)}
                        />
                      ) : (
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: getExtendedLabels(),
                            datasets: [
                              {
                                label: 'Operating Cash Flow (Billions)',
                                data: ocfData,
                                borderColor: 'rgb(54, 162, 235)',
                                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              },
                            ],
                          }}
                          options={createChartOptions('Operating Cash Flow', 'Billions ($)', showQuarterly)}
                        />
                      )}
                    </div>

                    {/* Slot 6: Free Cash Flow (Lynch) or Debt-to-Earnings (Buffett) */}
                    <div className="h-64 chart-container">
                      {isBuffett ? (
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: getExtendedLabels(),
                            datasets: [{
                              label: 'Debt-to-Earnings (Years)',
                              data: debtToEarningsData,
                              borderColor: 'rgb(244, 63, 94)', // Rose
                              backgroundColor: 'rgba(244, 63, 94, 0.2)',
                              pointRadius: activeIndex !== null ? 3 : 0,
                              pointHoverRadius: 5
                            }]
                          }}
                          options={createChartOptions('Debt-to-Earnings (Years)', 'Years', showQuarterly)}
                        />
                      ) : (
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: getExtendedLabels(),
                            datasets: [
                              {
                                label: 'Free Cash Flow (Billions)',
                                data: fcfData,
                                borderColor: 'rgb(16, 185, 129)',
                                backgroundColor: 'rgba(16, 185, 129, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              },
                            ],
                          }}
                          options={createChartOptions('Free Cash Flow', 'Billions ($)', showQuarterly)}
                        />
                      )}
                    </div>
                  </div>

                  {/* Row 2: Capital Expenditures + Debt-to-Equity */}
                  <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,350px),1fr))] gap-4 mb-4">
                    {/* Slot 7: CapEx (Lynch) or Shares Outstanding (Buffett) */}
                    <div className="h-64 chart-container">
                      {isBuffett ? (
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: getExtendedLabels(),
                            datasets: [{
                              label: 'Shares Outstanding (Billions)',
                              data: sharesDataBillion,
                              borderColor: 'rgb(59, 130, 246)', // Blue
                              backgroundColor: 'rgba(59, 130, 246, 0.2)',
                              pointRadius: activeIndex !== null ? 3 : 0,
                              pointHoverRadius: 5
                            }]
                          }}
                          options={createChartOptions('Shares Outstanding', 'Billions', showQuarterly)}
                        />
                      ) : (
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: getExtendedLabels(),
                            datasets: [
                              {
                                label: 'Capital Expenditures (Billions)',
                                data: capExData,
                                borderColor: 'rgb(239, 68, 68)',
                                backgroundColor: 'rgba(239, 68, 68, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              },
                            ],
                          }}
                          options={createChartOptions('Capital Expenditures', 'Billions ($)', showQuarterly)}
                        />
                      )}
                    </div>

                    {/* Slot 8: Debt-to-Equity (Lynch) or Book Value (Buffett) */}
                    <div className="h-64 chart-container">
                      {isBuffett ? (
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: getExtendedLabels(),
                            datasets: [{
                              label: 'Book Value Per Share ($)',
                              data: bookValueData,
                              borderColor: 'rgb(14, 165, 233)', // Sky Blue
                              backgroundColor: 'rgba(14, 165, 233, 0.2)',
                              pointRadius: activeIndex !== null ? 3 : 0,
                              pointHoverRadius: 5
                            }]
                          }}
                          options={createChartOptions('Book Value Per Share', 'BVPS ($)', showQuarterly)}
                        />
                      ) : (
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: getExtendedLabels(),
                            datasets: [
                              {
                                label: 'Debt-to-Equity Ratio',
                                data: debtToEquityData,
                                borderColor: 'rgb(255, 99, 132)',
                                backgroundColor: 'rgba(255, 99, 132, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              }
                            ]
                          }}
                          options={createChartOptions('Debt-to-Equity', 'D/E Ratio', showQuarterly)}
                        />
                      )}
                    </div>
                  </div>

                  {analyses.cash && <AnalysisBox content={analyses.cash} />}
                </CardContent>
              </Card>

              {/* SECTION 3: Market Valuation */}
              <Card className="mb-6">
                <CardHeader className="pb-2">
                  <CardTitle className="text-lg font-semibold" style={{ color: '#999999' }}>Market Valuation</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,350px),1fr))] gap-4 mb-4">
                    {/* Stock Price - Uses weekly data for granular display */}
                    <div>
                      <div className="h-64 chart-container">
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: activeData.weekly_prices?.dates?.length > 0
                              ? activeData.weekly_prices.dates
                              : labels,
                            datasets: [
                              {
                                label: 'Stock Price ($)',
                                data: activeData.weekly_prices?.prices?.length > 0
                                  ? activeData.weekly_prices.prices
                                  : activeData.price,
                                borderColor: 'rgb(255, 159, 64)',
                                backgroundColor: 'rgba(255, 159, 64, 0.2)',
                                pointRadius: 0,
                                pointHoverRadius: 3,
                                borderWidth: 1.5,
                                tension: 0.1,
                                spanGaps: true
                              },
                              // Price target mean line
                              ...(historyData.price_targets?.mean ? [{
                                label: 'Analyst Target (Mean)',
                                data: (activeData.weekly_prices?.dates || labels).map(() => historyData.price_targets.mean),
                                borderColor: 'rgba(16, 185, 129, 0.7)',
                                backgroundColor: 'transparent',
                                borderDash: [8, 4],
                                borderWidth: 2,
                                pointRadius: 0,
                                fill: false,
                              }] : []),
                              // Price target high line (upper bound)
                              ...(historyData.price_targets?.high ? [{
                                label: 'Target Range',
                                data: (activeData.weekly_prices?.dates || labels).map(() => historyData.price_targets.high),
                                borderColor: 'rgba(16, 185, 129, 0.3)',
                                backgroundColor: 'rgba(16, 185, 129, 0.15)',
                                borderWidth: 1,
                                pointRadius: 0,
                                fill: {
                                  target: '+1',  // Fill to the next dataset (low)
                                  above: 'rgba(16, 185, 129, 0.15)',
                                },
                              }] : []),
                              // Price target low line (lower bound)
                              ...(historyData.price_targets?.low ? [{
                                label: 'Target Low',
                                data: (activeData.weekly_prices?.dates || labels).map(() => historyData.price_targets.low),
                                borderColor: 'rgba(16, 185, 129, 0.3)',
                                backgroundColor: 'transparent',
                                borderWidth: 1,
                                pointRadius: 0,
                                fill: false,
                              }] : []),
                            ],
                          }}
                          options={{
                            ...createChartOptions('Stock Price', 'Price ($)', showQuarterly),
                            plugins: {
                              ...createChartOptions('Stock Price', 'Price ($)', showQuarterly).plugins,
                              legend: {
                                display: false,
                              }
                            },
                            scales: {
                              ...createChartOptions('Stock Price', 'Price ($)', showQuarterly).scales,
                              x: {
                                type: 'category',
                                ticks: {
                                  callback: yearTickCallback,
                                  maxRotation: 45,
                                  minRotation: 45,
                                  autoSkip: false
                                }
                              }
                            }
                          }}
                        />
                      </div>
                      <CustomLegend items={[
                        { label: 'Stock Price', color: 'rgb(255, 159, 64)' },
                        ...(historyData.price_targets?.mean ? [{ label: 'Analyst Target (Mean)', color: 'rgba(16, 185, 129, 0.7)', dashed: true }] : []),
                        ...(historyData.price_targets?.high ? [{ label: 'Target Range', color: 'rgba(16, 185, 129, 0.3)', type: 'rect' }] : [])
                      ]} />
                    </div>

                    {/* P/E Ratio - Uses weekly data for granular display */}
                    <div>
                      {(() => {
                        const weeklyPE = activeData?.weekly_pe_ratios
                        const useWeeklyPE = weeklyPE?.dates?.length > 0 && weeklyPE?.values?.length > 0
                        const peLabels = useWeeklyPE ? weeklyPE.dates : labels
                        const peData = useWeeklyPE ? weeklyPE.values : activeData?.pe_ratio

                        // Calculate 13-week rolling average (using partial windows at the start)
                        const peSMA13 = (() => {
                          if (!useWeeklyPE || !peData || peData.length < 1) return []

                          const windowSize = 13
                          const sma = []

                          for (let i = 0; i < peData.length; i++) {
                            // Use smaller window at the start (1, 2, 3... up to windowSize)
                            const actualWindowSize = Math.min(i + 1, windowSize)
                            const windowinfo = peData.slice(Math.max(0, i - actualWindowSize + 1), i + 1)
                            const validValues = windowinfo.filter(v => v !== null && v !== undefined)

                            if (validValues.length === 0) {
                              sma.push(null)
                            } else {
                              const sum = validValues.reduce((a, b) => a + b, 0)
                              sma.push(sum / validValues.length)
                            }
                          }
                          return sma
                        })()

                        // Calculate 52-week rolling average (using partial windows at the start)
                        const peSMA52 = (() => {
                          if (!useWeeklyPE || !peData || peData.length < 1) return []

                          const windowSize = 52
                          const sma = []

                          for (let i = 0; i < peData.length; i++) {
                            // Use smaller window at the start (1, 2, 3... up to windowSize)
                            const actualWindowSize = Math.min(i + 1, windowSize)
                            const windowinfo = peData.slice(Math.max(0, i - actualWindowSize + 1), i + 1)
                            const validValues = windowinfo.filter(v => v !== null && v !== undefined)

                            if (validValues.length === 0) {
                              sma.push(null)
                            } else {
                              const sum = validValues.reduce((a, b) => a + b, 0)
                              sma.push(sum / validValues.length)
                            }
                          }
                          return sma
                        })()

                        return (
                          <>
                            <div className="h-64 chart-container">
                              <Line
                                key={useWeeklyPE ? 'weekly' : 'annual'}
                                plugins={[zeroLinePlugin, crosshairPlugin]}
                                data={{
                                  labels: peLabels,
                                  datasets: [
                                    {
                                      label: 'P/E Ratio',
                                      data: peData,
                                      borderColor: 'rgb(168, 85, 247)',
                                      backgroundColor: 'rgba(168, 85, 247, 0.2)',
                                      pointRadius: 0,
                                      pointHoverRadius: 3,
                                      borderWidth: 1.5,
                                      tension: 0.1,
                                      spanGaps: true
                                    },
                                    // Add 13-Week Rolling Average Dataset
                                    ...(useWeeklyPE && peSMA13.length > 0 ? [{
                                      label: '13-Week Avg',
                                      data: peSMA13,
                                      borderColor: 'rgba(75, 192, 192, 0.8)', // Teal with 80% opacity
                                      backgroundColor: 'transparent',
                                      pointRadius: 0,
                                      pointHoverRadius: 0,
                                      borderWidth: 2,
                                      tension: 0.2,
                                      spanGaps: true
                                    }] : []),
                                    // Add 52-Week Rolling Average Dataset
                                    ...(useWeeklyPE && peSMA52.length > 0 ? [{
                                      label: '52-Week Avg',
                                      data: peSMA52,
                                      borderColor: 'rgba(168, 85, 247, 0.5)', // Purple with 50% opacity
                                      backgroundColor: 'transparent',
                                      borderDash: [5, 5], // Dashed line
                                      pointRadius: 0,
                                      pointHoverRadius: 0,
                                      borderWidth: 2.5,
                                      tension: 0.3,
                                      spanGaps: true
                                    }] : [])
                                  ]
                                }}
                                options={{
                                  ...createChartOptions('P/E Ratio', 'P/E', showQuarterly),
                                  scales: {
                                    ...createChartOptions('P/E Ratio', 'P/E', showQuarterly).scales,
                                    x: {
                                      type: 'category',
                                      ticks: {
                                        callback: yearTickCallback,
                                        maxRotation: 45,
                                        minRotation: 45,
                                        autoSkip: true,
                                        maxTicksLimit: 20
                                      }
                                    }
                                  }
                                }}
                              />
                            </div>
                            <CustomLegend items={[
                              { label: 'P/E Ratio', color: 'rgb(168, 85, 247)' },
                              ...(useWeeklyPE && peSMA13.length > 0 ? [{ label: '13-Week Avg', color: 'rgba(75, 192, 192, 0.8)' }] : []),
                              ...(useWeeklyPE && peSMA52.length > 0 ? [{ label: '52-Week Avg', color: 'rgba(168, 85, 247, 0.5)', dashed: true }] : [])
                            ]} />
                          </>
                        )
                      })()}
                    </div>
                  </div>

                  {analyses.valuation && <AnalysisBox content={analyses.valuation} />}
                </CardContent>
              </Card>
            </>
          ))}
        </div>
      </div>
    </div>
  )
}
