// ABOUTME: Stock reports component displaying filing sections with AI summaries
// ABOUTME: Full-width layout with filing sections and review panel

import FilingSections from './FilingSections'
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
  // Handler to send review message to chat
  const handleReviewAll = (message) => {
    if (onReviewComments) {
      onReviewComments(message)
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
      <div className="reports-main-column" style={{ flex: 1, maxWidth: '100%' }}>
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
    </div>
  )
}
