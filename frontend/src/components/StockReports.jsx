// ABOUTME: Stock reports component displaying filing sections with AI summaries
// ABOUTME: Two-column layout: reports left (2/3), chat right (1/3) with fixed input

import { useRef } from 'react'
import FilingSections from './FilingSections'
import AnalysisChat from './AnalysisChat'
import ReviewCommentsPanel from './ReviewCommentsPanel'

export default function StockReports({
  symbol,
  filingsData,
  loadingFilings,
  sectionsData,
  loadingSections,
  comments = [],
  onAddComment,
  onClearComments,
  onReviewComments,
  isReviewingComments
}) {
  const chatRef = useRef(null)

  // Handler to send review message to chat
  const handleReviewAll = (message) => {
    if (chatRef.current?.sendMessage) {
      // Hide user message bubble since it's from comment review, not chat input
      chatRef.current.sendMessage(message, { hideUserMessage: true })
      // Clear comments after sending
      if (onClearComments) {
        onClearComments()
      }
    }
  }

  if (loadingSections) {
    return <div className="sections-loading">Loading filing sections...</div>
  }

  if (!sectionsData || Object.keys(sectionsData).length === 0) {
    return null
  }

  return (
    <div className="reports-layout">
      {/* Left Column - Reports Content (2/3) */}
      <div className="reports-main-column">
        <FilingSections
          sections={sectionsData}
          symbol={symbol}
          filingsData={filingsData}
          comments={comments}
          onAddComment={onAddComment}
        />

        {/* Review Comments Panel - in reports column */}
        <ReviewCommentsPanel
          comments={comments}
          onReviewAll={handleReviewAll}
          onClearAll={onClearComments}
          isReviewing={isReviewingComments}
        />
      </div>

      {/* Right Column - Chat Sidebar (1/3) */}
      <div className="reports-chat-sidebar">
        <div className="chat-sidebar-header">
          <h3>💬 Ask Questions</h3>
          <p>Ask about the filings or select text to add comments</p>
        </div>
        <div className="chat-sidebar-content">
          <AnalysisChat ref={chatRef} symbol={symbol} chatOnly={true} />
        </div>
      </div>
    </div>
  )
}
