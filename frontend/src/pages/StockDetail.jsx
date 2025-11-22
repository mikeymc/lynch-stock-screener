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
    <div className="app">
      <div className="stock-detail-container">
        <button className="back-button" onClick={() => navigate('/')}>
          ← Back to Stock List
        </button>
        <button className="refresh-button" onClick={handleRefresh} style={{ margin: '20px 0 20px 10px' }}>
          🔄 Refresh Data
        </button>
        <AlgorithmSelector
          selectedAlgorithm={algorithm}
          onAlgorithmChange={setAlgorithm}
        />

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
              <div className="tabs-header">
                <button
                  className={`tab-button ${activeTab === 'charts' ? 'active' : ''}`}
                  onClick={() => setActiveTab('charts')}
                >
                  📊 Charts
                </button>
                <button
                  className={`tab-button ${activeTab === 'dcf' ? 'active' : ''}`}
                  onClick={() => setActiveTab('dcf')}
                >
                  💰 DCF Analysis
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
                  <StockCharts historyData={historyData} loading={loadingHistory} />
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
              </div>
            </div>
          </ErrorBoundary>
        )}
      </div>
    </div>
  )
}
