import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import { Routes, Route, useNavigate, useSearchParams, useLocation, Navigate } from 'react-router-dom'
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
import LoginPage from './pages/LoginPage'

import AdvancedFilter from './components/AdvancedFilter'
import SearchPopover from './components/SearchPopover'
import { useAuth } from './context/AuthContext'
import UserAvatar from './components/UserAvatar'
import Settings from './pages/Settings'
import Alerts from './pages/Alerts'
import Economy from './pages/Economy'
import Portfolios from './pages/Portfolios'
import Strategies from './pages/Strategies'
import StrategyDetail from './pages/StrategyDetail'
import { screeningCache } from './utils/cache'
import Help from './pages/Help'
import Dashboard from './pages/Dashboard'
import { OnboardingWizard } from './components/OnboardingWizard'
import EarningsCalendarPage from './pages/EarningsCalendarPage'
// import './App.css' // Disabled for shadcn migration
import { useTheme } from './components/theme-provider'

// Admin Components
import AdminLayout from './layouts/AdminLayout'
import RequireAdmin from './components/RequireAdmin'
import AdminConversations from './pages/admin/AdminConversations'
import AdminStrategies from './pages/admin/AdminStrategies'
import AdminPortfolios from './pages/admin/AdminPortfolios'
import AdminUserActions from './pages/admin/AdminUserActions'
import AdminJobStats from './pages/admin/AdminJobStats'

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
  allStocks, setAllStocks,
  summary, setSummary,
  filter, setFilter,
  searchQuery, setSearchQuery,
  currentPage, setCurrentPage,
  sortBy, setSortBy,
  sortDir, setSortDir,
  watchlist, toggleWatchlist,
  algorithm, setAlgorithm,
  showAdvancedFilters, setShowAdvancedFilters,
  advancedFilters, setAdvancedFilters,
  usStocksOnly, setUsStocksOnly,
  activeCharacter, setActiveCharacter,
  user
}) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const isAdmin = searchParams.get('user') === 'admin'
  const [loading, setLoading] = useState(false)
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [progress, setProgress] = useState('')
  const [error, setError] = useState(null)
  const itemsPerPage = 100


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

      // Safety check: Don't client-side re-evaluate huge lists to prevent browser hang/rate limits
      if (stocks.length > 200) {
        console.warn('Skipping client-side re-evaluation for large dataset (>200 items). Please run a new screen.')
        // Optionally we could force a refresh or show a toast, but for now just skip to prevent crash
        return
      }

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
          algorithm: algorithm,
          strong_buy_count: statusCounts['STRONG_BUY'] || 0,
          buy_count: statusCounts['BUY'] || 0,
          hold_count: statusCounts['HOLD'] || 0,
          caution_count: statusCounts['CAUTION'] || 0,
          avoid_count: statusCounts['AVOID'] || 0
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



  // Start with empty state (don't load cached session since algorithm may have changed)
  const [loadingSession, setLoadingSession] = useState(stocks.length === 0 && !summary)
  // Load latest session on mount AND when character changes
  useEffect(() => {
    // Always load session data when component mounts or character changes
    // The key={activeCharacter} on StockListView ensures this runs on character switch

    const controller = new AbortController()
    const signal = controller.signal

    const loadLatestSession = async () => {
      try {
        // Try to load from cache first
        if (user && user.id && activeCharacter) {
          const cachedData = await screeningCache.getResults(user.id, activeCharacter)
          if (cachedData) {
            setStocks(cachedData.results)
            setAllStocks(cachedData.results)
            setTotalPages(cachedData.total_pages || 1)
            setTotalCount(cachedData.total_count || 0)

            // Reconstruct summary from cached data status counts
            updateSummaryFromData(cachedData)

            setLoadingSession(false)
            return // Skip network fetch
          }
        }

        const response = await fetch(`${API_BASE}/sessions/latest?limit=10000&character=${activeCharacter}`, { signal })

        if (response.ok) {
          const sessionData = await response.json()
          const results = sessionData.results || []

          setStocks(results)
          setAllStocks(results)
          setTotalPages(sessionData.total_pages || 1)
          setTotalCount(sessionData.total_count || 0)


          updateSummaryFromData(sessionData)

          // Cache the fresh results
          if (user && user.id) {
            const charId = sessionData.active_character || activeCharacter || 'lynch'
            screeningCache.saveResults(user.id, charId, sessionData)
          }

        } else if (response.status === 404) {
          // No sessions yet, this is okay
          setStocks([])
          setAllStocks([])
          setSummary(null)
        } else {
          throw new Error(`Failed to load session: ${response.status}`)
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Error loading latest session:', err)
          // Don't show error to user on initial load, just start with empty state
          setStocks([])
          setAllStocks([])
          setSummary(null)
        }
      } finally {
        if (!signal.aborted) {
          setLoadingSession(false)
        }
      }
    }

    // Helper to update summary state from session data
    const updateSummaryFromData = (data) => {
      const results = data.results || []
      const counts = data.status_counts || {}

      setSummary({
        totalAnalyzed: data.total_count || results.length,
        strong_buy_count: counts['STRONG_BUY'] || 0,
        buy_count: counts['BUY'] || 0,
        hold_count: counts['HOLD'] || 0,
        caution_count: counts['CAUTION'] || 0,
        avoid_count: counts['AVOID'] || 0,
        algorithm: 'weighted'
      })
    }

    loadLatestSession()

    return () => controller.abort()
  }, [user, activeCharacter])

  // State for backend pagination
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)


  // Watchlist fetching logic
  // Watchlist fetching logic
  const prevFilterRef = useRef(filter)
  useEffect(() => {
    const prevFilter = prevFilterRef.current
    const controller = new AbortController()
    const signal = controller.signal

    // If switching to watchlist, fetch watchlist items manually
    if (filter === 'watchlist') {
      const fetchWatchlistItems = async () => {
        setLoading(true)
        setProgress('Loading watchlist...')

        try {
          if (watchlist.size === 0) {
            if (!signal.aborted) {
              setStocks([])
              setLoading(false)
              setProgress('')
            }
            return
          }

          const symbols = Array.from(watchlist)
          const res = await fetch(`${API_BASE}/stocks/batch`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              symbols: symbols,
              algorithm: algorithm
            }),
            signal // effective cancellation
          })

          if (res.ok) {
            const data = await res.json()
            if (!signal.aborted) {
              setStocks(data.results || [])
              setTotalPages(1)
              setTotalCount(data.results?.length || 0)
            }
          } else {
            console.error('Batch fetch failed', res.status)
            if (!signal.aborted) setError('Failed to load watchlist items')
          }
        } catch (e) {
          if (e.name !== 'AbortError') {
            console.error('Error fetching watchlist:', e)
            if (!signal.aborted) setError('Failed to load watchlist items')
          }
        } finally {
          if (!signal.aborted) {
            setLoading(false)
            setProgress('')
          }
        }
      }

      fetchWatchlistItems()
    }
    // If switching FROM watchlist back to other filters, OR changing status filter
    else if (filter !== 'watchlist') {
      // Force cleanup of any lingering loading state from quick switches
      setLoading(false)
      setProgress('')

      // If we were on watchlist (or accidentally empty), restore from master list
      if (prevFilter === 'watchlist' || (stocks.length === 0 && allStocks.length > 0)) {
        setStocks(allStocks)
      }
      // All stocks are loaded client-side, no need to fetch

      setCurrentPage(1)
    }

    prevFilterRef.current = filter

    return () => controller.abort()
  }, [filter, watchlist, algorithm, allStocks])

  // Debounced search handler - calls backend API after delay
  // Client-side search handler
  const handleSearchChange = useCallback((value) => {
    setSearchQuery(value)
    setCurrentPage(1) // Reset to first page
  }, [setSearchQuery, setCurrentPage])

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
              algorithm: progress.algorithm,
              strong_buy_count: progress.pass_count || 0,
              buy_count: progress.close_count || 0,
              hold_count: 0,
              caution_count: 0,
              avoid_count: progress.fail_count || 0
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



  // Use backend pagination - stocks already come paginated and sorted
  // Note: totalPages comes from the API response and is set in fetchStocks

  // Client-side Filtering & Sorting
  const processedStocks = useMemo(() => {
    let result = [...stocks]

    // Watchlist filter
    if (filter === 'watchlist') {
      result = result.filter(s => watchlist.has(s.symbol))
    }
    // Status filter
    else if (filter !== 'all') {
      result = result.filter(s => s.overall_status === filter)
    }

    // Search filter
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      result = result.filter(s =>
        s.symbol.toLowerCase().includes(q) ||
        (s.company_name && s.company_name.toLowerCase().includes(q))
      )
    }

    // Advanced filters (Country)
    if (advancedFilters.countries.length > 0) {
      result = result.filter(stock => {
        const stockCountry = stock.country || ''
        return advancedFilters.countries.includes(stockCountry)
      })
    }
    // Institutional ownership
    if (advancedFilters.institutionalOwnership?.max !== null && advancedFilters.institutionalOwnership?.max !== undefined) {
      result = result.filter(s => s.institutional_ownership <= advancedFilters.institutionalOwnership.max / 100)
    }
    // Revenue Growth
    if (advancedFilters.revenueGrowth?.min !== null && advancedFilters.revenueGrowth?.min !== undefined) {
      result = result.filter(s => s.revenue_cagr >= advancedFilters.revenueGrowth.min)
    }
    // Income Growth
    if (advancedFilters.incomeGrowth?.min !== null && advancedFilters.incomeGrowth?.min !== undefined) {
      result = result.filter(s => s.earnings_cagr >= advancedFilters.incomeGrowth.min)
    }
    // Debt/Equity
    if (advancedFilters.debtToEquity?.max !== null && advancedFilters.debtToEquity?.max !== undefined) {
      result = result.filter(s => s.debt_to_equity <= advancedFilters.debtToEquity.max)
    }
    // Market Cap
    if (advancedFilters.marketCap?.max !== null && advancedFilters.marketCap?.max !== undefined) {
      result = result.filter(s => (s.market_cap / 1e9) <= advancedFilters.marketCap.max)
    }
    // P/E Ratio
    if (advancedFilters.peRatio?.max !== null && advancedFilters.peRatio?.max !== undefined) {
      result = result.filter(s => s.pe_ratio <= advancedFilters.peRatio.max)
    }


    return result
  }, [stocks, filter, searchQuery, sortBy, sortDir, advancedFilters, watchlist])

  // Pagination Slice
  const visibleStocks = useMemo(() => {
    const start = (currentPage - 1) * itemsPerPage
    return processedStocks.slice(start, start + itemsPerPage)
  }, [processedStocks, currentPage])

  // Update counts
  useEffect(() => {
    setTotalPages(Math.ceil(processedStocks.length / itemsPerPage) || 1)
    setTotalCount(processedStocks.length)
    if (currentPage > Math.ceil(processedStocks.length / itemsPerPage)) {
      setCurrentPage(1)
    }
  }, [processedStocks.length])

  const toggleSort = (column) => {
    const newDir = sortBy === column ? (sortDir === 'asc' ? 'desc' : 'asc') : 'desc'
    setSortBy(column)
    setSortDir(newDir)
    setCurrentPage(1)
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
    if (advancedFilters.revenueGrowth?.min !== null) count++
    if (advancedFilters.incomeGrowth?.min !== null) count++
    if (advancedFilters.debtToEquity?.max !== null) count++
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
        usStocksOnly={usStocksOnly}
      />

      {visibleStocks.length > 0 && (
        <>
          <div className="space-y-3 pb-4">
            {visibleStocks.map(stock => (
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

      {!loadingSession && !loading && stocks.length === 0 && (
        <div className="empty-state">
          No stocks loaded. Click "Screen Stocks" to begin.
        </div>
      )}

      {!loading && processedStocks.length === 0 && stocks.length > 0 && (
        <div className="empty-state">
          No stocks match the current {searchQuery ? 'search and filter' : 'filter'}.
        </div>
      )}
    </div>
  )
}

function App() {
  const { user, loading, checkAuth } = useAuth()
  const { setTheme, syncTheme } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const [stocks, setStocks] = useState([])
  const [allStocks, setAllStocks] = useState([]) // Master list of all stocks for the session
  const [summary, setSummary] = useState(null)
  const [filter, setFilter] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [sortBy, setSortBy] = useState('overall_score')
  const [sortDir, setSortDir] = useState('desc')
  const [watchlist, setWatchlist] = useState(new Set())
  const [algorithm, setAlgorithm] = useState('weighted')
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false)
  const [usStocksOnly, setUsStocksOnly] = useState(true) // Default to true
  // Advanced filters state lifted from StockListView
  const [advancedFilters, setAdvancedFilters] = useState({
    countries: [],
    institutionalOwnership: { max: null },
    revenueGrowth: { min: null },
    incomeGrowth: { min: null },
    debtToEquity: { max: null },
    marketCap: { max: null },
    peRatio: { max: null }
  })
  const [featureFlags, setFeatureFlags] = useState({
    alertsEnabled: false,
    economyLinkEnabled: false,
    dashboardEnabled: false,
    redditEnabled: false
  })

  // Load all settings on mount
  useEffect(() => {
    const controller = new AbortController()
    const signal = controller.signal

    const loadSettings = async () => {
      try {
        const response = await fetch(`${API_BASE}/settings`, { signal })
        if (response.ok) {
          const settings = await response.json()

          // Load advanced filters defaults
          if (settings.advanced_filters && settings.advanced_filters.value) {
            setAdvancedFilters(prev => ({ ...prev, ...settings.advanced_filters.value }))
          }

          // Load us_stocks_only setting
          if (settings.us_stocks_only && settings.us_stocks_only.value !== undefined) {
            setUsStocksOnly(settings.us_stocks_only.value)
          }

          // Load user theme
          if (settings.user_theme) {
            syncTheme(settings.user_theme)
          }

          // Load feature flags
          setFeatureFlags({
            alertsEnabled: settings.feature_alerts_enabled?.value === true,
            economyLinkEnabled: settings.feature_economy_link_enabled?.value === true,
            dashboardEnabled: settings.feature_dashboard_enabled?.value === true,
            redditEnabled: settings.feature_reddit_enabled?.value === true || settings.feature_reddit_enabled?.value === 'true'
          })
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Error loading settings:', err)
        }
      }
    }

    loadSettings()

    return () => controller.abort()
  }, [])

  const [activeCharacter, setActiveCharacter] = useState(() => localStorage.getItem('activeCharacter') || 'lynch')
  const [showOnboarding, setShowOnboarding] = useState(false)

  // Sync activeCharacter from localStorage on navigation (e.g., coming back from Settings)
  useEffect(() => {
    const storedCharacter = localStorage.getItem('activeCharacter')
    if (storedCharacter && storedCharacter !== activeCharacter) {
      // Clear stocks immediately to prevent flash of old character's data
      setStocks([])
      setAllStocks([])
      setSummary(null)
      setActiveCharacter(storedCharacter)
    }
  }, [location.pathname, activeCharacter, setStocks, setAllStocks, setSummary])

  // Persist activeCharacter
  useEffect(() => {
    localStorage.setItem('activeCharacter', activeCharacter)
  }, [activeCharacter])

  // Listen for character changes from Settings page
  useEffect(() => {
    const handleStorageChange = (e) => {
      if (e.key === 'activeCharacter' && e.newValue !== activeCharacter) {
        setActiveCharacter(e.newValue)
      }
    }

    // Listen for storage events from other tabs/windows
    window.addEventListener('storage', handleStorageChange)

    // Also listen for custom event from same tab (Settings page)
    const handleCustomCharacterChange = (e) => {
      setActiveCharacter(e.detail.character)
    }
    window.addEventListener('characterChanged', handleCustomCharacterChange)

    return () => {
      window.removeEventListener('storage', handleStorageChange)
      window.removeEventListener('characterChanged', handleCustomCharacterChange)
    }
  }, [activeCharacter])

  // Check for first visit and show onboarding wizard
  useEffect(() => {
    if (!user || loading) return

    if (!user.has_completed_onboarding) {
      setShowOnboarding(true)
    }
  }, [user, loading])


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
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  return (
    <>
      <OnboardingWizard
        open={showOnboarding}
        onComplete={() => setShowOnboarding(false)}
        onSkip={() => setShowOnboarding(false)}
      />

      <Routes>

        {/* Admin Routes */}
        <Route element={<RequireAdmin />}>
          <Route element={<AdminLayout />}>
            <Route path="/admin" element={<AdminJobStats />} />
            <Route path="/admin/conversations" element={<AdminConversations />} />
            <Route path="/admin/strategies" element={<AdminStrategies />} />
            <Route path="/admin/portfolios" element={<AdminPortfolios />} />
            <Route path="/admin/user_actions" element={<AdminUserActions />} />
          </Route>
        </Route>

        <Route element={
          <AppShell
            filter={filter}
            setFilter={setFilter}
            algorithm={algorithm}
            setAlgorithm={setAlgorithm}
            summary={summary}
            watchlistCount={watchlist.size}
            featureFlags={featureFlags}
            showAdvancedFilters={showAdvancedFilters}
            setShowAdvancedFilters={setShowAdvancedFilters}
            advancedFilters={advancedFilters}
            setAdvancedFilters={setAdvancedFilters}
            usStocksOnly={usStocksOnly}
            setUsStocksOnly={setUsStocksOnly}
            activeCharacter={activeCharacter}
          />
        }>
          <Route path="/" element={
            <StockListView
              key={activeCharacter} // Force remount when character changes
              stocks={stocks}
              setStocks={setStocks}
              allStocks={allStocks}
              setAllStocks={setAllStocks}
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
              featureFlags={featureFlags}
              showAdvancedFilters={showAdvancedFilters}
              setShowAdvancedFilters={setShowAdvancedFilters}
              advancedFilters={advancedFilters}
              setAdvancedFilters={setAdvancedFilters}
              usStocksOnly={usStocksOnly}
              setUsStocksOnly={setUsStocksOnly}
              activeCharacter={activeCharacter}
              setActiveCharacter={setActiveCharacter}
              user={user}
            />
          } />
          <Route path="/stocks" element={<Navigate to="/" replace />} />
          <Route path="/earnings" element={<EarningsCalendarPage />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/stock/:symbol" element={
            <StockDetail
              watchlist={watchlist}
              toggleWatchlist={toggleWatchlist}
              algorithm={algorithm}
              activeCharacter={activeCharacter}
            />
          } />
          <Route path="/tuning" element={<AlgorithmTuning />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/portfolios" element={<Portfolios />} />
          <Route path="/portfolios/:id" element={<Portfolios />} />
          <Route path="/strategies" element={<Strategies />} />
          <Route path="/strategies/:id" element={<StrategyDetail />} />
          <Route path="/economy" element={<Economy />} />
          <Route path="/help" element={<Help />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}

export default App
