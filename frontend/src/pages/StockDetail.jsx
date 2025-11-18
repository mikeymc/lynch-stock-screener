// ABOUTME: Stock detail page with sticky header and tabbed content
// ABOUTME: Displays charts, reports, analysis, and chat for a specific stock

import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import StockTableHeader from '../components/StockTableHeader'
import StockTableRow from '../components/StockTableRow'
import StockCharts from '../components/StockCharts'
import StockReports from '../components/StockReports'
import AnalysisChat from '../components/AnalysisChat'

const API_BASE = '/api'

export default function StockDetail() {
  const { symbol } = useParams()
  const navigate = useNavigate()
  const [stock, setStock] = useState(null)
  const [loading, setLoading] = useState(true)
  const [watchlist, setWatchlist] = useState(new Set())
  const [activeTab, setActiveTab] = useState('charts')
  const [periodType, setPeriodType] = useState('annual')

  // Data state
  const [historyData, setHistoryData] = useState(null)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [filingsData, setFilingsData] = useState(null)
  const [loadingFilings, setLoadingFilings] = useState(false)
  const [sectionsData, setSectionsData] = useState(null)
  const [loadingSections, setLoadingSections] = useState(false)

  // Load watchlist
  useEffect(() => {
    const loadWatchlist = async () => {
      try {
        const response = await fetch(`${API_BASE}/watchlist`)
        if (response.ok) {
          const data = await response.json()
          setWatchlist(new Set(data.symbols))
        }
      } catch (err) {
        console.error('Error loading watchlist:', err)
      }
    }
    loadWatchlist()
  }, [])

  // Load stock data
  useEffect(() => {
    const fetchStockData = async () => {
      setLoading(true)
      try {
        // First try to get from latest session results
        const sessionResponse = await fetch(`${API_BASE}/sessions/latest`)
        if (sessionResponse.ok) {
          const sessionData = await sessionResponse.json()
          const results = sessionData.results || []
          const foundStock = results.find(s => s.symbol === symbol.toUpperCase())

          if (foundStock) {
            setStock(foundStock)
          } else {
            // Stock not found in session, could fetch individually or show error
            console.error(`Stock ${symbol} not found in latest session`)
          }
        }
      } catch (err) {
        console.error('Error fetching stock data:', err)
      } finally {
        setLoading(false)
      }
    }

    fetchStockData()
  }, [symbol])

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
  useEffect(() => {
    if (!stock) return

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
  }, [stock, symbol])

  // Fetch sections data
  useEffect(() => {
    if (!stock) return

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
  }, [stock, symbol])

  const toggleWatchlist = async (stockSymbol) => {
    const isInWatchlist = watchlist.has(stockSymbol)

    try {
      if (isInWatchlist) {
        await fetch(`${API_BASE}/watchlist/${stockSymbol}`, { method: 'DELETE' })
        setWatchlist(prev => {
          const newSet = new Set(prev)
          newSet.delete(stockSymbol)
          return newSet
        })
      } else {
        await fetch(`${API_BASE}/watchlist/${stockSymbol}`, { method: 'POST' })
        setWatchlist(prev => new Set([...prev, stockSymbol]))
      }
    } catch (err) {
      console.error('Error toggling watchlist:', err)
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
    <div className="app">
      <div className="stock-detail-container">
        <button className="back-button" onClick={() => navigate('/')}>
          ← Back to Stock List
        </button>

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
          <div className="tabs-header">
            <button
              className={`tab-button ${activeTab === 'charts' ? 'active' : ''}`}
              onClick={() => setActiveTab('charts')}
            >
              📊 Charts
            </button>
            <button
              className={`tab-button ${activeTab === 'reports' ? 'active' : ''}`}
              onClick={() => setActiveTab('reports')}
            >
              📄 Reports
            </button>
            <button
              className={`tab-button ${activeTab === 'analysis' ? 'active' : ''}`}
              onClick={() => setActiveTab('analysis')}
            >
              🎯 Analysis & Chat
            </button>
          </div>

          <div className="tabs-content">
            {activeTab === 'charts' && (
              <>
                {/* <div className="period-toggle"> */}
                  {/* <button
                    className={`period-button ${periodType === 'annual' ? 'active' : ''}`}
                    onClick={() => setPeriodType('annual')}
                  >
                    Annual
                  </button> */}
                  {/* <button
                    className={`period-button ${periodType === 'quarterly' ? 'active' : ''}`}
                    onClick={() => setPeriodType('quarterly')}
                  >
                    Quarterly
                  </button>
                  <button
                    className={`period-button ${periodType === 'both' ? 'active' : ''}`}
                    onClick={() => setPeriodType('both')}
                  >
                    Both
                  </button> */}
                {/* </div> */}
                <StockCharts historyData={historyData} loading={loadingHistory} />
              </>
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
          </div>
        </div>
      </div>
    </div>
  )
}
