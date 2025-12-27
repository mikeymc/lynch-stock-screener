// ABOUTME: Stock charts component displaying 10 financial metrics in 5 rows of 2
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
} from 'chart.js'

// Register ChartJS components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
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

  return (
    <div className="reports-layout">
      {/* Left Column - Charts Content (2/3) */}
      <div className="reports-main-column">
        <div className="section-item">
          <div className="section-header-simple">
            <span className="section-title">Financial Charts</span>
          </div>
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
                  {/* SECTION 1: Income Statement */}
                  <div className="chart-section">
                    <h3 className="section-title">Income Statement</h3>
                    <div className="charts-row">
                      {/* Revenue */}
                      <div className="chart-container">
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: labels,
                            datasets: [
                              {
                                label: 'Revenue (Billions)',
                                data: historyData.revenue.map(r => r / 1e9),
                                borderColor: 'rgb(75, 192, 192)',
                                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              }
                            ]
                          }}
                          options={createChartOptions('Revenue', 'Billions ($)')}
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
                    {analyses.growth && (
                      <div style={{ marginTop: '1rem', padding: '1rem', backgroundColor: '#1e293b', borderRadius: '0.5rem', border: '1px solid #334155' }}>
                        <div className="markdown-content">
                          <ReactMarkdown>{analyses.growth}</ReactMarkdown>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* SECTION 2: Cash Flow */}
                  <div className="chart-section">
                    <h3 className="section-title">Cash Flow</h3>
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
                    {analyses.cash && (
                      <div style={{ marginTop: '1rem', padding: '1rem', backgroundColor: '#1e293b', borderRadius: '0.5rem', border: '1px solid #334155' }}>
                        <div className="markdown-content">
                          <ReactMarkdown>{analyses.cash}</ReactMarkdown>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* SECTION 3: Capital & Leverage */}
                  <div className="chart-section">
                    <h3 className="section-title">Capital & Leverage</h3>
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
                  </div>

                  {/* SECTION 4: Market Valuation */}
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
                            ],
                          }}
                          options={{
                            ...createChartOptions('Stock Price', 'Price ($)'),
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
                    {analyses.valuation && (
                      <div style={{ marginTop: '1rem', padding: '1rem', backgroundColor: '#1e293b', borderRadius: '0.5rem', border: '1px solid #334155' }}>
                        <div className="markdown-content">
                          <ReactMarkdown>{analyses.valuation}</ReactMarkdown>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* SECTION 5: Per-Share Returns */}
                  <div className="chart-section">
                    <h3 className="section-title">Per-Share Returns</h3>
                    <div className="charts-row">
                      {/* EPS */}
                      <div className="chart-container">
                        <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                          data={{
                            labels: labels,
                            datasets: [
                              {
                                label: 'EPS ($)',
                                data: historyData.eps || [],
                                borderColor: 'rgb(6, 182, 212)',
                                backgroundColor: 'rgba(6, 182, 212, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                              }
                            ]
                          }}
                          options={createChartOptions('Earnings Per Share', 'EPS ($)')}
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
          <AnalysisChat ref={chatRef} symbol={symbol} chatOnly={true} />
        </div>
      </div>
    </div>
  )
}
