import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import { Routes, Route, useNavigate, useSearchParams } from 'react-router-dom'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js'
import LynchAnalysis from './components/LynchAnalysis'
import ChatInterface from './components/ChatInterface'
import StockDetail from './pages/StockDetail'


import AlgorithmTuning from './pages/AlgorithmTuning'
import AlgorithmSelector from './components/AlgorithmSelector'
import StatusBar from './components/StatusBar'
import AdvancedFilter from './components/AdvancedFilter'
import { useAuth } from './context/AuthContext'
import LoginModal from './components/LoginModal'
import UserAvatar from './components/UserAvatar'
import './App.css'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
)

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:5001/api'

// FilingSections component displays expandable filing content
function FilingSections({ sections }) {
  const [expandedSections, setExpandedSections] = useState(new Set())

  const toggleSection = (sectionName) => {
    setExpandedSections(prev => {
      const newSet = new Set(prev)
      if (newSet.has(sectionName)) {
        newSet.delete(sectionName)
      } else {
        newSet.add(sectionName)
      }
      return newSet
    })
  }

  const sectionTitles = {
    business: 'Business Description (Item 1)',
    risk_factors: 'Risk Factors (Item 1A)',
    mda: 'Management Discussion & Analysis',
    market_risk: 'Market Risk Disclosures'
  }

  return (
    <div className="sections-container">
      <h3>Key Filing Sections</h3>
      <div className="sections-list">
        {Object.entries(sections).map(([sectionName, sectionData]) => {
          const isExpanded = expandedSections.has(sectionName)
          const title = sectionTitles[sectionName] || sectionName
          const filingType = sectionData.filing_type
          const filingDate = sectionData.filing_date
          const content = sectionData.content

          return (
            <div key={sectionName} className="section-item">
              <div
                className="section-header"
                onClick={() => toggleSection(sectionName)}
              >
                <span className="section-toggle">{isExpanded ? '▼' : '▶'}</span>
                <span className="section-title">{title}</span>
                <span className="section-metadata">({filingType} - Filed: {filingDate})</span>
              </div>
              {isExpanded && (
                <div className="section-content">
                  <div className="section-text">
                    {content.split('\n').map((paragraph, idx) => {
                      // Skip empty lines
                      if (paragraph.trim() === '') return null
                      return <p key={idx}>{paragraph}</p>
                    })}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function StockListView({
  stocks, setStocks,
  summary, setSummary,
  filter, setFilter,
  searchQuery, setSearchQuery,
  currentPage, setCurrentPage,
  sortBy, setSortBy,
  sortDir, setSortDir,
  watchlist, toggleWatchlist,
  algorithm, setAlgorithm
}) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const isAdmin = searchParams.get('user') === 'admin'
  const [loading, setLoading] = useState(false)
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [progress, setProgress] = useState('')
  const [error, setError] = useState(null)
  const itemsPerPage = 100

  // Advanced filters state
  const [advancedFilters, setAdvancedFilters] = useState({
    countries: [],
    regions: [],
    institutionalOwnership: { max: null },
    revenueGrowth: { min: null },
    incomeGrowth: { min: null },
    debtToEquity: { max: null },
    marketCap: { max: null }
  })
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false)

  // Debounced search state
  const [searchLoading, setSearchLoading] = useState(false)
  const debounceTimerRef = useRef(null)

  // Re-evaluate existing stocks when algorithm changes
  const prevAlgorithmRef = useRef(algorithm)
  useEffect(() => {
    const reEvaluateStocks = async () => {
      // Only re-evaluate if algorithm actually changed
      if (prevAlgorithmRef.current === algorithm) {
        return
      }

      if (stocks.length === 0) return

      setLoading(true)
      setProgress('Re-evaluating stocks with new algorithm...')

      try {
        // Fetch re-evaluation for all existing stocks
        const reEvaluatedStocks = await Promise.all(
          stocks.map(async (stock) => {
            try {
              const response = await fetch(`${API_BASE}/stock/${stock.symbol}?algorithm=${algorithm}`)
              if (response.ok) {
                const data = await response.json()
                return data.evaluation || stock // Use evaluation, fallback to original
              }
              return stock // Keep original if fetch fails
            } catch (err) {
              console.error(`Error re-evaluating ${stock.symbol}:`, err)
              return stock // Keep original if fetch fails
            }
          })
        )

        setStocks(reEvaluatedStocks)

        // Recalculate summary stats
        const statusCounts = {}
        reEvaluatedStocks.forEach(stock => {
          const status = stock.overall_status
          statusCounts[status] = (statusCounts[status] || 0) + 1
        })

        const summaryData = {
          totalAnalyzed: reEvaluatedStocks.length,
          algorithm: algorithm
        }

        if (algorithm === 'classic') {
          summaryData.passCount = statusCounts['PASS'] || 0
          summaryData.closeCount = statusCounts['CLOSE'] || 0
          summaryData.failCount = statusCounts['FAIL'] || 0
        } else {
          summaryData.strong_buy_count = statusCounts['STRONG_BUY'] || 0
          summaryData.buy_count = statusCounts['BUY'] || 0
          summaryData.hold_count = statusCounts['HOLD'] || 0
          summaryData.caution_count = statusCounts['CAUTION'] || 0
          summaryData.avoid_count = statusCounts['AVOID'] || 0
        }

        setSummary(summaryData)
        setProgress('')

        // Update the ref after successful re-evaluation
        prevAlgorithmRef.current = algorithm
      } catch (err) {
        console.error('Error re-evaluating stocks:', err)
        setError(`Failed to re-evaluate stocks: ${err.message}`)
      } finally {
        setLoading(false)
      }
    }

    reEvaluateStocks()
  }, [algorithm])

  // Load advanced filters on mount
  useEffect(() => {
    const controller = new AbortController()
    const signal = controller.signal

    const loadAdvancedFilters = async () => {
      try {
        const response = await fetch(`${API_BASE}/settings`, { signal })
        if (response.ok) {
          const settings = await response.json()
          if (settings.advanced_filters && settings.advanced_filters.value) {
            setAdvancedFilters(settings.advanced_filters.value)
          }
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Error loading advanced filters:', err)
        }
      }
    }

    loadAdvancedFilters()

    return () => controller.abort()
  }, [])

  // Start with empty state (don't load cached session since algorithm may have changed)
  const [loadingSession, setLoadingSession] = useState(stocks.length === 0 && !summary)
  // Load latest session on mount
  useEffect(() => {
    if (stocks.length > 0 || summary) {
      setLoadingSession(false)
      return
    }

    const controller = new AbortController()
    const signal = controller.signal

    const loadLatestSession = async () => {
      try {
        const response = await fetch(`${API_BASE}/sessions/latest`, { signal })

        if (response.ok) {
          const sessionData = await response.json()
          const results = sessionData.results || []
          setStocks(results)

          // Calculate counts based on the algorithm type
          // Check if we have new algorithm statuses or old ones
          const hasNewStatuses = results.some(s =>
            ['STRONG_BUY', 'BUY', 'HOLD', 'CAUTION', 'AVOID'].includes(s.overall_status)
          )

          if (hasNewStatuses) {
            // New algorithm statuses
            const strongBuyCount = results.filter(s => s.overall_status === 'STRONG_BUY').length
            const buyCount = results.filter(s => s.overall_status === 'BUY').length
            const holdCount = results.filter(s => s.overall_status === 'HOLD').length
            const cautionCount = results.filter(s => s.overall_status === 'CAUTION').length
            const avoidCount = results.filter(s => s.overall_status === 'AVOID').length

            setSummary({
              totalAnalyzed: results.length,
              strong_buy_count: strongBuyCount,
              buy_count: buyCount,
              hold_count: holdCount,
              caution_count: cautionCount,
              avoid_count: avoidCount,
              algorithm: 'weighted' // Assume weighted for new statuses
            })
          } else {
            // Old algorithm statuses (classic)
            const passCount = results.filter(s => s.overall_status === 'PASS').length
            const closeCount = results.filter(s => s.overall_status === 'CLOSE').length
            const failCount = results.filter(s => s.overall_status === 'FAIL').length

            setSummary({
              totalAnalyzed: results.length,
              passCount,
              closeCount,
              failCount,
              algorithm: 'classic'
            })
          }
        } else if (response.status === 404) {
          // No sessions yet, this is okay
          setStocks([])
          setSummary(null)
        } else {
          throw new Error(`Failed to load session: ${response.status}`)
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Error loading latest session:', err)
          // Don't show error to user on initial load, just start with empty state
          setStocks([])
          setSummary(null)
        }
      } finally {
        if (!signal.aborted) {
          setLoadingSession(false)
        }
      }
    }

    loadLatestSession()

    return () => controller.abort()
  }, [])

  // Debounced search handler - calls backend API after delay
  const handleSearchChange = useCallback((value) => {
    setSearchQuery(value)

    // Clear previous debounce timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }

    // If search is cleared, reload all results immediately
    if (!value.trim()) {
      setSearchLoading(true)
      fetch(`${API_BASE}/sessions/latest`)
        .then(response => response.json())
        .then(data => {
          if (data.results) {
            setStocks(data.results)
          }
        })
        .catch(err => console.error('Error loading results:', err))
        .finally(() => setSearchLoading(false))
      return
    }

    // Set debounce timer for search
    debounceTimerRef.current = setTimeout(() => {
      setSearchLoading(true)
      fetch(`${API_BASE}/sessions/latest?search=${encodeURIComponent(value)}`)
        .then(response => response.json())
        .then(data => {
          if (data.results) {
            setStocks(data.results)
          }
        })
        .catch(err => console.error('Error searching:', err))
        .finally(() => setSearchLoading(false))
    }, 200) // 200ms debounce
  }, [setSearchQuery, setStocks])

  // Resume polling if there's an active screening session
  useEffect(() => {
    const activeSessionId = localStorage.getItem('activeScreeningSession')
    const activeJobId = localStorage.getItem('activeJobId')
    if (activeSessionId) {
      const sessionIdNum = parseInt(activeSessionId)
      const jobIdNum = activeJobId ? parseInt(activeJobId) : null
      setActiveSessionId(sessionIdNum)
      setLoading(true)
      setProgress('Resuming screening...')
      pollScreeningProgress(sessionIdNum, jobIdNum)
    }
  }, [])

  const screenStocks = async (limit) => {
    setLoading(true)
    setProgress('Starting screening...')
    setError(null)
    setStocks([])
    setSummary(null)
    setCurrentPage(1)

    try {
      // Start screening via background job
      const response = await fetch(`${API_BASE}/jobs`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include', // Include session cookie for OAuth
        body: JSON.stringify({
          type: 'full_screening',
          params: {
            algorithm,
            limit,
            force_refresh: false,
            region: 'us' // TODO: Make this configurable via UI
          }
        })
      })

      if (!response.ok) {
        throw new Error(`API returned ${response.status}: ${response.statusText}`)
      }

      const data = await response.json()
      const { session_id, job_id } = data

      // Store session_id in localStorage and state
      localStorage.setItem('activeScreeningSession', session_id)
      if (job_id) {
        localStorage.setItem('activeJobId', job_id)
      }
      setActiveSessionId(session_id)

      setProgress('Screening queued... waiting for worker to start')

      // Start polling for progress (works for both modes - worker updates session table)
      pollScreeningProgress(session_id, job_id)

    } catch (err) {
      console.error('Error starting screening:', err)
      setError(`Failed to start screening: ${err.message}`)
      setLoading(false)
      setProgress('')
    }
  }

  const stopScreening = async () => {
    if (!activeSessionId) return

    try {
      // Try to cancel via job API first if we have a job_id
      const jobId = localStorage.getItem('activeJobId')
      if (jobId) {
        const jobResponse = await fetch(`${API_BASE}/jobs/${jobId}/cancel`, {
          method: 'POST'
        })
        if (jobResponse.ok) {
          setProgress('Screening cancelled')
          setLoading(false)
          setActiveSessionId(null)
          localStorage.removeItem('activeScreeningSession')
          localStorage.removeItem('activeJobId')
          setTimeout(() => setProgress(''), 3000)
          return
        }
      }

      // Fall back to session stop endpoint
      const response = await fetch(`${API_BASE}/screen/stop/${activeSessionId}`, {
        method: 'POST'
      })

      if (response.ok || response.status === 404) {
        const data = await response.json()

        // Handle both successful stop and session-not-found
        if (response.status === 404) {
          // Session doesn't exist (database was likely reset)
          setProgress('Session not found - database may have been reset. Ready to screen.')
        } else {
          setProgress(data.message)
        }

        setLoading(false)
        setActiveSessionId(null)
        localStorage.removeItem('activeScreeningSession')
        localStorage.removeItem('activeJobId')

        // Clear progress after a delay
        setTimeout(() => setProgress(''), 3000)
      } else {
        const data = await response.json()
        setError(`Failed to stop screening: ${data.error || response.statusText}`)
      }
    } catch (err) {
      console.error('Error stopping screening:', err)
      setError(`Failed to stop screening: ${err.message}`)
    }
  }

  const pollScreeningProgress = async (sessionId, jobId = null) => {
    const pollInterval = setInterval(async () => {
      try {
        // If we have a job_id, poll the job endpoint for detailed progress
        if (jobId) {
          const jobResponse = await fetch(`${API_BASE}/jobs/${jobId}`)
          if (jobResponse.ok) {
            const job = await jobResponse.json()

            // Show job progress message if available
            if (job.progress_message) {
              const percent = job.progress_pct || 0
              setProgress(`${job.progress_message} (${percent}%)`)
            } else if (job.status === 'pending') {
              setProgress('Screening queued... waiting for worker')
            } else if (job.status === 'claimed') {
              setProgress('Worker starting...')
            }

            // Check if job completed or failed
            if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') {
              clearInterval(pollInterval)
              setActiveSessionId(null)
              localStorage.removeItem('activeScreeningSession')
              localStorage.removeItem('activeJobId')

              if (job.status === 'completed') {
                // Fetch final results from session
                const resultsResponse = await fetch(`${API_BASE}/screen/results/${sessionId}`)
                if (resultsResponse.ok) {
                  const { results } = await resultsResponse.json()
                  setStocks(results)
                }

                // Build summary from job result
                const result = job.result || {}
                setSummary({
                  totalAnalyzed: result.total_analyzed || 0,
                  strong_buy_count: result.pass_count || 0,
                  buy_count: result.close_count || 0,
                  hold_count: 0,
                  caution_count: 0,
                  avoid_count: result.fail_count || 0,
                  algorithm: 'weighted'
                })
                setProgress('Screening complete!')
              } else if (job.status === 'failed') {
                setError(`Screening failed: ${job.error_message || 'Unknown error'}`)
                setProgress('')
              } else {
                setProgress('Screening cancelled')
              }

              setLoading(false)
              setTimeout(() => setProgress(''), 3000)
              return
            }
          }
        }

        // Also poll session progress endpoint for results
        const progressResponse = await fetch(`${API_BASE}/screen/progress/${sessionId}`)
        if (!progressResponse.ok) {
          // Session might not exist yet if worker hasn't started - don't error out
          if (progressResponse.status !== 404) {
            clearInterval(pollInterval)
            setError('Failed to get screening progress')
            setLoading(false)
          }
          return
        }

        const progress = await progressResponse.json()

        // Update progress message (if not already set by job endpoint)
        if (!jobId) {
          const percent = progress.total_count > 0
            ? Math.round((progress.processed_count / progress.total_count) * 100)
            : 0
          setProgress(`Screening: ${progress.processed_count}/${progress.total_count} (${percent}%) - ${progress.current_symbol || ''}`)
        }

        // Fetch and update results incrementally
        const resultsResponse = await fetch(`${API_BASE}/screen/results/${sessionId}`)
        if (resultsResponse.ok) {
          const { results } = await resultsResponse.json()
          setStocks(results)
        }

        // Check if complete or cancelled (for non-job mode)
        if (!jobId && (progress.status === 'complete' || progress.status === 'cancelled')) {
          clearInterval(pollInterval)

          // Clear active session
          setActiveSessionId(null)
          localStorage.removeItem('activeScreeningSession')

          if (progress.status === 'complete') {
            // Set final summary
            const summaryData = {
              totalAnalyzed: progress.total_analyzed,
              algorithm: progress.algorithm
            }

            if (progress.algorithm === 'classic') {
              summaryData.passCount = progress.pass_count
              summaryData.closeCount = progress.close_count
              summaryData.failCount = progress.fail_count
            } else {
              summaryData.strong_buy_count = progress.pass_count  // Map to new format
              summaryData.buy_count = progress.close_count
              summaryData.hold_count = 0
              summaryData.caution_count = 0
              summaryData.avoid_count = progress.fail_count
            }

            setSummary(summaryData)
            setProgress('Screening complete!')
          } else {
            setProgress('Screening cancelled')
          }

          setLoading(false)

          // Clear progress after a delay
          setTimeout(() => setProgress(''), 3000)
        }

      } catch (err) {
        console.error('Error polling progress:', err)
        clearInterval(pollInterval)
        setError('Lost connection to screening progress')
        setLoading(false)
      }
    }, 5000) // Poll every 5 seconds (reduced from 2s to avoid Fly.io rate limits)
  }

  const getStatusColor = (status) => {
    switch (status) {
      // Classic algorithm statuses
      case 'PASS': return '#4ade80'
      case 'CLOSE': return '#fbbf24'
      case 'FAIL': return '#f87171'
      // New algorithm statuses
      case 'STRONG_BUY': return '#22c55e'
      case 'BUY': return '#4ade80'
      case 'HOLD': return '#fbbf24'
      case 'CAUTION': return '#fb923c'
      case 'AVOID': return '#f87171'
      default: return '#gray'
    }
  }

  const getStatusRank = (status) => {
    switch (status) {
      // Classic algorithm statuses
      case 'PASS': return 1
      case 'CLOSE': return 2
      case 'FAIL': return 3
      default: return 4
    }
  }

  const sortedStocks = useMemo(() => {
    const filtered = stocks.filter(stock => {
      // Apply watchlist filter
      if (filter === 'watchlist' && !watchlist.has(stock.symbol)) {
        return false
      }

      // Apply status filter
      if (filter !== 'all' && filter !== 'watchlist' && stock.overall_status !== filter) {
        return false
      }

      // Search is now handled by backend API - no frontend filter needed

      // Apply advanced filters
      // Region/Country filter
      if (advancedFilters.regions.length > 0 || advancedFilters.countries.length > 0) {
        const stockCountry = stock.country || ''
        let matchesRegion = false

        // Check if stock matches any selected region (using 2-letter country codes)
        const REGION_COUNTRIES = {
          'USA': ['US'],
          'Canada': ['CA'],
          'Central/South America': ['MX', 'BR', 'AR', 'CL', 'PE', 'CO', 'VE', 'EC', 'BO', 'PY', 'UY', 'CR', 'PA', 'GT', 'HN', 'SV', 'NI'],
          'Europe': ['GB', 'DE', 'FR', 'IT', 'ES', 'NL', 'CH', 'IE', 'BE', 'SE', 'NO', 'DK', 'FI', 'AT', 'PL', 'PT', 'GR', 'CZ', 'HU', 'RO', 'LU', 'IS'],
          'Asia': ['CN', 'JP', 'KR', 'IN', 'SG', 'HK', 'TW', 'TH', 'MY', 'ID', 'PH', 'VN', 'IL'],
          'Other': []
        }

        for (const region of advancedFilters.regions) {
          const countriesInRegion = REGION_COUNTRIES[region] || []
          if (countriesInRegion.includes(stockCountry)) {
            matchesRegion = true
            break
          }
        }

        // Check if stock matches any selected country
        const matchesCountry = advancedFilters.countries.includes(stockCountry)

        if (!matchesRegion && !matchesCountry) {
          return false
        }
      }

      // Institutional ownership filter
      if (advancedFilters.institutionalOwnership?.max !== null) {
        const instOwn = stock.institutional_ownership
        if (instOwn === null || instOwn === undefined || instOwn > advancedFilters.institutionalOwnership.max / 100) {
          return false
        }
      }

      // Revenue growth filter
      if (advancedFilters.revenueGrowth.min !== null) {
        const revGrowth = stock.revenue_cagr
        if (revGrowth === null || revGrowth === undefined || revGrowth < advancedFilters.revenueGrowth.min) {
          return false
        }
      }

      // Income growth filter
      if (advancedFilters.incomeGrowth.min !== null) {
        const incGrowth = stock.earnings_cagr
        if (incGrowth === null || incGrowth === undefined || incGrowth < advancedFilters.incomeGrowth.min) {
          return false
        }
      }

      // Debt to equity filter
      if (advancedFilters.debtToEquity.max !== null) {
        const de = stock.debt_to_equity
        if (de === null || de === undefined || de > advancedFilters.debtToEquity.max) {
          return false
        }
      }

      // Market cap filter
      if (advancedFilters.marketCap?.max !== null && advancedFilters.marketCap?.max !== undefined) {
        const mc = stock.market_cap
        if (mc === null || mc === undefined || mc / 1e9 > advancedFilters.marketCap.max) {
          return false
        }
      }

      return true
    })

    const sorted = [...filtered].sort((a, b) => {
      let aVal = a[sortBy]
      let bVal = b[sortBy]

      // Handle null/undefined values
      if (aVal == null && bVal == null) return 0
      if (aVal == null) return 1
      if (bVal == null) return -1

      // Special handling for status columns - use rank instead of alphabetical
      if (sortBy.endsWith('_status') || sortBy === 'overall_status') {
        const ranks = {
          'STRONG_BUY': 1,
          'BUY': 2,
          'HOLD': 3,
          'CAUTION': 4,
          'AVOID': 5,
          'SELL': 6,
          'PASS': 1,
          'CLOSE': 2,
          'FAIL': 3
        }
        aVal = ranks[aVal] || 999
        bVal = ranks[bVal] || 999
      } else if (typeof aVal === 'string') {
        aVal = aVal.toLowerCase()
        bVal = (bVal || '').toLowerCase()
      }

      if (sortDir === 'asc') {
        return aVal < bVal ? -1 : aVal > bVal ? 1 : 0
      } else {
        return aVal > bVal ? -1 : aVal < bVal ? 1 : 0
      }
    })
    return sorted
  }, [stocks, filter, sortBy, sortDir, watchlist, advancedFilters])

  const totalPages = Math.ceil(sortedStocks.length / itemsPerPage)
  const startIndex = (currentPage - 1) * itemsPerPage
  const endIndex = startIndex + itemsPerPage
  const paginatedStocks = sortedStocks.slice(startIndex, endIndex)

  const toggleSort = (column) => {
    if (sortBy === column) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(column)
      setSortDir('asc')
    }
  }

  const handleStockClick = (symbol) => {
    navigate(`/stock/${symbol}`)
  }

  const handleAdvancedFiltersChange = async (newFilters) => {
    setAdvancedFilters(newFilters)

    // Save to database
    try {
      await fetch(`${API_BASE}/settings`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          advanced_filters: {
            value: newFilters,
            description: 'Advanced stock filter settings'
          }
        })
      })
    } catch (err) {
      console.error('Error saving advanced filters:', err)
    }
  }

  const getActiveFilterCount = () => {
    let count = 0
    if (advancedFilters.regions.length > 0) count++
    if (advancedFilters.countries.length > 0) count++
    if (advancedFilters.institutionalOwnership?.max !== null) count++
    if (advancedFilters.revenueGrowth.min !== null) count++
    if (advancedFilters.incomeGrowth.min !== null) count++
    if (advancedFilters.debtToEquity.max !== null) count++
    if (advancedFilters.marketCap?.max !== null) count++
    return count
  }

  return (
    <div className="app stock-list-view">
      <div className="controls">
        {isAdmin && (
          <div className="flex gap-2">
            {activeSessionId ? (
              <button onClick={stopScreening} className="stop-button">
                Stop Screening
              </button>
            ) : (
              <button onClick={() => screenStocks(null)} disabled={loading}>
                Screen All Stocks
              </button>
            )}
          </div>
        )}

        <div className="filter-controls">
          <label>Search: </label>
          <div className="search-container">
            <span className="search-icon">{searchLoading ? '⏳' : '🔍'}</span>
            <input
              type="text"
              className="search-input"
              value={searchQuery}
              onChange={(e) => handleSearchChange(e.target.value)}
              placeholder="Search by symbol or company name..."
            />
            {searchQuery && (
              <button
                className="clear-button"
                onClick={() => handleSearchChange('')}
                aria-label="Clear search"
              >
                ×
              </button>
            )}
          </div>
        </div>

        <div className="filter-controls">
          <label>Filter: </label>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All</option>
            <option value="watchlist">⭐ Watchlist</option>
            {algorithm === 'classic' ? (
              <>
                <option value="PASS">Pass Only</option>
                <option value="CLOSE">Close Only</option>
                <option value="FAIL">Fail Only</option>
              </>
            ) : (
              <>
                <option value="STRONG_BUY">Strong Buy</option>
                <option value="BUY">Buy</option>
                <option value="HOLD">Hold</option>
                <option value="CAUTION">Caution</option>
                <option value="AVOID">Avoid</option>
              </>
            )}
          </select>
        </div>

        {summary && (
          <div className="summary-stats">
            <strong>Analyzed {summary.totalAnalyzed} stocks:</strong>
            {algorithm === 'classic' ? (
              <>
                <span className="summary-stat pass">{summary.passCount || 0} PASS</span>
                <span className="summary-stat close">{summary.closeCount || 0} CLOSE</span>
                <span className="summary-stat fail">{summary.failCount || 0} FAIL</span>
              </>
            ) : (
              <>
                <span className="summary-stat strong-buy">{summary.strong_buy_count || 0} Strong Buy</span>
                <span className="summary-stat buy">{summary.buy_count || 0} Buy</span>
                <span className="summary-stat hold">{summary.hold_count || 0} Hold</span>
                <span className="summary-stat caution">{summary.caution_count || 0} Caution</span>
                <span className="summary-stat avoid">{summary.avoid_count || 0} Avoid</span>
              </>
            )}
          </div>
        )}

        <AlgorithmSelector
          selectedAlgorithm={algorithm}
          onAlgorithmChange={setAlgorithm}
        />

        <button
          onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
          className="filter-button"
          title="Advanced Filters"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon>
          </svg>
          {getActiveFilterCount() > 0 && (
            <span className="filter-badge">{getActiveFilterCount()}</span>
          )}
        </button>

        {isAdmin && (
          <button
            onClick={() => navigate('/tuning')}
            className="settings-button"
            title="Tune Algorithm"
            style={{ marginLeft: '5px' }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="4" y1="21" x2="4" y2="14"></line>
              <line x1="4" y1="10" x2="4" y2="3"></line>
              <line x1="12" y1="21" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12" y2="3"></line>
              <line x1="20" y1="21" x2="20" y2="16"></line>
              <line x1="20" y1="12" x2="20" y2="3"></line>
              <line x1="1" y1="14" x2="7" y2="14"></line>
              <line x1="9" y1="8" x2="15" y2="8"></line>
              <line x1="17" y1="16" x2="23" y2="16"></line>
            </svg>
          </button>
        )}

        <UserAvatar />
      </div>

      {loading && (
        <div className="status-container">
          <div className="loading">
            {progress || 'Loading...'}
          </div>
        </div>
      )}

      {error && (
        <div className="error-message">
          {error}
          <button onClick={() => setError(null)} className="error-dismiss">Dismiss</button>
        </div>
      )}

      <AdvancedFilter
        filters={advancedFilters}
        onFiltersChange={handleAdvancedFiltersChange}
        isOpen={showAdvancedFilters}
        onToggle={() => setShowAdvancedFilters(!showAdvancedFilters)}
      />

      {sortedStocks.length > 0 && (
        <>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th className="watchlist-header">⭐</th>
                  <th onClick={() => toggleSort('symbol')}>Symbol {sortBy === 'symbol' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('company_name')}>Company {sortBy === 'company_name' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('country')}>Country {sortBy === 'country' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('market_cap')}>Market Cap {sortBy === 'market_cap' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('sector')}>Sector {sortBy === 'sector' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('ipo_year')}>Age (Years) {sortBy === 'ipo_year' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('price')}>Price {sortBy === 'price' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th
                    onClick={() => toggleSort('peg_ratio')}
                    title="PEG Ratio = P/E Ratio / 5-Year Earnings Growth Rate. A value under 1.0 is ideal. e.g., A company with a P/E of 20 and 25% earnings growth has a PEG of 0.8 (20 / 25)."
                  >PEG{sortBy === 'peg_ratio' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('pe_ratio')}>P/E {sortBy === 'pe_ratio' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th
                    onClick={() => toggleSort('debt_to_equity')}
                    title="Debt to Equity (D/E) Ratio = Total Liabilities / Shareholder Equity. It shows how much a company relies on debt to finance its assets. A lower ratio is generally better."
                  >D/E{sortBy === 'debt_to_equity' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th
                    onClick={() => toggleSort('institutional_ownership')}
                    title="Institutional Ownership: The percentage of a company's shares held by large organizations like mutual funds, pension funds, insurance companies, and hedge funds."
                  >Inst Own{sortBy === 'institutional_ownership' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('revenue_cagr')}>5Y Rev Growth {sortBy === 'revenue_cagr' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('earnings_cagr')}>5Y Inc Growth {sortBy === 'earnings_cagr' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th onClick={() => toggleSort('dividend_yield')}>Div Yield {sortBy === 'dividend_yield' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                  <th>PEG Status</th>
                  <th>Debt Status</th>
                  <th>Inst Own Status</th>
                  <th onClick={() => toggleSort('overall_status')}>Overall {sortBy === 'overall_status' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                </tr>
              </thead>
              <tbody>
                {paginatedStocks.map(stock => (
                  <tr
                    key={stock.symbol}
                    onClick={() => handleStockClick(stock.symbol)}
                    className="stock-row"
                  >
                    <td className="watchlist-cell" onClick={(e) => { e.stopPropagation(); toggleWatchlist(stock.symbol); }}>
                      <span className={`watchlist-star ${watchlist.has(stock.symbol) ? 'checked' : ''}`}>
                        ⭐
                      </span>
                    </td>
                    <td><strong>{stock.symbol}</strong></td>
                    <td>{stock.company_name || 'N/A'}</td>
                    <td>{stock.country || 'N/A'}</td>
                    <td>{typeof stock.market_cap === 'number' ? `$${(stock.market_cap / 1e9).toFixed(2)}B` : 'N/A'}</td>
                    <td>{stock.sector || 'N/A'}</td>
                    <td>{typeof stock.ipo_year === 'number' ? new Date().getFullYear() - stock.ipo_year : 'N/A'}</td>
                    <td>{typeof stock.price === 'number' ? `$${stock.price.toFixed(2)}` : 'N/A'}</td>
                    <td>{typeof stock.peg_ratio === 'number' ? stock.peg_ratio.toFixed(2) : 'N/A'}</td>
                    <td>{typeof stock.pe_ratio === 'number' ? stock.pe_ratio.toFixed(2) : 'N/A'}</td>
                    <td>{typeof stock.debt_to_equity === 'number' ? stock.debt_to_equity.toFixed(2) : 'N/A'}</td>
                    <td>{typeof stock.institutional_ownership === 'number' ? `${(stock.institutional_ownership * 100).toFixed(1)}%` : 'N/A'}</td>
                    <td>{typeof stock.revenue_cagr === 'number' ? `${stock.revenue_cagr.toFixed(1)}%` : 'N/A'}</td>
                    <td>{typeof stock.earnings_cagr === 'number' ? `${stock.earnings_cagr.toFixed(1)}%` : 'N/A'}</td>
                    <td>{typeof stock.dividend_yield === 'number' ? `${stock.dividend_yield.toFixed(1)}%` : 'N/A'}</td>
                    <td>
                      <StatusBar
                        status={stock.peg_status}
                        score={stock.peg_score || 0}
                        value={stock.peg_ratio}
                        metricType="peg"
                      />
                    </td>
                    <td>
                      <StatusBar
                        status={stock.debt_status}
                        score={stock.debt_score || 0}
                        value={stock.debt_to_equity}
                        metricType="debt"
                      />
                    </td>
                    <td>
                      <StatusBar
                        status={stock.institutional_ownership_status}
                        score={stock.institutional_ownership_score || 0}
                        value={stock.institutional_ownership}
                        metricType="institutional"
                      />
                    </td>
                    <td style={{ backgroundColor: getStatusColor(stock.overall_status), color: '#000', fontWeight: 'bold' }}>
                      {stock.overall_status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="pagination-info">
            Showing {startIndex + 1}-{Math.min(endIndex, sortedStocks.length)} of {sortedStocks.length} stocks
          </div>

          {totalPages > 1 && (
            <div className="pagination">
              <button
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
              >
                Previous
              </button>
              <span className="page-info">
                Page {currentPage} of {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}

      {loadingSession && (
        <div className="status-container">
          <div className="loading">
            Loading previous screening results...
          </div>
        </div>
      )}

      {!loadingSession && !loading && sortedStocks.length === 0 && stocks.length === 0 && (
        <div className="empty-state">
          No stocks loaded. Click "Screen Stocks" to begin.
        </div>
      )}

      {!loading && sortedStocks.length === 0 && stocks.length > 0 && (
        <div className="empty-state">
          No stocks match the current {searchQuery ? 'search and filter' : 'filter'}.
        </div>
      )}
    </div>
  )
}

function App() {
  const { user, loading } = useAuth()
  const [stocks, setStocks] = useState([])
  const [summary, setSummary] = useState(null)
  const [filter, setFilter] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [sortBy, setSortBy] = useState('overall_status')
  const [sortDir, setSortDir] = useState('asc')
  const [watchlist, setWatchlist] = useState(new Set())
  const [algorithm, setAlgorithm] = useState('weighted')

  // Load watchlist on mount
  useEffect(() => {
    if (!user) return

    const controller = new AbortController()
    const signal = controller.signal

    const loadWatchlist = async () => {
      try {
        const response = await fetch(`${API_BASE}/watchlist`, {
          signal,
          credentials: 'include'
        })
        if (response.ok) {
          const data = await response.json()
          setWatchlist(new Set(data.symbols))
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Error loading watchlist:', err)
        }
      }
    }
    loadWatchlist()

    return () => controller.abort()
  }, [user])

  const toggleWatchlist = async (symbol) => {
    const isInWatchlist = watchlist.has(symbol)

    try {
      if (isInWatchlist) {
        await fetch(`${API_BASE}/watchlist/${symbol}`, {
          method: 'DELETE',
          credentials: 'include'
        })
        setWatchlist(prev => {
          const newSet = new Set(prev)
          newSet.delete(symbol)
          return newSet
        })
      } else {
        await fetch(`${API_BASE}/watchlist/${symbol}`, {
          method: 'POST',
          credentials: 'include'
        })
        setWatchlist(prev => new Set([...prev, symbol]))
      }
    } catch (err) {
      console.error('Error toggling watchlist:', err)
    }
  }

  // Show login modal if not authenticated
  if (loading) {
    return <div className="flex items-center justify-center h-screen">Loading...</div>
  }

  if (!user) {
    return <LoginModal />
  }

  return (
    <Routes>
      <Route path="/" element={
        <StockListView
          stocks={stocks}
          setStocks={setStocks}
          summary={summary}
          setSummary={setSummary}
          filter={filter}
          setFilter={setFilter}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          currentPage={currentPage}
          setCurrentPage={setCurrentPage}
          sortBy={sortBy}
          setSortBy={setSortBy}
          sortDir={sortDir}
          setSortDir={setSortDir}
          watchlist={watchlist}
          toggleWatchlist={toggleWatchlist}
          algorithm={algorithm}
          setAlgorithm={setAlgorithm}
        />
      } />
      <Route path="/stock/:symbol" element={
        <StockDetail
          watchlist={watchlist}
          toggleWatchlist={toggleWatchlist}
        />
      } />


      <Route path="/tuning" element={<AlgorithmTuning />} />
    </Routes>
  )
}

export default App
