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

  const headerClasses = readOnly
    ? "px-3 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
    : "px-3 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-accent"

  return (
    <thead className="bg-muted/50 border-b">
      <tr>
        <th className="px-2 py-2 w-10 text-center">⭐</th>
        <th className={headerClasses} onClick={() => handleSort('symbol')}>
          Symbol{getSortIndicator('symbol')}
        </th>
        <th className={headerClasses} onClick={() => handleSort('company_name')}>
          Company{getSortIndicator('company_name')}
        </th>
        <th className={headerClasses} onClick={() => handleSort('country')}>
          Country{getSortIndicator('country')}
        </th>
        <th className={headerClasses} onClick={() => handleSort('market_cap')}>
          Market Cap{getSortIndicator('market_cap')}
        </th>
        <th className={headerClasses} onClick={() => handleSort('sector')}>
          Sector{getSortIndicator('sector')}
        </th>
        <th className={headerClasses} onClick={() => handleSort('ipo_year')}>
          Age (Years){getSortIndicator('ipo_year')}
        </th>
        <th className={headerClasses} onClick={() => handleSort('price')}>
          Price{getSortIndicator('price')}
        </th>
        <th
          className={headerClasses}
          onClick={() => handleSort('peg_ratio')}
          title="PEG Ratio = P/E Ratio / 5-Year Earnings Growth Rate. A value under 1.0 is ideal."
        >
          PEG{getSortIndicator('peg_ratio')}
        </th>
        <th className={headerClasses} onClick={() => handleSort('pe_ratio')}>
          P/E{getSortIndicator('pe_ratio')}
        </th>
        <th
          className={headerClasses}
          onClick={() => handleSort('debt_to_equity')}
          title="Debt to Equity (D/E) Ratio = Total Liabilities / Shareholder Equity."
        >
          D/E{getSortIndicator('debt_to_equity')}
        </th>
        <th
          className={headerClasses}
          onClick={() => handleSort('institutional_ownership')}
          title="Institutional Ownership: % of shares held by large organizations."
        >
          Inst Own{getSortIndicator('institutional_ownership')}
        </th>
        <th className={headerClasses} onClick={() => handleSort('revenue_cagr')}>
          5Y Rev Growth{getSortIndicator('revenue_cagr')}
        </th>
        <th className={headerClasses} onClick={() => handleSort('earnings_cagr')}>
          5Y Inc Growth{getSortIndicator('earnings_cagr')}
        </th>
        <th className={headerClasses} onClick={() => handleSort('dividend_yield')}>
          Dividend Yield{getSortIndicator('dividend_yield')}
        </th>
        <th
          className="px-3 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider w-28"
          title="52-week P/E Range: Shows where current P/E sits within its range."
        >
          TTM P/E Range
        </th>
        <th
          className="px-3 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider w-28"
          title="5-Year Revenue Consistency: Measures how steady revenue growth has been."
        >
          5y Revenue Consistency
        </th>
        <th
          className="px-3 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider w-28"
          title="5-Year Income Consistency: Measures how steady net income growth has been."
        >
          5y Income Consistency
        </th>
        <th className={headerClasses} onClick={() => handleSort('overall_status')}>
          Overall{getSortIndicator('overall_status')}
        </th>
      </tr>
    </thead>
  )
}
