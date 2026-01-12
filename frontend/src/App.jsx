import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import { Routes, Route, useNavigate, useSearchParams } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
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
import StockDetail from './pages/StockDetail'
import StockHeader from './components/StockHeader'
import StockListCard from './components/StockListCard'


import AlgorithmTuning from './pages/AlgorithmTuning'
import LoginModal from './components/LoginModal'
import AdvancedFilter from './components/AdvancedFilter'
import SearchPopover from './components/SearchPopover'
import { useAuth } from './context/AuthContext'
import UserAvatar from './components/UserAvatar'
import Settings from './pages/Settings'
import Alerts from './pages/Alerts'
// import './App.css' // Disabled for shadcn migration

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
)

const API_BASE = '/api'

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
  algorithm, setAlgorithm,
  algorithms,
  showAdvancedFilters, setShowAdvancedFilters,
  activeCharacter, setActiveCharacter
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
          setTotalPages(sessionData.total_pages || 1)
          setTotalCount(sessionData.total_count || 0)

          // Capture active character from API
          if (sessionData.active_character) {
            setActiveCharacter(sessionData.active_character)
          }

          // Use status_counts from API (counts for full session, not just current page)
          const counts = sessionData.status_counts || {}

          // Check if we have new algorithm statuses or old ones
          const hasNewStatuses = counts['STRONG_BUY'] !== undefined || counts['BUY'] !== undefined ||
            counts['HOLD'] !== undefined || counts['AVOID'] !== undefined

          if (hasNewStatuses) {
            // New algorithm statuses
            setSummary({
              totalAnalyzed: sessionData.total_count || results.length,
              strong_buy_count: counts['STRONG_BUY'] || 0,
              buy_count: counts['BUY'] || 0,
              hold_count: counts['HOLD'] || 0,
              caution_count: counts['CAUTION'] || 0,
              avoid_count: counts['AVOID'] || 0,
              algorithm: 'weighted'
            })
          } else {
            // Old algorithm statuses (classic)
            setSummary({
              totalAnalyzed: sessionData.total_count || results.length,
              passCount: counts['PASS'] || 0,
              closeCount: counts['CLOSE'] || 0,
              failCount: counts['FAIL'] || 0,
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

  // State for backend pagination
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)

  // Fetch stocks from backend with all parameters
  const fetchStocks = useCallback((options = {}) => {
    const {
      search = searchQuery,
      page = currentPage,
      sort = sortBy,
      dir = sortDir,
      showLoading = true
    } = options

    if (showLoading) {
      setSearchLoading(true)
    }

    const params = new URLSearchParams()
    if (search) params.set('search', search)
    params.set('page', page)
    params.set('limit', itemsPerPage)
    params.set('sort_by', sort)
    params.set('sort_dir', dir)

    const url = `${API_BASE}/sessions/latest?${params.toString()}`

    return fetch(url)
      .then(response => response.json())
      .then(data => {
        if (data.results) {
          setStocks(data.results)
          setTotalPages(data.total_pages || 1)
          setTotalCount(data.total_count || 0)
        }
        if (data.active_character) {
          setActiveCharacter(data.active_character)
        }
        return data
      })
      .catch(err => console.error('Error fetching stocks:', err))
      .finally(() => setSearchLoading(false))
  }, [searchQuery, currentPage, sortBy, sortDir, setStocks, setActiveCharacter])


  // Watchlist fetching logic
  const prevFilterRef = useRef(filter)
  useEffect(() => {
    const prevFilter = prevFilterRef.current

    // If switching to watchlist, fetch watchlist items manually
    if (filter === 'watchlist') {
      const fetchWatchlistItems = async () => {
        setLoading(true)
        setProgress('Loading watchlist...')

        try {
          if (watchlist.size === 0) {
            setStocks([])
            setLoading(false)
            setProgress('')
            return
          }

          const promises = Array.from(watchlist).map(async symbol => {
            try {
              const res = await fetch(`${API_BASE}/stock/${symbol}?algorithm=${algorithm}`)
              if (!res.ok) return null
              const data = await res.json()
              // Flatten structure to match session results
              if (data.stock_data && data.evaluation) {
                return {
                  ...data.stock_data,
                  ...data.evaluation,
                  // Ensure symbol is present
                  symbol: data.stock_data.symbol || symbol
                }
              }
              return null
            } catch (e) {
              console.error(`Failed to fetch ${symbol}`, e)
              return null
            }
          })

          const results = (await Promise.all(promises)).filter(item => item !== null)

          setStocks(results)
          setTotalPages(1) // Watchlist is single page for now
          setTotalCount(results.length)
        } catch (e) {
          console.error('Error fetching watchlist:', e)
          setError('Failed to load watchlist items')
        } finally {
          setLoading(false)
          setProgress('')
        }
      }

      fetchWatchlistItems()
    }
    // If switching FROM watchlist back to other filters, reload session data
    else if (prevFilter === 'watchlist' && filter !== 'watchlist') {
      setStocks([]) // Clear stale watchlist items immediately
      fetchStocks({ page: 1 })
      setCurrentPage(1)
    }

    prevFilterRef.current = filter
  }, [filter, watchlist, algorithm, fetchStocks])

  // Debounced search handler - calls backend API after delay
  const handleSearchChange = useCallback((value) => {
    setSearchQuery(value)
    setCurrentPage(1) // Reset to first page on new search

    // Clear previous debounce timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }

    // If search is cleared, reload immediately
    if (!value.trim()) {
      fetchStocks({ search: '', page: 1 })
      return
    }

    // Set debounce timer for search
    debounceTimerRef.current = setTimeout(() => {
      fetchStocks({ search: value, page: 1 })
    }, 200) // 200ms debounce
  }, [setSearchQuery, setCurrentPage, fetchStocks])

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

  const formatStatusName = (status) => {
    const statusMap = {
      'STRONG_BUY': 'Excellent',
      'BUY': 'Good',
      'HOLD': 'Fair',
      'CAUTION': 'Weak',
      'AVOID': 'Poor',
      'PASS': 'Pass',
      'CLOSE': 'Close',
      'FAIL': 'Fail'
    }
    return statusMap[status] || status
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

  const filteredStocks = useMemo(() => {
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
      // EXCEPT for watchlist mode which is client-side
      if (filter === 'watchlist' && searchQuery) {
        const query = searchQuery.toLowerCase()
        const symbol = stock.symbol || ''
        const name = stock.company_name || stock.company || ''
        const matchesSymbol = symbol.toLowerCase().includes(query)
        const matchesName = name.toLowerCase().includes(query)
        if (!matchesSymbol && !matchesName) {
          return false
        }
      }

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
    return filtered  // No frontend sorting - backend handles it
  }, [stocks, filter, watchlist, advancedFilters])

  // Use backend pagination - stocks already come paginated and sorted
  // Note: totalPages comes from the API response and is set in fetchStocks

  const toggleSort = (column) => {
    const newDir = sortBy === column ? (sortDir === 'asc' ? 'desc' : 'asc') : 'desc'
    const newSortBy = column

    setSortBy(newSortBy)
    setSortDir(newDir)
    setCurrentPage(1) // Reset to first page on sort change

    // Fetch with new sort params
    fetchStocks({ sort: newSortBy, dir: newDir, page: 1 })
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
    <div className="flex flex-col h-full">
      {/* Controls bar */}
      <div className="mb-4">
        <div className="flex flex-wrap items-center gap-4">
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

          {/* Summary badges - removed as they are now in the sidebar */}

          {/* Advanced Filters Button and Count moved to Header */}

          {isAdmin && (
            <button
              onClick={() => navigate('/tuning')}
              className="settings-button ml-1"
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
        </div>
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

      {filteredStocks.length > 0 && (
        <>
          <div className="space-y-3 pb-4">
            {filteredStocks.map(stock => (
              <StockListCard
                key={stock.symbol}
                stock={stock}
                toggleWatchlist={toggleWatchlist}
                watchlist={watchlist}
                activeCharacter={activeCharacter}
              />
            ))}
          </div>

          <div className="flex items-center justify-center gap-4 py-4">
            {totalPages > 1 && (
              <button
                onClick={() => {
                  const newPage = Math.max(1, currentPage - 1)
                  setCurrentPage(newPage)
                  fetchStocks({ page: newPage })
                }}
                disabled={currentPage === 1 || searchLoading}
                className="px-4 py-2 text-sm font-medium border rounded-md bg-background hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>
            )}
            <span className="text-sm text-muted-foreground">
              Page {currentPage} of {totalPages}
            </span>
            {totalPages > 1 && (
              <button
                onClick={() => {
                  const newPage = Math.min(totalPages, currentPage + 1)
                  setCurrentPage(newPage)
                  fetchStocks({ page: newPage })
                }}
                disabled={currentPage === totalPages || searchLoading}
                className="px-4 py-2 text-sm font-medium border rounded-md bg-background hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            )}
          </div>
        </>
      )}

      {loadingSession && (
        <div className="status-container">
          <div className="loading">
            Loading previous screening results...
          </div>
        </div>
      )}

      {!loadingSession && !loading && filteredStocks.length === 0 && stocks.length === 0 && (
        <div className="empty-state">
          No stocks loaded. Click "Screen Stocks" to begin.
        </div>
      )}

      {!loading && filteredStocks.length === 0 && stocks.length > 0 && (
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
  const [sortBy, setSortBy] = useState('overall_score')
  const [sortDir, setSortDir] = useState('desc')
  const [watchlist, setWatchlist] = useState(new Set())
  const [algorithm, setAlgorithm] = useState('weighted')
  const [algorithms, setAlgorithms] = useState({})
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false)
  const [activeCharacter, setActiveCharacter] = useState('lynch')

  // Fetch algorithm metadata
  useEffect(() => {
    const controller = new AbortController()
    // Fetch algorithm metadata from API
    fetch(`${API_BASE}/algorithms`, { signal: controller.signal, credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        setAlgorithms(data)
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          console.error('Error fetching algorithms:', err)
        }
      })
    return () => controller.abort()
  }, [])

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
      <Route element={
        <AppShell
          filter={filter}
          setFilter={setFilter}
          algorithm={algorithm}
          setAlgorithm={setAlgorithm}
          algorithms={algorithms}
          summary={summary}
          watchlistCount={watchlist.size}
          showAdvancedFilters={showAdvancedFilters}
          setShowAdvancedFilters={setShowAdvancedFilters}
        />
      }>
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
            algorithms={algorithms}
            showAdvancedFilters={showAdvancedFilters}
            setShowAdvancedFilters={setShowAdvancedFilters}
            activeCharacter={activeCharacter}
            setActiveCharacter={setActiveCharacter}
          />
        } />
        <Route path="/stock/:symbol" element={
          <StockDetail
            watchlist={watchlist}
            toggleWatchlist={toggleWatchlist}
            algorithm={algorithm}
            algorithms={algorithms}
            activeCharacter={activeCharacter}
          />
        } />
        <Route path="/tuning" element={<AlgorithmTuning />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/alerts" element={<Alerts />} />
      </Route>
    </Routes>
  )
}

export default App
