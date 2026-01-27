// ABOUTME: Component to generate and display unified chart analysis
// ABOUTME: Handles both new narrative format and legacy 3-section format
import { useState, useEffect } from 'react'
import { Sparkles, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function UnifiedChartAnalysis({ symbol, character, onAnalysisGenerated, onButtonStateChange }) {
    const [narrative, setNarrative] = useState(null)
    const [legacySections, setLegacySections] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [selectedModel, setSelectedModel] = useState('gemini-3-flash-preview')

    // Check for cached analyses on mount or when character changes
    useEffect(() => {
        const controller = new AbortController()

        fetch(`/api/stock/${symbol}/unified-chart-analysis`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                only_cached: true,
                model: selectedModel,
                character: character
            }),
            signal: controller.signal
        })
            .then(response => response.json())
            .then(data => {
                if (data.narrative) {
                    // New narrative format
                    setNarrative(data.narrative)
                    setLegacySections(null)
                    if (onAnalysisGenerated) {
                        onAnalysisGenerated({ narrative: data.narrative })
                    }
                } else if (data.sections) {
                    // Legacy 3-section format
                    setLegacySections(data.sections)
                    setNarrative(null)
                    if (onAnalysisGenerated) {
                        onAnalysisGenerated({ sections: data.sections })
                    }
                } else {
                    // No cached analysis found for this character
                    setNarrative(null)
                    setLegacySections(null)
                    if (onAnalysisGenerated) {
                        onAnalysisGenerated({ narrative: null })
                    }
                }
            })
            .catch(err => {
                if (err.name !== 'AbortError') {
                    console.error('Error checking cache:', err)
                }
            })

        return () => controller.abort()
    }, [symbol, selectedModel, character])

    const generateAnalysis = async (forceRefresh = false) => {
        setLoading(true)
        setError(null)
        try {
            const response = await fetch(`/api/stock/${symbol}/unified-chart-analysis`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    force_refresh: forceRefresh,
                    model: selectedModel,
                    character: character
                })
            })

            if (!response.ok) {
                throw new Error('Failed to generate analysis')
            }

            const data = await response.json()

            if (data.narrative) {
                setNarrative(data.narrative)
                setLegacySections(null)
                if (onAnalysisGenerated) {
                    onAnalysisGenerated({ narrative: data.narrative })
                }
            } else if (data.sections) {
                setLegacySections(data.sections)
                setNarrative(null)
                if (onAnalysisGenerated) {
                    onAnalysisGenerated({ sections: data.sections })
                }
            }
        } catch (err) {
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    const hasAnyAnalysis = narrative || (legacySections && (legacySections.growth || legacySections.cash || legacySections.valuation))

    // Notify parent of button state changes via useEffect
    useEffect(() => {
        if (onButtonStateChange) {
            onButtonStateChange({
                loading,
                hasAnyAnalysis,
                onAnalyze: () => generateAnalysis(hasAnyAnalysis)
            })
        }
    }, [loading, hasAnyAnalysis, onButtonStateChange, character, selectedModel])

    return (
        <div className="mb-8">
            {/* Only render button inline if parent doesn't want to control placement */}
            {!onButtonStateChange && (
                <div className="flex justify-start items-center gap-4 mb-4">
                    {!loading && (
                        <Button
                            onClick={() => generateAnalysis(hasAnyAnalysis)}
                            className="gap-2"
                            size="sm"
                        >
                            {hasAnyAnalysis ? (
                                <>
                                    <RefreshCw className="h-4 w-4" />
                                    Re-Analyze
                                </>
                            ) : (
                                <>
                                    <Sparkles className="h-4 w-4" />
                                    Analyze
                                </>
                            )}
                        </Button>
                    )}
                </div>
            )}

            {loading && (
                <div className="p-8 bg-muted rounded-lg border border-border text-muted-foreground italic text-center animate-pulse">
                    Generating analysis. Please wait. This could take up to a minute...
                </div>
            )}

            {error && (
                <div className="p-4 bg-destructive/10 rounded-lg border border-destructive/20 text-destructive">
                    Error: {error}
                </div>
            )}
        </div>
    )
}

