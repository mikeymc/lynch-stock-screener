import { useState, useEffect } from 'react'
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Label } from "@/components/ui/label"
import { Sparkles, ChevronDown, Play, Save, Loader2 } from 'lucide-react'
import { cn } from "@/lib/utils"

export default function OptimizationTab() {
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
    })

    const [validationRunning, setValidationRunning] = useState(false)
    const [optimizationRunning, setOptimizationRunning] = useState(false)
    const [rescoringRunning, setRescoringRunning] = useState(false)

    const [analysis, setAnalysis] = useState(null)
    const [optimizationResult, setOptimizationResult] = useState(null)
    const [optimizationProgress, setOptimizationProgress] = useState(null)
    const [rescoringProgress, setRescoringProgress] = useState(null)
    const [yearsBack, setYearsBack] = useState("5")

    const [openSections, setOpenSections] = useState({
        weights: true,
        peg: false,
        growth: false,
        debt: false,
        ownership: false
    })

    // Load current configuration on mount
    useEffect(() => {
        const controller = new AbortController()
        loadCurrentConfig(controller.signal)
        return () => controller.abort()
    }, [])

    const loadCurrentConfig = async (signal) => {
        try {
            const response = await fetch('/api/algorithm/config', { signal })
            const data = await response.json()
            if (data.current) {
                setConfig(data.current)
            }
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('Error loading config:', error)
            }
        }
    }

    const handleSliderChange = (key, value) => {
        const numValue = parseFloat(value)

        if (key.startsWith('weight_')) {
            const newConfig = { ...config, [key]: numValue }
            const weightKeys = Object.keys(config).filter(k => k.startsWith('weight_'))
            const total = weightKeys.reduce((sum, k) => sum + newConfig[k], 0)
            const normalized = { ...newConfig }
            weightKeys.forEach(k => {
                normalized[k] = newConfig[k] / total
            })
            setConfig(normalized)
        } else {
            setConfig({ ...config, [key]: numValue })
        }
    }

    const runValidation = async () => {
        setValidationRunning(true)
        setAnalysis(null)

        try {
            const response = await fetch('/api/validate/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    years_back: parseInt(yearsBack),
                    limit: null,
                    config: config
                })
            })

            const data = await response.json()
            pollValidationProgress(data.job_id)
        } catch (error) {
            console.error('Error starting validation:', error)
            setValidationRunning(false)
        }
    }

    const pollValidationProgress = async (jobId) => {
        const interval = setInterval(async () => {
            try {
                const response = await fetch(`/api/validate/progress/${jobId}`)
                const data = await response.json()

                if (data.status === 'complete') {
                    clearInterval(interval)
                    setValidationRunning(false)
                    setAnalysis(data.analysis)
                } else if (data.status === 'error') {
                    clearInterval(interval)
                    setValidationRunning(false)
                    console.error('Validation error:', data.error)
                }
            } catch (error) {
                console.error('Error polling validation:', error)
            }
        }, 2000)
    }

    const runOptimization = async () => {
        setOptimizationRunning(true)
        setOptimizationResult(null)
        setOptimizationProgress(null)

        try {
            const response = await fetch('/api/optimize/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    years_back: parseInt(yearsBack),
                    method: 'bayesian',
                    max_iterations: 100,
                    limit: null
                })
            })
            const data = await response.json()

            if (data.error) {
                alert('Error starting optimization: ' + data.error)
                setOptimizationRunning(false)
                return
            }

            const pollInterval = setInterval(async () => {
                try {
                    const statusRes = await fetch(`/api/optimize/progress/${data.job_id}`)
                    const statusData = await statusRes.json()

                    if (statusData.error) {
                        clearInterval(pollInterval)
                        setOptimizationRunning(false)
                        alert('Error checking progress: ' + statusData.error)
                        return
                    }

                    setOptimizationProgress(statusData)

                    if (statusData.status === 'complete') {
                        clearInterval(pollInterval)
                        setOptimizationResult(statusData)
                        setOptimizationRunning(false)
                        setOptimizationProgress(null)
                    } else if (statusData.status === 'error') {
                        clearInterval(pollInterval)
                        setOptimizationRunning(false)
                        alert('Optimization failed: ' + statusData.error)
                    }
                } catch (e) {
                    console.error("Polling error", e)
                }
            }, 1000)

        } catch (error) {
            console.error('Error running optimization:', error)
            setOptimizationRunning(false)
        }
    }

    const applyOptimizedConfig = () => {
        if (optimizationResult?.result?.best_config) {
            setConfig(optimizationResult.result.best_config)
        }
    }

    const saveConfiguration = async () => {
        try {
            setRescoringRunning(true)
            setRescoringProgress(null)

            const response = await fetch('/api/algorithm/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config })
            })

            const data = await response.json()

            if (data.rescore_job_id) {
                pollRescoringProgress(data.rescore_job_id)
            } else {
                alert('Configuration saved!')
                setRescoringRunning(false)
            }

            loadCurrentConfig()
        } catch (error) {
            console.error('Error saving configuration:', error)
            setRescoringRunning(false)
        }
    }

    const pollRescoringProgress = async (jobId) => {
        const interval = setInterval(async () => {
            try {
                const response = await fetch(`/api/rescore/progress/${jobId}`)
                const data = await response.json()

                setRescoringProgress(data)

                if (data.status === 'complete') {
                    clearInterval(interval)
                    setRescoringRunning(false)
                    setRescoringProgress(null)
                    alert(`Configuration saved and re-scored ${data.summary?.success || 0} stocks!`)
                } else if (data.status === 'error') {
                    clearInterval(interval)
                    setRescoringRunning(false)
                    setRescoringProgress(null)
                    alert('Rescoring error: ' + data.error)
                }
            } catch (error) {
                console.error('Error polling rescoring:', error)
            }
        }, 1000)
    }

    const toggleSection = (section) => {
        setOpenSections(prev => ({ ...prev, [section]: !prev[section] }))
    }

    const renderSlider = (key, label, min, max, step, isPercentage = false) => (
        <div key={key} className="space-y-2">
            <div className="flex justify-between">
                <Label className="text-sm">{label}</Label>
                <span className="text-sm font-medium text-primary">
                    {isPercentage ? (config[key] * 100).toFixed(1) + '%' : config[key]?.toFixed(2)}
                </span>
            </div>
            <input
                type="range"
                min={min}
                max={max}
                step={step}
                value={config[key] || 0}
                onChange={(e) => handleSliderChange(key, e.target.value)}
                className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
            />
        </div>
    )

    const renderLiveSlider = (key, label, min, max, step, isPercentage = false) => (
        <div key={key} className="space-y-1">
            <div className="flex justify-between text-xs">
                <span className="text-green-600">{label}</span>
                <span className="font-medium text-green-600">
                    {isPercentage
                        ? `${((optimizationProgress?.best_config?.[key] || 0) * 100).toFixed(0)}%`
                        : (optimizationProgress?.best_config?.[key] || 0).toFixed(2)}
                </span>
            </div>
            <input
                type="range"
                min={min}
                max={max}
                step={step}
                value={optimizationProgress?.best_config?.[key] || 0}
                disabled
                className="w-full h-1.5 bg-green-100 rounded-lg appearance-none cursor-not-allowed accent-green-600"
            />
        </div>
    )

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-lg font-medium">Algorithm Tuning</h3>
                <p className="text-sm text-muted-foreground">
                    Configure scoring weights and thresholds to optimize stock screening accuracy.
                </p>
            </div>
            <div className="border-t" />

            <div className="grid gap-6 lg:grid-cols-2">
                {/* Manual Tuning Card */}
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            ⚙️ Manual Tuning
                        </CardTitle>
                        <CardDescription>
                            Adjust algorithm parameters manually
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {/* Timeframe Selector */}
                        <div className="space-y-2">
                            <Label>Backtest Timeframe</Label>
                            <Select value={yearsBack} onValueChange={setYearsBack}>
                                <SelectTrigger>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="5">5 Years (Recommended)</SelectItem>
                                    <SelectItem value="10">10 Years (Long-term)</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        {/* Collapsible Sections */}
                        <div className="space-y-2">
                            {/* Algorithm Weights */}
                            <Collapsible open={openSections.weights} onOpenChange={() => toggleSection('weights')}>
                                <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg border bg-muted/50 px-4 py-3 font-medium hover:bg-muted">
                                    <span>Algorithm Weights</span>
                                    <ChevronDown className={cn("h-4 w-4 transition-transform", openSections.weights && "rotate-180")} />
                                </CollapsibleTrigger>
                                <CollapsibleContent className="px-4 pt-4 space-y-4">
                                    {renderSlider('weight_peg', 'PEG Score Weight', 0, 1, 0.01, true)}
                                    {renderSlider('weight_consistency', 'Consistency Weight', 0, 1, 0.01, true)}
                                    {renderSlider('weight_debt', 'Debt Score Weight', 0, 1, 0.01, true)}
                                    {renderSlider('weight_ownership', 'Ownership Weight', 0, 1, 0.01, true)}
                                </CollapsibleContent>
                            </Collapsible>

                            {/* PEG Thresholds */}
                            <Collapsible open={openSections.peg} onOpenChange={() => toggleSection('peg')}>
                                <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg border bg-muted/50 px-4 py-3 font-medium hover:bg-muted">
                                    <span>PEG Thresholds</span>
                                    <ChevronDown className={cn("h-4 w-4 transition-transform", openSections.peg && "rotate-180")} />
                                </CollapsibleTrigger>
                                <CollapsibleContent className="px-4 pt-4 space-y-4">
                                    {renderSlider('peg_excellent', 'Excellent PEG (Upper Limit)', 0.5, 1.5, 0.05)}
                                    {renderSlider('peg_good', 'Good PEG (Upper Limit)', 1.0, 2.5, 0.05)}
                                    {renderSlider('peg_fair', 'Fair PEG (Upper Limit)', 1.5, 3.0, 0.05)}
                                </CollapsibleContent>
                            </Collapsible>

                            {/* Growth Thresholds */}
                            <Collapsible open={openSections.growth} onOpenChange={() => toggleSection('growth')}>
                                <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg border bg-muted/50 px-4 py-3 font-medium hover:bg-muted">
                                    <span>Growth Thresholds</span>
                                    <ChevronDown className={cn("h-4 w-4 transition-transform", openSections.growth && "rotate-180")} />
                                </CollapsibleTrigger>
                                <CollapsibleContent className="px-4 pt-4 space-y-4">
                                    <div className="text-sm font-medium text-muted-foreground">Revenue Growth (CAGR %)</div>
                                    {renderSlider('revenue_growth_excellent', 'Excellent Revenue Growth', 10, 25, 0.5)}
                                    {renderSlider('revenue_growth_good', 'Good Revenue Growth', 5, 20, 0.5)}
                                    {renderSlider('revenue_growth_fair', 'Fair Revenue Growth', 0, 15, 0.5)}
                                    <div className="text-sm font-medium text-muted-foreground pt-2">Income Growth (CAGR %)</div>
                                    {renderSlider('income_growth_excellent', 'Excellent Income Growth', 10, 25, 0.5)}
                                    {renderSlider('income_growth_good', 'Good Income Growth', 5, 20, 0.5)}
                                    {renderSlider('income_growth_fair', 'Fair Income Growth', 0, 15, 0.5)}
                                </CollapsibleContent>
                            </Collapsible>

                            {/* Debt Thresholds */}
                            <Collapsible open={openSections.debt} onOpenChange={() => toggleSection('debt')}>
                                <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg border bg-muted/50 px-4 py-3 font-medium hover:bg-muted">
                                    <span>Debt Thresholds</span>
                                    <ChevronDown className={cn("h-4 w-4 transition-transform", openSections.debt && "rotate-180")} />
                                </CollapsibleTrigger>
                                <CollapsibleContent className="px-4 pt-4 space-y-4">
                                    {renderSlider('debt_excellent', 'Excellent Debt/Equity', 0.2, 1.0, 0.05)}
                                    {renderSlider('debt_good', 'Good Debt/Equity', 0.5, 1.5, 0.05)}
                                    {renderSlider('debt_moderate', 'Moderate Debt/Equity', 1.0, 3.0, 0.05)}
                                </CollapsibleContent>
                            </Collapsible>

                            {/* Institutional Ownership */}
                            <Collapsible open={openSections.ownership} onOpenChange={() => toggleSection('ownership')}>
                                <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg border bg-muted/50 px-4 py-3 font-medium hover:bg-muted">
                                    <span>Institutional Ownership</span>
                                    <ChevronDown className={cn("h-4 w-4 transition-transform", openSections.ownership && "rotate-180")} />
                                </CollapsibleTrigger>
                                <CollapsibleContent className="px-4 pt-4 space-y-4">
                                    {renderSlider('inst_own_min', 'Minimum Ideal Ownership', 0, 0.6, 0.01, true)}
                                    {renderSlider('inst_own_max', 'Maximum Ideal Ownership', 0.5, 1.1, 0.01, true)}
                                </CollapsibleContent>
                            </Collapsible>
                        </div>

                        {/* Action Buttons */}
                        <div className="flex gap-2 pt-4">
                            <Button onClick={runValidation} disabled={validationRunning} className="flex-1">
                                {validationRunning ? (
                                    <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Running...</>
                                ) : (
                                    <><Play className="mr-2 h-4 w-4" /> Run Validation</>
                                )}
                            </Button>
                            <Button onClick={saveConfiguration} variant="secondary" disabled={rescoringRunning}>
                                {rescoringRunning ? (
                                    <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> {rescoringProgress?.progress || 0}/{rescoringProgress?.total || 0}</>
                                ) : (
                                    <><Save className="mr-2 h-4 w-4" /> Save</>
                                )}
                            </Button>
                        </div>
                    </CardContent>
                </Card>

                {/* Auto-Optimization Card */}
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            🤖 Auto-Optimization
                        </CardTitle>
                        <CardDescription>
                            Let the algorithm find optimal weights using Bayesian optimization
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <Button
                            onClick={runOptimization}
                            disabled={optimizationRunning}
                            className="w-full bg-amber-500 hover:bg-amber-600 text-white"
                        >
                            {optimizationRunning ? (
                                optimizationProgress?.stage === 'optimizing' ? `Optimizing... Iteration ${optimizationProgress.progress}`
                                    : optimizationProgress?.stage === 'clearing_cache' ? 'Clearing cache...'
                                        : optimizationProgress?.stage === 'revalidating' ? 'Running validation...'
                                            : 'Starting...'
                            ) : (
                                <><Sparkles className="mr-2 h-4 w-4" /> Auto-Optimize</>
                            )}
                        </Button>

                        {/* Live Optimization Progress */}
                        {optimizationRunning && optimizationProgress && (
                            <div className="space-y-4 pt-4 border-t">
                                <div className="text-sm font-medium text-green-600">🚀 Optimization in Progress</div>

                                <div className="w-full bg-muted rounded-full h-3">
                                    <div
                                        className="bg-green-500 h-3 rounded-full transition-all"
                                        style={{ width: `${(optimizationProgress.progress / 100) * 100}%` }}
                                    />
                                </div>
                                <div className="text-right text-sm text-muted-foreground">
                                    Iteration {optimizationProgress.progress} / 100
                                </div>

                                <div className="bg-green-50 dark:bg-green-950 p-4 rounded-lg text-center">
                                    <div className="text-sm text-muted-foreground">Current Best Correlation</div>
                                    <div className="text-2xl font-bold text-green-600">
                                        {optimizationProgress.best_score?.toFixed(4) || '...'}
                                    </div>
                                </div>

                                {optimizationProgress.best_config && (
                                    <div className="space-y-3 bg-muted/50 p-4 rounded-lg">
                                        <div className="text-sm font-medium">Current Best Configuration</div>
                                        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                                            <div className="space-y-2">
                                                <div className="text-xs font-medium text-muted-foreground">Weights</div>
                                                {renderLiveSlider('weight_peg', 'PEG', 0, 1, 0.01, true)}
                                                {renderLiveSlider('weight_consistency', 'Consistency', 0, 1, 0.01, true)}
                                                {renderLiveSlider('weight_debt', 'Debt', 0, 1, 0.01, true)}
                                                {renderLiveSlider('weight_ownership', 'Ownership', 0, 1, 0.01, true)}
                                            </div>
                                            <div className="space-y-2">
                                                <div className="text-xs font-medium text-muted-foreground">PEG Thresholds</div>
                                                {renderLiveSlider('peg_excellent', 'Excellent', 0.5, 1.5, 0.05)}
                                                {renderLiveSlider('peg_good', 'Good', 1.0, 2.5, 0.05)}
                                                {renderLiveSlider('peg_fair', 'Fair', 1.5, 3.0, 0.05)}
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Optimization Results */}
                        {optimizationResult && !optimizationResult.error && (
                            <div className="space-y-4 pt-4 border-t">
                                <div className="text-sm font-medium">🎯 Optimization Results</div>

                                {optimizationResult.baseline_analysis && optimizationResult.optimized_analysis ? (
                                    <div className="grid grid-cols-3 gap-2 text-center">
                                        <div className="bg-muted p-3 rounded-lg">
                                            <div className="text-xs text-muted-foreground">Before</div>
                                            <div className="font-bold">{optimizationResult.baseline_analysis.overall_correlation?.coefficient?.toFixed(4)}</div>
                                        </div>
                                        <div className="flex items-center justify-center text-green-500">→</div>
                                        <div className="bg-green-100 dark:bg-green-950 p-3 rounded-lg border border-green-500">
                                            <div className="text-xs text-muted-foreground">After</div>
                                            <div className="font-bold text-green-600">{optimizationResult.optimized_analysis.overall_correlation?.coefficient?.toFixed(4)}</div>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="grid grid-cols-2 gap-4 text-center">
                                        <div className="bg-muted p-3 rounded-lg">
                                            <div className="text-xs text-muted-foreground">Initial</div>
                                            <div className="font-bold">{optimizationResult.result?.initial_correlation?.toFixed(4)}</div>
                                        </div>
                                        <div className="bg-green-100 dark:bg-green-950 p-3 rounded-lg">
                                            <div className="text-xs text-muted-foreground">Optimized</div>
                                            <div className="font-bold text-green-600">{optimizationResult.result?.final_correlation?.toFixed(4)}</div>
                                        </div>
                                    </div>
                                )}

                                <Button onClick={applyOptimizedConfig} className="w-full" variant="outline">
                                    ✅ Apply Optimized Config
                                </Button>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>

            {/* Analysis Results */}
            {analysis && (
                <Card>
                    <CardHeader>
                        <CardTitle>📊 Analysis Results</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-3 gap-4 mb-6">
                            <div className="bg-blue-50 dark:bg-blue-950 p-4 rounded-lg text-center">
                                <div className="text-sm text-muted-foreground">Overall Correlation</div>
                                <div className="text-2xl font-bold text-blue-600">{analysis.overall_correlation?.coefficient?.toFixed(4)}</div>
                                <div className="text-xs text-muted-foreground">{analysis.overall_correlation?.interpretation}</div>
                            </div>
                            <div className="bg-blue-50 dark:bg-blue-950 p-4 rounded-lg text-center">
                                <div className="text-sm text-muted-foreground">Stocks Analyzed</div>
                                <div className="text-2xl font-bold text-blue-600">{analysis.total_stocks}</div>
                            </div>
                            <div className="bg-blue-50 dark:bg-blue-950 p-4 rounded-lg text-center">
                                <div className="text-sm text-muted-foreground">Significance</div>
                                <div className="text-2xl font-bold text-blue-600">
                                    {analysis.overall_correlation?.significant ? '✅ Yes' : '❌ No'}
                                </div>
                                <div className="text-xs text-muted-foreground">p = {analysis.overall_correlation?.p_value?.toFixed(4)}</div>
                            </div>
                        </div>

                        {/* Component Correlations */}
                        <div className="space-y-3">
                            <div className="text-sm font-medium">Component Correlations</div>
                            {Object.entries(analysis.component_correlations || {}).map(([component, corr]) => (
                                <div key={component} className="flex items-center gap-4">
                                    <span className="text-sm w-24 text-muted-foreground">
                                        {component.replace('_score', '').toUpperCase()}
                                    </span>
                                    <div className="flex-1 bg-muted h-4 rounded-full overflow-hidden">
                                        <div
                                            className={cn("h-full", corr.coefficient > 0 ? "bg-green-500" : "bg-red-500")}
                                            style={{ width: `${Math.abs(corr.coefficient || 0) * 100}%` }}
                                        />
                                    </div>
                                    <span className="text-sm font-medium w-16 text-right">
                                        {(corr.coefficient || 0).toFixed(3)}
                                    </span>
                                </div>
                            ))}
                        </div>

                        {/* Insights */}
                        {analysis.insights?.length > 0 && (
                            <div className="mt-6 bg-amber-50 dark:bg-amber-950 p-4 rounded-lg">
                                <div className="text-sm font-medium mb-2">💡 Key Insights</div>
                                {analysis.insights.map((insight, idx) => (
                                    <div key={idx} className="text-sm py-1">{insight}</div>
                                ))}
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}

            {/* Correlation Guide Card */}
            <Card className="border-l-4 border-l-primary">
                <CardHeader>
                    <CardTitle>ℹ️ Understanding Correlation</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="space-y-3">
                        {[
                            { range: '0.00 - 0.05', label: 'Noise (Random)', desc: 'No predictive power' },
                            { range: '0.05 - 0.10', label: 'Weak Signal', desc: 'Better than a coin flip' },
                            { range: '0.10 - 0.15', label: 'Good (Respectable)', desc: 'A genuine edge' },
                            { range: '0.15 - 0.25', label: 'Excellent', desc: 'Very strong signal' },
                            { range: '> 0.30', label: 'Suspicious', desc: 'Likely overfitting' },
                        ].map(item => (
                            <div key={item.range} className="flex items-center gap-4 p-2 bg-muted/50 rounded hover:bg-muted transition-colors">
                                <code className="text-primary font-mono text-sm w-24">{item.range}</code>
                                <div>
                                    <div className="font-medium text-sm">{item.label}</div>
                                    <div className="text-xs text-muted-foreground">{item.desc}</div>
                                </div>
                            </div>
                        ))}
                    </div>
                    <div className="mt-4 bg-blue-50 dark:bg-blue-950 p-3 rounded-lg text-sm">
                        <strong>💡 Timeframe Selection:</strong> We recommend <strong>5 years</strong> for most analysis.
                        For a longer-term view, try <strong>10 years</strong> (but beware of survivorship bias).
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}
