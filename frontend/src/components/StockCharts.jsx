// ABOUTME: Stock charts component displaying 10 financial metrics in 3 thematic sections
// ABOUTME: Two-column layout: charts left (2/3), chat sidebar right (1/3)

import { useState, useCallback, useRef } from 'react'
import { Line } from 'react-chartjs-2'
import UnifiedChartAnalysis from './UnifiedChartAnalysis'
import ReactMarkdown from 'react-markdown'
import AnalysisChat from './AnalysisChat'
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

  // Extract year from date string (assumes YYYY-MM-DD format)
  const year = label.substring(0, 4)

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

export default function StockCharts({ historyData, loading, symbol }) {
  const [activeIndex, setActiveIndex] = useState(null)
  const [analyses, setAnalyses] = useState({ growth: null, cash: null, valuation: null })
  const chatRef = useRef(null)

  const handleHover = useCallback((event, elements) => {
    if (elements && elements.length > 0) {
      const index = elements[0].index;
      if (index !== activeIndex) {
        setActiveIndex(index);
      }
    }
  }, [activeIndex]);

  const handleMouseLeave = useCallback(() => {
    setActiveIndex(null);
  }, []);

  const labels = historyData?.labels || historyData?.years || []

  // Find the last year in historical data (extract year from label like "2024" or "2024 Q4")
  const getYearFromLabel = (label) => {
    if (!label) return null
    const match = String(label).match(/^(\d{4})/)
    return match ? parseInt(match[1]) : null
  }

  const lastHistoricalYear = labels.length > 0
    ? Math.max(...labels.map(getYearFromLabel).filter(y => y !== null))
    : new Date().getFullYear() - 1

  const hasEstimates = historyData?.analyst_estimates?.next_year  // Only show next year estimate

  // Build labels with ONE future estimate year appended (year after last historical)
  const getExtendedLabels = () => {
    if (!hasEstimates) return labels

    const baseLabels = [...labels]
    const estimateYear = lastHistoricalYear + 1

    // Only add if this year isn't already in the data
    const yearExists = labels.some(l => getYearFromLabel(l) === estimateYear)
    if (!yearExists) {
      baseLabels.push(`${estimateYear}E`)
    }

    return baseLabels
  }

  // Build estimate data array - only for the year AFTER historical data
  const buildEstimateData = (historicalData, estimateType, scaleFactor = 1) => {
    if (!hasEstimates) return historicalData.map(() => null)

    const estimates = historyData?.analyst_estimates
    const extLabels = getExtendedLabels()

    // Start with nulls for all positions
    const estimateData = new Array(extLabels.length).fill(null)

    // Find the estimate year position
    const estimateYear = lastHistoricalYear + 1
    const estimateYearIdx = extLabels.findIndex(l => l === `${estimateYear}E`)

    if (estimateYearIdx >= 0 && estimates?.next_year) {
      const estValue = estimates.next_year[`${estimateType}_avg`]
      if (estValue != null) {
        estimateData[estimateYearIdx] = estValue / scaleFactor

        // Connect from the last historical point for line continuity
        if (historicalData.length > 0 && estimateYearIdx > 0) {
          const lastHistorical = historicalData[historicalData.length - 1]
          if (lastHistorical != null) {
            estimateData[estimateYearIdx - 1] = lastHistorical / scaleFactor
          }
        }
      }
    }

    return estimateData
  }

  // Helper function to create chart options
  const createChartOptions = (title, yAxisLabel) => ({
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
        font: { size: 14 }
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
          minRotation: 45
        }
      },
      y: {
        title: {
          display: true,
          text: yAxisLabel
        },
        grid: {
          color: (context) => {
            // Hide default zero line so we can draw our own
            if (Math.abs(context.tick.value) < 0.00001) {
              return 'transparent';
            }
            return 'rgba(255, 255, 255, 0.1)';
          }
        }
      }
    }
  })

  // Styled analysis box component
  const AnalysisBox = ({ content }) => (
    <div style={{ marginTop: '1rem', padding: '1rem', backgroundColor: '#1e293b', borderRadius: '0.5rem', border: '1px solid #334155' }}>
      <div className="markdown-content">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </div>
  )

  return (
    <div className="reports-layout">
      {/* Left Column - Charts Content (2/3) */}
      <div className="reports-main-column">
        <div className="section-item">
          <div className="section-content">
            <div className="stock-charts" onMouseLeave={handleMouseLeave}>
              <UnifiedChartAnalysis
                symbol={symbol}
                onAnalysisGenerated={(sections) => setAnalyses(sections)}
              />

              {loading ? (
                <div className="loading">Loading historical data...</div>
              ) : !historyData ? (
                <div className="no-data">No historical data available</div>
              ) : (
                <>
                  {/* SECTION 1: Profitability & Growth */}
                  <div className="chart-section">
                    <h3 className="section-title">Profitability & Growth</h3>

                    {/* Row 1: Revenue + Net Income */}
                    <div className="charts-row">
                      {/* Revenue */}
                      <div className="chart-container">
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: getExtendedLabels(),
                            datasets: [
                              {
                                label: 'Revenue (Billions)',
                                data: historyData.revenue.map(r => r / 1e9),
                                borderColor: 'rgb(75, 192, 192)',
                                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              },
                              // Analyst estimate projection
                              ...(hasEstimates ? [{
                                label: 'Analyst Est.',
                                data: buildEstimateData(historyData.revenue, 'revenue', 1e9),
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
                            ...createChartOptions('Revenue', 'Billions ($)'),
                            plugins: {
                              ...createChartOptions('Revenue', 'Billions ($)').plugins,
                              legend: {
                                display: hasEstimates,
                              }
                            }
                          }}
                        />
                      </div>

                      {/* Net Income */}
                      <div className="chart-container">
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: labels,
                            datasets: [
                              {
                                label: 'Net Income (Billions)',
                                data: historyData.net_income?.map(ni => ni ? ni / 1e9 : null) || [],
                                borderColor: 'rgb(153, 102, 255)',
                                backgroundColor: 'rgba(153, 102, 255, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              }
                            ]
                          }}
                          options={createChartOptions('Net Income', 'Billions ($)')}
                        />
                      </div>
                    </div>

                    {/* Row 2: EPS + Dividend Yield */}
                    <div className="charts-row">
                      {/* EPS */}
                      <div className="chart-container">
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: getExtendedLabels(),
                            datasets: [
                              {
                                label: 'EPS ($)',
                                data: historyData.eps || [],
                                borderColor: 'rgb(6, 182, 212)',
                                backgroundColor: 'rgba(6, 182, 212, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              },
                              // Analyst estimate projection
                              ...(hasEstimates ? [{
                                label: 'Analyst Est.',
                                data: buildEstimateData(historyData.eps || [], 'eps', 1),
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
                            ...createChartOptions('Earnings Per Share', 'EPS ($)'),
                            plugins: {
                              ...createChartOptions('Earnings Per Share', 'EPS ($)').plugins,
                              legend: {
                                display: hasEstimates,
                              }
                            }
                          }}
                        />
                      </div>

                      {/* Dividend Yield - Uses weekly data for granular display */}
                      <div className="chart-container">
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: historyData.weekly_dividend_yields?.dates || [],
                            datasets: [
                              {
                                label: 'Dividend Yield (%)',
                                data: historyData.weekly_dividend_yields?.values || [],
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
                            ...createChartOptions('Dividend Yield', 'Yield (%)'),
                            scales: {
                              ...createChartOptions('Dividend Yield', 'Yield (%)').scales,
                              x: {
                                type: 'category',
                                grid: {
                                  display: false
                                },
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
                    </div>

                    {analyses.growth && <AnalysisBox content={analyses.growth} />}
                  </div>

                  {/* SECTION 2: Cash & Capital Efficiency */}
                  <div className="chart-section">
                    <h3 className="section-title">Cash & Capital Efficiency</h3>

                    {/* Row 1: Operating Cash Flow + Free Cash Flow */}
                    <div className="charts-row">
                      {/* Operating Cash Flow */}
                      <div className="chart-container">
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: labels,
                            datasets: [
                              {
                                label: 'Operating Cash Flow (Billions)',
                                data: historyData.operating_cash_flow?.map(ocf => ocf ? ocf / 1e9 : null) || [],
                                borderColor: 'rgb(54, 162, 235)',
                                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              },
                            ],
                          }}
                          options={createChartOptions('Operating Cash Flow', 'Billions ($)')}
                        />
                      </div>

                      {/* Free Cash Flow */}
                      <div className="chart-container">
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: labels,
                            datasets: [
                              {
                                label: 'Free Cash Flow (Billions)',
                                data: historyData.free_cash_flow?.map(fcf => fcf ? fcf / 1e9 : null) || [],
                                borderColor: 'rgb(34, 197, 94)',
                                backgroundColor: 'rgba(34, 197, 94, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              },
                            ],
                          }}
                          options={createChartOptions('Free Cash Flow', 'Billions ($)')}
                        />
                      </div>
                    </div>

                    {/* Row 2: Capital Expenditures + Debt-to-Equity */}
                    <div className="charts-row">
                      {/* Capital Expenditures */}
                      <div className="chart-container">
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: labels,
                            datasets: [
                              {
                                label: 'Capital Expenditures (Billions)',
                                data: historyData.capital_expenditures?.map(capex => capex ? Math.abs(capex) / 1e9 : null) || [],
                                borderColor: 'rgb(239, 68, 68)',
                                backgroundColor: 'rgba(239, 68, 68, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              },
                            ],
                          }}
                          options={createChartOptions('Capital Expenditures', 'Billions ($)')}
                        />
                      </div>

                      {/* Debt-to-Equity */}
                      <div className="chart-container">
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: labels,
                            datasets: [
                              {
                                label: 'Debt-to-Equity Ratio',
                                data: historyData.debt_to_equity,
                                borderColor: 'rgb(255, 99, 132)',
                                backgroundColor: 'rgba(255, 99, 132, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              }
                            ]
                          }}
                          options={createChartOptions('Debt-to-Equity', 'D/E Ratio')}
                        />
                      </div>
                    </div>

                    {analyses.cash && <AnalysisBox content={analyses.cash} />}
                  </div>

                  {/* SECTION 3: Market Valuation */}
                  <div className="chart-section">
                    <h3 className="section-title">Market Valuation</h3>
                    <div className="charts-row">
                      {/* Stock Price - Uses weekly data for granular display */}
                      <div className="chart-container">
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: historyData.weekly_prices?.dates?.length > 0
                              ? historyData.weekly_prices.dates
                              : labels,
                            datasets: [
                              {
                                label: 'Stock Price ($)',
                                data: historyData.weekly_prices?.prices?.length > 0
                                  ? historyData.weekly_prices.prices
                                  : historyData.price,
                                borderColor: 'rgb(255, 159, 64)',
                                backgroundColor: 'rgba(255, 159, 64, 0.2)',
                                pointRadius: 0,
                                pointHoverRadius: 3,
                                borderWidth: 1.5,
                                tension: 0.1
                              },
                              // Price target mean line
                              ...(historyData.price_targets?.mean ? [{
                                label: 'Analyst Target (Mean)',
                                data: (historyData.weekly_prices?.dates || labels).map(() => historyData.price_targets.mean),
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
                                data: (historyData.weekly_prices?.dates || labels).map(() => historyData.price_targets.high),
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
                                data: (historyData.weekly_prices?.dates || labels).map(() => historyData.price_targets.low),
                                borderColor: 'rgba(16, 185, 129, 0.3)',
                                backgroundColor: 'transparent',
                                borderWidth: 1,
                                pointRadius: 0,
                                fill: false,
                              }] : []),
                            ],
                          }}
                          options={{
                            ...createChartOptions('Stock Price', 'Price ($)'),
                            plugins: {
                              ...createChartOptions('Stock Price', 'Price ($)').plugins,
                              legend: {
                                display: historyData.price_targets?.mean ? true : false,
                                labels: {
                                  filter: (item) => item.text === 'Stock Price ($)' || item.text === 'Analyst Target (Mean)' || item.text === 'Target Range'
                                }
                              }
                            },
                            scales: {
                              ...createChartOptions('Stock Price', 'Price ($)').scales,
                              x: {
                                type: 'category',
                                grid: {
                                  display: false
                                },
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

                      {/* P/E Ratio - Uses weekly data for granular display */}
                      <div className="chart-container">
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: historyData.weekly_pe_ratios?.dates?.length > 0
                              ? historyData.weekly_pe_ratios.dates
                              : labels,
                            datasets: [
                              {
                                label: 'P/E Ratio',
                                data: historyData.weekly_pe_ratios?.values?.length > 0
                                  ? historyData.weekly_pe_ratios.values
                                  : historyData.pe_ratio,
                                borderColor: 'rgb(201, 203, 207)',
                                backgroundColor: 'rgba(201, 203, 207, 0.2)',
                                pointRadius: 0,
                                pointHoverRadius: 3,
                                borderWidth: 1.5,
                                tension: 0.1
                              }
                            ]
                          }}
                          options={{
                            ...createChartOptions('P/E Ratio', 'P/E Ratio'),
                            scales: {
                              ...createChartOptions('P/E Ratio', 'P/E Ratio').scales,
                              x: {
                                type: 'category',
                                grid: {
                                  display: false
                                },
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
                    </div>

                    {analyses.valuation && <AnalysisBox content={analyses.valuation} />}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Right Column - Chat Sidebar (1/3) */}
      <div className="reports-chat-sidebar">
        <div className="chat-sidebar-content">
          <AnalysisChat ref={chatRef} symbol={symbol} chatOnly={true} contextType="charts" />
        </div>
      </div>
    </div>
  )
}
