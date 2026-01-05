import { useState, useEffect, useRef } from 'react'
import './AlgorithmSelector.css'

const API_BASE = '/api'

const AlgorithmSelector = ({ selectedAlgorithm, onAlgorithmChange }) => {
  const [algorithms, setAlgorithms] = useState({})
  const [showHelp, setShowHelp] = useState(false)
  const [loading, setLoading] = useState(true)
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef(null)

  useEffect(() => {
    const controller = new AbortController()
    const signal = controller.signal

    // Fetch algorithm metadata from API
    fetch(`${API_BASE}/algorithms`, { signal, credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        setAlgorithms(data)
        setLoading(false)
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          console.error('Error fetching algorithms:', err)
          setLoading(false)
        }
      })

    return () => controller.abort()
  }, [])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (isOpen && dropdownRef.current && !dropdownRef.current.contains(event.target)) {
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

  const handleSelect = (key) => {
    onAlgorithmChange(key)
    setIsOpen(false)
  }

  if (loading) {
    return <div className="algorithm-selector">Loading algorithms...</div>
  }

  const selectedAlgo = algorithms[selectedAlgorithm]

  return (
    <>
      <div className="algorithm-selector" ref={dropdownRef}>
        <button
          className="algorithm-dropdown"
          onClick={() => setIsOpen(!isOpen)}
          type="button"
        >
          <span className="algorithm-dropdown-text">
            {selectedAlgo ? `${selectedAlgo.name} Scoring` : 'Select Algorithm'}
          </span>
          <span className="algorithm-dropdown-arrow">{isOpen ? '▲' : '▼'}</span>
        </button>

        {isOpen && (
          <div className="algorithm-dropdown-menu">
            {Object.entries(algorithms).map(([key, algo]) => (
              <div
                key={key}
                className={`algorithm-dropdown-item ${key === selectedAlgorithm ? 'selected' : ''}`}
                onClick={() => handleSelect(key)}
                title={algo.short_desc}
              >
                <span className="algorithm-name">{algo.name} Scoring</span>
                {key === selectedAlgorithm && <span className="checkmark">✓</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      {showHelp && (
        <div className="modal-overlay" onClick={() => setShowHelp(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Scoring Algorithms Explained</h2>
              <button className="modal-close" onClick={() => setShowHelp(false)}>×</button>
            </div>
            <div className="modal-body">
              {Object.entries(algorithms).map(([key, algo]) => (
                <div key={key} className="algorithm-detail">
                  <h3>
                    {algo.name}
                    {algo.recommended && <span className="recommended-badge">⭐ Recommended</span>}
                  </h3>
                  <p className="algorithm-short-desc">{algo.short_desc}</p>
                  <div className="algorithm-full-desc">
                    {algo.description.split('\n').map((line, idx) => (
                      <p key={idx}>{line}</p>
                    ))}
                  </div>
                  {selectedAlgorithm === key && (
                    <div className="current-algorithm-indicator">Currently Selected</div>
                  )}
                </div>
              ))}
            </div>
            <div className="modal-footer">
              <button onClick={() => setShowHelp(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default AlgorithmSelector
