import { useState, useEffect } from 'react'
import './ModelSelector.css'

const API_BASE = '/api'

const ModelSelector = ({ selectedModel, onModelChange, storageKey }) => {
  const [models, setModels] = useState([])
  const [defaultModel, setDefaultModel] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    const signal = controller.signal

    // Fetch available models from API
    fetch(`${API_BASE}/ai-models`, { signal, credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        setModels(data.models || [])
        setDefaultModel(data.default || '')

        // Load from localStorage or use default
        const saved = localStorage.getItem(storageKey)
        if (saved && data.models.includes(saved)) {
          onModelChange(saved)
        } else {
          onModelChange(data.default)
        }

        setLoading(false)
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          console.error('Error fetching models:', err)
          setLoading(false)
        }
      })

    return () => controller.abort()
  }, [storageKey, onModelChange])

  const handleChange = (model) => {
    onModelChange(model)
    localStorage.setItem(storageKey, model)
  }

  if (loading) {
    return <div className="model-selector">Loading models...</div>
  }

  return (
    <div className="model-selector">
      <select
        id={`model-select-${storageKey}`}
        value={selectedModel}
        onChange={(e) => handleChange(e.target.value)}
        className="model-dropdown"
      >
        {models.map(model => (
          <option key={model} value={model}>
            {model}
          </option>
        ))}
      </select>
    </div>
  )
}

export default ModelSelector
