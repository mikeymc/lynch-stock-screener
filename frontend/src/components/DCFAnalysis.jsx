import React, { useState, useEffect } from 'react';

const DCFAnalysis = ({ stockData, earningsHistory }) => {
  // Default assumptions
  const [assumptions, setAssumptions] = useState({
    growthRate: 5, // 5% growth for first 5 years
    terminalGrowthRate: 2.5, // 2.5% terminal growth
    discountRate: 10, // 10% discount rate
    terminalMultiple: 15, // 15x terminal multiple (alternative to terminal growth)
    projectionYears: 5,
    useTerminalMultiple: false // Toggle between Gordon Growth and Exit Multiple
  });

  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState(null);

  // Calculate DCF whenever assumptions or data change
  useEffect(() => {
    console.log('DCFAnalysis: useEffect triggered', {
      hasEarningsHistory: !!earningsHistory,
      earningsHistoryLength: earningsHistory?.length,
      stockDataPrice: stockData?.price
    });

    if (!earningsHistory || !earningsHistory.history || earningsHistory.history.length === 0) return;

    try {
      // Find latest annual Free Cash Flow
      // Filter for annual data and sort by year descending
      const annualHistory = earningsHistory.history
        .filter(h => h.period === 'annual' && h.free_cash_flow !== null)
        .sort((a, b) => b.year - a.year);

      if (annualHistory.length === 0) {
        console.log('DCFAnalysis: No annual history with FCF found');
        return;
      }

      const latestFCF = annualHistory[0].free_cash_flow;
      const latestYear = annualHistory[0].year;

      console.log('DCFAnalysis: Latest FCF', { latestFCF, latestYear });

      // Calculate projected FCFs
      const projections = [];
      let currentFCF = latestFCF;
      let totalPresentValue = 0;

      for (let i = 1; i <= assumptions.projectionYears; i++) {
        currentFCF = currentFCF * (1 + assumptions.growthRate / 100);
        const discountFactor = Math.pow(1 + assumptions.discountRate / 100, i);
        const presentValue = currentFCF / discountFactor;

        projections.push({
          year: latestYear + i,
          fcf: currentFCF,
          discountFactor,
          presentValue
        });

        totalPresentValue += presentValue;
      }

      // Calculate Terminal Value
      let terminalValue = 0;
      let terminalValuePresent = 0;
      const lastProjectedFCF = projections[projections.length - 1].fcf;

      if (assumptions.useTerminalMultiple) {
        // Exit Multiple Method
        terminalValue = lastProjectedFCF * assumptions.terminalMultiple;
      } else {
        // Gordon Growth Method
        // TV = (FCF_n * (1 + g)) / (r - g)
        const nextFCF = lastProjectedFCF * (1 + assumptions.terminalGrowthRate / 100);
        const denominator = (assumptions.discountRate - assumptions.terminalGrowthRate) / 100;

        if (denominator > 0) {
          terminalValue = nextFCF / denominator;
        } else {
          terminalValue = 0; // Invalid if growth >= discount
        }
      }

      // Discount Terminal Value
      terminalValuePresent = terminalValue / Math.pow(1 + assumptions.discountRate / 100, assumptions.projectionYears);

      // Total Equity Value
      const totalEquityValue = totalPresentValue + terminalValuePresent;

      // Shares Outstanding (approximate from Market Cap / Price)
      if (!stockData.price || stockData.price === 0) {
        throw new Error("Stock price is zero or missing");
      }

      const sharesOutstanding = stockData.market_cap / stockData.price;

      const intrinsicValuePerShare = totalEquityValue / sharesOutstanding;
      const upside = ((intrinsicValuePerShare - stockData.price) / stockData.price) * 100;

      console.log('DCFAnalysis: Calculation complete', { intrinsicValuePerShare, upside });

      setAnalysis({
        latestFCF,
        latestYear,
        projections,
        terminalValue,
        terminalValuePresent,
        totalPresentValue,
        totalEquityValue,
        intrinsicValuePerShare,
        upside,
        sharesOutstanding
      });
      setError(null);
    } catch (err) {
      console.error('DCFAnalysis: Calculation error', err);
      setError(err.message);
    }

  }, [assumptions, earningsHistory, stockData]);

  const handleAssumptionChange = (key, value) => {
    setAssumptions(prev => ({
      ...prev,
      [key]: parseFloat(value)
    }));
  };

  if (error) {
    return (
      <div className="dcf-container">
        <div className="error-message">
          Calculation Error: {error}
        </div>
      </div>
    );
  }

  if (!stockData || typeof stockData.price !== 'number' || !analysis) {
    return (
      <div className="dcf-container">
        <div className="empty-state">
          {!stockData || typeof stockData.price !== 'number'
            ? "Insufficient stock data (Price missing)"
            : "Insufficient data for DCF Analysis (Need Free Cash Flow history)"}
        </div>
      </div>
    );
  }

  return (
    <div className="dcf-container">
      <div className="dcf-grid">
        {/* Assumptions Panel */}
        <div className="dcf-panel assumptions-panel">
          <h3>Assumptions</h3>

          <div className="assumption-group">
            <div className="assumption-header">
              <label>Growth Rate (First 5 Years)</label>
              <span className="assumption-value">{assumptions.growthRate}%</span>
            </div>
            <input
              type="range"
              min="-10"
              max="30"
              value={assumptions.growthRate}
              onChange={(e) => handleAssumptionChange('growthRate', e.target.value)}
              className="assumption-slider"
            />
          </div>

          <div className="assumption-group">
            <div className="assumption-header">
              <label>Discount Rate (WACC)</label>
              <span className="assumption-value">{assumptions.discountRate}%</span>
            </div>
            <input
              type="range"
              min="5"
              max="20"
              value={assumptions.discountRate}
              onChange={(e) => handleAssumptionChange('discountRate', e.target.value)}
              className="assumption-slider"
            />
          </div>

          <div className="assumption-group">
            <div className="assumption-header">
              <label>Terminal Growth Rate</label>
              <span className="assumption-value">{assumptions.terminalGrowthRate}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="10"
              step="0.1"
              value={assumptions.terminalGrowthRate}
              onChange={(e) => handleAssumptionChange('terminalGrowthRate', e.target.value)}
              className="assumption-slider"
            />
          </div>
        </div>

        {/* Results Panel */}
        <div className="dcf-content">
          <div className="dcf-panel results-panel">
            <h3>Valuation Results</h3>
            <div className="results-grid">
              <div className="result-card">
                <span className="result-label">Intrinsic Value</span>
                <span className="result-value highlight">${analysis.intrinsicValuePerShare.toFixed(2)}</span>
              </div>
              <div className="result-card">
                <span className="result-label">Current Price</span>
                <span className="result-value">${stockData.price.toFixed(2)}</span>
              </div>
              <div className={`result-card ${analysis.upside > 0 ? 'positive' : 'negative'}`}>
                <span className="result-label">Upside / Downside</span>
                <span className="result-value">
                  {analysis.upside > 0 ? '+' : ''}{analysis.upside.toFixed(2)}%
                </span>
              </div>
            </div>
          </div>

          <div className="dcf-panel projections-panel">
            <h3>Projections</h3>
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Year</th>
                    <th align="right">Projected FCF</th>
                    <th align="right">Discount Factor</th>
                    <th align="right">Present Value</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.projections.map((row) => (
                    <tr key={row.year}>
                      <td>{row.year}</td>
                      <td align="right">${(row.fcf / 1000000).toFixed(0)}M</td>
                      <td align="right">{row.discountFactor.toFixed(3)}</td>
                      <td align="right">${(row.presentValue / 1000000).toFixed(0)}M</td>
                    </tr>
                  ))}
                  <tr className="summary-row">
                    <td colSpan={3} align="right"><strong>Sum of PV of FCF</strong></td>
                    <td align="right"><strong>${(analysis.totalPresentValue / 1000000).toFixed(0)}M</strong></td>
                  </tr>
                  <tr className="summary-row">
                    <td colSpan={3} align="right">
                      <strong>Terminal Value PV</strong>
                      <span className="info-icon" title={`Terminal Value: $${(analysis.terminalValue / 1000000).toFixed(0)}M`}>ⓘ</span>
                    </td>
                    <td align="right"><strong>${(analysis.terminalValuePresent / 1000000).toFixed(0)}M</strong></td>
                  </tr>
                  <tr className="total-row">
                    <td colSpan={3} align="right"><strong>Total Equity Value</strong></td>
                    <td align="right"><strong>${(analysis.totalEquityValue / 1000000).toFixed(0)}M</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

    </div>
  );
};

export default DCFAnalysis;
