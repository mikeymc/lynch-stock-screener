// ABOUTME: Component to fetch and display Peter Lynch-style analysis for a specific chart section
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'

export default function ChartAnalysis({ symbol, section }) {
    const [analysis, setAnalysis] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)

    const fetchAnalysis = async () => {
        setLoading(true)
        setError(null)
        try {
            const response = await fetch(`/api/stock/${symbol}/chart-analysis`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ section }),
            })

            if (!response.ok) {
                throw new Error('Failed to fetch analysis')
            }

            const data = await response.json()
            setAnalysis(data.analysis)
        } catch (err) {
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="chart-analysis-container" style={{ marginTop: '1rem', padding: '1rem', backgroundColor: '#1e293b', borderRadius: '0.5rem', border: '1px solid #334155' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <h4 style={{ margin: 0, color: '#e2e8f0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontSize: '1.2rem' }}>👓</span> Peter's Take
                </h4>
                {!analysis && !loading && (
                    <button
                        onClick={fetchAnalysis}
                        style={{
                            padding: '0.25rem 0.75rem',
                            backgroundColor: '#3b82f6',
                            color: 'white',
                            border: 'none',
                            borderRadius: '0.25rem',
                            cursor: 'pointer',
                            fontSize: '0.875rem'
                        }}
                    >
                        Analyze Section
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
                <div className="prose prose-invert max-w-none" style={{ fontSize: '0.95rem', lineHeight: '1.6', color: '#cbd5e1' }}>
                    <ReactMarkdown>{analysis}</ReactMarkdown>
                </div>
            )}
        </div>
    )
}
