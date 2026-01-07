// ABOUTME: Stock reports component displaying filing sections with AI summaries
// ABOUTME: Full-width layout: reports and review panel

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
  // Chat reference removed as AnalysisChat is now global
  // const chatRef = useRef(null)

  // Handler to send review message to chat
  const handleReviewAll = (message) => {
    // COMMENTED OUT: AnalysisChat removed from this component.
    // The user should use the global sidebar chat for interactions.
    // if (chatRef.current?.sendMessage) {
    //   chatRef.current.sendMessage(message, { hideUserMessage: true })
    //   if (onClearComments) {
    //     onClearComments()
    //   }
    // }
    console.log("Review request:", message);
  }

  if (loadingSections) {
    return <div className="sections-loading">Loading filing sections...</div>
  }

  if (!sectionsData || Object.keys(sectionsData).length === 0) {
    return null
  }

  return (
    <div className="w-full">
      <div className="section-item">
        <FilingSections
          sections={sectionsData}
          symbol={symbol}
          filingsData={filingsData}
          comments={comments}
          onAddComment={onAddComment}
        />

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
