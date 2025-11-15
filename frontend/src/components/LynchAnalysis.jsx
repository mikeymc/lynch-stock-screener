import { useState } from 'react'

const API_BASE = 'http://localhost:5001/api'

function LynchAnalysis({ symbol, stockName, onAnalysisLoaded }) {
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [generatedAt, setGeneratedAt] = useState(null)
  const [cached, setCached] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [requested, setRequested] = useState(false)

  const fetchAnalysis = async (forceRefresh = false) => {
    try {
      setRequested(true)
      if (forceRefresh) {
        setRefreshing(true)
      } else {
        setLoading(true)
      }
      setError(null)

      const url = forceRefresh
        ? `${API_BASE}/stock/${symbol}/lynch-analysis/refresh`
        : `${API_BASE}/stock/${symbol}/lynch-analysis`

      const method = forceRefresh ? 'POST' : 'GET'

      const response = await fetch(url, { method })

      if (!response.ok) {
        throw new Error(`Failed to fetch analysis: ${response.statusText}`)
      }

      const data = await response.json()
      setAnalysis(data.analysis)
      setGeneratedAt(data.generated_at)
      setCached(data.cached)

      // Notify parent component that analysis has been loaded
      if (onAnalysisLoaded && data.analysis) {
        onAnalysisLoaded(data.analysis)
      }
    } catch (err) {
      console.error('Error fetching Lynch analysis:', err)
      setError(err.message)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  const handleRefresh = () => {
    fetchAnalysis(true)
  }

  const formatDate = (isoString) => {
    if (!isoString) return ''
    const date = new Date(isoString)
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  if (!requested) {
    return (
      <div className="lynch-analysis-container">
        <div className="lynch-analysis-header">
          <h3>Peter Lynch Analysis</h3>
        </div>
        <div className="lynch-analysis-loading">
          <p>AI-powered Peter Lynch-style analysis for {stockName}</p>
          <button onClick={() => fetchAnalysis()} className="refresh-button">
            ✨ Generate Analysis
          </button>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="lynch-analysis-container">
        <div className="lynch-analysis-header">
          <h3>Peter Lynch Analysis</h3>
        </div>
        <div className="lynch-analysis-loading">
          <div className="spinner"></div>
          <p>Generating Peter Lynch-style analysis...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="lynch-analysis-container">
        <div className="lynch-analysis-header">
          <h3>Peter Lynch Analysis</h3>
        </div>
        <div className="lynch-analysis-error">
          <p>Failed to load analysis: {error}</p>
          <button onClick={() => fetchAnalysis()} className="retry-button">
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="lynch-analysis-container">
      <div className="lynch-analysis-header">
        <div>
          <h3>Peter Lynch Analysis: {stockName}</h3>
          <p className="analysis-metadata">
            {cached ? '📦 Cached' : '✨ Freshly Generated'} • Generated {formatDate(generatedAt)}
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="refresh-button"
        >
          {refreshing ? 'Regenerating...' : '🔄 Regenerate'}
        </button>
      </div>
      <div className="lynch-analysis-content">
        <p>{analysis}</p>
      </div>
    </div>
  )
}

export default LynchAnalysis
