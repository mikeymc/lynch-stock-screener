// ABOUTME: Stock charts component displaying 8 financial metrics over time
// ABOUTME: Shows Revenue, Net Income, P/E Ratio, Debt-to-Equity, Dividends, Stock Price, Free Cash Flow, and Capital Expenditures charts in a grid layout

import { Line } from 'react-chartjs-2'

export default function StockCharts({ historyData, loading }) {
  if (loading) {
    return <div className="loading">Loading historical data...</div>
  }

  if (!historyData) {
    return null
  }

  const labels = historyData.labels || historyData.years || []

  return (
    <div className="charts-grid">
      <div className="chart-container">
        <Line
          data={{
            labels: labels,
            datasets: [
              {
                label: 'Revenue (Billions)',
                data: historyData.revenue.map(r => r / 1e9),
                borderColor: 'rgb(75, 192, 192)',
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
              }
            ]
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              title: {
                display: true,
                text: 'Revenue',
                font: { size: 14 }
              },
              legend: {
                display: false
              }
            },
            scales: {
              y: {
                title: {
                  display: true,
                  text: 'Billions ($)'
                }
              }
            }
          }}
        />
      </div>

      <div className="chart-container">
        <Line
          data={{
            labels: labels,
            datasets: [
              {
                label: 'Net Income (Billions)',
                data: historyData.net_income ? historyData.net_income.map(ni => ni ? ni / 1e9 : null) : [],
                borderColor: 'rgb(255, 99, 132)',
                backgroundColor: 'rgba(255, 99, 132, 0.2)',
                pointBackgroundColor: historyData.net_income ? historyData.net_income.map(ni => ni && ni < 0 ? 'rgb(239, 68, 68)' : 'rgb(255, 99, 132)') : [],
                pointBorderColor: historyData.net_income ? historyData.net_income.map(ni => ni && ni < 0 ? 'rgb(239, 68, 68)' : 'rgb(255, 99, 132)') : [],
                pointRadius: 4,
                segment: {
                  borderColor: ctx => {
                    const value = ctx.p0.parsed.y;
                    return value < 0 ? 'rgb(239, 68, 68)' : 'rgb(255, 99, 132)';
                  }
                }
              }
            ]
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              title: {
                display: true,
                text: 'Net Income',
                font: { size: 14 }
              },
              legend: {
                display: false
              }
            },
            scales: {
              y: {
                title: {
                  display: true,
                  text: 'Billions ($)'
                },
                grid: {
                  color: (context) => {
                    if (context.tick.value === 0) {
                      return 'rgba(255, 255, 255, 0.3)';
                    }
                    return 'rgba(255, 255, 255, 0.1)';
                  },
                  lineWidth: (context) => {
                    if (context.tick.value === 0) {
                      return 2;
                    }
                    return 1;
                  }
                }
              }
            }
          }}
        />
      </div>

      <div className="chart-container">
        <Line
          data={{
            labels: labels,
            datasets: [
              {
                label: 'P/E Ratio',
                data: historyData.pe_ratio,
                borderColor: 'rgb(153, 102, 255)',
                backgroundColor: 'rgba(153, 102, 255, 0.2)',
              },
              {
                label: 'Zero Baseline',
                data: labels.map(() => 0),
                borderColor: 'rgba(255, 255, 255, 0.3)',
                borderDash: [5, 5],
                pointRadius: 0,
                borderWidth: 1,
                fill: false,
                order: 1
              }
            ]
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              title: {
                display: true,
                text: 'Price-to-Earnings Ratio',
                font: { size: 14 }
              },
              legend: {
                display: false
              }
            },
            scales: {
              y: {
                title: {
                  display: true,
                  text: 'P/E Ratio'
                }
              }
            }
          }}
        />
      </div>

      <div className="chart-container">
        <Line
          data={{
            labels: labels,
            datasets: [
              {
                label: 'Debt-to-Equity',
                data: historyData.debt_to_equity,
                borderColor: 'rgb(255, 159, 64)',
                backgroundColor: 'rgba(255, 159, 64, 0.2)',
              }
            ]
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              title: {
                display: true,
                text: 'Debt-to-Equity Ratio',
                font: { size: 14 }
              },
              legend: {
                display: false
              }
            },
            scales: {
              y: {
                title: {
                  display: true,
                  text: 'D/E Ratio'
                }
              }
            }
          }}
        />
      </div>

      <div className="chart-container">
        <Line
          data={{
            labels: labels,
            datasets: [
              {
                label: 'Dividend Yield (%)',
                data: historyData.dividend_yield,
                borderColor: 'rgb(54, 162, 235)',
                backgroundColor: 'rgba(54, 162, 235, 0.2)',
              }
            ]
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              title: {
                display: true,
                text: 'Dividend Yield',
                font: { size: 14 }
              },
              legend: {
                display: false
              },
              tooltip: {
                callbacks: {
                  label: function (context) {
                    let label = context.dataset.label || '';
                    if (label) {
                      label += ': ';
                    }
                    if (context.parsed.y !== null) {
                      label += context.parsed.y.toFixed(2) + '%';
                    }
                    return label;
                  }
                }
              }
            },
            scales: {
              y: {
                title: {
                  display: true,
                  text: 'Yield (%)'
                }
              }
            }
          }}
        />
      </div>

      <div className="chart-container">
        <Line
          data={{
            labels: labels,
            datasets: [
              {
                label: 'Stock Price ($)',
                data: historyData.price,
                borderColor: 'rgb(255, 159, 64)',
                backgroundColor: 'rgba(255, 159, 64, 0.2)',
              },
            ],
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              title: {
                display: true,
                text: 'Stock Price History',
                font: { size: 14 }
              },
              legend: {
                display: false
              }
            },
            scales: {
              y: {
                title: {
                  display: true,
                  text: 'Price ($)'
                }
              }
            }
          }}
        />
      </div>

      <div className="chart-container">
        <Line
          data={{
            labels: labels,
            datasets: [
              {
                label: 'Free Cash Flow (Billions)',
                data: historyData.free_cash_flow?.map(fcf => fcf ? fcf / 1e9 : null) || [],
                borderColor: 'rgb(34, 197, 94)',
                backgroundColor: 'rgba(34, 197, 94, 0.2)',
              },
            ],
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              title: {
                display: true,
                text: 'Free Cash Flow',
                font: { size: 14 }
              },
              legend: {
                display: false
              }
            },
            scales: {
              y: {
                title: {
                  display: true,
                  text: 'Billions ($)'
                }
              }
            }
          }}
        />
      </div>

      <div className="chart-container">
        <Line
          data={{
            labels: labels,
            datasets: [
              {
                label: 'Capital Expenditures (Billions)',
                data: historyData.capital_expenditures?.map(capex => capex ? Math.abs(capex) / 1e9 : null) || [],
                borderColor: 'rgb(239, 68, 68)',
                backgroundColor: 'rgba(239, 68, 68, 0.2)',
              },
            ],
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              title: {
                display: true,
                text: 'Capital Expenditures',
                font: { size: 14 }
              },
              legend: {
                display: false
              }
            },
            scales: {
              y: {
                title: {
                  display: true,
                  text: 'Billions ($)'
                }
              }
            }
          }}
        />
      </div>
    </div>
  )
}
