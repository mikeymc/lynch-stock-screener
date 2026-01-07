// ABOUTME: Reusable stock table row component displaying all stock metrics
// ABOUTME: Supports both clickable (in table view) and read-only (in detail view) modes

import StatusBar from './StatusBar'

function getStatusColor(status) {
  switch (status) {
    // Classic algorithm statuses
    case 'PASS':
      return 'bg-green-100 text-green-800'
    case 'CLOSE':
      return 'bg-yellow-100 text-yellow-800'
    case 'FAIL':
      return 'bg-red-100 text-red-800'
    // New algorithm statuses
    case 'STRONG_BUY':
      return 'bg-emerald-100 text-emerald-800'
    case 'BUY':
      return 'bg-green-100 text-green-800'
    case 'HOLD':
      return 'bg-slate-100 text-slate-700'
    case 'CAUTION':
      return 'bg-orange-100 text-orange-800'
    case 'AVOID':
      return 'bg-red-100 text-red-800'
    default:
      return 'bg-gray-100 text-gray-700'
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

  const rowClasses = readOnly
    ? "border-b"
    : "border-b cursor-pointer hover:bg-accent/50 transition-colors"

  const cellClasses = "px-3 py-2 text-sm whitespace-nowrap"

  return (
    <tr onClick={handleClick} className={rowClasses}>
      <td className="px-2 py-2 text-center" onClick={handleWatchlistClick}>
        <span className={`cursor-pointer ${watchlist && watchlist.has(stock.symbol) ? 'opacity-100' : 'opacity-30 hover:opacity-60'}`}>
          ⭐
        </span>
      </td>
      <td className={`${cellClasses} font-semibold text-primary`}>{stock.symbol}</td>
      <td className={cellClasses}>{stock.company_name || 'N/A'}</td>
      <td className={cellClasses}>{stock.country || 'N/A'}</td>
      <td className={cellClasses}>{typeof stock.market_cap === 'number' ? `$${(stock.market_cap / 1e9).toFixed(2)}B` : 'N/A'}</td>
      <td className={cellClasses}>{stock.sector || 'N/A'}</td>
      <td className={cellClasses}>{typeof stock.ipo_year === 'number' ? new Date().getFullYear() - stock.ipo_year : 'N/A'}</td>
      <td className={cellClasses}>{typeof stock.price === 'number' ? `$${stock.price.toFixed(2)}` : 'N/A'}</td>
      <td className={cellClasses}>{typeof stock.peg_ratio === 'number' ? stock.peg_ratio.toFixed(2) : 'N/A'}</td>
      <td className={cellClasses}>{typeof stock.pe_ratio === 'number' ? stock.pe_ratio.toFixed(2) : 'N/A'}</td>
      <td className={cellClasses}>{typeof stock.debt_to_equity === 'number' ? stock.debt_to_equity.toFixed(2) : 'N/A'}</td>
      <td className={cellClasses}>{typeof stock.institutional_ownership === 'number' ? `${(stock.institutional_ownership * 100).toFixed(1)}%` : 'N/A'}</td>
      <td className={cellClasses}>{typeof stock.revenue_cagr === 'number' ? `${stock.revenue_cagr.toFixed(1)}%` : 'N/A'}</td>
      <td className={cellClasses}>{typeof stock.earnings_cagr === 'number' ? `${stock.earnings_cagr.toFixed(1)}%` : 'N/A'}</td>
      <td className={cellClasses}>{typeof stock.dividend_yield === 'number' ? `${stock.dividend_yield.toFixed(1)}%` : 'N/A'}</td>
      <td className="px-3 py-2">
        <StatusBar
          status={stock.pe_52_week_position !== null ? 'info' : 'N/A'}
          score={stock.pe_52_week_position !== null ? stock.pe_52_week_position : 0}
          value={stock.pe_52_week_position !== null ? `${stock.pe_52_week_position.toFixed(0)}%` : 'N/A'}
          metricType="pe_range"
        />
      </td>
      <td className="px-3 py-2">
        <StatusBar
          status={stock.revenue_consistency_score !== null ? 'info' : 'N/A'}
          score={stock.revenue_consistency_score || 0}
          value={stock.revenue_consistency_score !== null ? `${stock.revenue_consistency_score.toFixed(0)}%` : 'N/A'}
          metricType="revenue_consistency"
        />
      </td>
      <td className="px-3 py-2">
        <StatusBar
          status={stock.income_consistency_score !== null ? 'info' : 'N/A'}
          score={stock.income_consistency_score || 0}
          value={stock.income_consistency_score !== null ? `${stock.income_consistency_score.toFixed(0)}%` : 'N/A'}
          metricType="income_consistency"
        />
      </td>
      <td className="px-3 py-2">
        <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(stock.overall_status)}`}>
          {formatStatusName(stock.overall_status)}
        </span>
      </td>
    </tr>
  )
}
