// ABOUTME: Filing sections component displaying expandable SEC filing content
// ABOUTME: Shows business description, risk factors, MD&A, and market risk disclosures

import { useState } from 'react'

export default function FilingSections({ sections }) {
  const [expandedSections, setExpandedSections] = useState(new Set())

  const toggleSection = (sectionName) => {
    setExpandedSections(prev => {
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
    business: 'Business Description (Item 1)',
    risk_factors: 'Risk Factors (Item 1A)',
    mda: 'Management Discussion & Analysis',
    market_risk: 'Market Risk Disclosures'
  }

  return (
    <div className="sections-container">
      <h3>Key Filing Sections</h3>
      <div className="sections-list">
        {Object.entries(sections).map(([sectionName, sectionData]) => {
          const isExpanded = expandedSections.has(sectionName)
          const title = sectionTitles[sectionName] || sectionName
          const filingType = sectionData.filing_type
          const filingDate = sectionData.filing_date
          const content = sectionData.content

          return (
            <div key={sectionName} className="section-item">
              <div
                className="section-header"
                onClick={() => toggleSection(sectionName)}
              >
                <span className="section-toggle">{isExpanded ? '▼' : '▶'}</span>
                <span className="section-title">{title}</span>
                <span className="section-metadata">({filingType} - Filed: {filingDate})</span>
              </div>
              {isExpanded && (
                <div className="section-content">
                  <div className="section-text">
                    {content.split('\n').map((paragraph, idx) => {
                      // Skip empty lines
                      if (paragraph.trim() === '') return null
                      return <p key={idx}>{paragraph}</p>
                    })}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
