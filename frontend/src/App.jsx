import { useState, useMemo, useEffect, useRef } from 'react'
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
import Settings from './pages/Settings'
import AlgorithmSelector from './components/AlgorithmSelector'
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
  watchlist, toggleWatchlist,
  algorithm, setAlgorithm
}) {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState('')
  const [error, setError] = useState(null)
  const itemsPerPage = 100

  // Re-evaluate existing stocks when algorithm changes
  const prevAlgorithmRef = useRef(algorithm)
  useEffect(() => {
    const reEvaluateStocks = async () => {
      // Only re-evaluate if algorithm actually changed
      if (prevAlgorithmRef.current === algorithm) {
        return
      }

      if (stocks.length === 0) return

      setLoading(true)
      setProgress('Re-evaluating stocks with new algorithm...')

      try {
        // Fetch re-evaluation for all existing stocks
        const reEvaluatedStocks = await Promise.all(
          stocks.map(async (stock) => {
            try {
              const response = await fetch(`${API_BASE}/stock/${stock.symbol}?algorithm=${algorithm}`)
              if (response.ok) {
                const data = await response.json()
                return data.evaluation || stock // Use evaluation, fallback to original
              }
              return stock // Keep original if fetch fails
            } catch (err) {
              console.error(`Error re-evaluating ${stock.symbol}:`, err)
              return stock // Keep original if fetch fails
            }
          })
        )

        setStocks(reEvaluatedStocks)

        // Recalculate summary stats
        const statusCounts = {}
        reEvaluatedStocks.forEach(stock => {
          const status = stock.overall_status
          statusCounts[status] = (statusCounts[status] || 0) + 1
        })

        const summaryData = {
          totalAnalyzed: reEvaluatedStocks.length,
          algorithm: algorithm
        }

        if (algorithm === 'classic') {
          summaryData.passCount = statusCounts['PASS'] || 0
          summaryData.closeCount = statusCounts['CLOSE'] || 0
          summaryData.failCount = statusCounts['FAIL'] || 0
        } else {
          summaryData.strong_buy_count = statusCounts['STRONG_BUY'] || 0
          summaryData.buy_count = statusCounts['BUY'] || 0
          summaryData.hold_count = statusCounts['HOLD'] || 0
          summaryData.caution_count = statusCounts['CAUTION'] || 0
          summaryData.avoid_count = statusCounts['AVOID'] || 0
        }

        setSummary(summaryData)
        setProgress('')

        // Update the ref after successful re-evaluation
        prevAlgorithmRef.current = algorithm
      } catch (err) {
        console.error('Error re-evaluating stocks:', err)
        setError(`Failed to re-evaluate stocks: ${err.message}`)
      } finally {
        setLoading(false)
      }
    }

    reEvaluateStocks()
  }, [algorithm])

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

  // Start with empty state (don't load cached session since algorithm may have changed)
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
      const params = new URLSearchParams({ algorithm })
      if (limit) params.append('limit', limit)
      const url = `${API_BASE}/screen?${params.toString()}`
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
              // Handle both classic and new algorithm summary formats
              const summaryData = {
                totalAnalyzed: data.total_analyzed,
                algorithm: data.algorithm
              }

              if (data.algorithm === 'classic') {
                summaryData.passCount = data.pass_count
                summaryData.closeCount = data.close_count
                summaryData.failCount = data.fail_count
              } else {
                summaryData.strong_buy_count = data.strong_buy_count
                summaryData.buy_count = data.buy_count
                summaryData.hold_count = data.hold_count
                summaryData.caution_count = data.caution_count
                summaryData.avoid_count = data.avoid_count
              }

              setSummary(summaryData)
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
      // Classic algorithm statuses
      case 'PASS': return '#4ade80'
      case 'CLOSE': return '#fbbf24'
      case 'FAIL': return '#f87171'
      // New algorithm statuses
      case 'STRONG_BUY': return '#22c55e'
      case 'BUY': return '#4ade80'
      case 'HOLD': return '#fbbf24'
      case 'CAUTION': return '#fb923c'
      case 'AVOID': return '#f87171'
      default: return '#gray'
    }
  }

  const getStatusRank = (status) => {
    switch (status) {
      // Classic algorithm statuses
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

    const sorted = [...filtered].sort((a, b) => {
      let aVal = a[sortBy]
      let bVal = b[sortBy]

      // Handle null/undefined values
      if (aVal == null && bVal == null) return 0
      if (aVal == null) return 1
      if (bVal == null) return -1

      // Special handling for status columns - use rank instead of alphabetical
      if (sortBy.endsWith('_status') || sortBy === 'overall_status') {
        const ranks = {
          'STRONG_BUY': 1,
          'BUY': 2,
          'HOLD': 3,
          'CAUTION': 4,
          'AVOID': 5,
          'SELL': 6,
          'PASS': 1,
          'CLOSE': 2,
          'FAIL': 3
        }
        aVal = ranks[aVal] || 999
        bVal = ranks[bVal] || 999
      } else if (typeof aVal === 'string') {
        aVal = aVal.toLowerCase()
        bVal = (bVal || '').toLowerCase()
      }

      if (sortDir === 'asc') {
        return aVal < bVal ? -1 : aVal > bVal ? 1 : 0
      } else {
        return aVal > bVal ? -1 : aVal < bVal ? 1 : 0
      }
    })
    return sorted
  }, [stocks, filter, sortBy, sortDir, searchQuery, watchlist])

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
        <div className="flex gap-2">
          <button onClick={() => screenStocks(null)} disabled={loading}>
            Screen All Stocks
          </button>
          <button
            onClick={() => navigate('/settings')}
            className="bg-slate-700 hover:bg-slate-600 px-4 py-2 rounded text-white flex items-center gap-2"
          >
            ⚙️
          </button>
        </div>

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
            {algorithm === 'classic' ? (
              <>
                <option value="PASS">Pass Only</option>
                <option value="CLOSE">Close Only</option>
                <option value="FAIL">Fail Only</option>
              </>
            ) : (
              <>
                <option value="STRONG_BUY">Strong Buy</option>
                <option value="BUY">Buy</option>
                <option value="HOLD">Hold</option>
                <option value="CAUTION">Caution</option>
                <option value="AVOID">Avoid</option>
              </>
            )}
          </select>
        </div>

        {summary && (
          <div className="summary-stats">
            <strong>Analyzed {summary.totalAnalyzed} stocks:</strong>
            {algorithm === 'classic' ? (
              <>
                <span className="summary-stat pass">{summary.passCount || 0} PASS</span>
                <span className="summary-stat close">{summary.closeCount || 0} CLOSE</span>
                <span className="summary-stat fail">{summary.failCount || 0} FAIL</span>
              </>
            ) : (
              <>
                <span className="summary-stat strong-buy">{summary.strong_buy_count || 0} Strong Buy</span>
                <span className="summary-stat buy">{summary.buy_count || 0} Buy</span>
                <span className="summary-stat hold">{summary.hold_count || 0} Hold</span>
                <span className="summary-stat caution">{summary.caution_count || 0} Caution</span>
                <span className="summary-stat avoid">{summary.avoid_count || 0} Avoid</span>
              </>
            )}
          </div>
        )}

        <AlgorithmSelector
          selectedAlgorithm={algorithm}
          onAlgorithmChange={setAlgorithm}
        />
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
                  <th onClick={() => toggleSort('revenue_cagr')}>5Y Rev Growth {sortBy === 'revenue_cagr' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('earnings_cagr')}>5Y EPS Growth {sortBy === 'earnings_cagr' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('dividend_yield')}>Div Yield {sortBy === 'dividend_yield' && (sortDir === 'asc' ? '↑' : '↓')}</th>
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
                    <td>{typeof stock.revenue_cagr === 'number' ? `${stock.revenue_cagr.toFixed(1)}%` : 'N/A'}</td>
                    <td>{typeof stock.earnings_cagr === 'number' ? `${stock.earnings_cagr.toFixed(1)}%` : 'N/A'}</td>
                    <td>{typeof stock.dividend_yield === 'number' ? `${stock.dividend_yield.toFixed(1)}%` : 'N/A'}</td>
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
  const [algorithm, setAlgorithm] = useState('weighted')

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
          algorithm={algorithm}
          setAlgorithm={setAlgorithm}
        />
      } />
      <Route path="/stock/:symbol" element={
        <StockDetail
          watchlist={watchlist}
          toggleWatchlist={toggleWatchlist}
        />
      } />
      <Route path="/settings" element={
        <Settings />
      } />
    </Routes>
  )
}

export default App
