// ABOUTME: Algorithm tuning UI for configuring scoring weights and thresholds
// ABOUTME: Supports per-character configurations (Lynch, Buffett have different tunable params)

import { useState, useEffect } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Label } from "@/components/ui/label"
import { Sparkles, Play, Save, Loader2, TrendingUp, CheckCircle2, XCircle, Target, BarChart3, Info, AlertCircle } from 'lucide-react'
import { cn } from "@/lib/utils"

// Character-specific slider configurations
const CHARACTER_SLIDER_CONFIGS = {
    lynch: {
        displayName: 'Peter Lynch',
        weights: [
            { key: 'weight_peg', label: 'PEG Score', default: 0.50 },
            { key: 'weight_consistency', label: 'Consistency', default: 0.25 },
            { key: 'weight_debt', label: 'Debt Score', default: 0.15 },
            { key: 'weight_ownership', label: 'Ownership', default: 0.10 },
        ],
        thresholdGroups: [
            {
                title: 'PEG Thresholds',
                color: 'blue-500',
                sliders: [
                    { key: 'peg_excellent', label: 'Excellent (Upper)', min: 0.5, max: 1.5, step: 0.05, default: 1.0 },
                    { key: 'peg_good', label: 'Good (Upper)', min: 1.0, max: 2.5, step: 0.05, default: 1.5 },
                    { key: 'peg_fair', label: 'Fair (Upper)', min: 1.5, max: 3.0, step: 0.05, default: 2.0 },
                ]
            },
            {
                title: 'D/E Thresholds',
                color: 'red-500',
                sliders: [
                    { key: 'debt_excellent', label: 'Excellent D/E', min: 0.2, max: 1.0, step: 0.05, default: 0.5 },
                    { key: 'debt_good', label: 'Good D/E', min: 0.5, max: 1.5, step: 0.05, default: 1.0 },
                    { key: 'debt_moderate', label: 'Moderate D/E', min: 1.0, max: 3.0, step: 0.05, default: 2.0 },
                ]
            },
            {
                title: 'Institutional Ownership',
                color: 'purple-500',
                sliders: [
                    { key: 'inst_own_min', label: 'Minimum Ideal', min: 0, max: 0.6, step: 0.01, isPercentage: true, default: 0.20 },
                    { key: 'inst_own_max', label: 'Maximum Ideal', min: 0.5, max: 1.1, step: 0.01, isPercentage: true, default: 0.60 },
                ]
            },
            {
                title: 'Revenue Thresholds',
                color: 'green-500',
                sliders: [
                    { key: 'revenue_growth_excellent', label: 'Excellent (CAGR %)', min: 10, max: 25, step: 0.5, default: 15.0 },
                    { key: 'revenue_growth_good', label: 'Good (CAGR %)', min: 5, max: 20, step: 0.5, default: 10.0 },
                    { key: 'revenue_growth_fair', label: 'Fair (CAGR %)', min: 0, max: 15, step: 0.5, default: 5.0 },
                ]
            },
            {
                title: 'Net Income Thresholds',
                color: 'emerald-500',
                sliders: [
                    { key: 'income_growth_excellent', label: 'Excellent (CAGR %)', min: 10, max: 25, step: 0.5, default: 15.0 },
                    { key: 'income_growth_good', label: 'Good (CAGR %)', min: 5, max: 20, step: 0.5, default: 10.0 },
                    { key: 'income_growth_fair', label: 'Fair (CAGR %)', min: 0, max: 15, step: 0.5, default: 5.0 },
                ]
            },
        ]
    },
    buffett: {
        displayName: 'Warren Buffett',
        weights: [
            { key: 'weight_roe', label: 'ROE Score', default: 0.35 },
            { key: 'weight_consistency', label: 'Consistency', default: 0.25 },
            { key: 'weight_debt_to_earnings', label: 'Debt-to-Earnings', default: 0.20 },
            { key: 'weight_gross_margin', label: 'Gross Margin', default: 0.20 },
        ],
        thresholdGroups: [
            {
                title: 'ROE Thresholds',
                color: 'blue-500',
                sliders: [
                    { key: 'roe_excellent', label: 'Excellent (%)', min: 15, max: 30, step: 1, default: 20.0 },
                    { key: 'roe_good', label: 'Good (%)', min: 10, max: 25, step: 1, default: 15.0 },
                    { key: 'roe_fair', label: 'Fair (%)', min: 5, max: 20, step: 1, default: 10.0 },
                ]
            },
            {
                title: 'Debt-to-Earnings (Years)',
                color: 'red-500',
                sliders: [
                    { key: 'debt_to_earnings_excellent', label: 'Excellent (years)', min: 0, max: 3, step: 0.5, default: 2.0 },
                    { key: 'debt_to_earnings_good', label: 'Good (years)', min: 1, max: 5, step: 0.5, default: 4.0 },
                    { key: 'debt_to_earnings_fair', label: 'Fair (years)', min: 3, max: 10, step: 0.5, default: 7.0 },
                ]
            },
            {
                title: 'Gross Margin Thresholds',
                color: 'green-500',
                sliders: [
                    { key: 'gross_margin_excellent', label: 'Excellent (%)', min: 30, max: 60, step: 1, default: 50.0 },
                    { key: 'gross_margin_good', label: 'Good (%)', min: 20, max: 50, step: 1, default: 40.0 },
                    { key: 'gross_margin_fair', label: 'Fair (%)', min: 10, max: 40, step: 1, default: 30.0 },
                ]
            },
            {
                title: 'Revenue Thresholds',
                color: 'emerald-500',
                sliders: [
                    { key: 'revenue_growth_excellent', label: 'Excellent (CAGR %)', min: 10, max: 25, step: 0.5, default: 15.0 },
                    { key: 'revenue_growth_good', label: 'Good (CAGR %)', min: 5, max: 20, step: 0.5, default: 10.0 },
                    { key: 'revenue_growth_fair', label: 'Fair (CAGR %)', min: 0, max: 15, step: 0.5, default: 5.0 },
                ]
            },
            {
                title: 'Net Income Thresholds',
                color: 'purple-500',
                sliders: [
                    { key: 'income_growth_excellent', label: 'Excellent (CAGR %)', min: 10, max: 25, step: 0.5, default: 15.0 },
                    { key: 'income_growth_good', label: 'Good (CAGR %)', min: 5, max: 20, step: 0.5, default: 10.0 },
                    { key: 'income_growth_fair', label: 'Fair (CAGR %)', min: 0, max: 15, step: 0.5, default: 5.0 },
                ]
            },
        ]
    }
}

