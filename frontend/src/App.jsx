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
import AlgorithmSelector from './components/AlgorithmSelector'
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

function StockListView() {
  const navigate = useNavigate()
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
  const [loadingSession, setLoadingSession] = useState(true)
  const [watchlist, setWatchlist] = useState(new Set())
  const [algorithm, setAlgorithm] = useState('weighted')

  // Clear stocks when algorithm changes
  useEffect(() => {
    // Only clear if we actually have stocks displayed
    if (stocks.length > 0) {
      setStocks([])
      setSummary(null)
      setProgress('Algorithm changed. Click "Screen All Stocks" to re-evaluate.')
    }
    // Reset filter to 'all' when algorithm changes
    setFilter('all')
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
  useEffect(() => {
    setLoadingSession(false)
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
      console.log('Screening with URL:', url, 'Algorithm:', algorithm)
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
              // Debug: Log first few stocks to see what we're getting
              if (data.stock) {
                console.log('Stock received:', {
                  symbol: data.stock.symbol,
                  algorithm: data.stock.algorithm,
                  overall_status: data.stock.overall_status,
                  overall_score: data.stock.overall_score,
                  rating_label: data.stock.rating_label
                })
              }
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
      // New algorithm statuses
      case 'STRONG_BUY': return 1
      case 'BUY': return 2
      case 'HOLD': return 3
      case 'CAUTION': return 4
      case 'AVOID': return 5
      default: return 6
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
    console.log('sortedStocks useMemo running with sortBy:', sortBy, 'sortDir:', sortDir)
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
        const origA = aVal
        const origB = bVal
        aVal = ranks[aVal] || 999
        bVal = ranks[bVal] || 999
        if (a.symbol === 'AAPL' || b.symbol === 'AAPL') {
          console.log(`Comparing ${a.symbol}(${origA}=${aVal}) vs ${b.symbol}(${origB}=${bVal}), sortDir=${sortDir}`)
        }
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
    console.log('First 5 sorted stocks:', sorted.slice(0, 5).map(s => `${s.symbol}:${s.overall_status}`))
    return sorted
  }, [stocks, filter, sortBy, sortDir, searchQuery, watchlist])

  const totalPages = Math.ceil(sortedStocks.length / itemsPerPage)
  const startIndex = (currentPage - 1) * itemsPerPage
  const endIndex = startIndex + itemsPerPage
  const paginatedStocks = sortedStocks.slice(startIndex, endIndex)

  const toggleSort = (column) => {
    console.log('toggleSort called with column:', column, 'current sortBy:', sortBy, 'current sortDir:', sortDir)
    if (sortBy === column) {
      const newDir = sortDir === 'asc' ? 'desc' : 'asc'
      console.log('Toggling direction to:', newDir)
      setSortDir(newDir)
    } else {
      console.log('Setting new column:', column, 'direction: asc')
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
  return (
    <Routes>
      <Route path="/" element={<StockListView />} />
      <Route path="/stock/:symbol" element={<StockDetail />} />
    </Routes>
  )
}

export default App
