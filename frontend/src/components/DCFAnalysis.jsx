import React, { useState, useEffect } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

// Helper function to calculate CAGR
const calculateCAGR = (startValue, endValue, years) => {
  if (!startValue || !endValue || years <= 0) return null;
  return (Math.pow(endValue / startValue, 1 / years) - 1) * 100;
};

// Helper function to calculate average
const calculateAverage = (values) => {
  const validValues = values.filter(v => v !== null && v !== undefined);
  if (validValues.length === 0) return null;
  return validValues.reduce((sum, val) => sum + val, 0) / validValues.length;
};

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

  const [baseYearMethod, setBaseYearMethod] = useState('latest'); // 'latest', 'avg3', 'avg5'
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState(null);
  const [historicalMetrics, setHistoricalMetrics] = useState(null);
  const [showSensitivity, setShowSensitivity] = useState(false);

  // Update discount rate when WACC becomes available
  useEffect(() => {
    if (earningsHistory?.wacc?.wacc && assumptions.discountRate === 10) {
      // Only update if still at default value (10%)
      setAssumptions(prev => ({
        ...prev,
        discountRate: earningsHistory.wacc.wacc
      }));
    }
  }, [earningsHistory]);

  // Calculate historical metrics
  useEffect(() => {
    if (!earningsHistory || !earningsHistory.history || earningsHistory.history.length === 0) return;

    const annualHistory = earningsHistory.history
      .filter(h => h.period === 'annual' && h.free_cash_flow !== null)
      .sort((a, b) => b.year - a.year);

    if (annualHistory.length === 0) return;

    const fcfValues = annualHistory.map(h => h.free_cash_flow);
    const years = annualHistory.map(h => h.year);

    // Calculate averages
    const avg3 = annualHistory.length >= 3 ? calculateAverage(fcfValues.slice(0, 3)) : null;
    const avg5 = annualHistory.length >= 5 ? calculateAverage(fcfValues.slice(0, 5)) : null;

    // Calculate CAGRs
    const cagr3 = annualHistory.length >= 4 ? calculateCAGR(fcfValues[3], fcfValues[0], 3) : null;
    const cagr5 = annualHistory.length >= 6 ? calculateCAGR(fcfValues[5], fcfValues[0], 5) : null;
    const cagr10 = annualHistory.length >= 11 ? calculateCAGR(fcfValues[10], fcfValues[0], 10) : null;

    setHistoricalMetrics({
      annualHistory,
      latest: fcfValues[0],
      avg3,
      avg5,
      cagr3,
      cagr5,
      cagr10,
      years,
      fcfValues
    });
  }, [earningsHistory]);

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

      // Determine base FCF based on selected method
      let baseFCF;
      let baseYear = annualHistory[0].year;

      if (!historicalMetrics) return; // Wait for historical metrics to be calculated

      switch (baseYearMethod) {
        case 'avg3':
          baseFCF = historicalMetrics.avg3;
          if (!baseFCF) baseFCF = historicalMetrics.latest; // Fallback
          break;
        case 'avg5':
          baseFCF = historicalMetrics.avg5;
          if (!baseFCF) baseFCF = historicalMetrics.latest; // Fallback
          break;
        case 'latest':
        default:
          baseFCF = historicalMetrics.latest;
      }

      console.log('DCFAnalysis: Base FCF', { baseFCF, baseYear, method: baseYearMethod });

      // Calculate projected FCFs
      const projections = [];
      let currentFCF = baseFCF;
      let totalPresentValue = 0;

      for (let i = 1; i <= assumptions.projectionYears; i++) {
        currentFCF = currentFCF * (1 + assumptions.growthRate / 100);
        const discountFactor = Math.pow(1 + assumptions.discountRate / 100, i);
        const presentValue = currentFCF / discountFactor;

        projections.push({
          year: baseYear + i,
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
        baseFCF,
        baseYear,
        baseYearMethod,
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

  }, [assumptions, earningsHistory, stockData, baseYearMethod, historicalMetrics]);

  const handleAssumptionChange = (key, value) => {
    setAssumptions(prev => ({
      ...prev,
      [key]: parseFloat(value)
    }));
  };

  // Calculate sensitivity table
  const calculateSensitivity = () => {
    if (!analysis || !historicalMetrics) return null;

    const growthRates = [-5, 0, 5, 10, 15];
    const discountRates = [8, 10, 12, 14];
    const results = [];

    discountRates.forEach(discountRate => {
      const row = { discountRate, values: [] };
      growthRates.forEach(growthRate => {
        // Quick DCF calc with these rates
        let fcf = analysis.baseFCF;
        let pv = 0;
        for (let i = 1; i <= assumptions.projectionYears; i++) {
          fcf = fcf * (1 + growthRate / 100);
          pv += fcf / Math.pow(1 + discountRate / 100, i);
        }
        // Terminal value
        const terminalFCF = fcf * (1 + assumptions.terminalGrowthRate / 100);
        const terminalValue = terminalFCF / ((discountRate - assumptions.terminalGrowthRate) / 100);
        const terminalPV = terminalValue / Math.pow(1 + discountRate / 100, assumptions.projectionYears);
        const totalValue = pv + terminalPV;
        const valuePerShare = totalValue / analysis.sharesOutstanding;

        row.values.push({
          growthRate,
          value: valuePerShare,
          isCurrent: growthRate === assumptions.growthRate && discountRate === assumptions.discountRate
        });
      });
      results.push(row);
    });

    return { growthRates, results };
  };

  // Prepare chart data
  const getChartData = () => {
    if (!historicalMetrics || !analysis) return null;

    const last10Years = historicalMetrics.annualHistory.slice(0, 10).reverse();

    // Prepare historical data
    const historicalLabels = last10Years.map(h => h.year.toString());
    const historicalData = last10Years.map(h => h.free_cash_flow / 1000000);

    // Prepare projection data
    // Start from base year and add projections
    const projectionLabels = [analysis.baseYear.toString(), ...analysis.projections.map(p => p.year.toString())];
    const projectionData = [analysis.baseFCF / 1000000, ...analysis.projections.map(p => p.fcf / 1000000)];

    // Combine labels (historical + future years)
    const allLabels = [...historicalLabels, ...analysis.projections.map(p => p.year.toString())];

    // Create datasets with null padding
    const historicalDataset = [...historicalData, ...Array(analysis.projections.length).fill(null)];

    // For projection, start from the last historical value to ensure smooth connection
    const lastHistoricalValue = historicalData[historicalData.length - 1];
    const projectionDataset = [...Array(historicalLabels.length - 1).fill(null), lastHistoricalValue, ...analysis.projections.map(p => p.fcf / 1000000)];

    return {
      labels: allLabels,
      datasets: [
        {
          label: 'Historical FCF',
          data: historicalDataset,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          tension: 0.1,
          borderWidth: 2
        },
        {
          label: 'Projected FCF',
          data: projectionDataset,
          borderColor: '#10b981',
          backgroundColor: 'rgba(16, 185, 129, 0.1)',
          borderDash: [5, 5],
          tension: 0.1,
          borderWidth: 2
        }
      ]
    };
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true,
        labels: {
          color: '#cbd5e1',
          usePointStyle: true,
          padding: 15
        }
      },
      title: {
        display: true,
        text: 'Historical & Projected Free Cash Flow',
        color: '#f1f5f9'
      }
    },
    scales: {
      y: {
        ticks: { color: '#94a3b8' },
        grid: { color: '#334155' },
        title: {
          display: true,
          text: 'FCF ($M)',
          color: '#94a3b8'
        }
      },
      x: {
        ticks: { color: '#94a3b8' },
        grid: { color: '#334155' }
      }
    }
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
      {/* Historical FCF Chart */}
      {historicalMetrics && getChartData() && (
        <div className="dcf-panel dcf-historical-chart">
          <div style={{ height: '250px' }}>
            <Line data={getChartData()} options={chartOptions} />
          </div>
        </div>
      )}

      <div className="dcf-grid">
        {/* Assumptions Panel */}
        <div className="dcf-panel assumptions-panel">
          <h3>Assumptions</h3>

          {/* Base Year Selection */}
          {historicalMetrics && (
            <div className="assumption-group">
              <div className="assumption-header">
                <label>Base Year FCF</label>
                <span className="assumption-value">
                  ${(analysis.baseFCF / 1000000).toFixed(0)}M
                </span>
              </div>
              <div className="base-year-selector">
                <label className={baseYearMethod === 'latest' ? 'active' : ''}>
                  <input
                    type="radio"
                    name="baseYear"
                    value="latest"
                    checked={baseYearMethod === 'latest'}
                    onChange={(e) => setBaseYearMethod(e.target.value)}
                  />
                  Latest Year ({historicalMetrics.annualHistory[0].year})
                </label>
                {historicalMetrics.avg3 && (
                  <label className={baseYearMethod === 'avg3' ? 'active' : ''}>
                    <input
                      type="radio"
                      name="baseYear"
                      value="avg3"
                      checked={baseYearMethod === 'avg3'}
                      onChange={(e) => setBaseYearMethod(e.target.value)}
                    />
                    3-Year Average
                  </label>
                )}
                {historicalMetrics.avg5 && (
                  <label className={baseYearMethod === 'avg5' ? 'active' : ''}>
                    <input
                      type="radio"
                      name="baseYear"
                      value="avg5"
                      checked={baseYearMethod === 'avg5'}
                      onChange={(e) => setBaseYearMethod(e.target.value)}
                    />
                    5-Year Average
                  </label>
                )}
              </div>
            </div>
          )}

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
            {historicalMetrics && (
              <div className="historical-growth-rates">
                <small>Historical FCF Growth: </small>
                {historicalMetrics.cagr3 !== null && (
                  <small>3yr: {historicalMetrics.cagr3.toFixed(1)}%</small>
                )}
                {historicalMetrics.cagr5 !== null && (
                  <small> | 5yr: {historicalMetrics.cagr5.toFixed(1)}%</small>
                )}
                {historicalMetrics.cagr10 !== null && (
                  <small> | 10yr: {historicalMetrics.cagr10.toFixed(1)}%</small>
                )}
              </div>
            )}
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
            {earningsHistory?.wacc && (
              <div className="wacc-breakdown">
                <small>
                  <strong>Calculated WACC: {earningsHistory.wacc.wacc}%</strong>
                  <span className="info-icon" title="Weighted Average Cost of Capital">ⓘ</span>
                </small>
                <small>
                  • Cost of Equity: {earningsHistory.wacc.cost_of_equity}% (Beta: {earningsHistory.wacc.beta})
                </small>
                <small>
                  • After-Tax Cost of Debt: {earningsHistory.wacc.after_tax_cost_of_debt}%
                </small>
                <small>
                  • Capital Structure: {earningsHistory.wacc.equity_weight}% Equity / {earningsHistory.wacc.debt_weight}% Debt
                </small>
              </div>
            )}
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

      {/* Sensitivity Analysis */}
      <div className="dcf-panel">
        <div
          className="sensitivity-toggle"
          onClick={() => setShowSensitivity(!showSensitivity)}
        >
          <span>{showSensitivity ? '▼' : '▶'}</span>
          <h3>Sensitivity Analysis</h3>
        </div>
        {showSensitivity && (() => {
          const sensitivity = calculateSensitivity();
          if (!sensitivity) return null;

          return (
            <div className="sensitivity-content">
              <p style={{ color: '#94a3b8', fontSize: '0.9rem', marginBottom: '1rem' }}>
                Intrinsic value at different growth and discount rates (current assumption highlighted)
              </p>
              <div className="table-container">
                <table className="sensitivity-table">
                  <thead>
                    <tr>
                      <th>Discount Rate ↓ / Growth Rate →</th>
                      {sensitivity.growthRates.map(rate => (
                        <th key={rate} align="center">{rate}%</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sensitivity.results.map(row => (
                      <tr key={row.discountRate}>
                        <td><strong>{row.discountRate}%</strong></td>
                        {row.values.map((cell, idx) => {
                          const currentPrice = stockData.price;
                          const percentDiff = ((cell.value - currentPrice) / currentPrice) * 100;
                          let colorClass = '';
                          if (percentDiff > 20) colorClass = 'sens-high';
                          else if (percentDiff > 0) colorClass = 'sens-medium';
                          else if (percentDiff > -20) colorClass = 'sens-low';
                          else colorClass = 'sens-very-low';

                          return (
                            <td
                              key={idx}
                              align="center"
                              className={`${colorClass} ${cell.isCurrent ? 'sens-current' : ''}`}
                            >
                              ${cell.value.toFixed(0)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })()}
      </div>

    </div>
  );
};

export default DCFAnalysis;
