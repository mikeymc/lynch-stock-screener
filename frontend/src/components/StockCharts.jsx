// ABOUTME: Stock charts component displaying 9 financial metrics in a 3x3 grid
// ABOUTME: Top row: Growth & Profitability, Middle row: Cash Management, Bottom row: Market Valuation & Risk

import { useState, useCallback } from 'react'
import { Line } from 'react-chartjs-2'
import UnifiedChartAnalysis from './UnifiedChartAnalysis'
import ReactMarkdown from 'react-markdown'
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

export default function StockCharts({ historyData, loading, symbol }) {
  const [activeIndex, setActiveIndex] = useState(null)
  const [analyses, setAnalyses] = useState({ growth: null, cash: null, valuation: null })

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

  // Plugin to draw a dashed zero line
  const zeroLinePlugin = {
    id: 'zeroLine',
    beforeDraw: (chart) => {
      const ctx = chart.ctx;
      const yAxis = chart.scales.y;
      const xAxis = chart.scales.x;

      // Check if 0 is visible on the y-axis
      if (yAxis.min <= 0 && yAxis.max >= 0) {
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

      // Get the dataset meta to find the x-coordinate of the point at the active index
      const meta = chart.getDatasetMeta(0);
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
          {/* SECTION 1: Growth & Profitability */}
          <div className="chart-section">
            <h3 className="section-title">Growth & Profitability</h3>
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
                        pointRadius: activeIndex !== null ? 3 : 0, // Show points only on hover/active
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
            </div>
            {analyses.growth && (
              <div style={{ marginTop: '1rem', padding: '1rem', backgroundColor: '#1e293b', borderRadius: '0.5rem', border: '1px solid #334155' }}>
                <div className="markdown-content">
                  <ReactMarkdown>{analyses.growth}</ReactMarkdown>
                </div>
              </div>
            )}
          </div>

          {/* SECTION 2: Cash Management */}
          <div className="chart-section">
            <h3 className="section-title">Cash Management</h3>
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

              {/* Dividend Yield */}
              <div className="chart-container">
                <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                  data={{
                    labels: labels,
                    datasets: [
                      {
                        label: 'Dividend Yield (%)',
                        data: historyData.dividend_yield,
                        borderColor: 'rgb(255, 205, 86)',
                        backgroundColor: 'rgba(255, 205, 86, 0.2)',
                        pointRadius: activeIndex !== null ? 3 : 0,
                        pointHoverRadius: 5
                      }
                    ]
                  }}
                  options={createChartOptions('Dividend Yield', 'Yield (%)')}
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

          {/* SECTION 3: Market Valuation & Risk */}
          <div className="chart-section">
            <h3 className="section-title">Market Valuation & Risk</h3>
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
                        pointRadius: 0, // Hide points for dense weekly data
                        pointHoverRadius: 3,
                        borderWidth: 1.5,
                        tension: 0.1 // Slight smoothing
                      },
                    ],
                  }}
                  options={{
                    ...createChartOptions('Stock Price', 'Price ($)'),
                    scales: {
                      ...createChartOptions('Stock Price', 'Price ($)').scales,
                      x: {
                        type: 'category',
                        ticks: {
                          // Show only year labels, not every week
                          callback: function (value, index, values) {
                            const label = this.getLabelForValue(value);
                            // For weekly data, only show label if it's January (first week of year)
                            if (historyData.weekly_prices?.dates?.length > 0) {
                              if (label && label.includes('-01-')) {
                                return label.substring(0, 4); // Return just the year
                              }
                              return null; // Hide other labels
                            }
                            return label; // For annual data, show as-is
                          },
                          maxRotation: 0,
                          autoSkip: true,
                          maxTicksLimit: 12
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
                        pointRadius: 0, // Hide points for dense weekly data
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
                        ticks: {
                          callback: function (value, index, values) {
                            const label = this.getLabelForValue(value);
                            if (historyData.weekly_pe_ratios?.dates?.length > 0) {
                              if (label && label.includes('-01-')) {
                                return label.substring(0, 4);
                              }
                              return null;
                            }
                            return label;
                          },
                          maxRotation: 0,
                          autoSkip: true,
                          maxTicksLimit: 12
                        }
                      }
                    }
                  }}
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
            {analyses.valuation && (
              <div style={{ marginTop: '1rem', padding: '1rem', backgroundColor: '#1e293b', borderRadius: '0.5rem', border: '1px solid #334155' }}>
                <div className="markdown-content">
                  <ReactMarkdown>{analyses.valuation}</ReactMarkdown>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
