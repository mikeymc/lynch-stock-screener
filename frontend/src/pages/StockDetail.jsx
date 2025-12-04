// ABOUTME: Stock detail page with sticky header and tabbed content
// ABOUTME: Displays charts, reports, analysis, and chat for a specific stock

import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import StockTableHeader from '../components/StockTableHeader'
import StockTableRow from '../components/StockTableRow'
import StockCharts from '../components/StockCharts'
import StockReports from '../components/StockReports'
import AnalysisChat from '../components/AnalysisChat'
import AlgorithmSelector from '../components/AlgorithmSelector'
import ErrorBoundary from '../components/ErrorBoundary'
import DCFAnalysis from '../components/DCFAnalysis'
import StockNews from '../components/StockNews'
import MaterialEvents from '../components/MaterialEvents'

const API_BASE = '/api'

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



  // Load stock data
  useEffect(() => {
    const fetchStockData = async () => {
      setLoading(true)
      try {
        // Fetch stock with selected algorithm
        const response = await fetch(`${API_BASE}/stock/${symbol.toUpperCase()}?algorithm=${algorithm}`)
        if (response.ok) {
          const data = await response.json()
          if (data.evaluation) {
            setStock(data.evaluation)
          }
        }
      } catch (err) {
        console.error('Error fetching stock data:', err)
      } finally {
        setLoading(false)
      }
    }

    fetchStockData()
  }, [symbol, algorithm])

  // Fetch history data
  useEffect(() => {
    if (!stock) return

    const fetchHistoryData = async () => {
      setLoadingHistory(true)
      try {
        const response = await fetch(`${API_BASE}/stock/${symbol}/history?period_type=${periodType}`)
        if (response.ok) {
          const data = await response.json()
          setHistoryData(data)
        }
      } catch (err) {
        console.error('Error fetching history:', err)
        setHistoryData(null)
      } finally {
        setLoadingHistory(false)
      }
    }

    fetchHistoryData()
  }, [stock, symbol, periodType])

  // Fetch filings data
  // Fetch filings data (Lazy load)
  useEffect(() => {
    if (!stock || activeTab !== 'reports' || filingsData) return

    const fetchFilingsData = async () => {
      setLoadingFilings(true)
      try {
        const response = await fetch(`${API_BASE}/stock/${symbol}/filings`)
        if (response.ok) {
          const data = await response.json()
          setFilingsData(data)
        }
      } catch (err) {
        console.error('Error fetching filings:', err)
        setFilingsData(null)
      } finally {
        setLoadingFilings(false)
      }
    }

    fetchFilingsData()
  }, [stock, symbol, activeTab, filingsData])

  // Fetch sections data
  // Fetch sections data (Lazy load)
  useEffect(() => {
    if (!stock || activeTab !== 'reports' || sectionsData) return

    const fetchSectionsData = async () => {
      setLoadingSections(true)
      try {
        const response = await fetch(`${API_BASE}/stock/${symbol}/sections`)
        if (response.ok) {
          const data = await response.json()
          setSectionsData(data.sections || null)
        }
      } catch (err) {
        console.error('Error fetching sections:', err)
        setSectionsData(null)
      } finally {
        setLoadingSections(false)
      }
    }

    fetchSectionsData()
  }, [stock, symbol, activeTab, sectionsData])

  // Fetch news data
  useEffect(() => {
    if (!stock) return

    const fetchNewsData = async () => {
      setLoadingNews(true)
      try {
        const response = await fetch(`${API_BASE}/stock/${symbol}/news`)
        if (response.ok) {
          const data = await response.json()
          setNewsData(data)
        }
      } catch (err) {
        console.error('Error fetching news:', err)
        setNewsData(null)
      } finally {
        setLoadingNews(false)
      }
    }

    fetchNewsData()
  }, [stock, symbol])

  // Fetch material events data
  useEffect(() => {
    if (!stock) return

    const fetchMaterialEvents = async () => {
      setLoadingMaterialEvents(true)
      try {
        const response = await fetch(`${API_BASE}/stock/${symbol}/material-events`)
        if (response.ok) {
          const data = await response.json()
          setMaterialEventsData(data)
        }
      } catch (err) {
        console.error('Error fetching material events:', err)
        setMaterialEventsData(null)
      } finally {
        setLoadingMaterialEvents(false)
      }
    }

    fetchMaterialEvents()
  }, [stock, symbol])



  const handleRefresh = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE}/stock/${symbol}?refresh=true`)
      if (response.ok) {
        const data = await response.json()
        if (data.evaluation) {
          setStock(data.evaluation)
          // Reset other data states to trigger re-fetch via useEffects
          setHistoryData(null)
          setFilingsData(null)
          setSectionsData(null)
          setNewsData(null)
          setMaterialEventsData(null)
        }
      }
    } catch (err) {
      console.error('Error refreshing stock data:', err)
    } finally {
      setLoading(false)
    }
  }

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
    <div className="app stock-list-view">
      <div className="controls">
        <div style={{ display: 'flex', gap: '10px' }}>
          <button className="back-button" onClick={() => navigate('/')}>
            Back to List
          </button>
          <button className="refresh-button" onClick={handleRefresh}>
            Refresh Data
          </button>
        </div>

        <div style={{ display: 'flex', gap: '10px', marginLeft: '20px', overflowX: 'auto' }}>
          <button
            className={`tab-button ${activeTab === 'charts' ? 'active' : ''}`}
            onClick={() => setActiveTab('charts')}
          >
            Charts
          </button>
          <button
            className={`tab-button ${activeTab === 'dcf' ? 'active' : ''}`}
            onClick={() => setActiveTab('dcf')}
          >
            DCF Analysis
          </button>
          <button
            className={`tab-button ${activeTab === 'reports' ? 'active' : ''}`}
            onClick={() => setActiveTab('reports')}
          >
            Reports
          </button>
          <button
            className={`tab-button ${activeTab === 'analysis' ? 'active' : ''}`}
            onClick={() => setActiveTab('analysis')}
          >
            Analysis & Chat
          </button>
          <button
            className={`tab-button ${activeTab === 'news' ? 'active' : ''}`}
            onClick={() => setActiveTab('news')}
          >
            News
          </button>
          <button
            className={`tab-button ${activeTab === 'events' ? 'active' : ''}`}
            onClick={() => setActiveTab('events')}
          >
            Material Events
          </button>
        </div>
      </div>

      <div className="stock-detail-container">
        {loading ? (
          <div className="loading">Loading stock data...</div>
        ) : !stock ? (
          <div className="error">
            Stock {symbol} not found
            <button onClick={() => navigate('/')} style={{ marginLeft: '10px' }}>Back to List</button>
          </div>
        ) : (
          <ErrorBoundary>
            <div className="sticky-header">
              <table className="stocks-table">
                <StockTableHeader readOnly={true} />
                <tbody>
                  <StockTableRow
                    stock={stock}
                    watchlist={watchlist}
                    onToggleWatchlist={toggleWatchlist}
                    readOnly={true}
                  />
                </tbody>
              </table>
            </div>

            <div className="tabs-container">
              <div className="tabs-content">
                {activeTab === 'charts' && (
                  <StockCharts historyData={historyData} loading={loadingHistory} symbol={symbol} />
                )}

                {activeTab === 'dcf' && (
                  <DCFAnalysis stockData={stock} earningsHistory={historyData} />
                )}

                {activeTab === 'reports' && (
                  <StockReports
                    filingsData={filingsData}
                    loadingFilings={loadingFilings}
                    sectionsData={sectionsData}
                    loadingSections={loadingSections}
                  />
                )}

                {activeTab === 'analysis' && (
                  <AnalysisChat
                    symbol={stock.symbol}
                    stockName={stock.company_name}
                  />
                )}

                {activeTab === 'news' && (
                  <StockNews newsData={newsData} loading={loadingNews} />
                )}

                {activeTab === 'events' && (
                  <MaterialEvents eventsData={materialEventsData} loading={loadingMaterialEvents} />
                )}
              </div>
            </div>
          </ErrorBoundary>
        )}
      </div>
    </div>
  )
}
