import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './AlgorithmTuning.css';

const CollapsibleSection = ({ title, children, defaultOpen = false }) => {
    const [isOpen, setIsOpen] = useState(defaultOpen);

    return (
        <div className="collapsible-section">
            <div className="collapsible-header" onClick={() => setIsOpen(!isOpen)}>
                <span>{title}</span>
                <span className={`collapsible-arrow ${isOpen ? 'open' : ''}`}>▼</span>
            </div>
            {isOpen && (
                <div className="collapsible-content">
                    {children}
                </div>
            )}
        </div>
    );
};

export default function AlgorithmTuning() {
    const navigate = useNavigate();
    const [config, setConfig] = useState({
        // Weights
        weight_peg: 0.50,
        weight_consistency: 0.25,
        weight_debt: 0.15,
        weight_ownership: 0.10,

        // PEG Thresholds
        peg_excellent: 1.0,
        peg_good: 1.5,
        peg_fair: 2.0,

        // Debt Thresholds
        debt_excellent: 0.5,
        debt_good: 1.0,
        debt_moderate: 2.0,

        // Institutional Ownership Thresholds
        inst_own_min: 0.20,
        inst_own_max: 0.60,

        // Revenue Growth Thresholds
        revenue_growth_excellent: 15.0,
        revenue_growth_good: 10.0,
        revenue_growth_fair: 5.0,

        // Income Growth Thresholds
        income_growth_excellent: 15.0,
        income_growth_good: 10.0,
        income_growth_fair: 5.0
    });

    const [validationRunning, setValidationRunning] = useState(false);
    const [optimizationRunning, setOptimizationRunning] = useState(false);
    const [rescoringRunning, setRescoringRunning] = useState(false);
    const [validationJobId, setValidationJobId] = useState(null);
    const [optimizationJobId, setOptimizationJobId] = useState(null);
    const [rescoringJobId, setRescoringJobId] = useState(null);

    const [analysis, setAnalysis] = useState(null);
    const [optimizationResult, setOptimizationResult] = useState(null);
    const [optimizationProgress, setOptimizationProgress] = useState(null);
    const [rescoringProgress, setRescoringProgress] = useState(null);
    const [yearsBack, setYearsBack] = useState(5);

    // Load current configuration on mount
    useEffect(() => {
        const controller = new AbortController();
        const signal = controller.signal;

        loadCurrentConfig(signal);

        return () => controller.abort();
    }, []);

    const loadCurrentConfig = async (signal) => {
        try {
            const response = await fetch('/api/algorithm/config', { signal });
            const data = await response.json();
            if (data.current) {
                setConfig(data.current);
            }
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('Error loading config:', error);
            }
        }
    };

    const handleSliderChange = (key, value) => {
        const numValue = parseFloat(value);

        // If it's a weight, we need to normalize other weights
        if (key.startsWith('weight_')) {
            const newConfig = { ...config, [key]: numValue };

            // Auto-normalize to ensure sum = 1
            // Get all weight keys
            const weightKeys = Object.keys(config).filter(k => k.startsWith('weight_'));

            // Calculate total
            const total = weightKeys.reduce((sum, k) => sum + newConfig[k], 0);

            // Normalize
            const normalized = { ...newConfig };
            weightKeys.forEach(k => {
                normalized[k] = newConfig[k] / total;
            });

            setConfig(normalized);
        } else {
            // For thresholds, just update the value directly
            setConfig({ ...config, [key]: numValue });
        }
    };

    const runValidation = async () => {
        setValidationRunning(true);
        setAnalysis(null);

        try {
            const response = await fetch('/api/validate/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    years_back: yearsBack,
                    limit: null,  // No limit - run full S&P 500
                    config: config
                })
            });

            const data = await response.json();
            setValidationJobId(data.job_id);

            // Poll for results
            pollValidationProgress(data.job_id);
        } catch (error) {
            console.error('Error starting validation:', error);
            setValidationRunning(false);
        }
    };

    const pollValidationProgress = async (jobId) => {
        const interval = setInterval(async () => {
            try {
                const response = await fetch(`/api/validate/progress/${jobId}`);
                const data = await response.json();

                if (data.status === 'complete') {
                    clearInterval(interval);
                    setValidationRunning(false);
                    setAnalysis(data.analysis);
                } else if (data.status === 'error') {
                    clearInterval(interval);
                    setValidationRunning(false);
                    console.error('Validation error:', data.error);
                }
            } catch (error) {
                console.error('Error polling validation:', error);
            }
        }, 2000);
    };

    const runOptimization = async () => {
        setOptimizationRunning(true);
        setOptimizationResult(null);
        setOptimizationProgress(null);

        try {
            const response = await fetch('/api/optimize/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    years_back: yearsBack,
                    method: 'bayesian',
                    max_iterations: 100,
                    limit: null  // Run on full S&P 500
                })
            });
            const data = await response.json();

            if (data.error) {
                alert('Error starting optimization: ' + data.error);
                setOptimizationRunning(false);
                return;
            }

            const jobId = data.job_id;

            // Poll for progress
            const pollInterval = setInterval(async () => {
                try {
                    const statusRes = await fetch(`/api/optimize/progress/${jobId}`);
                    const statusData = await statusRes.json();

                    if (statusData.error) {
                        clearInterval(pollInterval);
                        setOptimizationRunning(false);
                        alert('Error checking progress: ' + statusData.error);
                        return;
                    }

                    // Update progress state
                    setOptimizationProgress(statusData);

                    if (statusData.status === 'complete') {
                        clearInterval(pollInterval);
                        setOptimizationResult(statusData);
                        setOptimizationRunning(false);
                        setOptimizationProgress(null); // Clear progress when done
                    } else if (statusData.status === 'error') {
                        clearInterval(pollInterval);
                        setOptimizationRunning(false);
                        alert('Optimization failed: ' + statusData.error);
                    }
                } catch (e) {
                    console.error("Polling error", e);
                }
            }, 1000);

        } catch (error) {
            console.error('Error running optimization:', error);
            setOptimizationRunning(false);
        }
    };



    const applyOptimizedConfig = () => {
        if (optimizationResult && optimizationResult.result && optimizationResult.result.best_config) {
            setConfig(optimizationResult.result.best_config);
        }
    };

    const saveConfiguration = async () => {
        try {
            setRescoringRunning(true);
            setRescoringProgress(null);

            const response = await fetch('/api/algorithm/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config })
            });

            const data = await response.json();

            if (data.rescore_job_id) {
                setRescoringJobId(data.rescore_job_id);
                // Poll for rescoring progress
                pollRescoringProgress(data.rescore_job_id);
            } else {
                alert('Configuration saved!');
                setRescoringRunning(false);
            }

            loadCurrentConfig();
        } catch (error) {
            console.error('Error saving configuration:', error);
            setRescoringRunning(false);
        }
    };

    const pollRescoringProgress = async (jobId) => {
        const interval = setInterval(async () => {
            try {
                const response = await fetch(`/api/rescore/progress/${jobId}`);
                const data = await response.json();

                setRescoringProgress(data);

                if (data.status === 'complete') {
                    clearInterval(interval);
                    setRescoringRunning(false);
                    setRescoringProgress(null);
                    alert(`Configuration saved and re-scored ${data.summary?.success || 0} stocks!`);
                } else if (data.status === 'error') {
                    clearInterval(interval);
                    setRescoringRunning(false);
                    setRescoringProgress(null);
                    alert('Rescoring error: ' + data.error);
                }
            } catch (error) {
                console.error('Error polling rescoring:', error);
            }
        }, 1000);
    };

    const renderSlider = (key, label, min, max, step, isPercentage = false) => (
        <div key={key} className="slider-group">
            <label>{label}</label>
            <div className="slider-container">
                <input
                    type="range"
                    min={min}
                    max={max}
                    step={step}
                    value={config[key] || 0}
                    onChange={(e) => handleSliderChange(key, e.target.value)}
                />
                <span className="slider-value">
                    {isPercentage ? (config[key] * 100).toFixed(1) + '%' : config[key]?.toFixed(2)}
                </span>
            </div>
        </div>
    );

    const renderLiveSlider = (key, label, min, max, step, isPercentage = false) => (
        <div key={key} className="slider-group live-slider">
            <label>{label}</label>
            <div className="slider-container">
                <input
                    type="range"
                    min={min}
                    max={max}
                    step={step}
                    value={optimizationProgress?.best_config?.[key] || 0}
                    disabled={true}
                />
                <span className="slider-value">
                    {isPercentage
                        ? `${((optimizationProgress?.best_config?.[key] || 0) * 100).toFixed(0)}%`
                        : (optimizationProgress?.best_config?.[key] || 0).toFixed(2)}
                </span>
            </div>
        </div>
    );

    return (
        <div className="algorithm-tuning">
            <button className="back-button" onClick={() => navigate('/')}>
                ← Back to Stock List
            </button>
            <div className="tuning-grid">
                {/* Manual Tuning Section */}
                <div className="tuning-card manual-tuning">
                    <h2>⚙️ Manual Tuning</h2>

                    <div className="timeframe-selector">
                        <label>Backtest Timeframe:</label>
                        <select value={yearsBack} onChange={(e) => setYearsBack(parseInt(e.target.value))}>
                            <option value={5}>5 Years (Recommended)</option>
                            <option value={10}>10 Years (Long-term)</option>
                        </select>
                    </div>

                    <div className="weight-sliders">
                        <CollapsibleSection title="Algorithm Weights" defaultOpen={true}>
                            {renderSlider('weight_peg', 'PEG Score Weight', 0, 1, 0.01, true)}
                            {renderSlider('weight_consistency', 'Consistency Weight', 0, 1, 0.01, true)}
                            {renderSlider('weight_debt', 'Debt Score Weight', 0, 1, 0.01, true)}
                            {renderSlider('weight_ownership', 'Ownership Weight', 0, 1, 0.01, true)}
                        </CollapsibleSection>

                        <CollapsibleSection title="PEG Thresholds">
                            {renderSlider('peg_excellent', 'Excellent PEG (Upper Limit)', 0.5, 1.5, 0.05)}
                            {renderSlider('peg_good', 'Good PEG (Upper Limit)', 1.0, 2.5, 0.05)}
                            {renderSlider('peg_fair', 'Fair PEG (Upper Limit)', 1.5, 3.0, 0.05)}
                        </CollapsibleSection>

                        <CollapsibleSection title="Growth Thresholds">
                            <h4>Revenue Growth (CAGR %)</h4>
                            {renderSlider('revenue_growth_excellent', 'Excellent Revenue Growth', 10, 25, 0.5)}
                            {renderSlider('revenue_growth_good', 'Good Revenue Growth', 5, 20, 0.5)}
                            {renderSlider('revenue_growth_fair', 'Fair Revenue Growth', 0, 15, 0.5)}

                            <h4 className="mt-4">Income Growth (CAGR %)</h4>
                            {renderSlider('income_growth_excellent', 'Excellent Income Growth', 10, 25, 0.5)}
                            {renderSlider('income_growth_good', 'Good Income Growth', 5, 20, 0.5)}
                            {renderSlider('income_growth_fair', 'Fair Income Growth', 0, 15, 0.5)}
                        </CollapsibleSection>

                        <CollapsibleSection title="Debt Thresholds">
                            {renderSlider('debt_excellent', 'Excellent Debt/Equity', 0.2, 1.0, 0.05)}
                            {renderSlider('debt_good', 'Good Debt/Equity', 0.5, 1.5, 0.05)}
                            {renderSlider('debt_moderate', 'Moderate Debt/Equity', 1.0, 3.0, 0.05)}
                        </CollapsibleSection>

                        <CollapsibleSection title="Institutional Ownership">
                            {renderSlider('inst_own_min', 'Minimum Ideal Ownership', 0, 0.6, 0.01, true)}
                            {renderSlider('inst_own_max', 'Maximum Ideal Ownership', 0.5, 1.1, 0.01, true)}
                        </CollapsibleSection>
                    </div>

                    <div className="action-buttons">
                        <button
                            onClick={runValidation}
                            disabled={validationRunning}
                            className="btn-primary"
                        >
                            {validationRunning ? '🔄 Running...' : '▶️ Run Validation'}
                        </button>

                        <button
                            onClick={saveConfiguration}
                            className="btn-secondary"
                            disabled={rescoringRunning}
                        >
                            {rescoringRunning
                                ? `🔄 Re-scoring... ${rescoringProgress?.progress || 0}/${rescoringProgress?.total || 0}`
                                : '💾 Save Config'}
                        </button>
                    </div>
                </div>

                {/* Auto-Optimization Section */}
                <div className="tuning-card auto-optimization">
                    <h2>🤖 Auto-Optimization</h2>
                    <p>Let the algorithm find the best weights and thresholds automatically using Bayesian optimization</p>

                    <button
                        onClick={runOptimization}
                        disabled={optimizationRunning}
                        className="btn-optimize"
                    >
                        {optimizationRunning
                            ? (optimizationProgress?.stage === 'optimizing' ? `🔄 Optimizing... Iteration ${optimizationProgress.progress}`
                                : optimizationProgress?.stage === 'clearing_cache' ? '🔄 Clearing cache...'
                                    : optimizationProgress?.stage === 'revalidating' ? '🔄 Running validation...'
                                        : '🔄 Starting...')
                            : <><Sparkles className="mr-2 h-4 w-4" /> Auto-Optimize</>}
                    </button>

                    {/* Live Optimization Progress */}
                    {optimizationRunning && optimizationProgress && (
                        <div className="live-optimization">
                            <h3>🚀 Optimization in Progress</h3>

                            <div className="progress-bar-container">
                                <div
                                    className="progress-bar-fill"
                                    style={{ width: `${(optimizationProgress.progress / 100) * 100}%` }}
                                ></div>
                            </div>
                            <div className="progress-text">
                                Iteration {optimizationProgress.progress} / 100
                            </div>

                            <div className="current-best">
                                <div className="stat">
                                    <span className="label">Current Best Correlation:</span>
                                    <span className="value highlight">{optimizationProgress.best_score?.toFixed(4) || '...'}</span>
                                </div>
                            </div>

                            {optimizationProgress.best_config && (
                                <div className="live-sliders">
                                    <h4>Current Best Configuration</h4>
                                    <div className="sliders-grid">
                                        <div className="slider-column">
                                            <h5>Weights</h5>
                                            {renderLiveSlider('weight_peg', 'PEG Weight', 0, 1, 0.01, true)}
                                            {renderLiveSlider('weight_consistency', 'Consistency', 0, 1, 0.01, true)}
                                            {renderLiveSlider('weight_debt', 'Debt Weight', 0, 1, 0.01, true)}
                                            {renderLiveSlider('weight_ownership', 'Ownership', 0, 1, 0.01, true)}

                                            <h5 className="mt-6">PEG Thresholds</h5>
                                            {renderLiveSlider('peg_excellent', 'PEG Excellent', 0.5, 1.5, 0.05)}
                                            {renderLiveSlider('peg_good', 'PEG Good', 1.0, 2.5, 0.05)}
                                            {renderLiveSlider('peg_fair', 'PEG Fair', 1.5, 3.0, 0.05)}

                                            <h5 className="mt-6">Debt Thresholds</h5>
                                            {renderLiveSlider('debt_excellent', 'Debt Excellent', 0.2, 1.0, 0.05)}
                                            {renderLiveSlider('debt_good', 'Debt Good', 0.5, 1.5, 0.05)}
                                            {renderLiveSlider('debt_moderate', 'Debt Moderate', 1.0, 3.0, 0.05)}
                                        </div>
                                        <div className="slider-column">
                                            <h5>Growth Thresholds</h5>
                                            {renderLiveSlider('revenue_growth_excellent', 'Rev Excellent', 10, 25, 0.5)}
                                            {renderLiveSlider('revenue_growth_good', 'Rev Good', 5, 20, 0.5)}
                                            {renderLiveSlider('revenue_growth_fair', 'Rev Fair', 0, 15, 0.5)}

                                            <div className="h-2"></div>
                                            {renderLiveSlider('income_growth_excellent', 'Inc Excellent', 10, 25, 0.5)}
                                            {renderLiveSlider('income_growth_good', 'Inc Good', 5, 20, 0.5)}
                                            {renderLiveSlider('income_growth_fair', 'Inc Fair', 0, 15, 0.5)}

                                            <h5 className="mt-6">Ownership</h5>
                                            {renderLiveSlider('inst_own_min', 'Min Ownership', 0, 0.6, 0.01, true)}
                                            {renderLiveSlider('inst_own_max', 'Max Ownership', 0.5, 1.1, 0.01, true)}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {optimizationResult && !optimizationResult.error && (
                        <div className="optimization-results">
                            <h3>🎯 Optimization Results</h3>

                            {/* Before/After Comparison */}
                            {optimizationResult.baseline_analysis && optimizationResult.optimized_analysis ? (
                                <div className="before-after-comparison">
                                    <div className="comparison-row">
                                        <div className="comparison-col">
                                            <h4>Before (Current Config)</h4>
                                            <div className="stat">
                                                <span className="label">Correlation:</span>
                                                <span className="value">{optimizationResult.baseline_analysis.overall_correlation?.coefficient?.toFixed(4)}</span>
                                            </div>
                                            <div className="stat">
                                                <span className="label">Stocks:</span>
                                                <span className="value">{optimizationResult.baseline_analysis.total_stocks}</span>
                                            </div>
                                            <div className="stat">
                                                <span className="label">Significant:</span>
                                                <span className="value">{optimizationResult.baseline_analysis.overall_correlation?.significant ? 'Yes' : 'No'}</span>
                                            </div>
                                        </div>

                                        <div className="comparison-arrow">→</div>

                                        <div className="comparison-col success">
                                            <h4>After (Optimized Config)</h4>
                                            <div className="stat">
                                                <span className="label">Correlation:</span>
                                                <span className="value">{optimizationResult.optimized_analysis.overall_correlation?.coefficient?.toFixed(4)}</span>
                                            </div>
                                            <div className="stat">
                                                <span className="label">Stocks:</span>
                                                <span className="value">{optimizationResult.optimized_analysis.total_stocks}</span>
                                            </div>
                                            <div className="stat">
                                                <span className="label">Significant:</span>
                                                <span className="value">{optimizationResult.optimized_analysis.overall_correlation?.significant ? 'Yes' : 'No'}</span>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="improvement-highlight">
                                        <span className="label">Correlation Improvement:</span>
                                        <span className="value">
                                            {optimizationResult.optimized_analysis?.overall_correlation?.coefficient && optimizationResult.baseline_analysis?.overall_correlation?.coefficient
                                                ? ((optimizationResult.optimized_analysis.overall_correlation.coefficient - optimizationResult.baseline_analysis.overall_correlation.coefficient) / Math.abs(optimizationResult.baseline_analysis.overall_correlation.coefficient) * 100).toFixed(1) + '%'
                                                : 'N/A'}
                                        </span>
                                    </div>
                                </div>
                            ) : (
                                /* Fallback to old display if analyses not available */
                                <div className="improvement-stats">
                                    <div className="stat">
                                        <span className="label">Initial Correlation:</span>
                                        <span className="value">{optimizationResult.result?.initial_correlation?.toFixed(4)}</span>
                                    </div>
                                    <div className="stat">
                                        <span className="label">Optimized Correlation:</span>
                                        <span className="value success">{optimizationResult.result?.final_correlation?.toFixed(4)}</span>
                                    </div>
                                    <div className="stat highlight">
                                        <span className="label">Improvement:</span>
                                        <span className="value">
                                            {optimizationResult.result?.final_correlation && optimizationResult.result?.initial_correlation
                                                ? ((optimizationResult.result.final_correlation - optimizationResult.result.initial_correlation) / Math.abs(optimizationResult.result.initial_correlation) * 100).toFixed(1) + '%'
                                                : 'N/A'}
                                        </span>
                                    </div>
                                </div>
                            )}

                            <div className="optimized-config">
                                <h4>Best Configuration:</h4>
                                {['weight_peg', 'weight_consistency', 'weight_debt', 'weight_ownership',
                                    'peg_excellent', 'peg_good', 'peg_fair',
                                    'revenue_growth_excellent', 'revenue_growth_good', 'revenue_growth_fair',
                                    'income_growth_excellent', 'income_growth_good', 'income_growth_fair',
                                    'debt_excellent', 'debt_good', 'debt_moderate',
                                    'inst_own_min', 'inst_own_max'].map(key => {
                                        const value = optimizationResult.result?.best_config?.[key];
                                        if (value === undefined) return null;
                                        return (
                                            <div key={key} className="config-item">
                                                <span>{key.replace(/_/g, ' ').toUpperCase()}:</span>
                                                <span>
                                                    {key.startsWith('weight_') || key.startsWith('inst_own')
                                                        ? (value * 100).toFixed(1) + '%'
                                                        : value.toFixed(2)}
                                                </span>
                                            </div>
                                        );
                                    })}
                            </div>

                            <button onClick={applyOptimizedConfig} className="btn-apply">
                                ✅ Apply Optimized Config
                            </button>
                        </div>
                    )}
                </div>

                {/* Results Display */}
                {analysis && (
                    <div className="tuning-card results-display">
                        <h2>📊 Analysis Results</h2>

                        <div className="overall-stats">
                            <div className="stat-card">
                                <div className="stat-label">Overall Correlation</div>
                                <div className="stat-value">{analysis.overall_correlation?.coefficient?.toFixed(4)}</div>
                                <div className="stat-subtext">{analysis.overall_correlation?.interpretation}</div>
                            </div>

                            <div className="stat-card">
                                <div className="stat-label">Stocks Analyzed</div>
                                <div className="stat-value">{analysis.total_stocks}</div>
                            </div>

                            <div className="stat-card">
                                <div className="stat-label">Significance</div>
                                <div className="stat-value">
                                    {analysis.overall_correlation?.significant ? '✅ Yes' : '❌ No'}
                                </div>
                                <div className="stat-subtext">p = {analysis.overall_correlation?.p_value?.toFixed(4)}</div>
                            </div>
                        </div>

                        <div className="component-correlations">
                            <h3>Component Correlations</h3>
                            {Object.entries(analysis.component_correlations || {}).map(([component, corr]) => (
                                <div key={component} className="correlation-bar">
                                    <span className="component-name">{component.replace('_score', '').toUpperCase()}</span>
                                    <div className="bar-container">
                                        <div
                                            className={`bar-fill ${corr.coefficient > 0 ? 'bg-green-400' : 'bg-red-400'}`}
                                            style={{
                                                width: `${Math.abs(corr.coefficient || 0) * 100}%`
                                            }}
                                        />
                                    </div>
                                    <span className="correlation-value">{(corr.coefficient || 0).toFixed(3)}</span>
                                </div>
                            ))}
                        </div>

                        <div className="insights-section">
                            <h3>💡 Key Insights</h3>
                            {analysis.insights?.map((insight, idx) => (
                                <div key={idx} className="insight">{insight}</div>
                            ))}
                        </div>
                    </div>
                )}
                {/* Correlation Guide */}
                <div className="tuning-card guide-card">
                    <h2>ℹ️ Understanding Correlation</h2>

                    <div className="correlation-scale">
                        <div className="scale-item">
                            <div className="scale-range">0.00 - 0.05</div>
                            <div className="scale-desc">
                                <strong>Noise (Random)</strong>
                                <p>No predictive power. The score has no relationship to stock performance.</p>
                            </div>
                        </div>

                        <div className="scale-item">
                            <div className="scale-range">0.05 - 0.10</div>
                            <div className="scale-desc">
                                <strong>Weak Signal</strong>
                                <p>Better than a coin flip, but many exceptions. Typical starting point for basic models.</p>
                            </div>
                        </div>

                        <div className="scale-item">
                            <div className="scale-range">0.10 - 0.15</div>
                            <div className="scale-desc">
                                <strong>Good (Respectable)</strong>
                                <p>A genuine "edge". If you consistently hit this, the algorithm is adding real value.</p>
                            </div>
                        </div>

                        <div className="scale-item">
                            <div className="scale-range">0.15 - 0.25</div>
                            <div className="scale-desc">
                                <strong>Excellent</strong>
                                <p>Very strong signal. Clearly separates winners from losers over time.</p>
                            </div>
                        </div>

                        <div className="scale-item">
                            <div className="scale-range">&gt; 0.30</div>
                            <div className="scale-desc">
                                <strong>Suspicious</strong>
                                <p>Likely "overfitting" or a bug. Be skeptical of numbers this high.</p>
                            </div>
                        </div>
                    </div>

                    <div className="guide-footer">
                        <strong>💡 Timeframe Selection:</strong> We recommend <strong>5 years</strong> for most analysis. For an even longer-term view that smooths out market cycles, try <strong>10 years</strong> - though be aware of survivorship bias (only companies that "survived" are in today's S&P 500).
                    </div>
                </div>
            </div>
        </div >
    );
}
