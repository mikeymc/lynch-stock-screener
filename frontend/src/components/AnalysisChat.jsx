// ABOUTME: Combined component displaying Lynch Analysis with Chat interface
// ABOUTME: Analysis panel is collapsible, and analysis context is passed to chat

import { useState } from 'react'
import LynchAnalysis from './LynchAnalysis'
import ChatInterface from './ChatInterface'

export default function AnalysisChat({ symbol, stockName }) {
  const [analysisExpanded, setAnalysisExpanded] = useState(false)
  const [analysisText, setAnalysisText] = useState(null)

  const handleAnalysisLoaded = (analysis) => {
    setAnalysisText(analysis)
  }

  return (
    <div className="analysis-chat-container">
      <div className={`analysis-panel ${analysisExpanded ? 'expanded' : 'collapsed'}`}>
        <button
          className="analysis-toggle-button"
          onClick={() => setAnalysisExpanded(!analysisExpanded)}
        >
          {analysisExpanded ? '▼' : '▶'} Peter Lynch Analysis
          {analysisText && !analysisExpanded && <span className="analysis-loaded-indicator">✓</span>}
        </button>

        {analysisExpanded && (
          <div className="analysis-panel-content">
            <LynchAnalysis
              symbol={symbol}
              stockName={stockName}
              onAnalysisLoaded={handleAnalysisLoaded}
            />
          </div>
        )}
      </div>

      <div className={`chat-panel ${analysisExpanded ? 'with-analysis' : 'full-height'}`}>
        <ChatInterface
          symbol={symbol}
          lynchAnalysis={analysisText}
        />
      </div>
    </div>
  )
}
