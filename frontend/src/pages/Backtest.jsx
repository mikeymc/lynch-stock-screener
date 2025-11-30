import React, { useState } from 'react'
import { Line } from 'react-chartjs-2'

function Backtest() {
    const [symbol, setSymbol] = useState('')
    const [yearsBack, setYearsBack] = useState(1)
    const [loading, setLoading] = useState(false)
    const [result, setResult] = useState(null)
    const [error, setError] = useState(null)

    const handleRunBacktest = async (e) => {
        e.preventDefault()
        if (!symbol) return

        setLoading(true)
        setError(null)
        setResult(null)

        try {
            const response = await fetch('/api/backtest', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    symbol: symbol,
                    years_back: yearsBack
                })
            })

            const data = await response.json()

            if (!response.ok) {
                throw new Error(data.error || 'Failed to run backtest')
            }

            setResult(data)
        } catch (err) {
            console.error('Backtest error:', err)
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="backtest-page" style={{ padding: '20px', maxWidth: '800px', margin: '0 auto' }}>
            <h1>Backtest Strategy</h1>
            <p className="description">
                See how the Lynch strategy would have performed if you used it in the past.
                Enter a stock symbol and choose a timeframe to "time travel" and see the historical score vs. actual return.
            </p>

            <form onSubmit={handleRunBacktest} className="backtest-form" style={{ display: 'flex', gap: '10px', marginBottom: '30px', alignItems: 'center' }}>
                <input
                    type="text"
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                    placeholder="Symbol (e.g. GOOGL)"
                    style={{ padding: '10px', fontSize: '16px', borderRadius: '4px', border: '1px solid #ccc' }}
                />

                <select
                    value={yearsBack}
                    onChange={(e) => setYearsBack(Number(e.target.value))}
                    style={{ padding: '10px', fontSize: '16px', borderRadius: '4px', border: '1px solid #ccc' }}
                >
                    <option value={1}>1 Year Ago</option>
                    <option value={3}>3 Years Ago</option>
                    <option value={5}>5 Years Ago</option>
                </select>

                <button
                    type="submit"
                    disabled={loading || !symbol}
                    style={{
                        padding: '10px 20px',
                        fontSize: '16px',
                        backgroundColor: '#2563eb',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: loading ? 'not-allowed' : 'pointer',
                        opacity: loading ? 0.7 : 1
                    }}
                >
                    {loading ? 'Running...' : 'Run Backtest'}
                </button>
            </form>

            {error && (
                <div className="error-message" style={{ padding: '15px', backgroundColor: '#fee2e2', color: '#b91c1c', borderRadius: '4px', marginBottom: '20px' }}>
                    Error: {error}
                </div>
            )}

            {result && (
                <div className="results-container" style={{ backgroundColor: '#f8fafc', padding: '20px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                    <h2 style={{ marginTop: 0 }}>Results for {result.symbol}</h2>

                    <div className="metrics-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px', marginTop: '20px' }}>
                        <div className="metric-card" style={{ backgroundColor: 'white', padding: '15px', borderRadius: '6px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                            <div className="label" style={{ color: '#64748b', fontSize: '14px' }}>Historical Date</div>
                            <div className="value" style={{ fontSize: '18px', fontWeight: 'bold' }}>{result.backtest_date}</div>
                        </div>

                        <div className="metric-card" style={{ backgroundColor: 'white', padding: '15px', borderRadius: '6px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                            <div className="label" style={{ color: '#64748b', fontSize: '14px' }}>Historical Score</div>
                            <div className="value" style={{ fontSize: '24px', fontWeight: 'bold', color: result.historical_score >= 80 ? '#16a34a' : result.historical_score >= 60 ? '#2563eb' : '#ca8a04' }}>
                                {result.historical_score}
                            </div>
                            <div className="sub-value" style={{ fontSize: '14px', color: '#64748b' }}>{result.historical_rating}</div>
                        </div>

                        <div className="metric-card" style={{ backgroundColor: 'white', padding: '15px', borderRadius: '6px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                            <div className="label" style={{ color: '#64748b', fontSize: '14px' }}>Total Return</div>
                            <div className="value" style={{ fontSize: '24px', fontWeight: 'bold', color: result.total_return >= 0 ? '#16a34a' : '#dc2626' }}>
                                {result.total_return > 0 ? '+' : ''}{result.total_return.toFixed(2)}%
                            </div>
                            <div className="sub-value" style={{ fontSize: '14px', color: '#64748b' }}>
                                ${result.start_price.toFixed(2)} → ${result.end_price.toFixed(2)}
                            </div>
                        </div>
                    </div>

                    <div className="details-section" style={{ marginTop: '30px' }}>
                        <h3>Historical Snapshot</h3>
                        <p>Based on data available on {result.backtest_date}:</p>
                        <ul style={{ lineHeight: '1.6' }}>
                            <li><strong>P/E Ratio:</strong> {result.historical_data.pe_ratio ? result.historical_data.pe_ratio.toFixed(2) : 'N/A'}</li>
                            <li><strong>PEG Ratio:</strong> {result.historical_data.peg_ratio ? result.historical_data.peg_ratio.toFixed(2) : 'N/A'}</li>
                            <li><strong>Earnings Growth (CAGR):</strong> {result.historical_data.earnings_cagr ? result.historical_data.earnings_cagr.toFixed(2) + '%' : 'N/A'}</li>
                            <li><strong>Debt/Equity:</strong> {result.historical_data.debt_to_equity ? result.historical_data.debt_to_equity.toFixed(2) : 'N/A'}</li>
                        </ul>
                    </div>
                </div>
            )}
        </div>
    )
}

export default Backtest
