// ABOUTME: Search input with popover dropdown for quick stock navigation
// ABOUTME: Used in stock detail page header for jumping between stocks

import { useState, useRef, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'

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
    <div className="relative" ref={containerRef}>
      <div className="relative flex items-center" ref={inputWrapperRef}>
        <Input
          ref={inputRef}
          type="text"
          className="w-[200px] pr-8"
          value={query}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => results.length > 0 && setIsOpen(true)}
          placeholder="Search..."
        />
        {query && (
          <Button
            variant="ghost"
            size="sm"
            className="absolute right-0 h-full px-2"
            onClick={() => {
              setQuery('')
              setResults([])
              setIsOpen(false)
              inputRef.current?.focus()
            }}
            aria-label="Clear search"
          >
            ×
          </Button>
        )}
      </div>

      {isOpen && results.length > 0 && createPortal(
        <div
          className="bg-popover border rounded-md shadow-md py-1 z-50 min-w-[200px]"
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
              className={`px-3 py-2 cursor-pointer flex gap-2 items-center ${index === highlightedIndex ? 'bg-accent' : 'hover:bg-muted'}`}
              onClick={() => handleSelect(stock)}
              onMouseEnter={() => setHighlightedIndex(index)}
            >
              <span className="font-medium text-sm">{stock.symbol}</span>
              <span className="text-sm text-muted-foreground truncate">{stock.company_name}</span>
            </div>
          ))}
        </div>,
        document.body
      )}
    </div>
  )
}
