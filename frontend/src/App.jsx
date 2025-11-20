import { useState, useMemo, useEffect } from 'react'
import { Routes, Route, useNavigate } from 'react-router-dom'
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
import ChatInterface from './components/ChatInterface'
import StockDetail from './pages/StockDetail'
import StatusBar from './components/StatusBar'
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

const API_BASE = '/api'

// FilingSections component displays expandable filing content
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
                  <div className="section-text">
                    {content.split('\n').map((paragraph, idx) => {
                      // Skip empty lines
                      if (paragraph.trim() === '') return null
                      return <p key={idx}>{paragraph}</p>
                    })}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function StockListView({
  stocks, setStocks,
  summary, setSummary,
  filter, setFilter,
  searchQuery, setSearchQuery,
  currentPage, setCurrentPage,
  sortBy, setSortBy,
  sortDir, setSortDir,
  watchlist, toggleWatchlist
}) {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState('')
  const [error, setError] = useState(null)
  const itemsPerPage = 100
  const [loadingSession, setLoadingSession] = useState(stocks.length === 0 && !summary)
  // Load latest session on mount
  useEffect(() => {
    if (stocks.length > 0 || summary) {
      setLoadingSession(false)
      return
    }

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

  const handleStockClick = (symbol) => {
    navigate(`/stock/${symbol}`)
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
                  <tr
                    key={stock.symbol}
                    onClick={() => handleStockClick(stock.symbol)}
                    className="stock-row"
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
                        metricType="peg"
                      />
                    </td>
                    <td>
                      <StatusBar
                        status={stock.debt_status}
                        score={stock.debt_score || 0}
                        value={stock.debt_to_equity}
                        metricType="debt"
                      />
                    </td>
                    <td>
                      <StatusBar
                        status={stock.institutional_ownership_status}
                        score={stock.institutional_ownership_score || 0}
                        value={stock.institutional_ownership}
                        metricType="institutional"
                      />
                    </td>
                    <td style={{ backgroundColor: getStatusColor(stock.overall_status), color: '#000', fontWeight: 'bold' }}>
                      {stock.overall_status}
                    </td>
                  </tr>
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

function App() {
  const [stocks, setStocks] = useState([])
  const [summary, setSummary] = useState(null)
  const [filter, setFilter] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [sortBy, setSortBy] = useState('symbol')
  const [sortDir, setSortDir] = useState('asc')
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

  return (
    <Routes>
      <Route path="/" element={
        <StockListView
          stocks={stocks}
          setStocks={setStocks}
          summary={summary}
          setSummary={setSummary}
          filter={filter}
          setFilter={setFilter}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          currentPage={currentPage}
          setCurrentPage={setCurrentPage}
          sortBy={sortBy}
          setSortBy={setSortBy}
          sortDir={sortDir}
          setSortDir={setSortDir}
          watchlist={watchlist}
          toggleWatchlist={toggleWatchlist}
        />
      } />
      <Route path="/stock/:symbol" element={
        <StockDetail
          watchlist={watchlist}
          toggleWatchlist={toggleWatchlist}
        />
      } />
    </Routes>
  )
}

export default App