// Build default config from slider config
function buildDefaultConfig(characterId) {
    const charConfig = CHARACTER_SLIDER_CONFIGS[characterId] || CHARACTER_SLIDER_CONFIGS.lynch
    const defaults = {}

    // Weights
    charConfig.weights.forEach(w => {
        defaults[w.key] = w.default
    })

    // Thresholds
    charConfig.thresholdGroups.forEach(group => {
        group.sliders.forEach(s => {
            defaults[s.key] = s.default
        })
    })

    return defaults
}

export default function OptimizationTab() {
    const [activeCharacter, setActiveCharacter] = useState('lynch')
    const [config, setConfig] = useState(() => buildDefaultConfig('lynch'))

    const [validationRunning, setValidationRunning] = useState(false)
    const [optimizationRunning, setOptimizationRunning] = useState(false)
    const [rescoringRunning, setRescoringRunning] = useState(false)

    const [analysis, setAnalysis] = useState(null)
    const [optimizationResult, setOptimizationResult] = useState(null)
    const [optimizationProgress, setOptimizationProgress] = useState(null)
    const [rescoringProgress, setRescoringProgress] = useState(null)
    const [yearsBack, setYearsBack] = useState("5")
    const [optimizationMethod, setOptimizationMethod] = useState("bayesian")
    const [maxIterations, setMaxIterations] = useState("100")



    // Initialize on mount
    useEffect(() => {
        const controller = new AbortController()
        initialize(controller.signal)
        return () => controller.abort()
    }, [])

    const initialize = async (signal) => {
        try {
            // Fetch character setting first to set initial state
            const charResponse = await fetch('/api/settings/character', { signal, credentials: 'include' })
            const charData = await charResponse.json()
            const character = charData.active_character || 'lynch'

            setActiveCharacter(character)
            loadConfigForCharacter(character, signal)
        } catch (error) {
            // Ignore abort errors (component unmounted)
            if (error.name === 'AbortError') return
            console.error('Error initializing:', error)
        }
    }

    const loadConfigForCharacter = async (character, signal) => {
        try {
            // Fetch algorithm config for specific character
            const response = await fetch(`/api/algorithm/config?character_id=${character}`, { signal, credentials: 'include' })
            const data = await response.json()
            if (data.current) {
                setConfig(data.current)
                // Auto-validation removed - users can manually trigger validation if needed
            } else {
                // No saved config, use defaults for character
                setConfig(buildDefaultConfig(character))
            }
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('Error loading config:', error)
            }
        }
    }

    const handleCharacterChange = (newCharacter) => {
        setActiveCharacter(newCharacter)
        setAnalysis(null)
        setOptimizationResult(null)
        loadConfigForCharacter(newCharacter)
    }

    // Separate function to run validation with a specific config (used on load)
    const runValidationForConfig = async (configToValidate, signal) => {
        try {
            const response = await fetch('/api/validate/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    years_back: parseInt(yearsBack),
                    limit: null,
                    config: configToValidate,
                    character_id: activeCharacter
                }),
                signal
            })
            const data = await response.json()
            if (data.job_id) {
                pollValidationProgress(data.job_id)
            }
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('Error running initial validation:', error)
            }
        }
    }

    const handleSliderChange = (key, value) => {
        const numValue = parseFloat(value)

        if (key.startsWith('weight_')) {
            const newConfig = { ...config, [key]: numValue }
            // Get weight keys from current character's config
            const charConfig = CHARACTER_SLIDER_CONFIGS[activeCharacter] || CHARACTER_SLIDER_CONFIGS.lynch
            const weightKeys = charConfig.weights.map(w => w.key)
            const total = weightKeys.reduce((sum, k) => sum + (newConfig[k] || 0), 0)
            const normalized = { ...newConfig }
            weightKeys.forEach(k => {
                if (newConfig[k] !== undefined && total > 0) {
                    normalized[k] = newConfig[k] / total
                }
            })
            setConfig(normalized)
        } else {
            setConfig({ ...config, [key]: numValue })
        }
    }

    const runValidation = async (configOverride = null) => {
        setValidationRunning(true)
        setAnalysis(null)

        // If an override is provided (and it's not a click event), use it
        const configToUse = (configOverride && !configOverride.nativeEvent) ? configOverride : config

        try {
            const response = await fetch('/api/validate/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    years_back: parseInt(yearsBack),
                    limit: null,
                    config: configToUse,
                    character_id: activeCharacter
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
                    method: optimizationMethod,
                    max_iterations: parseInt(maxIterations),
                    limit: null,
                    character_id: activeCharacter
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
                        // Update sliders to show the winning configuration
                        if (statusData.result?.best_config) {
                            setConfig(statusData.result.best_config)
                        }
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

    const saveConfiguration = async (configOverride = null) => {
        try {
            setRescoringRunning(true)
            setRescoringProgress(null)

            // If an override is provided (and it's not a click event), use it
            const configToUse = (configOverride && !configOverride.nativeEvent) ? configOverride : config

            // Try to find the correlation associated with this config
            let correlation = null

            // 1. If we have an optimization result and we are saving THAT config
            if (optimizationResult?.result?.final_correlation &&
                JSON.stringify(configToUse) === JSON.stringify(optimizationResult.result.best_config)) {
                correlation = optimizationResult.result.final_correlation
            }
            // 2. Fallback: use current analysis if available
            else if (analysis?.overall_correlation?.coefficient) {
                correlation = analysis.overall_correlation.coefficient
            }

            const configToSave = {
                ...configToUse,
                [`correlation_${yearsBack}yr`]: correlation
            }

            const response = await fetch('/api/algorithm/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    config: configToSave,
                    character_id: activeCharacter
                })
            })

            if (!response.ok) {
                const errorData = await response.json()
                throw new Error(errorData.error || 'Failed to save configuration')
            }

            // Configuration saved successfully
            alert('Configuration saved successfully!')

        } catch (error) {
            console.error('Error saving configuration:', error)
            alert(`Failed to save configuration: ${error.message}`)
        } finally {
            setRescoringRunning(false)
        }
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

    const renderLiveSlider = (key, label, min, max, step, isPercentage = false) => {
        const val = optimizationProgress?.current_config?.[key] ?? optimizationProgress?.best_config?.[key] ?? config[key] ?? 0

        return (
            <div key={key} className="space-y-2">
                <div className="flex justify-between">
                    <Label className="text-sm">{label}</Label>
                    <span className={cn(
                        "text-sm font-medium transition-colors",
                        optimizationProgress?.best_config ? "text-green-600" : "text-muted-foreground"
                    )}>
                        {isPercentage ? (val * 100).toFixed(1) + '%' : val.toFixed(2)}
                    </span>
                </div>
                <input
                    type="range"
                    min={min}
                    max={max}
                    step={step}
                    value={val}
                    disabled
                    className={cn(
                        "w-full h-2 rounded-lg appearance-none cursor-not-allowed",
                        optimizationProgress?.best_config ? "bg-green-100 accent-green-600" : "bg-muted"
                    )}
                />
            </div>
        )
    }



    return (
        <div className="space-y-6">
            <div>
                <div className="flex items-center justify-between">
                    <div>
                        <h3 className="text-lg font-medium">
                            Algorithm Tuning
                        </h3>
                        <p className="text-sm text-muted-foreground">
                            Configure scoring weights and thresholds
                        </p>
                    </div>
                    <div className="text-sm font-medium text-muted-foreground">
                        {CHARACTER_SLIDER_CONFIGS[activeCharacter]?.displayName || 'Peter Lynch'}
                    </div>
                </div>
            </div>
            <div className="border-t" />

            <Tabs defaultValue="manual" className="w-full">
                <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="manual">Manual</TabsTrigger>
                    <TabsTrigger value="auto">Auto</TabsTrigger>
                    <TabsTrigger value="help">Help</TabsTrigger>
                </TabsList>

                <TabsContent value="manual" className="mt-6">
                    {/* Manual Tuning Card */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                Manual
                            </CardTitle>
                            <CardDescription>
                                Adjust algorithm parameters manually
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            {/* Timeframe Selector */}


                            <div className="border-t" />

                            {/* Settings Grid - Dynamic based on character */}
                            <div className="columns-1 md:columns-2 lg:columns-3 gap-6 space-y-6">
                                {/* Algorithm Weights */}
                                <div className="break-inside-avoid space-y-4">
                                    <div className="font-medium text-sm text-foreground mb-2 flex items-center gap-2">
                                        <div className="w-1 h-4 bg-primary rounded-full"></div>
                                        Algorithm Weights
                                    </div>
                                    <div className="space-y-4 p-4 bg-muted/30 rounded-lg border">
                                        {CHARACTER_SLIDER_CONFIGS[activeCharacter]?.weights.map(w => (
                                            renderSlider(w.key, w.label, 0, 1, 0.01, true)
                                        ))}
                                    </div>
                                </div>

                                {/* Threshold Groups - Dynamic based on character */}
                                {CHARACTER_SLIDER_CONFIGS[activeCharacter]?.thresholdGroups.map((group, idx) => (
                                    <div key={group.title} className="break-inside-avoid space-y-4">
                                        <div className="font-medium text-sm text-foreground mb-2 flex items-center gap-2">
                                            <div className={`w-1 h-4 bg-${group.color} rounded-full`}></div>
                                            {group.title}
                                        </div>
                                        <div className="space-y-4 p-4 bg-muted/30 rounded-lg border">
                                            {group.sliders.map(s => (
                                                renderSlider(s.key, s.label, s.min, s.max, s.step, s.isPercentage)
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>


                            {/* Timeframe Selector */}
                            <div className="space-y-3 pt-6 border-t">
                                <Label>Backtest Timeframe</Label>
                                <RadioGroup
                                    value={yearsBack}
                                    onValueChange={setYearsBack}
                                    className="grid grid-cols-2 gap-4"
                                >
                                    <Label
                                        htmlFor="5y-manual"
                                        className="relative flex flex-col items-center justify-between rounded-md border-2 border-muted bg-popover p-4 hover:bg-accent hover:text-accent-foreground cursor-pointer has-[[data-state=checked]]:border-primary"
                                    >
                                        <RadioGroupItem value="5" id="5y-manual" className="absolute inset-0 opacity-0" />
                                        <span className="font-semibold">5 Years</span>
                                    </Label>
                                    <Label
                                        htmlFor="10y-manual"
                                        className="relative flex flex-col items-center justify-between rounded-md border-2 border-muted bg-popover p-4 hover:bg-accent hover:text-accent-foreground cursor-pointer has-[[data-state=checked]]:border-primary"
                                    >
                                        <RadioGroupItem value="10" id="10y-manual" className="absolute inset-0 opacity-0" />
                                        <span className="font-semibold">10 Years</span>
                                    </Label>
                                </RadioGroup>
                            </div>

                            {/* Action Buttons */}
                            <div className="flex gap-4 pt-4">
                                <Button onClick={runValidation} size="lg" disabled={validationRunning} className="flex-1">
                                    {validationRunning ? (
                                        <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Running Backtest...</>
                                    ) : (
                                        <><Play className="mr-2 h-4 w-4" /> Run Backtest</>
                                    )}
                                </Button>
                                <Button onClick={saveConfiguration} size="lg" variant="secondary" disabled={rescoringRunning} className="flex-1">
                                    {rescoringRunning ? (
                                        <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Saving... {rescoringProgress?.progress || 0}/{rescoringProgress?.total || 0}</>
                                    ) : (
                                        <><Save className="mr-2 h-4 w-4" /> Save Configuration</>
                                    )}
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="auto" className="mt-6">
                    {/* Auto-Optimization Card */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-7">
                            <div className="space-y-1.5">
                                <CardTitle className="flex items-center gap-2">
                                    Auto
                                </CardTitle>
                                <CardDescription>
                                    Automatically find optimal algorithm configuration
                                </CardDescription>
                            </div>
                            <Button
                                onClick={runOptimization}
                                disabled={optimizationRunning}
                                size="sm"
                                className="shadow-sm"
                            >
                                {optimizationRunning ? (
                                    <><Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Running...</>
                                ) : (
                                    <><Sparkles className="mr-2 h-3.5 w-3.5" /> Start</>
                                )}
                            </Button>
                        </CardHeader>
                        <CardContent className="space-y-6">

                            {/* Control Group */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pb-6 border-b">
                                <div className="space-y-3">
                                    <Label>Optimization Method</Label>
                                    <RadioGroup
                                        value={optimizationMethod}
                                        onValueChange={setOptimizationMethod}
                                        className="flex gap-2"
                                    >
                                        <div className="flex-1">
                                            <RadioGroupItem value="bayesian" id="meth_bayes" className="peer sr-only" />
                                            <Label
                                                htmlFor="meth_bayes"
                                                className="flex flex-col items-center justify-center rounded-md border-2 border-muted bg-popover p-2 hover:bg-accent hover:text-accent-foreground peer-data-[state=checked]:border-amber-500 [&:has([data-state=checked])]:border-amber-500 h-16 text-center cursor-pointer"
                                            >
                                                <span className="font-semibold text-sm">Bayesian</span>
                                                <span className="text-[10px] text-muted-foreground">Smart Search</span>
                                            </Label>
                                        </div>
                                        <div className="flex-1">
                                            <RadioGroupItem value="gradient_descent" id="meth_grad" className="peer sr-only" />
                                            <Label
                                                htmlFor="meth_grad"
                                                className="flex flex-col items-center justify-center rounded-md border-2 border-muted bg-popover p-2 hover:bg-accent hover:text-accent-foreground peer-data-[state=checked]:border-amber-500 [&:has([data-state=checked])]:border-amber-500 h-16 text-center cursor-pointer"
                                            >
                                                <span className="font-semibold text-sm">Gradient</span>
                                                <span className="text-[10px] text-muted-foreground">Local Descent</span>
                                            </Label>
                                        </div>
                                        <div className="flex-1">
                                            <RadioGroupItem value="grid_search" id="meth_grid" className="peer sr-only" />
                                            <Label
                                                htmlFor="meth_grid"
                                                className="flex flex-col items-center justify-center rounded-md border-2 border-muted bg-popover p-2 hover:bg-accent hover:text-accent-foreground peer-data-[state=checked]:border-amber-500 [&:has([data-state=checked])]:border-amber-500 h-16 text-center cursor-pointer"
                                            >
                                                <span className="font-semibold text-sm">Grid</span>
                                                <span className="text-[10px] text-muted-foreground">Exhaustive</span>
                                            </Label>
                                        </div>
                                    </RadioGroup>
                                </div>

                                <div className="space-y-3">
                                    <Label>Max Iterations</Label>
                                    <RadioGroup
                                        value={maxIterations}
                                        onValueChange={setMaxIterations}
                                        className="flex gap-2"
                                    >
                                        {['100', '200', '500'].map((iter) => (
                                            <div key={iter} className="flex-1">
                                                <RadioGroupItem value={iter} id={`iter_${iter}`} className="peer sr-only" />
                                                <Label
                                                    htmlFor={`iter_${iter}`}
                                                    className="flex flex-col items-center justify-center rounded-md border-2 border-muted bg-popover p-2 hover:bg-accent hover:text-accent-foreground peer-data-[state=checked]:border-amber-500 [&:has([data-state=checked])]:border-amber-500 h-16 text-center cursor-pointer"
                                                >
                                                    <span className="font-semibold text-sm">{iter}</span>
                                                    <span className="text-[10px] text-muted-foreground">Steps</span>
                                                </Label>
                                            </div>
                                        ))}
                                    </RadioGroup>
                                </div>
                            </div>

                            {/* Live Progress Bar */}
                            {optimizationRunning && optimizationProgress && (
                                <div className="space-y-2">
                                    <div className="flex justify-between text-sm">
                                        <span className="font-medium text-amber-600 flex items-center gap-2">
                                            <Loader2 className="h-3 w-3 animate-spin" />
                                            {optimizationProgress?.stage === 'optimizing' ? `Optimizing... Iteration ${optimizationProgress.progress}/${optimizationProgress.total}`
                                                : optimizationProgress?.stage === 'clearing_cache' ? 'Clearing cache...'
                                                    : optimizationProgress?.stage === 'revalidating' ? 'Finalizing validation...'
                                                        : 'Starting...'}
                                        </span>
                                        <span className="font-bold text-green-600">
                                            Best: {(optimizationProgress.best_score || 0).toFixed(4)}
                                        </span>
                                    </div>
                                    <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                                        <div
                                            className="bg-amber-500 h-full transition-all duration-300 ease-out"
                                            style={{ width: `${((optimizationProgress.progress || 0) / (optimizationProgress.total || 100)) * 100}%` }}
                                        />
                                    </div>
                                </div>
                            )}

                            {/* Live Visualization Masonry Layout - Dynamic based on character */}
                            <div className="columns-1 md:columns-2 lg:columns-3 gap-6 space-y-6">
                                {/* Algorithm Weights */}
                                <div className="break-inside-avoid space-y-4">
                                    <div className="font-medium text-sm text-foreground mb-2 flex items-center gap-2">
                                        <div className={cn("w-1 h-4 rounded-full", optimizationRunning ? "bg-amber-500" : "bg-primary")}></div>
                                        Algorithm Weights
                                    </div>
                                    <div className={cn("space-y-4 p-4 rounded-lg border", optimizationRunning ? "bg-amber-50/50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900" : "bg-muted/30")}>
                                        {CHARACTER_SLIDER_CONFIGS[activeCharacter]?.weights.map(w => (
                                            renderLiveSlider(w.key, w.label, 0, 1, 0.01, true)
                                        ))}
                                    </div>
                                </div>

                                {/* Threshold Groups - Dynamic based on character */}
                                {CHARACTER_SLIDER_CONFIGS[activeCharacter]?.thresholdGroups.map((group, idx) => (
                                    <div key={group.title} className="break-inside-avoid space-y-4">
                                        <div className="font-medium text-sm text-foreground mb-2 flex items-center gap-2">
                                            <div className={cn("w-1 h-4 rounded-full", optimizationRunning ? "bg-amber-500" : `bg-${group.color}`)}></div>
                                            {group.title}
                                        </div>
                                        <div className={cn("space-y-4 p-4 rounded-lg border", optimizationRunning ? "bg-amber-50/50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900" : "bg-muted/30")}>
                                            {group.sliders.map(s => (
                                                renderLiveSlider(s.key, s.label, s.min, s.max, s.step, s.isPercentage)
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>


                            {/* Timeframe Selector for Auto Tab */}
                            {/* Preliminary Results */}
                            {optimizationResult && !optimizationResult.error && (
                                <div className="space-y-4 pt-6 border-t">
                                    <div className="text-sm font-medium">Preliminary Results</div>

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
                                </div>
                            )}

                            {/* Timeframe Selector & Actions */}
                            <div className="space-y-4 pt-6 border-t">
                                <Label>Backtest Timeframe</Label>
                                <RadioGroup
                                    value={yearsBack}
                                    onValueChange={setYearsBack}
                                    className="grid grid-cols-2 gap-4"
                                >
                                    <Label
                                        htmlFor="5y-auto"
                                        className="relative flex flex-col items-center justify-between rounded-md border-2 border-muted bg-popover p-4 hover:bg-accent hover:text-accent-foreground cursor-pointer has-[[data-state=checked]]:border-primary"
                                    >
                                        <RadioGroupItem value="5" id="5y-auto" className="absolute inset-0 opacity-0" />
                                        <span className="font-semibold">5 Years</span>
                                    </Label>
                                    <Label
                                        htmlFor="10y-auto"
                                        className="relative flex flex-col items-center justify-between rounded-md border-2 border-muted bg-popover p-4 hover:bg-accent hover:text-accent-foreground cursor-pointer has-[[data-state=checked]]:border-primary"
                                    >
                                        <RadioGroupItem value="10" id="10y-auto" className="absolute inset-0 opacity-0" />
                                        <span className="font-semibold">10 Years</span>
                                    </Label>
                                </RadioGroup>

                                {optimizationResult && !optimizationResult.error && (
                                    <div className="flex gap-4 pt-2">
                                        <Button
                                            onClick={() => {
                                                const optimizedConfig = optimizationResult.result.best_config;
                                                setConfig(optimizedConfig);
                                                runValidation(optimizedConfig);
                                            }}
                                            size="lg"
                                            disabled={validationRunning}
                                            className="flex-1"
                                        >
                                            {validationRunning ? (
                                                <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Running Backtest...</>
                                            ) : (
                                                <><Play className="mr-2 h-4 w-4" /> Run Backtest</>
                                            )}
                                        </Button>
                                        <Button
                                            onClick={() => {
                                                const optimizedConfig = optimizationResult.result.best_config;
                                                setConfig(optimizedConfig);
                                                saveConfiguration(optimizedConfig);
                                            }}
                                            size="lg"
                                            variant="secondary"
                                            disabled={rescoringRunning}
                                            className="flex-1"
                                        >
                                            {rescoringRunning ? (
                                                <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Saving... {rescoringProgress?.progress || 0}/{rescoringProgress?.total || 0}</>
                                            ) : (
                                                <><Save className="mr-2 h-4 w-4" /> Save Configuration</>
                                            )}
                                        </Button>
                                    </div>
                                )}
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="help" className="mt-6">
                    {/* Correlation Guide Card */}
                    <Card className="border-l-4 border-l-primary">
                        <CardHeader>
                            <CardTitle>Understanding Correlation</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="mb-4 text-sm text-muted-foreground space-y-2">
                                <p>
                                    <strong>What we're measuring:</strong> We backtest our algorithm by calculating what each stock's <strong>Overall Score</strong> would have been in the past, then comparing those scores to the stock's <strong>actual price performance</strong> over that time period.
                                </p>
                                <p>
                                    <strong>What correlation means:</strong> A value from 0 to 1 measuring how strongly two things are related. A correlation of <strong>0</strong> means no relationship (random). A correlation of <strong>1</strong> means perfect relationship (higher scores always meant higher returns). In finance, even small positive correlations are valuable.
                                </p>
                            </div>
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
                                ))}\n                            </div>
                            <div className="mt-4 bg-blue-50 dark:bg-blue-950 p-3 rounded-lg text-sm">
                                <strong>Timeframe Selection:</strong> We recommend <strong>5 years</strong> for most analysis.
                                For a longer-term view, try <strong>10 years</strong> (but beware of survivorship bias).
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div >
    )
}
