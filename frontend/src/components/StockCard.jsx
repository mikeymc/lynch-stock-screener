// ABOUTME: Stock card component - building element by element
// ABOUTME: Step 3: Adding first metric column (Price)

import './StockCard.css'
import StatusBar from './StatusBar'

// Format number to 3 significant digits
function formatSigFigs(num, sigFigs = 3) {
    if (typeof num !== 'number' || isNaN(num)) return 'N/A'
    if (num === 0) return '0'

    const magnitude = Math.floor(Math.log10(Math.abs(num)))
    const precision = sigFigs - magnitude - 1

    if (precision < 0) {
        // Large numbers - round to nearest integer
        return Math.round(num).toString()
    } else {
        return num.toFixed(Math.max(0, precision))
    }
}

// Format market cap with 3 sig figs - use M for < 1B, B for >= 1B, T for >= 1T
function formatMarketCap(marketCap) {
    if (typeof marketCap !== 'number') return 'N/A'
    if (marketCap >= 1e12) {
        return `$${formatSigFigs(marketCap / 1e12)}T`
    } else if (marketCap >= 1e9) {
        return `$${formatSigFigs(marketCap / 1e9)}B`
    } else {
        return `$${formatSigFigs(marketCap / 1e6)}M`
    }
}

// Format growth percentage with +/- sign, always 2 digits (e.g., +12%, +3.0%, -25%)
function formatGrowth(value) {
    if (typeof value !== 'number' || isNaN(value)) return 'N/A'
    const sign = value >= 0 ? '+' : ''
    // If value is >= 10 or <= -10, show no decimals. Otherwise show 1 decimal.
    const formatted = Math.abs(value) >= 10 ? value.toFixed(0) : value.toFixed(1)
    return `${sign}${formatted}%`
}

// Format status name for display
function formatStatusName(status) {
    const statusMap = {
        'STRONG_BUY': 'Excellent',
        'BUY': 'Good',
        'HOLD': 'Fair',
        'CAUTION': 'Weak',
        'AVOID': 'Poor'
    }
    return statusMap[status] || status
}

// Get status CSS class
function getStatusClass(status) {
    const classMap = {
        'STRONG_BUY': 'strong-buy',
        'BUY': 'buy',
        'HOLD': 'hold',
        'CAUTION': 'caution',
        'AVOID': 'avoid'
    }
    return classMap[status] || ''
}

export default function StockCard({ stock, watchlist, onToggleWatchlist, onClick }) {
    const handleClick = () => {
        if (onClick) onClick(stock.symbol)
    }

    const handleStarClick = (e) => {
        e.stopPropagation()
        if (onToggleWatchlist) onToggleWatchlist(stock.symbol)
    }

    const isWatched = watchlist && watchlist.has(stock.symbol)

    return (
        <div className="stock-card" onClick={handleClick}>
            {/* Star */}
            <button
                className={`stock-card-star ${isWatched ? 'watched' : ''}`}
                onClick={handleStarClick}
            >
                ⭐
            </button>

            {/* Symbol + Company Name */}
            <div className="stock-card-identity">
                <span className="stock-card-symbol">{stock.symbol}</span>
                <span className="stock-card-name">{stock.company_name || 'N/A'}</span>
            </div>

            {/* Price */}
            <div className="stock-card-metric metric-price">
                <span className="metric-value">
                    {typeof stock.price === 'number' ? `$${stock.price.toFixed(0)}` : 'N/A'}
                </span>
                <span className="metric-label">Current Price</span>
            </div>

            {/* Market Cap */}
            <div className="stock-card-metric metric-cap">
                <span className="metric-value">{formatMarketCap(stock.market_cap)}</span>
                <span className="metric-label">Market Cap</span>
            </div>

            {/* P/E Ratio */}
            <div className="stock-card-metric metric-pe">
                <span className="metric-value">{formatSigFigs(stock.pe_ratio)}</span>
                <span className="metric-label">P/E Ratio</span>
            </div>

            {/* PEG Ratio */}
            <div className="stock-card-metric metric-peg">
                <span className="metric-value">
                    {typeof stock.peg_ratio === 'number' ? stock.peg_ratio.toFixed(1) : 'N/A'}
                </span>
                <span className="metric-label">PEG Ratio</span>
            </div>

            {/* Revenue Growth */}
            <div className="stock-card-metric metric-revenue">
                <span className={`metric-value ${typeof stock.revenue_cagr === 'number' ? (stock.revenue_cagr >= 0 ? 'positive' : 'negative') : ''}`}>
                    {formatGrowth(stock.revenue_cagr)}
                </span>
                <span className="metric-label">Revenue Growth</span>
            </div>

            {/* Income Growth */}
            <div className="stock-card-metric metric-income">
                <span className={`metric-value ${typeof stock.earnings_cagr === 'number' ? (stock.earnings_cagr >= 0 ? 'positive' : 'negative') : ''}`}>
                    {formatGrowth(stock.earnings_cagr)}
                </span>
                <span className="metric-label">Income Growth</span>
            </div>

            {/* Dividend Yield */}
            <div className="stock-card-metric metric-dividend">
                <span className="metric-value">
                    {typeof stock.dividend_yield === 'number'
                        ? `${stock.dividend_yield.toFixed(1)}%`
                        : 'N/A'}
                </span>
                <span className="metric-label">Dividend Yield</span>
            </div>

            {/* D/E Ratio */}
            <div className="stock-card-metric metric-de">
                <span className="metric-value">
                    {typeof stock.debt_to_equity === 'number'
                        ? stock.debt_to_equity.toFixed(1)
                        : 'N/A'}
                </span>
                <span className="metric-label">D/E Ratio</span>
            </div>

            {/* Status Bars Section */}
            <div className="stock-card-bars">
                <div className="stock-card-bar-item">
                    <StatusBar
                        compact={true}
                        metricType="pe_range"
                        score={stock.pe_52_week_position || 0}
                        value={stock.pe_ratio}
                        status="P/E"
                    />
                    <span className="bar-label">P/E Range</span>
                </div>
                <div className="stock-card-bar-item">
                    <StatusBar
                        compact={true}
                        metricType="revenue_consistency"
                        score={stock.revenue_consistency_score || 0}
                        value={stock.revenue_consistency_score}
                        status="Revenue"
                    />
                    <span className="bar-label">Rev Consistency</span>
                </div>
                <div className="stock-card-bar-item">
                    <StatusBar
                        compact={true}
                        metricType="income_consistency"
                        score={stock.income_consistency_score || 0}
                        value={stock.income_consistency_score}
                        status="Income"
                    />
                    <span className="bar-label">Inc Consistency</span>
                </div>
                <div className="stock-card-bar-item">
                    <StatusBar
                        compact={true}
                        metricType="institutional"
                        score={(stock.institutional_ownership || 0) * 100}
                        value={(stock.institutional_ownership || 0) * 100}
                        status="Inst"
                    />
                    <span className="bar-label">Inst Ownership</span>
                </div>
            </div>

            {/* Overall Score Badge */}
            <div className={`stock-card-badge summary-stat ${getStatusClass(stock.overall_status)}`}>
                {formatStatusName(stock.overall_status)}
            </div>
        </div>
    )
}
