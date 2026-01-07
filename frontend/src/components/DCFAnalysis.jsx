import React, { useState, useEffect } from 'react';
import { Line } from 'react-chartjs-2';
import DCFAIRecommendations, { DCFOptimizeButton } from './DCFAIRecommendations';
// import AnalysisChat from './AnalysisChat'; // Removed for duplicate cleanup
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
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

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

// Helper function to format large numbers as B (billions) or M (millions)
const formatLargeValue = (value) => {
  const absValue = Math.abs(value);
  if (absValue >= 1000000000) {
    return `$${(value / 1000000000).toFixed(2)}B`;
  }
  return `$${(value / 1000000).toFixed(0)}M`;
};

// Custom Legend Component - Matching StockCharts.jsx style
const CustomLegend = ({ items }) => {
  if (!items || items.length === 0) return null

  return (
    <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 mt-4 px-2">
      {items.map((item, idx) => (
        <div key={idx} className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <span
            className="block"
            style={{
              width: item.type === 'rect' ? '12px' : '16px',
              height: item.type === 'rect' ? '12px' : '2px',
              borderRadius: item.type === 'rect' ? '2px' : '0',
              backgroundColor: item.color,
              border: item.border ? `1px solid ${item.borderColor}` : 'none',
              borderStyle: item.dashed ? 'dashed' : 'solid',
              borderColor: item.color
            }}
          />
          <span>{item.label}</span>
        </div>
      ))}
    </div>
  )
}

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

  // AI Recommendations state (lifted from DCFAIRecommendations)
  const [aiRecommendations, setAiRecommendations] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState(null);
  const [selectedScenario, setSelectedScenario] = useState('base');

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

  // Helper to apply a scenario to assumptions
  const applyScenario = (scenario) => {
    setAssumptions(prev => ({
      ...prev,
      growthRate: scenario.growthRate,
      terminalGrowthRate: scenario.terminalGrowthRate,
      discountRate: scenario.discountRate
    }));
    if (scenario.baseYearMethod) {
      setBaseYearMethod(scenario.baseYearMethod);
    }
  };

  // Fetch cached AI recommendations on mount
  useEffect(() => {
    if (!stockData?.symbol) return;

    const controller = new AbortController();

    fetch(`/api/stock/${stockData.symbol}/dcf-recommendations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ only_cached: true }),
      signal: controller.signal
    })
      .then(response => response.json())
      .then(data => {
        if (data.scenarios) {
          setAiRecommendations(data);
          if (data.scenarios.base) {
            applyScenario(data.scenarios.base);
          }
        }
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          console.error('Error checking AI recommendations cache:', err);
        }
      });

    return () => controller.abort();
  }, [stockData?.symbol]);

  // Generate AI recommendations
  const generateAiRecommendations = async () => {
    const forceRefresh = !!aiRecommendations?.scenarios;
    setAiLoading(true);
    setAiError(null);

    try {
      const response = await fetch(`/api/stock/${stockData.symbol}/dcf-recommendations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force_refresh: forceRefresh })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to generate recommendations');
      }

      const data = await response.json();
      setAiRecommendations(data);
      setSelectedScenario('base');

      if (data.scenarios?.base) {
        applyScenario(data.scenarios.base);
      }
    } catch (err) {
      setAiError(err.message);
    } finally {
      setAiLoading(false);
    }
  };

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
          label: 'Historical',
          data: historicalDataset,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          tension: 0.1,
          borderWidth: 2
        },
        {
          label: 'Projected',
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
        display: false
      },
      title: {
        display: false, // Moved to CardTitle for consistency
        text: 'Historical & Projected Free Cash Flow',
        color: 'hsl(var(--foreground))'
      }
    },
    scales: {
      x: {
        ticks: {
          color: '#64748b', // Slate gray for labels
          autoSkip: false,
          maxRotation: 45,
          minRotation: 45
        },
        grid: {
          color: 'rgba(100, 116, 139, 0.1)' // Light grid lines
        }
      },
      y: {
        title: {
          display: true,
          text: 'FCF ($M)',
          color: '#64748b'
        },
        ticks: {
          color: '#64748b'
        },
        grid: {
          color: (context) => {
            // Hide default zero line so we can draw our own
            if (Math.abs(context.tick.value) < 0.00001) {
              return 'transparent';
            }
            return 'rgba(100, 116, 139, 0.1)'; // Light grid for Paper theme
          }
        }
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
    <div className="w-full">
      <div className="dcf-container">
        {/* Historical FCF Chart with AI Optimize Button */}
        {historicalMetrics && getChartData() && (
          <Card className="mb-6 relative">
            <CardHeader className="flex flex-col items-center gap-4 pb-4">
              <CardTitle className="text-xl font-semibold text-center">Free Cash Flow</CardTitle>
            </CardHeader>

            <CardContent className="pt-0">
              <div className="h-64">
                <Line data={getChartData()} options={chartOptions} />
              </div>
              <CustomLegend items={[
                { label: 'Historical', color: '#3b82f6' },
                { label: 'Projected', color: '#10b981', dashed: true }
              ]} />
            </CardContent>
          </Card>
        )}

        {/* AI Recommendations Panel (full display with scenarios and reasoning) */}
        <DCFAIRecommendations
          recommendations={aiRecommendations}
          loading={aiLoading}
          error={aiError}
          selectedScenario={selectedScenario}
          onScenarioSelect={setSelectedScenario}
          onApplyScenario={applyScenario}
        />

        <div className="grid grid-cols-1 2xl:grid-cols-2 gap-6">
          {/* Assumptions Panel */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle>Assumptions</CardTitle>
              <DCFOptimizeButton
                loading={aiLoading}
                hasRecommendations={!!aiRecommendations?.scenarios}
                onGenerate={generateAiRecommendations}
              />
            </CardHeader>
            <CardContent className="space-y-6">

              {/* Base Year Selection */}
              {historicalMetrics && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Base Year FCF</span>
                    <span className="text-sm font-bold text-primary">
                      {formatLargeValue(analysis.baseFCF)}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <label className={`flex items-center gap-2 px-3 py-1.5 rounded-md border cursor-pointer transition-colors ${baseYearMethod === 'latest' ? 'bg-primary/10 border-primary text-primary' : 'border-border hover:bg-muted'}`}>
                      <input
                        type="radio"
                        name="baseYear"
                        value="latest"
                        checked={baseYearMethod === 'latest'}
                        onChange={(e) => setBaseYearMethod(e.target.value)}
                        className="sr-only"
                      />
                      <span className="text-sm">Latest Year ({historicalMetrics.annualHistory[0].year})</span>
                    </label>
                    {historicalMetrics.avg3 && (
                      <label className={`flex items-center gap-2 px-3 py-1.5 rounded-md border cursor-pointer transition-colors ${baseYearMethod === 'avg3' ? 'bg-primary/10 border-primary text-primary' : 'border-border hover:bg-muted'}`}>
                        <input
                          type="radio"
                          name="baseYear"
                          value="avg3"
                          checked={baseYearMethod === 'avg3'}
                          onChange={(e) => setBaseYearMethod(e.target.value)}
                          className="sr-only"
                        />
                        <span className="text-sm">3-Year Average</span>
                      </label>
                    )}
                    {historicalMetrics.avg5 && (
                      <label className={`flex items-center gap-2 px-3 py-1.5 rounded-md border cursor-pointer transition-colors ${baseYearMethod === 'avg5' ? 'bg-primary/10 border-primary text-primary' : 'border-border hover:bg-muted'}`}>
                        <input
                          type="radio"
                          name="baseYear"
                          value="avg5"
                          checked={baseYearMethod === 'avg5'}
                          onChange={(e) => setBaseYearMethod(e.target.value)}
                          className="sr-only"
                        />
                        <span className="text-sm">5-Year Average</span>
                      </label>
                    )}
                  </div>
                </div>
              )}

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Growth Rate (First 5 Years)</span>
                  <span className="text-sm font-bold text-primary">{assumptions.growthRate}%</span>
                </div>
                <input
                  type="range"
                  min="-10"
                  max="30"
                  value={assumptions.growthRate}
                  onChange={(e) => handleAssumptionChange('growthRate', e.target.value)}
                  className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                />
                {historicalMetrics && (
                  <p className="text-xs text-muted-foreground">
                    Historical FCF Growth: {' '}
                    {historicalMetrics.cagr3 !== null && (
                      <span>3yr: {historicalMetrics.cagr3.toFixed(1)}%</span>
                    )}
                    {historicalMetrics.cagr5 !== null && (
                      <span> | 5yr: {historicalMetrics.cagr5.toFixed(1)}%</span>
                    )}
                  </p>
                )}
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Discount Rate (WACC)</span>
                  <span className="text-sm font-bold text-primary">{assumptions.discountRate.toFixed(2)}%</span>
                </div>
                <input
                  type="range"
                  min="5"
                  max="20"
                  step="0.1"
                  value={assumptions.discountRate}
                  onChange={(e) => handleAssumptionChange('discountRate', e.target.value)}
                  className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                />
                {earningsHistory?.wacc && (
                  <div className="text-xs text-muted-foreground space-y-1 p-3 bg-muted/50 rounded-md">
                    <p className="font-semibold flex items-center gap-1">
                      Calculated WACC: {earningsHistory.wacc.wacc}%
                      <span className="cursor-help" title="Weighted Average Cost of Capital">ⓘ</span>
                    </p>
                    <p>• Cost of Equity: {earningsHistory.wacc.cost_of_equity}% (Beta: {earningsHistory.wacc.beta})</p>
                    <p>• After-Tax Cost of Debt: {earningsHistory.wacc.after_tax_cost_of_debt}%</p>
                    <p>• Capital Structure: {earningsHistory.wacc.equity_weight}% Equity / {earningsHistory.wacc.debt_weight}% Debt</p>
                  </div>
                )}
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Terminal Growth Rate</span>
                  <span className="text-sm font-bold text-primary">{assumptions.terminalGrowthRate}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="10"
                  step="0.1"
                  value={assumptions.terminalGrowthRate}
                  onChange={(e) => handleAssumptionChange('terminalGrowthRate', e.target.value)}
                  className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                />
              </div>
            </CardContent>
          </Card>

          {/* Results Panel */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Valuation Results</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="flex-1 min-w-[120px] p-4 bg-muted/50 rounded-lg text-center">
                    <p className="text-sm text-muted-foreground mb-1">Intrinsic Value</p>
                    <p className="text-xl sm:text-2xl font-bold text-primary">${analysis.intrinsicValuePerShare.toFixed(2)}</p>
                  </div>
                  <div className="flex-1 min-w-[120px] p-4 bg-muted/50 rounded-lg text-center">
                    <p className="text-sm text-muted-foreground mb-1">Current Price</p>
                    <p className="text-xl sm:text-2xl font-semibold">${stockData.price.toFixed(2)}</p>
                  </div>
                  <div className={`flex-1 min-w-[120px] p-4 rounded-lg text-center ${analysis.upside > 0 ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
                    <p className="text-sm text-muted-foreground mb-1">Upside / Downside</p>
                    <p className={`text-xl sm:text-2xl font-semibold ${analysis.upside > 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {analysis.upside > 0 ? '+' : ''}{analysis.upside.toFixed(0)}%
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Projections</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Year</TableHead>
                        <TableHead className="text-right">Projected FCF</TableHead>
                        <TableHead className="text-right">Discount Factor</TableHead>
                        <TableHead className="text-right">Present Value</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {analysis.projections.map((row) => (
                        <TableRow key={row.year}>
                          <TableCell>{row.year}</TableCell>
                          <TableCell className="text-right">{formatLargeValue(row.fcf)}</TableCell>
                          <TableCell className="text-right">{row.discountFactor.toFixed(3)}</TableCell>
                          <TableCell className="text-right">{formatLargeValue(row.presentValue)}</TableCell>
                        </TableRow>
                      ))}
                      <TableRow className="font-bold bg-muted/50">
                        <TableCell colSpan={3} className="text-right">Sum of PV of FCF</TableCell>
                        <TableCell className="text-right">{formatLargeValue(analysis.totalPresentValue)}</TableCell>
                      </TableRow>
                      <TableRow className="font-bold bg-muted/50">
                        <TableCell colSpan={3} className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            Terminal Value PV
                            <span className="text-xs text-muted-foreground" title={`Terminal Value: ${formatLargeValue(analysis.terminalValue)}`}>ⓘ</span>
                          </div>
                        </TableCell>
                        <TableCell className="text-right">{formatLargeValue(analysis.terminalValuePresent)}</TableCell>
                      </TableRow>
                      <TableRow className="font-bold text-base border-t-2">
                        <TableCell colSpan={3} className="text-right">Total Equity Value</TableCell>
                        <TableCell className="text-right">{formatLargeValue(analysis.totalEquityValue)}</TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Sensitivity Analysis */}
        < Card className="mt-6" >
          <CardHeader
            className="cursor-pointer flex flex-row items-center space-y-0 pb-2"
            onClick={() => setShowSensitivity(!showSensitivity)}
          >
            <CardTitle className="text-lg flex items-center gap-2">
              <span>{showSensitivity ? '▼' : '▶'}</span>
              Sensitivity Analysis
            </CardTitle>
          </CardHeader>
          {
            showSensitivity && (() => {
              const sensitivity = calculateSensitivity();
              if (!sensitivity) return null;

              return (
                <CardContent className="fade-in-slide-down">
                  <p className="text-sm text-muted-foreground mb-4">
                    Intrinsic value at different growth and discount rates (current assumption highlighted)
                  </p>
                  <div className="rounded-md border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Discount Rate ↓ / Growth Rate →</TableHead>
                          {sensitivity.growthRates.map(rate => (
                            <TableHead key={rate} className="text-center">{rate}%</TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {sensitivity.results.map(row => (
                          <TableRow key={row.discountRate}>
                            <TableCell className="font-semibold">{row.discountRate}%</TableCell>
                            {row.values.map((cell, idx) => {
                              const currentPrice = stockData.price;
                              const percentDiff = ((cell.value - currentPrice) / currentPrice) * 100;

                              let colorClass = '';
                              if (percentDiff > 20) colorClass = 'text-green-500 bg-green-500/10 font-bold';
                              else if (percentDiff > 0) colorClass = 'text-green-600 bg-green-500/5';
                              else if (percentDiff > -20) colorClass = 'text-orange-500 bg-orange-500/5';
                              else colorClass = 'text-red-500 bg-red-500/10 font-bold';

                              return (
                                <TableCell
                                  key={idx}
                                  className={`text-center ${colorClass} ${cell.isCurrent ? 'ring-2 ring-primary' : ''}`}
                                >
                                  ${cell.value.toFixed(0)}
                                </TableCell>
                              );
                            })}
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              );
            })()
          }
        </Card >

      </div >
    </div >
  );
};

export default DCFAnalysis;
