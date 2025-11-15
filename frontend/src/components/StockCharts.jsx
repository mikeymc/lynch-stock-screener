// ABOUTME: Stock charts component displaying 4 financial metrics over time
// ABOUTME: Shows Revenue, EPS, P/E Ratio, and Debt-to-Equity charts in a grid layout

import { Line } from 'react-chartjs-2'

export default function StockCharts({ historyData, loading }) {
  if (loading) {
    return <div className="loading">Loading historical data...</div>
  }

  if (!historyData) {
    return null
  }

  return (
    <div className="charts-grid">
      <div className="chart-container">
        <Line
          data={{
            labels: historyData.years,
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
            labels: historyData.years,
            datasets: [
              {
                label: 'EPS',
                data: historyData.eps,
                borderColor: 'rgb(255, 99, 132)',
                backgroundColor: 'rgba(255, 99, 132, 0.2)',
                pointBackgroundColor: historyData.eps.map(eps => eps < 0 ? 'rgb(239, 68, 68)' : 'rgb(255, 99, 132)'),
                pointBorderColor: historyData.eps.map(eps => eps < 0 ? 'rgb(239, 68, 68)' : 'rgb(255, 99, 132)'),
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
                text: 'Earnings Per Share',
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
                  text: 'EPS ($)'
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
            labels: historyData.years,
            datasets: [
              {
                label: 'P/E Ratio',
                data: historyData.pe_ratio,
                borderColor: 'rgb(153, 102, 255)',
                backgroundColor: 'rgba(153, 102, 255, 0.2)',
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
            labels: historyData.years,
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

      {historyData.dividends && historyData.dividends.some(d => d !== null) && (
        <div className="chart-container chart-container-wide">
          <Line
            data={{
              labels: historyData.years,
              datasets: [
                {
                  label: 'Dividend per Share',
                  data: historyData.dividends,
                  borderColor: 'rgb(34, 197, 94)',
                  backgroundColor: 'rgba(34, 197, 94, 0.2)',
                  spanGaps: true,
                }
              ]
            }}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              plugins: {
                title: {
                  display: true,
                  text: 'Dividend per Share',
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
                    text: 'Dividend ($)'
                  },
                  beginAtZero: true
                }
              }
            }}
          />
        </div>
      )}
    </div>
  )
}
