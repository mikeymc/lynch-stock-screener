// ABOUTME: Popover component for entering a comment about selected text
// ABOUTME: Shows excerpt of selected text and textarea for user's question/comment

import { useState, useRef, useEffect } from 'react'

export default function CommentPopover({ selectedText, position, onSave, onCancel }) {
    const [comment, setComment] = useState('')
    const textareaRef = useRef(null)
    const popoverRef = useRef(null)

    // Auto-focus textarea when popover opens
    useEffect(() => {
        textareaRef.current?.focus()
    }, [])

    // Handle escape key to cancel
    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.key === 'Escape') {
                onCancel()
            }
        }
        document.addEventListener('keydown', handleKeyDown)
        return () => document.removeEventListener('keydown', handleKeyDown)
    }, [onCancel])

    // Click outside to cancel
    useEffect(() => {
        const handleClickOutside = (e) => {
            if (popoverRef.current && !popoverRef.current.contains(e.target)) {
                onCancel()
            }
        }
        // Delay adding listener to avoid immediate trigger
        const timeout = setTimeout(() => {
            document.addEventListener('mousedown', handleClickOutside)
        }, 100)
        return () => {
            clearTimeout(timeout)
            document.removeEventListener('mousedown', handleClickOutside)
        }
    }, [onCancel])

    const handleSubmit = (e) => {
        e.preventDefault()
        if (comment.trim()) {
            onSave(comment)
        }
    }

    const handleKeyPress = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            if (comment.trim()) {
                onSave(comment)
            }
        }
    }

    // Truncate selected text for display
    const displayText = selectedText.length > 100
        ? selectedText.substring(0, 100) + '...'
        : selectedText

    return (
        <div
            ref={popoverRef}
            className="comment-popover"
            style={{
                position: 'absolute',
                top: position.top + 45,
                left: position.left,
                transform: 'translateX(-50%)'
            }}
        >
            <div className="comment-popover-arrow" />

            <div className="comment-popover-excerpt">
                <span className="excerpt-label">Selected:</span>
                <span className="excerpt-text">"{displayText}"</span>
            </div>

            <form onSubmit={handleSubmit}>
                <textarea
                    ref={textareaRef}
                    className="comment-popover-input"
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder="Add your question or comment..."
                    rows="2"
                />

                <div className="comment-popover-actions">
                    <button
                        type="button"
                        className="comment-popover-cancel"
                        onClick={onCancel}
                    >
                        Cancel
                    </button>
                    <button
                        type="submit"
                        className="comment-popover-save"
                        disabled={!comment.trim()}
                    >
                        Add Comment
                    </button>
                </div>
            </form>
        </div>
    )
}
