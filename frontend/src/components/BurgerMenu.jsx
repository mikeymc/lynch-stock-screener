// ABOUTME: Burger menu slide-out panel component
// ABOUTME: Provides a collapsible sidebar that expands from 50px to 310px

import { useState, useEffect, useRef } from 'react'
import './BurgerMenu.css'

export default function BurgerMenu() {
  const [isOpen, setIsOpen] = useState(false)
  const [isHovered, setIsHovered] = useState(false)
  const panelRef = useRef(null)
  const buttonRef = useRef(null)

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
          {/* Menu content will go here */}
          <p style={{ color: '#9CA3AF', padding: '20px', fontSize: '14px' }}>
            Menu content coming soon...
          </p>
        </div>
      )}
    </div>
  )
}
