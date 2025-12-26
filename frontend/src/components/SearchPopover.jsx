// ABOUTME: Search input with popover dropdown for quick stock navigation
// ABOUTME: Used in stock detail page header for jumping between stocks

import { useState, useRef, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import './SearchPopover.css'

const API_BASE = '/api'

export default function SearchPopover({ onSelect }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [isOpen, setIsOpen] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, left: 0 })

  const containerRef = useRef(null)
  const inputRef = useRef(null)
  const inputWrapperRef = useRef(null)
  const dropdownRef = useRef(null)
  const debounceRef = useRef(null)

  // Update dropdown position when open
  useEffect(() => {
    if (isOpen && inputWrapperRef.current) {
      const rect = inputWrapperRef.current.getBoundingClientRect()
      setDropdownPosition({
        top: rect.bottom + 4,
        left: rect.left
      })
    }
  }, [isOpen])

  // Fetch search results
  const fetchResults = useCallback(async (searchQuery) => {
    if (!searchQuery.trim()) {
      setResults([])
      setIsOpen(false)
      return
    }

    setLoading(true)
    try {
      const response = await fetch(
        `${API_BASE}/sessions/latest?search=${encodeURIComponent(searchQuery)}&limit=10`
      )
      if (response.ok) {
        const data = await response.json()
        setResults(data.results || [])
        setIsOpen(data.results?.length > 0)
        setHighlightedIndex(0)
      }
    } catch (err) {
      console.error('Search error:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  // Debounced search handler
  const handleInputChange = (e) => {
    const value = e.target.value
    setQuery(value)

    if (debounceRef.current) {
      clearTimeout(debounceRef.current)
    }

    if (!value.trim()) {
      setResults([])
      setIsOpen(false)
      return
    }

    debounceRef.current = setTimeout(() => {
      fetchResults(value)
    }, 200)
  }

  // Handle stock selection
  const handleSelect = (stock) => {
    setQuery('')
    setResults([])
    setIsOpen(false)
    onSelect(stock.symbol)
  }

  // Keyboard navigation
  const handleKeyDown = (e) => {
    if (!isOpen || results.length === 0) {
      if (e.key === 'Escape') {
        inputRef.current?.blur()
      }
      return
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setHighlightedIndex(prev =>
          prev < results.length - 1 ? prev + 1 : prev
        )
        break
      case 'ArrowUp':
        e.preventDefault()
        setHighlightedIndex(prev => prev > 0 ? prev - 1 : 0)
        break
      case 'Enter':
        e.preventDefault()
        if (results[highlightedIndex]) {
          handleSelect(results[highlightedIndex])
        }
        break
      case 'Escape':
        e.preventDefault()
        setIsOpen(false)
        inputRef.current?.blur()
        break
    }
  }

  // Click outside to close
  useEffect(() => {
    const handleClickOutside = (e) => {
      const clickedInContainer = containerRef.current?.contains(e.target)
      const clickedInDropdown = dropdownRef.current?.contains(e.target)
      if (!clickedInContainer && !clickedInDropdown) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
    }
  }, [])

  return (
    <div className="search-popover-container" ref={containerRef}>
      <div className="search-popover-input-wrapper" ref={inputWrapperRef}>
        <input
          ref={inputRef}
          type="text"
          className="search-popover-input"
          value={query}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => results.length > 0 && setIsOpen(true)}
          placeholder="Search..."
        />
        {query && (
          <button
            className="search-popover-clear"
            onClick={() => {
              setQuery('')
              setResults([])
              setIsOpen(false)
              inputRef.current?.focus()
            }}
            aria-label="Clear search"
          >
            ×
          </button>
        )}
      </div>

      {isOpen && results.length > 0 && createPortal(
        <div
          className="search-popover-dropdown"
          ref={dropdownRef}
          style={{
            position: 'fixed',
            top: dropdownPosition.top,
            left: dropdownPosition.left
          }}
        >
          {results.map((stock, index) => (
            <div
              key={stock.symbol}
              className={`search-popover-item ${index === highlightedIndex ? 'highlighted' : ''}`}
              onClick={() => handleSelect(stock)}
              onMouseEnter={() => setHighlightedIndex(index)}
            >
              <span className="search-popover-symbol">{stock.symbol}</span>
              <span className="search-popover-name">{stock.company_name}</span>
            </div>
          ))}
        </div>,
        document.body
      )}
    </div>
  )
}
