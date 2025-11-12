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

function StatusBar({ status, score, value }) {
  const displayValue = typeof value === 'number' ? value.toFixed(2) : 'N/A'
  const tooltipText = `${status}: ${displayValue}`

  // Invert position: score 100 (best) = left (0%), score 0 (worst) = right (100%)
  const markerPosition = `${100 - score}%`

  return (
    <div className="status-bar-container" title={tooltipText}>
      <div className="status-bar">
        <div className="status-zone pass"></div>
        <div className="status-zone close"></div>
        <div className="status-zone fail"></div>
        <div
          className="status-marker"
          style={{ left: markerPosition }}
        ></div>
      </div>
    </div>
  )
}

function FilingSections({ sections }) {
  const [expandedSections, setExpandedSections] = useState(new Set())

  const toggleSection = (sectionName) => {
    setExpandedSections(prev => {
      const newSet = new Set(prev)
      if (newSet.has(sectionName)) {
        newSet.delete(sectionName)
      } else {
        newSet.add(sectionName)
      }
      return newSet
    })
  }

  const sectionTitles = {
    business: 'Business Description (Item 1)',
    risk_factors: 'Risk Factors (Item 1A)',
    mda: 'Management Discussion & Analysis',
    market_risk: 'Market Risk Disclosures'
  }

  return (
    <div className="sections-container">
      <h3>Key Filing Sections</h3>
      <div className="sections-list">
        {Object.entries(sections).map(([sectionName, sectionData]) => {
          const isExpanded = expandedSections.has(sectionName)
          const title = sectionTitles[sectionName] || sectionName
          const filingType = sectionData.filing_type
          const filingDate = sectionData.filing_date
          const content = sectionData.content

          return (
            <div key={sectionName} className="section-item">
              <div
                className="section-header"
                onClick={() => toggleSection(sectionName)}
              >
                <span className="section-toggle">{isExpanded ? '▼' : '▶'}</span>
                <span className="section-title">{title}</span>
                <span className="section-metadata">({filingType} - Filed: {filingDate})</span>
              </div>
              {isExpanded && (
                <div className="section-content">
                  <div className="section-text">{content}</div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

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
  const [filingsData, setFilingsData] = useState(null)
  const [loadingFilings, setLoadingFilings] = useState(false)
  const [sectionsData, setSectionsData] = useState(null)
  const [loadingSections, setLoadingSections] = useState(false)
  const [loadingSession, setLoadingSession] = useState(true)
  const [watchlist, setWatchlist] = useState(new Set())

  // Load watchlist on mount
  useEffect(() => {
    const loadWatchlist = async () => {
      try {
        const response = await fetch(`${API_BASE}/watchlist`)
        if (response.ok) {
          const data = await response.json()
          setWatchlist(new Set(data.symbols))
        }
      } catch (err) {
        console.error('Error loading watchlist:', err)
      }
    }
    loadWatchlist()
  }, [])

  // Load latest session on mount
  useEffect(() => {
    const loadLatestSession = async () => {
      try {
        const response = await fetch(`${API_BASE}/sessions/latest`)

        if (response.ok) {
          const sessionData = await response.json()
          const results = sessionData.results || []
          setStocks(results)

          // Calculate counts from actual results instead of trusting stored metadata
          const passCount = results.filter(s => s.overall_status === 'PASS').length
          const closeCount = results.filter(s => s.overall_status === 'CLOSE').length
          const failCount = results.filter(s => s.overall_status === 'FAIL').length

          setSummary({
            totalAnalyzed: results.length,
            passCount,
            closeCount,
            failCount
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

  const getStatusRank = (status) => {
    switch (status) {
      case 'PASS': return 1
      case 'CLOSE': return 2
      case 'FAIL': return 3
      default: return 4
    }
  }

  const toggleWatchlist = async (symbol) => {
    const isInWatchlist = watchlist.has(symbol)

    try {
      if (isInWatchlist) {
        await fetch(`${API_BASE}/watchlist/${symbol}`, { method: 'DELETE' })
        setWatchlist(prev => {
          const newSet = new Set(prev)
          newSet.delete(symbol)
          return newSet
        })
      } else {
        await fetch(`${API_BASE}/watchlist/${symbol}`, { method: 'POST' })
        setWatchlist(prev => new Set([...prev, symbol]))
      }
    } catch (err) {
      console.error('Error toggling watchlist:', err)
    }
  }

  const sortedStocks = useMemo(() => {
    const filtered = stocks.filter(stock => {
      // Apply watchlist filter
      if (filter === 'watchlist' && !watchlist.has(stock.symbol)) {
        return false
      }

      // Apply status filter
      if (filter !== 'all' && filter !== 'watchlist' && stock.overall_status !== filter) {
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

      // Special handling for status columns - use rank instead of alphabetical
      if (sortBy.endsWith('_status') || sortBy === 'overall_status') {
        aVal = getStatusRank(aVal)
        bVal = getStatusRank(bVal)
      } else if (typeof aVal === 'string') {
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

  const fetchFilingsData = async (symbol) => {
    setLoadingFilings(true)
    try {
      const response = await fetch(`${API_BASE}/stock/${symbol}/filings`)
      if (!response.ok) {
        throw new Error(`Failed to fetch filings for ${symbol}`)
      }
      const data = await response.json()
      setFilingsData(data)
    } catch (err) {
      console.error('Error fetching filings:', err)
      setFilingsData(null)
    } finally {
      setLoadingFilings(false)
    }
  }

  const fetchSectionsData = async (symbol) => {
    setLoadingSections(true)
    try {
      const response = await fetch(`${API_BASE}/stock/${symbol}/sections`)
      if (!response.ok) {
        throw new Error(`Failed to fetch sections for ${symbol}`)
      }
      const data = await response.json()
      setSectionsData(data.sections || null)
    } catch (err) {
      console.error('Error fetching sections:', err)
      setSectionsData(null)
    } finally {
      setLoadingSections(false)
    }
  }

  const toggleRowExpansion = (symbol) => {
    if (expandedSymbol === symbol) {
      setExpandedSymbol(null)
      setHistoryData(null)
      setFilingsData(null)
      setSectionsData(null)
    } else {
      setExpandedSymbol(symbol)
      fetchHistoryData(symbol)
      fetchFilingsData(symbol)
      fetchSectionsData(symbol)
    }
  }

  return (
    <div className="app">
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
            <option value="watchlist">⭐ Watchlist</option>
            <option value="PASS">Pass Only</option>
            <option value="CLOSE">Close Only</option>
            <option value="FAIL">Fail Only</option>
          </select>
        </div>

        {summary && (
          <div className="summary-stats">
            <strong>Analyzed {summary.totalAnalyzed} stocks:</strong>
            <span className="summary-stat pass">{summary.passCount} PASS</span>
            <span className="summary-stat close">{summary.closeCount} CLOSE</span>
            <span className="summary-stat fail">{summary.failCount} FAIL</span>
          </div>
        )}
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

      {sortedStocks.length > 0 && (
        <>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th className="watchlist-header">⭐</th>
                  <th onClick={() => toggleSort('symbol')}>Symbol {sortBy === 'symbol' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('company_name')}>Company {sortBy === 'company_name' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('country')}>Country {sortBy === 'country' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('market_cap')}>Market Cap {sortBy === 'market_cap' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('sector')}>Sector {sortBy === 'sector' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('ipo_year')}>Age (Years) {sortBy === 'ipo_year' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('price')}>Price {sortBy === 'price' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th
                    onClick={() => toggleSort('peg_ratio')}
                    title="PEG Ratio = P/E Ratio / 5-Year Earnings Growth Rate. A value under 1.0 is ideal. e.g., A company with a P/E of 20 and 25% earnings growth has a PEG of 0.8 (20 / 25)."
                  >PEG <sup>i</sup>{sortBy === 'peg_ratio' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('pe_ratio')}>P/E {sortBy === 'pe_ratio' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th
                    onClick={() => toggleSort('debt_to_equity')}
                    title="Debt to Equity (D/E) Ratio = Total Liabilities / Shareholder Equity. It shows how much a company relies on debt to finance its assets. A lower ratio is generally better."
                  >D/E <sup>i</sup>{sortBy === 'debt_to_equity' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th
                    onClick={() => toggleSort('institutional_ownership')}
                    title="Institutional Ownership: The percentage of a company's shares held by large organizations like mutual funds, pension funds, insurance companies, and hedge funds."
                  >Inst Own <sup>i</sup>{sortBy === 'institutional_ownership' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('dividend_yield')}>Div Yield {sortBy === 'dividend_yield' && (sortDir === 'asc' ? '↑' : '↓')}</th>
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
                      <td className="watchlist-cell" onClick={(e) => { e.stopPropagation(); toggleWatchlist(stock.symbol); }}>
                        <span className={`watchlist-star ${watchlist.has(stock.symbol) ? 'checked' : ''}`}>
                          ⭐
                        </span>
                      </td>
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
                      <td>
                        <StatusBar
                          status={stock.peg_status}
                          score={stock.peg_score || 0}
                          value={stock.peg_ratio}
                        />
                      </td>
                      <td>
                        <StatusBar
                          status={stock.debt_status}
                          score={stock.debt_score || 0}
                          value={stock.debt_to_equity}
                        />
                      </td>
                      <td>
                        <StatusBar
                          status={stock.institutional_ownership_status}
                          score={stock.institutional_ownership_score || 0}
                          value={stock.institutional_ownership}
                        />
                      </td>
                      <td style={{ backgroundColor: getStatusColor(stock.overall_status), color: '#000', fontWeight: 'bold' }}>
                        {stock.overall_status}
                      </td>
                    </tr>
                    {expandedSymbol === stock.symbol && (
                      <tr key={`${stock.symbol}-details`} className="expanded-row">
                        <td colSpan="19">
                          <div className="charts-grid">
                            {loadingHistory && <div className="loading">Loading historical data...</div>}
                            {!loadingHistory && historyData && (
                              <>
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
                              </>
                            )}
                          </div>

                          {!loadingFilings && filingsData && (Object.keys(filingsData).length > 0) && (
                            <div className="filings-container">
                              <h3>SEC Filings</h3>
                              <div className="filings-links">
                                {filingsData['10-K'] && (
                                  <div className="filing-item">
                                    <a href={filingsData['10-K'].url} target="_blank" rel="noopener noreferrer">
                                      📄 10-K Annual Report (Filed: {filingsData['10-K'].filed_date})
                                    </a>
                                  </div>
                                )}
                                {filingsData['10-Q']?.map((filing, idx) => (
                                  <div key={idx} className="filing-item">
                                    <a href={filing.url} target="_blank" rel="noopener noreferrer">
                                      📄 10-Q Quarterly Report (Filed: {filing.filed_date})
                                    </a>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {loadingSections && (
                            <div className="sections-container">
                              <div className="sections-loading">Loading filing sections...</div>
                            </div>
                          )}

                          {!loadingSections && sectionsData && Object.keys(sectionsData).length > 0 && (
                            <FilingSections sections={sectionsData} />
                          )}

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

        <div className="pagination-info">
          Showing {startIndex + 1}-{Math.min(endIndex, sortedStocks.length)} of {sortedStocks.length} stocks
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
