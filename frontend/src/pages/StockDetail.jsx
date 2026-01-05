// ABOUTME: Stock detail page with sticky header and tabbed content
// ABOUTME: Displays charts, reports, analysis, and chat for a specific stock

import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import StockCard from '../components/StockCard'
import StockCharts from '../components/StockCharts'
import StockReports from '../components/StockReports'
import AnalysisChat from '../components/AnalysisChat'
import ErrorBoundary from '../components/ErrorBoundary'
import DCFAnalysis from '../components/DCFAnalysis'
import StockNews from '../components/StockNews'
import MaterialEvents from '../components/MaterialEvents'
import FutureOutlook from '../components/FutureOutlook'
import SearchPopover from '../components/SearchPopover'
import UserAvatar from '../components/UserAvatar'
import TranscriptViewer from '../components/TranscriptViewer'
import BurgerMenu from '../components/BurgerMenu'

const API_BASE = '/api'

const detailTabs = [
  { id: 'analysis', label: 'Brief' },
  { id: 'charts', label: 'Financials' },
  { id: 'outlook', label: 'Forward Metrics' },
  { id: 'dcf', label: 'DCF Analysis' },
  { id: 'news', label: 'News' },
  { id: 'reports', label: 'Quarterly & Annual Reports' },
  { id: 'events', label: 'Material Event Filings' },
  { id: 'transcript', label: 'Earnings Transcript' }
]

export default function StockDetail({ watchlist, toggleWatchlist }) {
  const { symbol } = useParams()
  const navigate = useNavigate()
  const [stock, setStock] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('charts')
  const [periodType, setPeriodType] = useState('annual')
  const [algorithm, setAlgorithm] = useState('weighted')

  // Data state
  const [historyData, setHistoryData] = useState(null)
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

  // Chat panel state
  const [isChatOpen, setIsChatOpen] = useState(false)
  const chatRef = useRef(null)

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


  // Load stock data
  // Load stock data
  useEffect(() => {
    const controller = new AbortController()
    const signal = controller.signal

    const fetchStockData = async () => {
      setLoading(true)
      try {
        // Fetch stock with selected algorithm
        const response = await fetch(`${API_BASE}/stock/${symbol.toUpperCase()}?algorithm=${algorithm}`, { signal })
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

  // Fetch history data
  // Fetch history data
  useEffect(() => {
    if (!stock) return

    const controller = new AbortController()
    const signal = controller.signal

    const fetchHistoryData = async () => {
      setLoadingHistory(true)
      try {
        const response = await fetch(`${API_BASE}/stock/${symbol}/history?period_type=${periodType}`, { signal })
        if (response.ok) {
          const data = await response.json()
          setHistoryData(data)
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Error fetching history:', err)
          setHistoryData(null)
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

  // Fetch filings data
  // Fetch filings data (Lazy load)
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

  // Fetch sections data
  // Fetch sections data (Lazy load)
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
    return <div className="app"><div className="loading">Loading stock data...</div></div>
  }

  if (!stock) {
    return (
      <div className="app">
        <div className="error">Stock {symbol} not found</div>
        <button onClick={() => navigate('/')}>Back to Stock List</button>
      </div>
    )
  }

  return (
    <>
      <BurgerMenu
        tabs={detailTabs}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />
      <div className="stock-detail-page">
        {/* Sticky zone - controls and stock summary stick together */}
        <div className="sticky-zone">
        <div className="controls">
          {/* All Stocks button */}
          <button className="tab-button nav-button" onClick={() => navigate('/')}>
            All Stocks
          </button>

          {/* Search popover for quick stock navigation */}
          <SearchPopover onSelect={(sym) => navigate(`/stock/${sym}`)} />

          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '12px' }}>
            {/* Chat icon */}
            <button
              onClick={() => setIsChatOpen(!isChatOpen)}
              className="icon-button"
              style={{
                width: '24px',
                height: '24px',
                padding: 0,
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                opacity: 0.7,
                transition: 'opacity 0.2s ease'
              }}
              onMouseEnter={(e) => e.currentTarget.style.opacity = '1'}
              onMouseLeave={(e) => e.currentTarget.style.opacity = '0.7'}
              title="Chat"
            >
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#E2E8F0"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
            </button>

            <UserAvatar />
          </div>
        </div>

        {/* Stock summary card - part of sticky zone */}
        <div className="stock-summary-section">
          <StockCard
            stock={stock}
            watchlist={watchlist}
            onToggleWatchlist={toggleWatchlist}
          />
        </div>
      </div>

      {/* Content area - fills remaining space */}
      <ErrorBoundary>
        <div className="stock-detail-content">
          {activeTab === 'charts' && (
            <StockCharts historyData={historyData} loading={loadingHistory} symbol={symbol} />
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
            />
          )}

          {activeTab === 'outlook' && (
            <FutureOutlook symbol={stock.symbol} />
          )}

          {activeTab === 'news' && (
            <StockNews newsData={newsData} loading={loadingNews} symbol={stock.symbol} />
          )}

          {activeTab === 'events' && (
            <MaterialEvents eventsData={materialEventsData} loading={loadingMaterialEvents} symbol={stock.symbol} />
          )}

          {activeTab === 'transcript' && (
            <TranscriptViewer symbol={symbol} />
          )}
        </div>
      </ErrorBoundary>
    </div>

    {/* Chat panel - slides in from right */}
    <div
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        width: '400px',
        height: '100vh',
        padding: '16px',
        backgroundColor: '#0f172a',
        borderLeft: '1px solid #334155',
        transition: 'transform 0.3s ease',
        transform: isChatOpen ? 'translateX(0)' : 'translateX(100%)',
        zIndex: 999,
        display: 'flex',
        flexDirection: 'column'
      }}
    >
        {/* Close button */}
        <button
          onClick={() => setIsChatOpen(false)}
          style={{
            position: 'absolute',
            top: '16px',
            right: '16px',
            background: 'transparent',
            border: 'none',
            color: '#94a3b8',
            cursor: 'pointer',
            fontSize: '20px',
            padding: '4px 8px',
            lineHeight: 1,
            zIndex: 1
          }}
          onMouseEnter={(e) => e.currentTarget.style.color = '#E2E8F0'}
          onMouseLeave={(e) => e.currentTarget.style.color = '#94a3b8'}
        >
          ×
        </button>

        {/* Reports chat sidebar */}
        <div className="reports-chat-sidebar" style={{ height: '100%', marginTop: 0 }}>
          <div className="chat-sidebar-content">
            <AnalysisChat
              ref={chatRef}
              symbol={stock.symbol}
              stockName={stock.company_name}
              chatOnly={true}
              contextType={
                activeTab === 'analysis' ? 'brief' :
                activeTab === 'charts' ? 'charts' :
                activeTab === 'outlook' ? 'outlook' :
                activeTab === 'dcf' ? 'dcf' :
                activeTab === 'news' ? 'news' :
                activeTab === 'reports' ? 'filings' :
                activeTab === 'events' ? 'events' :
                activeTab === 'transcript' ? 'transcript' :
                'brief'
              }
            />
          </div>
        </div>
      </div>
    </>
  )
}

