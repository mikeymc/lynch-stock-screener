// ABOUTME: Component to fetch and display Peter Lynch-style analysis for a specific chart section
import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'

export default function ChartAnalysis({ symbol, section }) {
    const [analysis, setAnalysis] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)

    const fetchAnalysis = async (forceRefresh = false, signal = null) => {
        setLoading(true)
        setError(null)
        try {
            const response = await fetch(`/api/stock/${symbol}/chart-analysis`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    section,
                    force_refresh: forceRefresh
                }),
                signal // Pass the abort signal
            })

            if (!response.ok) {
                throw new Error('Failed to fetch analysis')
            }

            const data = await response.json()
            setAnalysis(data.analysis)
        } catch (err) {
            if (err.name === 'AbortError') {
                console.log('Fetch aborted')
                return
            }
            setError(err.message)
        } finally {
            // Only turn off loading if not aborted (to avoid flickering if a new request started)
            if (!signal || !signal.aborted) {
                setLoading(false)
            }
        }
    }

    // Check for cached analysis on mount (don't generate if missing)
    useEffect(() => {
        const controller = new AbortController()

        // Try to fetch cached analysis only
        fetch(`/api/stock/${symbol}/chart-analysis`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                section,
                only_cached: true
            }),
            signal: controller.signal
        })
            .then(response => response.json())
            .then(data => {
                if (data.analysis) {
                    setAnalysis(data.analysis)
                }
                // If no cached analysis, do nothing (user will see "Generate" button)
            })
            .catch(err => {
                if (err.name !== 'AbortError') {
                    console.error('Error checking cache:', err)
                }
            })

        return () => controller.abort()
    }, [symbol, section])

    return (
        <div className="chart-analysis-container" style={{ marginTop: '1rem', padding: '1rem', backgroundColor: '#1e293b', borderRadius: '0.5rem', border: '1px solid #334155' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <h4 style={{ margin: 0, color: '#e2e8f0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontSize: '1.2rem' }}>👓</span> Peter's Take
                </h4>
                {!loading && (
                    <button
                        onClick={() => fetchAnalysis(analysis ? true : false)}
                        style={{
                            padding: '0.25rem 0.75rem',
                            backgroundColor: '#3b82f6',
                            color: 'white',
                            border: 'none',
                            borderRadius: '0.25rem',
                            cursor: 'pointer',
                            fontSize: '0.875rem',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.25rem'
                        }}
                    >
                        {analysis ? '🔄 Regenerate' : '✨ Generate Analysis'}
                    </button>
                )}
            </div>

            {loading && (
                <div style={{ color: '#94a3b8', fontStyle: 'italic' }}>
                    Consulting with Peter...
                </div>
            )}

            {error && (
                <div style={{ color: '#ef4444' }}>
                    Error: {error}
                </div>
            )}

            {analysis && (
                <div className="markdown-content">
                    <ReactMarkdown>{analysis}</ReactMarkdown>
                </div>
            )}
        </div>
    )
}
