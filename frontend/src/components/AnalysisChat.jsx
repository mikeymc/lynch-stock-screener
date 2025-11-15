// ABOUTME: Unified component displaying Lynch Analysis followed by chat conversation
// ABOUTME: Creates continuous flow from analysis reading to discussion

import { useState } from 'react'
import LynchAnalysis from './LynchAnalysis'
import ChatInterface from './ChatInterface'

export default function AnalysisChat({ symbol, stockName }) {
  const [analysisText, setAnalysisText] = useState(null)

  const handleAnalysisLoaded = (analysis) => {
    setAnalysisText(analysis)
  }

  return (
    <div className="unified-analysis-chat">
      <LynchAnalysis
        symbol={symbol}
        stockName={stockName}
        onAnalysisLoaded={handleAnalysisLoaded}
      />

      <ChatInterface
        symbol={symbol}
        lynchAnalysis={analysisText}
      />
    </div>
  )
}
