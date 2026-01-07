// ABOUTME: Panel displaying all collected comments with Review All button
// ABOUTME: Sends batch of comments to AI for analysis, auto-clears after review

import { useState } from 'react'
import { Button } from "@/components/ui/button"

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
        <div className="bg-card border rounded-lg overflow-hidden my-4 shadow-sm">
            <div
                className="flex items-center justify-between p-3 bg-muted/50 border-b cursor-pointer hover:bg-muted/80 transition-colors"
                onClick={() => setExpanded(!expanded)}
            >
                <span className="font-semibold text-sm flex items-center gap-2">
                    💬 Comments <span className="text-xs bg-primary text-primary-foreground px-1.5 py-0.5 rounded-full">{comments.length}</span>
                </span>
                <span className="text-muted-foreground text-xs">
                    {expanded ? '▲' : '▶'}
                </span>
            </div>

            {expanded && (
                <>
                    <div className="max-h-[300px] overflow-y-auto p-3 space-y-2">
                        {comments.map((comment, idx) => (
                            <div key={comment.id} className="flex gap-3 p-3 bg-muted/30 rounded-md border border-transparent hover:border-border transition-colors">
                                <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-bold shadow-sm">
                                    {idx + 1}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1 font-semibold">
                                        {sectionLabels[comment.sectionName] || comment.sectionName}
                                    </div>
                                    <div className="text-xs italic text-muted-foreground mb-1 truncate border-l-2 border-primary/20 pl-2">
                                        "{truncate(comment.selectedText)}"
                                    </div>
                                    <div className="text-sm">
                                        {comment.comment}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>

                    <div className="flex justify-end gap-2 p-3 bg-muted/50 border-t">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={onClearAll}
                            disabled={isReviewing}
                            className="h-8"
                        >
                            Clear All
                        </Button>
                        <Button
                            size="sm"
                            onClick={handleReviewClick}
                            disabled={isReviewing}
                            className="h-8 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white border-0"
                        >
                            {isReviewing ? 'Reviewing...' : `Review All (${comments.length})`}
                        </Button>
                    </div>
                </>
            )}
        </div>
    )
}
