// ABOUTME: Burger menu slide-out panel component
// ABOUTME: Provides a collapsible sidebar that expands from 50px to 310px

import { useState, useEffect, useRef } from 'react'
import AlgorithmSelector from './AlgorithmSelector'
import './BurgerMenu.css'

export default function BurgerMenu({ algorithm, onAlgorithmChange, filter, setFilter }) {
  const [isOpen, setIsOpen] = useState(false)
  const [isHovered, setIsHovered] = useState(false)
  const [filterDropdownOpen, setFilterDropdownOpen] = useState(false)
  const panelRef = useRef(null)
  const buttonRef = useRef(null)
  const filterDropdownRef = useRef(null)

  const filterOptions = [
    { value: 'all', label: 'All' },
    { value: 'watchlist', label: '⭐ Watchlist' },
    { value: 'STRONG_BUY', label: 'Excellent Only' },
    { value: 'BUY', label: 'Good Only' },
    { value: 'HOLD', label: 'Fair Only' },
    { value: 'CAUTION', label: 'Weak Only' },
    { value: 'AVOID', label: 'Poor Only' }
  ]

  const getFilterLabel = (value) => {
    const option = filterOptions.find(opt => opt.value === value)
    return option ? option.label : 'All'
  }

  // Close panel when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (isOpen && panelRef.current && !panelRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  // Close filter dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (filterDropdownOpen && filterDropdownRef.current && !filterDropdownRef.current.contains(event.target)) {
        setFilterDropdownOpen(false)
      }
    }

    if (filterDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [filterDropdownOpen])

  return (
    <div
      ref={panelRef}
      className={`burger-menu ${isOpen ? 'open' : ''}`}
    >
      <button
        ref={buttonRef}
        className="burger-icon"
        onClick={() => {
          setIsOpen(!isOpen)
          if (buttonRef.current) {
            buttonRef.current.blur()
          }
        }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        aria-label="Toggle menu"
        style={{
          backgroundColor: isHovered ? 'rgba(255, 255, 255, 0.1)' : 'transparent'
        }}
      >
        <div className="burger-line"></div>
        <div className="burger-line"></div>
        <div className="burger-line"></div>
      </button>

      {isOpen && (
        <div className="burger-content">
          <div className="burger-section">
            <div className="burger-section-label">Status Filter</div>
            <div className="filter-dropdown-container" ref={filterDropdownRef}>
              <button
                className="burger-filter-dropdown"
                onClick={() => setFilterDropdownOpen(!filterDropdownOpen)}
                type="button"
              >
                <span className="filter-dropdown-text">{getFilterLabel(filter)}</span>
                <span className="filter-dropdown-arrow">{filterDropdownOpen ? '▲' : '▼'}</span>
              </button>

              {filterDropdownOpen && (
                <div className="filter-dropdown-menu">
                  {filterOptions.map(option => (
                    <div
                      key={option.value}
                      className={`filter-dropdown-item ${filter === option.value ? 'selected' : ''}`}
                      onClick={() => {
                        setFilter(option.value)
                        setFilterDropdownOpen(false)
                      }}
                    >
                      <span className="filter-option-label">{option.label}</span>
                      {filter === option.value && <span className="checkmark">✓</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="burger-section">
            <div className="burger-section-label">Scoring Algorithm</div>
            <AlgorithmSelector
              selectedAlgorithm={algorithm}
              onAlgorithmChange={onAlgorithmChange}
            />
          </div>
        </div>
      )}
    </div>
  )
}
