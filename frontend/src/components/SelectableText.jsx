// ABOUTME: Wrapper component enabling text selection with floating plus button for comments
// ABOUTME: Detects mouse selection, shows positioned button, triggers comment popover

import { useState, useRef, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import CommentPopover from './CommentPopover'

export default function SelectableText({ children, sectionName, onAddComment, comments = [] }) {
    const containerRef = useRef(null)
    const [selection, setSelection] = useState(null)
    const [showPopover, setShowPopover] = useState(false)
    const [buttonPosition, setButtonPosition] = useState({ top: 0, left: 0 })

    // Handle text selection
    const handleMouseUp = useCallback((e) => {
        // Small delay to ensure selection is complete
        setTimeout(() => {
            const windowSelection = window.getSelection()

            if (!windowSelection || windowSelection.isCollapsed || !windowSelection.toString().trim()) {
                // Only clear if we're not showing popover - don't interrupt comment entry
                if (!showPopover) {
                    setSelection(null)
                }
                return
            }

            // Check if selection is within our container
            const range = windowSelection.getRangeAt(0)
            if (!containerRef.current?.contains(range.commonAncestorContainer)) {
                return
            }

            const selectedText = windowSelection.toString().trim()
            if (selectedText.length < 3) {
                // Too short to be meaningful
                return
            }

            // Get position for the plus button
            const rect = range.getBoundingClientRect()

            setSelection({
                text: selectedText,
                range: range.cloneRange()
            })

            setButtonPosition({
                top: rect.top + window.scrollY - 35,
                left: rect.left + rect.width / 2 + window.scrollX
            })
        }, 10)
    }, [showPopover])

    // Clear selection when clicking outside
    useEffect(() => {
        const handleClickOutside = (e) => {
            if (showPopover) return // Don't clear during popover interaction

            const plusButton = document.querySelector('.selection-plus-button')
            if (plusButton?.contains(e.target)) return

            if (!containerRef.current?.contains(e.target)) {
                setSelection(null)
            }
        }

        document.addEventListener('mousedown', handleClickOutside)
        return () => document.removeEventListener('mousedown', handleClickOutside)
    }, [showPopover])

    const handlePlusClick = () => {
        setShowPopover(true)
    }

    const handlePopoverSave = (comment) => {
        if (selection && comment.trim()) {
            onAddComment({
                id: Date.now().toString(),
                sectionName,
                selectedText: selection.text,
                comment: comment.trim()
            })
        }
        setShowPopover(false)
        setSelection(null)
        window.getSelection()?.removeAllRanges()
    }

    const handlePopoverCancel = () => {
        setShowPopover(false)
        setSelection(null)
        window.getSelection()?.removeAllRanges()
    }

    // Count comments for this section
    const sectionCommentCount = comments.filter(c => c.sectionName === sectionName).length

    return (
        <div
            ref={containerRef}
            className="selectable-text-container"
            onMouseUp={handleMouseUp}
        >
            {/* Show comment count badge if there are comments */}
            {sectionCommentCount > 0 && (
                <div className="section-comment-badge">
                    💬 {sectionCommentCount} comment{sectionCommentCount > 1 ? 's' : ''}
                </div>
            )}

            {children}

            {/* Floating plus button - rendered via portal for proper positioning */}
            {selection && !showPopover && createPortal(
                <button
                    className="selection-plus-button"
                    style={{
                        position: 'absolute',
                        top: buttonPosition.top,
                        left: buttonPosition.left,
                        transform: 'translateX(-50%)'
                    }}
                    onClick={handlePlusClick}
                    title="Add comment"
                >
                    +
                </button>,
                document.body
            )}

            {/* Comment popover */}
            {showPopover && selection && createPortal(
                <CommentPopover
                    selectedText={selection.text}
                    position={buttonPosition}
                    onSave={handlePopoverSave}
                    onCancel={handlePopoverCancel}
                />,
                document.body
            )}
        </div>
    )
}
