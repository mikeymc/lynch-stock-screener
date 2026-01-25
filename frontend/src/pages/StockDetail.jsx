// ABOUTME: Stock detail page with sticky header and tabbed content
// ABOUTME: Displays charts, reports, analysis, and chat for a specific stock

import { useState, useEffect } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import StockCharts from '../components/StockCharts'
import StockHeader from '../components/StockHeader'
import StockOverview from '../components/StockOverview'
import StockReports from '../components/StockReports'
import AnalysisChat from '../components/AnalysisChat'
import ErrorBoundary from '../components/ErrorBoundary'
import DCFAnalysis from '../components/DCFAnalysis'
import StockNews from '../components/StockNews'
import MaterialEvents from '../components/MaterialEvents'
import WallStreetSentiment from '../components/WallStreetSentiment'
import BusinessHealth from '../components/BusinessHealth'
import TranscriptViewer from '../components/TranscriptViewer'
import WordOnTheStreet from '../components/WordOnTheStreet'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from "@/components/ui/card"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

const API_BASE = '/api'

export default function StockDetail({ watchlist, toggleWatchlist, algorithm, activeCharacter }) {
  const { symbol } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [stock, setStock] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  // Read active tab from URL, default to 'overview'
  const activeTab = searchParams.get('tab') || 'overview'
  const [periodType, setPeriodType] = useState('annual')
  // Data state
  const [historyData, setHistoryData] = useState(null)
  const [quarterlyHistoryData, setQuarterlyHistoryData] = useState(null)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [filingsData, setFilingsData] = useState(null)
  const [loadingFilings, setLoadingFilings] = useState(false)
  const [sectionsData, setSectionsData] = useState(null)
  const [loadingSections, setLoadingSections] = useState(false)
  const [newsData, setNewsData] = useState(null)
  const [loadingNews, setLoadingNews] = useState(false)
  const [materialEventsData, setMaterialEventsData] = useState(null)
  const [loadingMaterialEvents, setLoadingMaterialEvents] = useState(false)

  // Comments state for inline commenting feature
  const [comments, setComments] = useState([])
  const [isReviewingComments, setIsReviewingComments] = useState(false)

  // Feature flags
  const [redditEnabled, setRedditEnabled] = useState(false)

  // Handler to add a new comment
  const handleAddComment = (comment) => {
    setComments(prev => [...prev, { ...comment, id: Date.now() }])
  }

  // Handler to clear all comments
  const handleClearComments = () => {
    setComments([])
  }

  // Handler to review all comments (sends to chat)
  const handleReviewComments = async (message) => {
    setIsReviewingComments(true)
    console.log('Review message:', message)
    setTimeout(() => {
      setComments([])
      setIsReviewingComments(false)
    }, 1000)
  }

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      const response = await fetch(`${API_BASE}/stock/${symbol.toUpperCase()}?algorithm=${algorithm}&force_refresh=true&character=${activeCharacter}`)
      if (response.ok) {
        const data = await response.json()
        if (data.evaluation) {
          setStock(data.evaluation)
        }
      }
    } catch (err) {
      console.error('Error refreshing stock:', err)
    } finally {
      setRefreshing(false)
    }
  }


  // Load stock data
  useEffect(() => {
    const controller = new AbortController()
    const signal = controller.signal

    const fetchStockData = async () => {
      setLoading(true)
      try {
        // Fetch stock with selected algorithm
        const response = await fetch(`${API_BASE}/stock/${symbol.toUpperCase()}?algorithm=${algorithm}&character=${activeCharacter}`, { signal })
        if (response.ok) {
          const data = await response.json()
          if (data.evaluation) {
            setStock(data.evaluation)
          }
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Error fetching stock data:', err)
        }
      } finally {
        if (!signal.aborted) {
          setLoading(false)
        }
      }
    }

    fetchStockData()

    return () => controller.abort()
  }, [symbol, algorithm])

  const [flash, setFlash] = useState({})

  // Handle real-time updates
  useEffect(() => {
    const handleUpdate = (e) => {
      const updates = e.detail?.updates
      if (!updates || !stock) return

      const update = updates.find(u => u.symbol === stock.symbol)
      if (update) {
        const newFlash = {}
        let hasChanges = false

        // Fields to animate
        const fieldsToCheck = [
          'price', 'pe_ratio', 'peg_ratio', 'market_cap',
          'dividend_yield', 'forward_pe', 'forward_peg_ratio',
          'revenue_cagr', 'earnings_cagr', 'debt_to_equity', 'gross_margin'
        ]

        fieldsToCheck.forEach(field => {
          const newValue = update[field]
          const oldValue = stock[field]

          if (newValue !== undefined && newValue !== null && newValue !== oldValue) {
            if (field === 'price') {
              newFlash[field] = (newValue > oldValue) ? 'animate-flash-green' : 'animate-flash-red'
            } else {
              newFlash[field] = 'animate-flash-green'
            }
            hasChanges = true
          }
        })

        if (hasChanges) {
          setStock(prev => ({ ...prev, ...update }))
          setFlash(newFlash)
          setTimeout(() => setFlash({}), 2000)
        }
      }
    }

    window.addEventListener('price-updates', handleUpdate)
    return () => window.removeEventListener('price-updates', handleUpdate)
  }, [stock]) // Re-bind when stock changes so we have correct oldValue

  // Fetch feature flags
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const response = await fetch(`${API_BASE}/settings`)
        if (response.ok) {
          const settings = await response.json()
          setRedditEnabled(settings.feature_reddit_enabled?.value === true || settings.feature_reddit_enabled?.value === 'true')
        }
      } catch (err) {
        console.error('Error fetching settings:', err)
      }
    }
    fetchSettings()
  }, [])

  // Fetch history data
  useEffect(() => {
    if (!stock) return

    const controller = new AbortController()
    const signal = controller.signal

    const fetchHistoryData = async () => {
      setLoadingHistory(true)
      try {
        // Fetch annual and quarterly data in parallel
        const [annualRes, quarterlyRes] = await Promise.all([
          fetch(`${API_BASE}/stock/${symbol}/history?period_type=annual`, { signal }),
          fetch(`${API_BASE}/stock/${symbol}/history?period_type=quarterly`, { signal })
        ])

        if (annualRes.ok) {
          const annualData = await annualRes.json()
          setHistoryData(annualData)
        }

        if (quarterlyRes.ok) {
          const quarterlyData = await quarterlyRes.json()
          setQuarterlyHistoryData(quarterlyData)
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Error fetching history:', err)
          // Keep existing data if one fails? Or clear?
          // We'll just log e error for now
        }
      } finally {
        if (!signal.aborted) {
          setLoadingHistory(false)
        }
      }
    }

    fetchHistoryData()

    return () => controller.abort()
  }, [stock, symbol, periodType])

  // Fetch filings data (Lazy load)
  useEffect(() => {
    if (!stock || activeTab !== 'reports' || filingsData) return

    const controller = new AbortController()
    const signal = controller.signal

    const fetchFilingsData = async () => {
      setLoadingFilings(true)
      try {
        const response = await fetch(`${API_BASE}/stock/${symbol}/filings`, { signal })
        if (response.ok) {
          const data = await response.json()
          setFilingsData(data)
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Error fetching filings:', err)
          setFilingsData(null)
        }
      } finally {
        if (!signal.aborted) {
          setLoadingFilings(false)
        }
      }
    }

    fetchFilingsData()

    return () => controller.abort()
  }, [stock, symbol, activeTab, filingsData])

  // Fetch sections data (Lazy load)
  useEffect(() => {
    if (!stock || activeTab !== 'reports' || sectionsData) return

    const controller = new AbortController()
    const signal = controller.signal

    const fetchSectionsData = async () => {
      setLoadingSections(true)
      try {
        const response = await fetch(`${API_BASE}/stock/${symbol}/sections`, { signal })
        if (response.ok) {
          const data = await response.json()
          setSectionsData(data.sections || null)
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Error fetching sections:', err)
          setSectionsData(null)
        }
      } finally {
        if (!signal.aborted) {
          setLoadingSections(false)
        }
      }
    }

    fetchSectionsData()

    return () => controller.abort()
  }, [stock, symbol, activeTab, sectionsData])

  // Fetch news data
  useEffect(() => {
    if (!stock) return

    const controller = new AbortController()
    const signal = controller.signal

    const fetchNewsData = async () => {
      setLoadingNews(true)
      try {
        const response = await fetch(`${API_BASE}/stock/${symbol}/news`, { signal })
        if (response.ok) {
          const data = await response.json()
          setNewsData(data)
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Error fetching news:', err)
          setNewsData(null)
        }
      } finally {
        if (!signal.aborted) {
          setLoadingNews(false)
        }
      }
    }

    fetchNewsData()

    return () => controller.abort()
  }, [stock, symbol])

  // Fetch material events data
  useEffect(() => {
    if (!stock) return

    const controller = new AbortController()
    const signal = controller.signal

    const fetchMaterialEvents = async () => {
      setLoadingMaterialEvents(true)
      try {
        const response = await fetch(`${API_BASE}/stock/${symbol}/material-events`, { signal })
        if (response.ok) {
          const data = await response.json()
          setMaterialEventsData(data)
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Error fetching material events:', err)
          setMaterialEventsData(null)
        }
      } finally {
        if (!signal.aborted) {
          setLoadingMaterialEvents(false)
        }
      }
    }

    fetchMaterialEvents()

    return () => controller.abort()
  }, [stock, symbol])

  // Scroll to top when switching tabs
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [activeTab])


  if (loading) {
    return (
      <div className="p-6 space-y-4 w-full">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-32" />
        <div className="grid grid-cols-6 gap-4">
          {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-12" />)}
        </div>
      </div>
    )
  }

  if (!stock) {
    return (
      <div className="flex flex-col items-center justify-center p-12 space-y-4">
        <Alert variant="destructive" className="max-w-md">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>Stock {symbol} not found or could not be loaded.</AlertDescription>
        </Alert>
        <Button onClick={() => navigate('/')}>Back to Stock List</Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col w-full min-h-full space-y-6">
      {/* Stock info header - reusing shared StockHeader */}
      <StockHeader
        stock={stock}
        toggleWatchlist={toggleWatchlist}
        watchlist={watchlist}
        flash={flash}
      />

      {/* Content area - fills remaining space */}
      <ErrorBoundary>
        <div className="flex-1 w-full">
          {activeTab === 'overview' && (
            <StockOverview stock={stock} activeCharacter={activeCharacter} flash={flash} />
          )}

          {activeTab === 'charts' && (
            <StockCharts
              historyData={historyData}
              quarterlyHistoryData={quarterlyHistoryData}
              loading={loadingHistory}
              symbol={symbol}
              activeCharacter={activeCharacter}
            />
          )}

          {activeTab === 'dcf' && (
            <DCFAnalysis stockData={stock} earningsHistory={historyData} />
          )}

          {activeTab === 'reports' && (
            <StockReports
              symbol={symbol}
              filingsData={filingsData}
              loadingFilings={loadingFilings}
              sectionsData={sectionsData}
              loadingSections={loadingSections}
              comments={comments}
              onAddComment={handleAddComment}
              onClearComments={handleClearComments}
              onReviewComments={handleReviewComments}
              isReviewingComments={isReviewingComments}
            />
          )}

          {activeTab === 'analysis' && (
            <AnalysisChat
              symbol={stock.symbol}
              stockName={stock.company_name}
              hideChat={true}
            />
          )}


          {activeTab === 'sentiment' && (
            <WallStreetSentiment symbol={stock.symbol} />
          )}

          {activeTab === 'health' && (
            <BusinessHealth symbol={stock.symbol} />
          )}

          {activeTab === 'news' && (
            <StockNews newsData={newsData} loading={loadingNews} symbol={stock.symbol} />
          )}

          {activeTab === 'reddit' && (
            <WordOnTheStreet symbol={stock.symbol} />
          )}

          {activeTab === 'events' && (
            <MaterialEvents eventsData={materialEventsData} loading={loadingMaterialEvents} symbol={stock.symbol} />
          )}

          {activeTab === 'transcripts' && (
            <TranscriptViewer symbol={symbol} />
          )}
        </div>
      </ErrorBoundary>
    </div>
  )
}

