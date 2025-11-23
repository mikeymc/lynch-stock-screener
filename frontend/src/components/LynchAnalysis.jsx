import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'

const API_BASE = '/api'

function LynchAnalysis({ symbol, stockName, onAnalysisLoaded }) {
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [generatedAt, setGeneratedAt] = useState(null)
  const [cached, setCached] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const fetchAnalysis = async (forceRefresh = false, signal = null, onlyCached = false) => {
    try {
      if (forceRefresh) {
        setRefreshing(true)
      } else {
        setLoading(true)
      }
      setError(null)

      let url = forceRefresh
        ? `${API_BASE}/stock/${symbol}/lynch-analysis/refresh`
        : `${API_BASE}/stock/${symbol}/lynch-analysis`

      if (onlyCached && !forceRefresh) {
        url += '?only_cached=true'
      }

      const method = forceRefresh ? 'POST' : 'GET'

      const response = await fetch(url, { method, signal })

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
      if (err.name === 'AbortError') {
        console.log('Fetch aborted')
        return
      }
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

  const handleGenerate = () => {
    fetchAnalysis(false)
  }

  // Auto-fetch analysis on mount (but only check cache)
  useEffect(() => {
    const controller = new AbortController()
    fetchAnalysis(false, controller.signal, true)
    return () => controller.abort()
  }, [symbol])

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

  if (loading) {
    return (
      <div className="lynch-analysis-container">
        <div className="lynch-analysis-header">
          <h3>Peter Lynch Analysis</h3>
        </div>
        <div className="lynch-analysis-loading">
          <div className="spinner"></div>
          <p>Checking for analysis...</p>
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
          <button onClick={() => fetchAnalysis(false, null, true)} className="retry-button">
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (!analysis) {
    return (
      <div className="lynch-analysis-container">
        <div className="lynch-analysis-header">
          <h3>Peter Lynch Analysis</h3>
        </div>
        <div className="lynch-analysis-empty">
          <p>No analysis generated yet for {stockName}.</p>
          <button onClick={handleGenerate} className="generate-button">
            ✨ Generate Analysis
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
      <div className="lynch-analysis-content markdown-content">
        <ReactMarkdown>{analysis}</ReactMarkdown>
      </div>
    </div>
  )
}

export default LynchAnalysis
