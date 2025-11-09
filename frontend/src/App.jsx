import { useState, useMemo, useEffect } from 'react'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js'
import LynchAnalysis from './components/LynchAnalysis'
import './App.css'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
)

const API_BASE = 'http://localhost:5001/api'

function App() {
  const [stocks, setStocks] = useState([])
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState('')
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all')
  const [sortBy, setSortBy] = useState('symbol')
  const [sortDir, setSortDir] = useState('asc')
  const [summary, setSummary] = useState(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [searchQuery, setSearchQuery] = useState('')
  const itemsPerPage = 100
  const [expandedSymbol, setExpandedSymbol] = useState(null)
  const [historyData, setHistoryData] = useState(null)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [loadingSession, setLoadingSession] = useState(true)

  // Load latest session on mount
  useEffect(() => {
    const loadLatestSession = async () => {
      try {
        const response = await fetch(`${API_BASE}/sessions/latest`)

        if (response.ok) {
          const sessionData = await response.json()
          setStocks(sessionData.results || [])
          setSummary({
            totalAnalyzed: sessionData.total_analyzed,
            passCount: sessionData.pass_count,
            closeCount: sessionData.close_count,
            failCount: sessionData.fail_count
          })
        } else if (response.status === 404) {
          // No sessions yet, this is okay
          setStocks([])
          setSummary(null)
        } else {
          throw new Error(`Failed to load session: ${response.status}`)
        }
      } catch (err) {
        console.error('Error loading latest session:', err)
        // Don't show error to user on initial load, just start with empty state
        setStocks([])
        setSummary(null)
      } finally {
        setLoadingSession(false)
      }
    }

    loadLatestSession()
  }, [])

  const screenStocks = async (limit) => {
    setLoading(true)
    setProgress('Fetching stock list...')
    setError(null)
    setStocks([])
    setSummary(null)
    setCurrentPage(1)

    try {
      const url = limit ? `${API_BASE}/screen?limit=${limit}` : `${API_BASE}/screen`
      const response = await fetch(url)

      if (!response.ok) {
        throw new Error(`API returned ${response.status}: ${response.statusText}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()

        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6))

            if (data.type === 'progress') {
              setProgress(data.message)
            } else if (data.type === 'stock_result') {
              setStocks(prevStocks => [...prevStocks, data.stock])
            } else if (data.type === 'complete') {
              setSummary({
                totalAnalyzed: data.total_analyzed,
                passCount: data.pass_count,
                closeCount: data.close_count,
                failCount: data.fail_count
              })
              setProgress('')
            } else if (data.type === 'error') {
              setError(data.message)
            }
          }
        }
      }
    } catch (err) {
      console.error('Error screening stocks:', err)
      setError(`Failed to screen stocks: ${err.message}`)
    } finally {
      setLoading(false)
      setProgress('')
    }
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'PASS': return '#4ade80'
      case 'CLOSE': return '#fbbf24'
      case 'FAIL': return '#f87171'
      default: return '#gray'
    }
  }

  const sortedStocks = useMemo(() => {
    const filtered = stocks.filter(stock => {
      // Apply status filter
      if (filter !== 'all' && stock.overall_status !== filter) {
        return false
      }

      // Apply search filter
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase()
        const symbol = (stock.symbol || '').toLowerCase()
        const companyName = (stock.company_name || '').toLowerCase()

        if (!symbol.includes(query) && !companyName.includes(query)) {
          return false
        }
      }

      return true
    })

    return [...filtered].sort((a, b) => {
      let aVal = a[sortBy]
      let bVal = b[sortBy]

      // Handle null/undefined values
      if (aVal == null && bVal == null) return 0
      if (aVal == null) return 1
      if (bVal == null) return -1

      if (typeof aVal === 'string') {
        aVal = aVal.toLowerCase()
        bVal = (bVal || '').toLowerCase()
      }

      if (sortDir === 'asc') {
        return aVal < bVal ? -1 : 1
      } else {
        return aVal > bVal ? -1 : 1
      }
    })
  }, [stocks, filter, sortBy, sortDir, searchQuery])

  const totalPages = Math.ceil(sortedStocks.length / itemsPerPage)
  const startIndex = (currentPage - 1) * itemsPerPage
  const endIndex = startIndex + itemsPerPage
  const paginatedStocks = sortedStocks.slice(startIndex, endIndex)

  const toggleSort = (column) => {
    if (sortBy === column) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(column)
      setSortDir('asc')
    }
  }

  const fetchHistoryData = async (symbol) => {
    setLoadingHistory(true)
    try {
      const response = await fetch(`${API_BASE}/stock/${symbol}/history`)
      if (!response.ok) {
        throw new Error(`Failed to fetch history for ${symbol}`)
      }
      const data = await response.json()
      setHistoryData(data)
    } catch (err) {
      console.error('Error fetching history:', err)
      setError(`Failed to load history: ${err.message}`)
      setHistoryData(null)
    } finally {
      setLoadingHistory(false)
    }
  }

  const toggleRowExpansion = (symbol) => {
    if (expandedSymbol === symbol) {
      setExpandedSymbol(null)
      setHistoryData(null)
    } else {
      setExpandedSymbol(symbol)
      fetchHistoryData(symbol)
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Lynch Stock Screener</h1>
        <p>Screen stocks using Peter Lynch criteria</p>
      </header>

      <div className="controls">
        <button onClick={() => screenStocks(null)} disabled={loading}>
          Screen All Stocks
        </button>

        <div className="filter-controls">
          <label>Search: </label>
          <div className="search-container">
            <span className="search-icon">🔍</span>
            <input
              type="text"
              className="search-input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter by symbol or company name..."
            />
            {searchQuery && (
              <button
                className="clear-button"
                onClick={() => setSearchQuery('')}
                aria-label="Clear search"
              >
                ×
              </button>
            )}
          </div>
        </div>

        <div className="filter-controls">
          <label>Filter: </label>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All</option>
            <option value="PASS">Pass Only</option>
            <option value="CLOSE">Close Only</option>
            <option value="FAIL">Fail Only</option>
          </select>
        </div>
      </div>

      {loading && (
        <div className="status-container">
          <div className="loading">
            {progress || 'Loading...'}
          </div>
        </div>
      )}

      {error && (
        <div className="error-message">
          {error}
          <button onClick={() => setError(null)} className="error-dismiss">Dismiss</button>
        </div>
      )}

      {summary && (
        <div className="summary-banner">
          <strong>Analyzed {summary.totalAnalyzed} stocks:</strong>
          <span className="summary-stat pass">{summary.passCount} PASS</span>
          <span className="summary-stat close">{summary.closeCount} CLOSE</span>
          <span className="summary-stat fail">{summary.failCount} FAIL</span>
        </div>
      )}

      {sortedStocks.length > 0 && (
        <>
          <div className="pagination-info">
            Showing {startIndex + 1}-{Math.min(endIndex, sortedStocks.length)} of {sortedStocks.length} stocks
          </div>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th onClick={() => toggleSort('symbol')}>Symbol {sortBy === 'symbol' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('company_name')}>Company {sortBy === 'company_name' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('country')}>Country {sortBy === 'country' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('market_cap')}>Market Cap {sortBy === 'market_cap' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('sector')}>Sector {sortBy === 'sector' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('ipo_year')}>Age (Years) {sortBy === 'ipo_year' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('price')}>Price {sortBy === 'price' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('peg_ratio')}>PEG {sortBy === 'peg_ratio' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('pe_ratio')}>P/E {sortBy === 'pe_ratio' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('debt_to_equity')}>D/E {sortBy === 'debt_to_equity' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('institutional_ownership')}>Inst Own % {sortBy === 'institutional_ownership' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('dividend_yield')}>Div Yield % {sortBy === 'dividend_yield' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('earnings_cagr')}>5Y EPS Growth {sortBy === 'earnings_cagr' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('revenue_cagr')}>5Y Rev Growth {sortBy === 'revenue_cagr' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th>PEG Status</th>
                  <th>Debt Status</th>
                  <th>Inst Own Status</th>
                  <th onClick={() => toggleSort('overall_status')}>Overall {sortBy === 'overall_status' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                </tr>
              </thead>
              <tbody>
                {paginatedStocks.map(stock => (
                  <>
                    <tr
                      key={stock.symbol}
                      onClick={() => toggleRowExpansion(stock.symbol)}
                      className={`stock-row ${expandedSymbol === stock.symbol ? 'expanded' : ''}`}
                    >
                      <td><strong>{stock.symbol}</strong></td>
                      <td>{stock.company_name || 'N/A'}</td>
                      <td>{stock.country || 'N/A'}</td>
                      <td>{typeof stock.market_cap === 'number' ? `$${(stock.market_cap / 1e9).toFixed(2)}B` : 'N/A'}</td>
                      <td>{stock.sector || 'N/A'}</td>
                      <td>{typeof stock.ipo_year === 'number' ? new Date().getFullYear() - stock.ipo_year : 'N/A'}</td>
                      <td>{typeof stock.price === 'number' ? `$${stock.price.toFixed(2)}` : 'N/A'}</td>
                      <td>{typeof stock.peg_ratio === 'number' ? stock.peg_ratio.toFixed(2) : 'N/A'}</td>
                      <td>{typeof stock.pe_ratio === 'number' ? stock.pe_ratio.toFixed(2) : 'N/A'}</td>
                      <td>{typeof stock.debt_to_equity === 'number' ? stock.debt_to_equity.toFixed(2) : 'N/A'}</td>
                      <td>{typeof stock.institutional_ownership === 'number' ? `${(stock.institutional_ownership * 100).toFixed(1)}%` : 'N/A'}</td>
                      <td>{typeof stock.dividend_yield === 'number' ? `${stock.dividend_yield.toFixed(1)}%` : 'N/A'}</td>
                      <td>{typeof stock.earnings_cagr === 'number' ? `${stock.earnings_cagr.toFixed(1)}%` : 'N/A'}</td>
                      <td>{typeof stock.revenue_cagr === 'number' ? `${stock.revenue_cagr.toFixed(1)}%` : 'N/A'}</td>
                      <td style={{ backgroundColor: getStatusColor(stock.peg_status), color: '#000' }}>
                        {stock.peg_status}
                      </td>
                      <td style={{ backgroundColor: getStatusColor(stock.debt_status), color: '#000' }}>
                        {stock.debt_status}
                      </td>
                      <td style={{ backgroundColor: getStatusColor(stock.institutional_ownership_status), color: '#000' }}>
                        {stock.institutional_ownership_status}
                      </td>
                      <td style={{ backgroundColor: getStatusColor(stock.overall_status), color: '#000', fontWeight: 'bold' }}>
                        {stock.overall_status}
                      </td>
                    </tr>
                    {expandedSymbol === stock.symbol && (
                      <tr key={`${stock.symbol}-details`} className="expanded-row">
                        <td colSpan="18">
                          <div className="chart-container">
                            {loadingHistory && <div className="loading">Loading historical data...</div>}
                            {!loadingHistory && historyData && (
                              <Line
                                data={{
                                  labels: historyData.years,
                                  datasets: [
                                    {
                                      label: 'Revenue (Billions)',
                                      data: historyData.revenue.map(r => r / 1e9),
                                      borderColor: 'rgb(75, 192, 192)',
                                      backgroundColor: 'rgba(75, 192, 192, 0.2)',
                                      yAxisID: 'y',
                                    },
                                    {
                                      label: 'EPS',
                                      data: historyData.eps,
                                      borderColor: 'rgb(255, 99, 132)',
                                      backgroundColor: 'rgba(255, 99, 132, 0.2)',
                                      yAxisID: 'y1',
                                    },
                                    {
                                      label: 'P/E Ratio',
                                      data: historyData.pe_ratio,
                                      borderColor: 'rgb(153, 102, 255)',
                                      backgroundColor: 'rgba(153, 102, 255, 0.2)',
                                      yAxisID: 'y1',
                                    }
                                  ]
                                }}
                                options={{
                                  responsive: true,
                                  interaction: {
                                    mode: 'index',
                                    intersect: false,
                                  },
                                  plugins: {
                                    title: {
                                      display: true,
                                      text: `${stock.symbol} - Historical Financials`,
                                      font: { size: 16 }
                                    },
                                    legend: {
                                      position: 'top',
                                    }
                                  },
                                  scales: {
                                    y: {
                                      type: 'linear',
                                      display: true,
                                      position: 'left',
                                      title: {
                                        display: true,
                                        text: 'Revenue (Billions)'
                                      }
                                    },
                                    y1: {
                                      type: 'linear',
                                      display: true,
                                      position: 'right',
                                      title: {
                                        display: true,
                                        text: 'EPS / P/E Ratio'
                                      },
                                      grid: {
                                        drawOnChartArea: false,
                                      },
                                    },
                                  }
                                }}
                              />
                            )}
                          </div>

                          {!loadingHistory && historyData && (
                            <LynchAnalysis
                              symbol={stock.symbol}
                              stockName={stock.company_name}
                            />
                          )}
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="pagination">
            <button
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              disabled={currentPage === 1}
            >
              Previous
            </button>
            <span className="page-info">
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
            >
              Next
            </button>
          </div>
        )}
        </>
      )}

      {loadingSession && (
        <div className="status-container">
          <div className="loading">
            Loading previous screening results...
          </div>
        </div>
      )}

      {!loadingSession && !loading && sortedStocks.length === 0 && stocks.length === 0 && (
        <div className="empty-state">
          No stocks loaded. Click "Screen Stocks" to begin.
        </div>
      )}

      {!loading && sortedStocks.length === 0 && stocks.length > 0 && (
        <div className="empty-state">
          No stocks match the current {searchQuery ? 'search and filter' : 'filter'}.
        </div>
      )}
    </div>
  )
}

export default App
