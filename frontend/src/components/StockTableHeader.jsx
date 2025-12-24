// ABOUTME: Reusable table header component for stock table
// ABOUTME: Supports both sortable (in table view) and read-only (in detail view) modes

export default function StockTableHeader({ sortBy, sortDir, onSort, readOnly = false }) {
  const handleSort = (column) => {
    if (!readOnly && onSort) {
      onSort(column)
    }
  }

  const getSortIndicator = (column) => {
    if (readOnly || sortBy !== column) return ''
    return sortDir === 'asc' ? ' ↑' : ' ↓'
  }

  const getCursorStyle = () => {
    return readOnly ? {} : { cursor: 'pointer' }
  }

  return (
    <thead>
      <tr>
        <th className="watchlist-header">⭐</th>
        <th onClick={() => handleSort('symbol')} style={getCursorStyle()}>
          Symbol{getSortIndicator('symbol')}
        </th>
        <th onClick={() => handleSort('company_name')} style={getCursorStyle()}>
          Company{getSortIndicator('company_name')}
        </th>
        <th onClick={() => handleSort('country')} style={getCursorStyle()}>
          Country{getSortIndicator('country')}
        </th>
        <th onClick={() => handleSort('market_cap')} style={getCursorStyle()}>
          Market Cap{getSortIndicator('market_cap')}
        </th>
        <th onClick={() => handleSort('sector')} style={getCursorStyle()}>
          Sector{getSortIndicator('sector')}
        </th>
        <th onClick={() => handleSort('ipo_year')} style={getCursorStyle()}>
          Age (Years){getSortIndicator('ipo_year')}
        </th>
        <th onClick={() => handleSort('price')} style={getCursorStyle()}>
          Price{getSortIndicator('price')}
        </th>
        <th
          onClick={() => handleSort('peg_ratio')}
          style={getCursorStyle()}
          title="PEG Ratio = P/E Ratio / 5-Year Earnings Growth Rate. A value under 1.0 is ideal. e.g., A company with a P/E of 20 and 25% earnings growth has a PEG of 0.8 (20 / 25)."
        >
          PEG{getSortIndicator('peg_ratio')}
        </th>
        <th onClick={() => handleSort('pe_ratio')} style={getCursorStyle()}>
          P/E{getSortIndicator('pe_ratio')}
        </th>
        <th
          onClick={() => handleSort('debt_to_equity')}
          style={getCursorStyle()}
          title="Debt to Equity (D/E) Ratio = Total Liabilities / Shareholder Equity. It shows how much a company relies on debt to finance its assets. A lower ratio is generally better."
        >
          D/E{getSortIndicator('debt_to_equity')}
        </th>
        <th
          onClick={() => handleSort('institutional_ownership')}
          style={getCursorStyle()}
          title="Institutional Ownership: The percentage of a company's shares held by large organizations like mutual funds, pension funds, insurance companies, and hedge funds."
        >
          Inst Own{getSortIndicator('institutional_ownership')}
        </th>
        <th onClick={() => handleSort('revenue_cagr')} style={getCursorStyle()}>
          5Y Rev Growth{getSortIndicator('revenue_cagr')}
        </th>
        <th onClick={() => handleSort('earnings_cagr')} style={getCursorStyle()}>
          5Y Inc Growth{getSortIndicator('earnings_cagr')}
        </th>
        <th onClick={() => handleSort('dividend_yield')} style={getCursorStyle()}>
          Dividend Yield{getSortIndicator('dividend_yield')}
        </th>
        <th
          title="52-week P/E Range: Shows where current P/E sits within its 52-week range. Left = low (cheap), Right = high (expensive)."
          style={{ width: '110px' }}
        >
          TTM P/E Range
        </th>
        <th
          title="5-Year Revenue Consistency: Measures how steady revenue growth has been. Higher is more consistent."
          style={{ width: '110px' }}
        >
          5y Revenue Consistency
        </th>
        <th
          title="5-Year Income Consistency: Measures how steady net income growth has been. Higher is more consistent."
          style={{ width: '110px' }}
        >
          5y Income Consistency
        </th>
        <th onClick={() => handleSort('overall_status')} style={getCursorStyle()}>
          Overall{getSortIndicator('overall_status')}
        </th>
      </tr>
    </thead>
  )
}
