// ABOUTME: Component to generate and display unified chart analysis for all three sections
import { useState, useEffect } from 'react'

export default function UnifiedChartAnalysis({ symbol, onAnalysisGenerated }) {
    const [sections, setSections] = useState({ growth: null, cash: null, valuation: null })
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [selectedModel, setSelectedModel] = useState('gemini-2.5-flash')

    // Check for cached analyses on mount
    useEffect(() => {
        const controller = new AbortController()

        fetch(`/api/stock/${symbol}/unified-chart-analysis`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                only_cached: true,
                model: selectedModel
            }),
            signal: controller.signal
        })
            .then(response => response.json())
            .then(data => {
                if (data.sections) {
                    setSections(data.sections)
                    if (onAnalysisGenerated) {
                        onAnalysisGenerated(data.sections)
                    }
                }
            })
            .catch(err => {
                if (err.name !== 'AbortError') {
                    console.error('Error checking cache:', err)
                }
            })

        return () => controller.abort()
    }, [symbol, selectedModel])

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
                    model: selectedModel
                })
            })

            if (!response.ok) {
                throw new Error('Failed to generate analysis')
            }

            const data = await response.json()
            setSections(data.sections)
            if (onAnalysisGenerated) {
                onAnalysisGenerated(data.sections)
            }
        } catch (err) {
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    const hasAnyAnalysis = sections.growth || sections.cash || sections.valuation

    return (
        <div style={{ marginBottom: '2rem' }}>
            <div style={{ display: 'flex', justifyContent: 'flex-start', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
                {!loading && (
                    <button
                        onClick={() => generateAnalysis(hasAnyAnalysis)}
                        style={{
                            padding: '0.5rem 1rem',
                            backgroundColor: '#3b82f6',
                            color: 'white',
                            border: 'none',
                            borderRadius: '0.375rem',
                            cursor: 'pointer',
                            fontSize: '1rem',
                            fontWeight: '500',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.5rem'
                        }}
                    >
                        {hasAnyAnalysis ? '🔄 Re-Analyze' : '✨ Analyze'}
                    </button>
                )}
            </div>

            {loading && (
                <div style={{
                    padding: '2rem',
                    backgroundColor: '#1e293b',
                    borderRadius: '0.5rem',
                    border: '1px solid #334155',
                    color: '#94a3b8',
                    fontStyle: 'italic',
                    textAlign: 'center'
                }}>
                    Generating analysis. Please wait. This could take up to a minute...
                </div>
            )}

            {error && (
                <div style={{
                    padding: '1rem',
                    backgroundColor: '#7f1d1d',
                    borderRadius: '0.5rem',
                    border: '1px solid #991b1b',
                    color: '#fecaca'
                }}>
                    Error: {error}
                </div>
            )}
        </div>
    )
}
