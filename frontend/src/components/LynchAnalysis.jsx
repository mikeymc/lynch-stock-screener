import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import ModelSelector from './ModelSelector'

const API_BASE = '/api'

function LynchAnalysis({ symbol, stockName, onAnalysisLoaded }) {
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [generatedAt, setGeneratedAt] = useState(null)
  const [cached, setCached] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [selectedModel, setSelectedModel] = useState('gemini-2.5-flash')

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
        url += `?only_cached=true&model=${selectedModel}`
      } else if (!forceRefresh) {
        url += `?model=${selectedModel}`
      }

      const method = forceRefresh ? 'POST' : 'GET'

      const options = { method, signal }
      if (forceRefresh) {
        options.headers = { 'Content-Type': 'application/json' }
        options.body = JSON.stringify({ model: selectedModel })
      }

      const response = await fetch(url, options)

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
  }, [symbol, selectedModel])

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
          <h3>AI Analysis</h3>
        </div>
        <div className="lynch-analysis-loading">
          <div className="spinner"></div>
          <p>Checking for AI analysis...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="lynch-analysis-container">
        <div className="lynch-analysis-header">
          <h3>AI Analysis</h3>
        </div>
        <div className="lynch-analysis-error">
          <p>Failed to load AI analysis: {error}</p>
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
          <h3>AI Analysis</h3>
        </div>
        <div className="lynch-analysis-empty">
          <p>No analysis generated yet for {stockName}.</p>
          <div style={{ display: 'flex', flexDirection: 'row', gap: '1rem', alignItems: 'center', justifyContent: 'center' }}>
            <ModelSelector
              selectedModel={selectedModel}
              onModelChange={setSelectedModel}
              storageKey="lynchAnalysisModel"
            />
            <button onClick={handleGenerate} className="generate-button">
              ✨ Generate Analysis
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="lynch-analysis-container">
      <div className="lynch-analysis-header">
        <div>
          <h3>AI Analysis: {stockName}</h3>
          <p className="analysis-metadata">
            {cached ? '📦 Cached' : '✨ Freshly Generated'} • Generated {formatDate(generatedAt)}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <ModelSelector
            selectedModel={selectedModel}
            onModelChange={setSelectedModel}
            storageKey="lynchAnalysisModel"
          />
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="refresh-button"
          >
            {refreshing ? 'Regenerating...' : '🔄 Regenerate'}
          </button>
        </div>
      </div>
      <div className="lynch-analysis-content markdown-content">
        <ReactMarkdown>{analysis}</ReactMarkdown>
      </div>
    </div>
  )
}

export default LynchAnalysis
