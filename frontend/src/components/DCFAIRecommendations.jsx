// ABOUTME: Component for AI-powered DCF recommendations with three scenarios
// ABOUTME: Displays Conservative, Base Case, and Optimistic scenarios with reasoning

import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'

export default function DCFAIRecommendations({ symbol, onApplyScenario }) {
    const [recommendations, setRecommendations] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [selectedScenario, setSelectedScenario] = useState('base')
    const [reasoningExpanded, setReasoningExpanded] = useState(true)

    // Check for cached recommendations on mount
    useEffect(() => {
        const controller = new AbortController()

        fetch(`/api/stock/${symbol}/dcf-recommendations`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                only_cached: true
            }),
            signal: controller.signal
        })
            .then(response => response.json())
            .then(data => {
                if (data.scenarios) {
                    setRecommendations(data)
                    // Auto-apply base case scenario
                    if (data.scenarios.base && onApplyScenario) {
                        onApplyScenario(data.scenarios.base)
                    }
                }
            })
            .catch(err => {
                if (err.name !== 'AbortError') {
                    console.error('Error checking cache:', err)
                }
            })

        return () => controller.abort()
    }, [symbol])

    const generateRecommendations = async (forceRefresh = false) => {
        setLoading(true)
        setError(null)
        try {
            const response = await fetch(`/api/stock/${symbol}/dcf-recommendations`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    force_refresh: forceRefresh
                })
            })

            if (!response.ok) {
                const errorData = await response.json()
                throw new Error(errorData.error || 'Failed to generate recommendations')
            }

            const data = await response.json()
            setRecommendations(data)
            setSelectedScenario('base')

            // Auto-apply base case scenario
            if (data.scenarios?.base && onApplyScenario) {
                onApplyScenario(data.scenarios.base)
            }
        } catch (err) {
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    const handleScenarioSelect = (scenarioName) => {
        setSelectedScenario(scenarioName)
        if (recommendations?.scenarios?.[scenarioName] && onApplyScenario) {
            onApplyScenario(recommendations.scenarios[scenarioName])
        }
    }

    const scenarioLabels = {
        conservative: { label: 'Conservative', icon: '🛡️', color: '#60a5fa' },
        base: { label: 'Base Case', icon: '📊', color: '#4ade80' },
        optimistic: { label: 'Optimistic', icon: '🚀', color: '#fbbf24' }
    }

    const hasRecommendations = recommendations?.scenarios

    return (
        <div style={{ marginBottom: '1.5rem' }}>
            {/* Generate Button */}
            <div style={{ display: 'flex', justifyContent: 'flex-start', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
                {!loading && (
                    <button
                        onClick={() => generateRecommendations(hasRecommendations)}
                        style={{
                            padding: '0.5rem 1rem',
                            backgroundColor: '#8b5cf6',
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
                        {hasRecommendations ? '🔄 Regenerate AI Settings' : '✨ AI Optimize Settings'}
                    </button>
                )}
            </div>

            {/* Loading State */}
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
                    Generating AI recommendations. Please wait. This could take up to a minute...
                </div>
            )}

            {/* Error State */}
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

            {/* Recommendations Display */}
            {hasRecommendations && !loading && (
                <div style={{
                    backgroundColor: '#1e293b',
                    borderRadius: '0.5rem',
                    border: '1px solid #334155',
                    padding: '1rem'
                }}>
                    {/* Scenario Buttons */}
                    <div style={{
                        display: 'flex',
                        gap: '0.75rem',
                        marginBottom: '1rem'
                    }}>
                        {Object.entries(scenarioLabels).map(([key, { label, icon, color }]) => (
                            <button
                                key={key}
                                onClick={() => handleScenarioSelect(key)}
                                style={{
                                    flex: 1,
                                    padding: '0.75rem 1rem',
                                    backgroundColor: selectedScenario === key ? color : '#334155',
                                    color: selectedScenario === key ? '#0f172a' : '#e2e8f0',
                                    border: selectedScenario === key ? `2px solid ${color}` : '2px solid transparent',
                                    borderRadius: '0.5rem',
                                    cursor: 'pointer',
                                    fontSize: '0.95rem',
                                    fontWeight: selectedScenario === key ? '600' : '400',
                                    transition: 'all 0.2s ease',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    gap: '0.5rem'
                                }}
                            >
                                <span>{icon}</span>
                                <span>{label}</span>
                            </button>
                        ))}
                    </div>

                    {/* Selected Scenario Summary */}
                    {recommendations.scenarios[selectedScenario] && (
                        <div style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(4, 1fr)',
                            gap: '0.75rem',
                            marginBottom: '1rem',
                            padding: '0.75rem',
                            backgroundColor: 'rgba(0,0,0,0.2)',
                            borderRadius: '0.375rem'
                        }}>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Growth Rate</div>
                                <div style={{ fontSize: '1.1rem', fontWeight: '600', color: '#e2e8f0' }}>
                                    {recommendations.scenarios[selectedScenario].growthRate}%
                                </div>
                            </div>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Discount Rate</div>
                                <div style={{ fontSize: '1.1rem', fontWeight: '600', color: '#e2e8f0' }}>
                                    {recommendations.scenarios[selectedScenario].discountRate}%
                                </div>
                            </div>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Terminal Growth</div>
                                <div style={{ fontSize: '1.1rem', fontWeight: '600', color: '#e2e8f0' }}>
                                    {recommendations.scenarios[selectedScenario].terminalGrowthRate}%
                                </div>
                            </div>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Base FCF</div>
                                <div style={{ fontSize: '1.1rem', fontWeight: '600', color: '#e2e8f0' }}>
                                    {recommendations.scenarios[selectedScenario].baseYearMethod === 'latest' ? 'Latest Year' :
                                        recommendations.scenarios[selectedScenario].baseYearMethod === 'avg3' ? '3-Year Avg' : '5-Year Avg'}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* AI Reasoning */}
                    {recommendations.reasoning && (
                        <div>
                            <div
                                onClick={() => setReasoningExpanded(!reasoningExpanded)}
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.5rem',
                                    cursor: 'pointer',
                                    marginBottom: reasoningExpanded ? '0.75rem' : 0,
                                    color: '#94a3b8',
                                    fontSize: '0.9rem'
                                }}
                            >
                                <span>{reasoningExpanded ? '▼' : '▶'}</span>
                                <span>AI Reasoning</span>
                            </div>
                            {reasoningExpanded && (
                                <div style={{
                                    padding: '1rem',
                                    backgroundColor: 'rgba(0,0,0,0.2)',
                                    borderRadius: '0.375rem',
                                    fontSize: '0.9rem',
                                    lineHeight: '1.6',
                                    color: '#cbd5e1'
                                }}>
                                    <ReactMarkdown>{recommendations.reasoning}</ReactMarkdown>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
