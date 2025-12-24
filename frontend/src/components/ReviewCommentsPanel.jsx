// ABOUTME: Panel displaying all collected comments with Review All button
// ABOUTME: Sends batch of comments to AI for analysis, auto-clears after review

import { useState } from 'react'

export default function ReviewCommentsPanel({ comments, onReviewAll, onClearAll, isReviewing }) {
    const [expanded, setExpanded] = useState(true)

    if (comments.length === 0) {
        return null
    }

    // Truncate text for display
    const truncate = (text, maxLength = 60) => {
        if (text.length <= maxLength) return text
        return text.substring(0, maxLength) + '...'
    }

    // Section labels for display
    const sectionLabels = {
        business: 'Business',
        risk_factors: 'Risk Factors',
        mda: "MD&A",
        market_risk: 'Market Risk'
    }

    const handleReviewClick = () => {
        // Build structured message for AI
        const message = buildReviewMessage(comments)
        onReviewAll(message)
    }

    const buildReviewMessage = (comments) => {
        const header = `Questions/comments about specific passages in the SEC filings:\n`

        const items = comments.map((c, idx) => {
            const sectionLabel = sectionLabels[c.sectionName] || c.sectionName
            return `${idx + 1}. **${sectionLabel}**\n> "${truncate(c.selectedText, 150)}"\n**Q:** ${c.comment}`
        }).join('\n\n')

        const footer = `\nPlease address each point with context from the filings.`

        return header + items + footer
    }

    return (
        <div className="review-comments-panel">
            <div
                className="review-panel-header"
                onClick={() => setExpanded(!expanded)}
            >
                <span className="review-panel-title">
                    💬 Comments ({comments.length})
                </span>
                <span className="review-panel-toggle">
                    {expanded ? '▼' : '▶'}
                </span>
            </div>

            {expanded && (
                <>
                    <div className="review-panel-list">
                        {comments.map((comment, idx) => (
                            <div key={comment.id} className="review-panel-item">
                                <div className="review-item-number">{idx + 1}</div>
                                <div className="review-item-content">
                                    <div className="review-item-section">
                                        {sectionLabels[comment.sectionName] || comment.sectionName}
                                    </div>
                                    <div className="review-item-excerpt">
                                        "{truncate(comment.selectedText)}"
                                    </div>
                                    <div className="review-item-comment">
                                        {comment.comment}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>

                    <div className="review-panel-actions">
                        <button
                            className="review-panel-clear"
                            onClick={onClearAll}
                            disabled={isReviewing}
                        >
                            Clear All
                        </button>
                        <button
                            className="review-panel-submit"
                            onClick={handleReviewClick}
                            disabled={isReviewing}
                        >
                            {isReviewing ? 'Reviewing...' : `Review All (${comments.length})`}
                        </button>
                    </div>
                </>
            )}
        </div>
    )
}
