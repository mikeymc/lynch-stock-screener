// ABOUTME: Filing sections component displaying SEC filing content with AI summaries
// ABOUTME: Shows business description, risk factors, MD&A, and market risk disclosures

import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'

export default function FilingSections({ sections, symbol, filingsData }) {
  const [showFullText, setShowFullText] = useState(new Set())
  const [summaries, setSummaries] = useState({})
  const [loadingSummaries, setLoadingSummaries] = useState(false)
  const [summaryError, setSummaryError] = useState(null)

  // Fetch summaries when component mounts or sections change
  useEffect(() => {
    if (symbol && Object.keys(sections).length > 0) {
      fetchSummaries()
    }
  }, [symbol, Object.keys(sections).length])

  const fetchSummaries = async () => {
    setLoadingSummaries(true)
    setSummaryError(null)
    try {
      const response = await fetch(`/api/stock/${symbol}/section-summaries`)
      if (!response.ok) {
        throw new Error('Failed to fetch summaries')
      }
      const data = await response.json()
      setSummaries(data.summaries || {})
    } catch (error) {
      console.error('Error fetching section summaries:', error)
      setSummaryError(error.message)
    } finally {
      setLoadingSummaries(false)
    }
  }

  const toggleFullText = (sectionName) => {
    setShowFullText(prev => {
      const newSet = new Set(prev)
      if (newSet.has(sectionName)) {
        newSet.delete(sectionName)
      } else {
        newSet.add(sectionName)
      }
      return newSet
    })
  }

  const sectionTitles = {
    business: 'Business',
    risk_factors: 'Risk Factors',
    mda: "Management Discussion & Analysis",
    market_risk: 'Market Risk'
  }

  // Format date as "January 2, 2024"
  const formatDate = (dateStr) => {
    if (!dateStr) return ''
    try {
      const date = new Date(dateStr)
      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      })
    } catch {
      return dateStr
    }
  }

  // Get filing URL based on filing type
  const getFilingUrl = (filingType) => {
    if (!filingsData) return null
    if (filingType === '10-K' && filingsData['10-K']) {
      return filingsData['10-K'].url
    }
    if (filingType === '10-Q' && filingsData['10-Q']?.[0]) {
      return filingsData['10-Q'][0].url
    }
    return null
  }

  // Order sections logically
  const sectionOrder = ['business', 'mda', 'risk_factors', 'market_risk']
  const orderedSections = sectionOrder
    .filter(name => sections[name])
    .map(name => [name, sections[name]])

  return (
    <div className="sections-container">
      <h3>Key Filing Sections</h3>
      <div className="sections-list">
        {orderedSections.map(([sectionName, sectionData]) => {
          const isShowingFullText = showFullText.has(sectionName)
          const title = sectionTitles[sectionName] || sectionName
          const filingType = sectionData.filing_type
          const filingDate = sectionData.filing_date
          const content = sectionData.content
          const summary = summaries[sectionName]?.summary || sectionData.summary
          const filingUrl = getFilingUrl(filingType)

          return (
            <div key={sectionName} className="section-item">
              <div className="section-header-simple">
                <span className="section-title">{title}</span>
                {filingUrl ? (
                  <a
                    href={filingUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="section-metadata-link"
                    onClick={(e) => e.stopPropagation()}
                  >
                    ({filingType} · {formatDate(filingDate)})
                  </a>
                ) : (
                  <span className="section-metadata">({filingType} · {formatDate(filingDate)})</span>
                )}
              </div>
              <div className="section-content">
                {/* AI Summary */}
                {!isShowingFullText && (
                  <div className="section-summary">
                    {loadingSummaries ? (
                      <div className="summary-loading">
                        <span className="loading-spinner"></span>
                        <span>Generating summary...</span>
                      </div>
                    ) : summary ? (
                      <>
                        <div className="summary-content">
                          <ReactMarkdown>{summary}</ReactMarkdown>
                        </div>
                        <button
                          className="view-fulltext-btn"
                          onClick={() => toggleFullText(sectionName)}
                        >
                          View Full Text
                        </button>
                      </>
                    ) : summaryError ? (
                      <div className="summary-error">
                        <p>Unable to generate summary</p>
                        <button
                          className="view-fulltext-btn"
                          onClick={() => toggleFullText(sectionName)}
                        >
                          View Full Text
                        </button>
                      </div>
                    ) : (
                      <div className="summary-loading">
                        <span className="loading-spinner"></span>
                        <span>Loading...</span>
                      </div>
                    )}
                  </div>
                )}

                {/* Full Text */}
                {isShowingFullText && (
                  <div className="section-fulltext">
                    <button
                      className="view-summary-btn"
                      onClick={() => toggleFullText(sectionName)}
                    >
                      ← Back to Summary
                    </button>
                    <div className="fulltext-content">
                      {content.split('\n').map((paragraph, idx) => {
                        // Skip empty lines
                        if (paragraph.trim() === '') return null
                        return <p key={idx}>{paragraph}</p>
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
