import { useState, useEffect } from 'react';
import './AlgorithmTuning.css';

export default function AlgorithmTuning() {
    const [config, setConfig] = useState({
        weight_peg: 0.50,
        weight_consistency: 0.25,
        weight_debt: 0.15,
        weight_ownership: 0.10
    });

    const [validationRunning, setValidationRunning] = useState(false);
    const [optimizationRunning, setOptimizationRunning] = useState(false);
    const [validationJobId, setValidationJobId] = useState(null);
    const [optimizationJobId, setOptimizationJobId] = useState(null);

    const [analysis, setAnalysis] = useState(null);
    const [optimizationResult, setOptimizationResult] = useState(null);
    const [savedConfigs, setSavedConfigs] = useState([]);
    const [yearsBack, setYearsBack] = useState(1);

    // Load current configuration on mount
    useEffect(() => {
        loadCurrentConfig();
    }, []);

    const loadCurrentConfig = async () => {
        try {
            const response = await fetch('http://localhost:8080/api/algorithm/config');
            const data = await response.json();
            if (data.current) {
                setConfig(data.current);
            }
            if (data.saved_configs) {
                setSavedConfigs(data.saved_configs);
            }
        } catch (error) {
            console.error('Error loading config:', error);
        }
    };

    const handleSliderChange = (key, value) => {
        const newConfig = { ...config, [key]: parseFloat(value) };

        // Auto-normalize to ensure sum = 1
        const total = Object.values(newConfig).reduce((a, b) => a + b, 0);
        const normalized = {};
        Object.keys(newConfig).forEach(k => {
            normalized[k] = newConfig[k] / total;
        });

        setConfig(normalized);
    };

    const runValidation = async () => {
        setValidationRunning(true);
        setAnalysis(null);

        try {
            const response = await fetch('http://localhost:8080/api/validate/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ years_back: yearsBack, limit: 50 })  // Limit for faster testing
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
                const response = await fetch(`http://localhost:8080/api/validate/progress/${jobId}`);
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

        try {
            const response = await fetch('http://localhost:8080/api/optimize/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    years_back: yearsBack,
                    method: 'gradient_descent',
                    max_iterations: 50
                })
            });

            const data = await response.json();
            setOptimizationJobId(data.job_id);

            // Poll for results
            pollOptimizationProgress(data.job_id);
        } catch (error) {
            console.error('Error starting optimization:', error);
            setOptimizationRunning(false);
        }
    };

    const pollOptimizationProgress = async (jobId) => {
        const interval = setInterval(async () => {
            try {
                const response = await fetch(`http://localhost:8080/api/optimize/progress/${jobId}`);
                const data = await response.json();

                if (data.status === 'complete') {
                    clearInterval(interval);
                    setOptimizationRunning(false);
                    setOptimizationResult(data.result);
                } else if (data.status === 'error') {
                    clearInterval(interval);
                    setOptimizationRunning(false);
                    console.error('Optimization error:', data.error);
                }
            } catch (error) {
                console.error('Error polling optimization:', error);
            }
        }, 2000);
    };

    const applyOptimizedConfig = () => {
        if (optimizationResult && optimizationResult.best_config) {
            setConfig(optimizationResult.best_config);
        }
    };

    const saveConfiguration = async () => {
        try {
            await fetch('http://localhost:8080/api/algorithm/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config })
            });
            alert('Configuration saved!');
            loadCurrentConfig();
        } catch (error) {
            console.error('Error saving configuration:', error);
        }
    };

    return (
        <div className="algorithm-tuning">
            <div className="tuning-header">
                <h1>🎛️ Algorithm Tuning Lab</h1>
                <p>Optimize your Lynch scoring algorithm to predict stock returns</p>
            </div>

            <div className="tuning-grid">
                {/* Manual Tuning Section */}
                <div className="tuning-card manual-tuning">
                    <h2>⚙️ Manual Tuning</h2>

                    <div className="timeframe-selector">
                        <label>Backtest Timeframe:</label>
                        <select value={yearsBack} onChange={(e) => setYearsBack(parseInt(e.target.value))}>
                            <option value={1}>1 Year</option>
                            <option value={3}>3 Years</option>
                            <option value={5}>5 Years</option>
                        </select>
                    </div>

                    <div className="weight-sliders">
                        {Object.keys(config).map(key => (
                            <div key={key} className="slider-group">
                                <label>{key.replace('weight_', '').replace('_', ' ').toUpperCase()}</label>
                                <div className="slider-container">
                                    <input
                                        type="range"
                                        min="0"
                                        max="1"
                                        step="0.01"
                                        value={config[key]}
                                        onChange={(e) => handleSliderChange(key, e.target.value)}
                                    />
                                    <span className="slider-value">{(config[key] * 100).toFixed(1)}%</span>
                                </div>
                            </div>
                        ))}
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
                        >
                            💾 Save Config
                        </button>
                    </div>
                </div>

                {/* Auto-Optimization Section */}
                <div className="tuning-card auto-optimization">
                    <h2>🤖 Auto-Optimization</h2>
                    <p>Let the algorithm find the best weights automatically</p>

                    <button
                        onClick={runOptimization}
                        disabled={optimizationRunning}
                        className="btn-optimize"
                    >
                        {optimizationRunning ? '🔄 Optimizing...' : '✨ Auto-Optimize'}
                    </button>

                    {optimizationResult && (
                        <div className="optimization-results">
                            <h3>🎯 Optimization Results</h3>
                            <div className="improvement-stats">
                                <div className="stat">
                                    <span className="label">Initial Correlation:</span>
                                    <span className="value">{optimizationResult.initial_correlation?.toFixed(4)}</span>
                                </div>
                                <div className="stat">
                                    <span className="label">Optimized Correlation:</span>
                                    <span className="value success">{optimizationResult.final_correlation?.toFixed(4)}</span>
                                </div>
                                <div className="stat highlight">
                                    <span className="label">Improvement:</span>
                                    <span className="value">{((optimizationResult.improvement / Math.abs(optimizationResult.initial_correlation)) * 100).toFixed(1)}%</span>
                                </div>
                            </div>

                            <div className="optimized-config">
                                <h4>Best Configuration:</h4>
                                {Object.entries(optimizationResult.best_config || {}).map(([key, value]) => (
                                    <div key={key} className="config-item">
                                        <span>{key.replace('weight_', '').toUpperCase()}:</span>
                                        <span>{(value * 100).toFixed(1)}%</span>
                                    </div>
                                ))}
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
                                            className="bar-fill"
                                            style={{
                                                width: `${Math.abs(corr.coefficient || 0) * 100}%`,
                                                backgroundColor: (corr.coefficient || 0) > 0 ? '#4ade80' : '#ef4444'
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
            </div>
        </div>
    );
}
