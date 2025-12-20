// ABOUTME: Reusable stock table row component displaying all stock metrics
// ABOUTME: Supports both clickable (in table view) and read-only (in detail view) modes

import StatusBar from './StatusBar'

function getStatusColor(status) {
  switch (status) {
    // Classic algorithm statuses
    case 'PASS':
      return '#90EE90' // light green
    case 'CLOSE':
      return '#FFD700' // gold/yellow
    case 'FAIL':
      return '#FFB6C1' // light red/pink
    // New algorithm statuses
    case 'STRONG_BUY':
      return '#22c55e' // strong green
    case 'BUY':
      return '#4ade80' // light green
    case 'HOLD':
      return '#fbbf24' // yellow/gold
    case 'CAUTION':
      return '#fb923c' // orange
    case 'AVOID':
      return '#f87171' // red
    default:
      return '#FFFFFF' // white
  }
}

function formatStatusName(status) {
  const statusMap = {
    'STRONG_BUY': 'Excellent',
    'BUY': 'Good',
    'HOLD': 'Fair',
    'CAUTION': 'Weak',
    'AVOID': 'Poor',
    'PASS': 'Pass',
    'CLOSE': 'Close',
    'FAIL': 'Fail'
  }
  return statusMap[status] || status
}

export default function StockTableRow({ stock, watchlist, onToggleWatchlist, onClick, readOnly = false }) {
  const handleClick = () => {
    if (!readOnly && onClick) {
      onClick(stock.symbol)
    }
  }

  const handleWatchlistClick = (e) => {
    e.stopPropagation()
    if (onToggleWatchlist) {
      onToggleWatchlist(stock.symbol)
    }
  }

  const getCursorStyle = () => {
    return readOnly ? {} : { cursor: 'pointer' }
  }

  return (
    <tr onClick={handleClick} style={getCursorStyle()} className="stock-row">
      <td className="watchlist-cell" onClick={handleWatchlistClick}>
        <span className={`watchlist-star ${watchlist && watchlist.has(stock.symbol) ? 'checked' : ''}`}>
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
          status={stock.pe_52_week_position !== null ? 'info' : 'N/A'}
          score={stock.pe_52_week_position !== null ? 100 - stock.pe_52_week_position : 0}
          value={stock.pe_52_week_position !== null ? `${stock.pe_52_week_position.toFixed(0)}%` : 'N/A'}
          metricType="pe_range"
        />
      </td>
      <td>
        <StatusBar
          status={stock.revenue_consistency_score !== null ? 'info' : 'N/A'}
          score={stock.revenue_consistency_score || 0}
          value={stock.revenue_consistency_score !== null ? `${stock.revenue_consistency_score.toFixed(0)}%` : 'N/A'}
          metricType="revenue_consistency"
        />
      </td>
      <td>
        <StatusBar
          status={stock.income_consistency_score !== null ? 'info' : 'N/A'}
          score={stock.income_consistency_score || 0}
          value={stock.income_consistency_score !== null ? `${stock.income_consistency_score.toFixed(0)}%` : 'N/A'}
          metricType="income_consistency"
        />
      </td>
      <td style={{ backgroundColor: getStatusColor(stock.overall_status), color: '#000', fontWeight: 'bold' }}>
        {formatStatusName(stock.overall_status)}
      </td>
    </tr>
  )
}
