import { useState, useEffect } from 'react'
import './AlgorithmSelector.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:5001/api'

const AlgorithmSelector = ({ selectedAlgorithm, onAlgorithmChange }) => {
  const [algorithms, setAlgorithms] = useState({})
  const [showHelp, setShowHelp] = useState(false)
  const [loading, setLoading] = useState(true)

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

  if (loading) {
    return <div className="algorithm-selector">Loading algorithms...</div>
  }

  return (
    <>
      <div className="algorithm-selector">
        <label htmlFor="algorithm-select">
          Scoring Algo <sup onClick={() => setShowHelp(true)} style={{ cursor: 'pointer' }} title="Learn about scoring algorithms">i</sup>:
        </label>
        <select
          id="algorithm-select"
          value={selectedAlgorithm}
          onChange={(e) => onAlgorithmChange(e.target.value)}
          className="algorithm-dropdown"
        >
          {Object.entries(algorithms).map(([key, algo]) => (
            <option
              key={key}
              value={key}
              title={algo.short_desc}
            >
              {algo.name} {algo.recommended ? '⭐' : ''}
            </option>
          ))}
        </select>
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
