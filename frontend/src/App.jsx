import { useState } from 'react'
import './App.css'

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

  const screenStocks = async (limit) => {
    setLoading(true)
    setProgress('Fetching stock list...')
    setError(null)
    setStocks([])
    setSummary(null)

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

  const filteredStocks = stocks.filter(stock => {
    if (filter === 'all') return true
    return stock.overall_status === filter
  })

  const sortedStocks = [...filteredStocks].sort((a, b) => {
    let aVal = a[sortBy]
    let bVal = b[sortBy]

    if (typeof aVal === 'string') {
      aVal = aVal.toLowerCase()
      bVal = bVal.toLowerCase()
    }

    if (sortDir === 'asc') {
      return aVal < bVal ? -1 : 1
    } else {
      return aVal > bVal ? -1 : 1
    }
  })

  const toggleSort = (column) => {
    if (sortBy === column) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(column)
      setSortDir('asc')
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Lynch Stock Screener</h1>
        <p>Screen stocks using Peter Lynch criteria</p>
      </header>

      <div className="controls">
        <button onClick={() => screenStocks(50)} disabled={loading}>
          Screen 50 Stocks
        </button>
        <button onClick={() => screenStocks(null)} disabled={loading}>
          Screen All Stocks
        </button>

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
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th onClick={() => toggleSort('symbol')}>Symbol {sortBy === 'symbol' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                <th onClick={() => toggleSort('company_name')}>Company {sortBy === 'company_name' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                <th onClick={() => toggleSort('price')}>Price {sortBy === 'price' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                <th onClick={() => toggleSort('peg_ratio')}>PEG {sortBy === 'peg_ratio' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                <th onClick={() => toggleSort('pe_ratio')}>P/E {sortBy === 'pe_ratio' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                <th onClick={() => toggleSort('debt_to_equity')}>D/E {sortBy === 'debt_to_equity' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                <th onClick={() => toggleSort('institutional_ownership')}>Inst Own % {sortBy === 'institutional_ownership' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                <th onClick={() => toggleSort('earnings_cagr')}>5Y EPS Growth {sortBy === 'earnings_cagr' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                <th onClick={() => toggleSort('revenue_cagr')}>5Y Rev Growth {sortBy === 'revenue_cagr' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                <th>PEG Status</th>
                <th>Debt Status</th>
                <th>Inst Own Status</th>
                <th onClick={() => toggleSort('overall_status')}>Overall {sortBy === 'overall_status' && (sortDir === 'asc' ? '↑' : '↓')}</th>
              </tr>
            </thead>
            <tbody>
              {sortedStocks.map(stock => (
                <tr key={stock.symbol}>
                  <td><strong>{stock.symbol}</strong></td>
                  <td>{stock.company_name}</td>
                  <td>${stock.price?.toFixed(2)}</td>
                  <td>{stock.peg_ratio?.toFixed(2)}</td>
                  <td>{stock.pe_ratio?.toFixed(2)}</td>
                  <td>{stock.debt_to_equity?.toFixed(2)}</td>
                  <td>{(stock.institutional_ownership * 100)?.toFixed(1)}%</td>
                  <td>{stock.earnings_cagr?.toFixed(1)}%</td>
                  <td>{stock.revenue_cagr?.toFixed(1)}%</td>
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
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && sortedStocks.length === 0 && stocks.length === 0 && (
        <div className="empty-state">
          No stocks loaded. Click "Load Cached Stocks" or "Screen Stocks" to begin.
        </div>
      )}

      {!loading && sortedStocks.length === 0 && stocks.length > 0 && (
        <div className="empty-state">
          No stocks match the current filter.
        </div>
      )}
    </div>
  )
}

export default App
