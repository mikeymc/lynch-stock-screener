// ABOUTME: Component for AI-powered DCF recommendations with three scenarios
// ABOUTME: Displays Conservative, Base Case, and Optimistic scenarios with reasoning

import { useState } from 'react'
import { Sparkles, Loader2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { Card, CardContent } from '@/components/ui/card'

// Overlay button component for rendering inside the chart
export function DCFOptimizeButton({ loading, hasRecommendations, onGenerate, className }) {
    if (loading) {
        return (
            <div className={`px-4 py-2 bg-slate-700 text-white rounded-md text-sm flex items-center gap-2 ${className || ''}`}>
                <Loader2 className="h-4 w-4 animate-spin" />
                Optimizing...
            </div>
        )
    }

    return (
        <button
            onClick={onGenerate}
            className={`px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground shadow-sm rounded-md text-sm font-medium flex items-center gap-2 transition-colors ${className || ''}`}
        >
            <Sparkles className="h-4 w-4" />
            {hasRecommendations ? 'Re-Optimize' : 'Optimize'}
        </button>
    )
}

// Full panel component for displaying recommendations
export default function DCFAIRecommendations({
    recommendations,
    loading,
    error,
    onApplyScenario,
    selectedScenario,
    onScenarioSelect
}) {
    const [reasoningExpanded, setReasoningExpanded] = useState(true)

    const scenarioLabels = {
        conservative: { label: 'Conservative' },
        base: { label: 'Base Case' },
        optimistic: { label: 'Optimistic' }
    }

    const hasRecommendations = recommendations?.scenarios

    const handleScenarioSelect = (scenarioName) => {
        onScenarioSelect(scenarioName)
        if (recommendations?.scenarios?.[scenarioName] && onApplyScenario) {
            onApplyScenario(recommendations.scenarios[scenarioName])
        }
    }

    // Don't render anything if no recommendations and not loading
    if (!hasRecommendations && !loading && !error) {
        return null
    }

    return (
        <div className="mb-6">
            {/* Loading State */}
            {loading && (
                <Card>
                    <CardContent className="py-8 text-center text-muted-foreground italic">
                        <Loader2 className="h-6 w-6 animate-spin mx-auto mb-3" />
                        Generating DCF recommendation. Please wait. This could take up to a minute...
                    </CardContent>
                </Card>
            )}

            {/* Error State */}
            {error && (
                <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-600">
                    Error: {error}
                </div>
            )}

            {/* Recommendations Display */}
            {hasRecommendations && !loading && (
                <Card>
                    <CardContent className="pt-6 space-y-4">
                        {/* Scenario Buttons */}
                        <div className="grid grid-cols-3 gap-3">
                            {Object.entries(scenarioLabels).map(([key, { label }]) => (
                                <button
                                    key={key}
                                    onClick={() => handleScenarioSelect(key)}
                                    className={`py-3 px-4 rounded-lg font-medium transition-all flex items-center justify-center
                                        ${selectedScenario === key
                                            ? 'bg-primary text-primary-foreground shadow-sm'
                                            : 'bg-muted hover:bg-muted/80 text-foreground'
                                        }`}
                                >
                                    {label}
                                </button>
                            ))}
                        </div>

                        {/* Selected Scenario Summary */}
                        {recommendations.scenarios[selectedScenario] && (
                            <div className="grid grid-cols-4 gap-3 p-4 bg-muted/50 rounded-lg">
                                <div className="text-center">
                                    <div className="text-xs text-muted-foreground mb-1">Growth Rate</div>
                                    <div className="text-lg font-semibold">
                                        {recommendations.scenarios[selectedScenario].growthRate}%
                                    </div>
                                </div>
                                <div className="text-center">
                                    <div className="text-xs text-muted-foreground mb-1">Discount Rate</div>
                                    <div className="text-lg font-semibold">
                                        {recommendations.scenarios[selectedScenario].discountRate}%
                                    </div>
                                </div>
                                <div className="text-center">
                                    <div className="text-xs text-muted-foreground mb-1">Terminal Growth</div>
                                    <div className="text-lg font-semibold">
                                        {recommendations.scenarios[selectedScenario].terminalGrowthRate}%
                                    </div>
                                </div>
                                <div className="text-center">
                                    <div className="text-xs text-muted-foreground mb-1">Base FCF</div>
                                    <div className="text-lg font-semibold">
                                        {recommendations.scenarios[selectedScenario].baseYearMethod === 'latest' ? 'Latest Year' :
                                            recommendations.scenarios[selectedScenario].baseYearMethod === 'avg3' ? '3-Year Avg' : '5-Year Avg'}
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* AI Reasoning */}
                        {recommendations.reasoning && (
                            <div>
                                <button
                                    onClick={() => setReasoningExpanded(!reasoningExpanded)}
                                    className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors mb-3"
                                >
                                    <span>{reasoningExpanded ? '▼' : '▶'}</span>
                                    <span>AI Reasoning</span>
                                </button>
                                {reasoningExpanded && (
                                    <div className="p-4 bg-muted/50 rounded-lg text-sm leading-relaxed">
                                        <div className="prose prose-sm dark:prose-invert max-w-none [&>p]:mb-4 [&>p:last-child]:mb-0 [&>ul]:mb-4 [&>ol]:mb-4">
                                            <ReactMarkdown>{recommendations.reasoning}</ReactMarkdown>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}
        </div>
    )
}
