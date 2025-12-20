// ABOUTME: Status bar component that visualizes stock metric scores
// ABOUTME: Displays metric-specific color zones with a marker indicating the score position

export default function StatusBar({ status, score, value, metricType }) {
  const displayValue = typeof value === 'number' ? value.toFixed(2) : (value || 'N/A')
  const tooltipText = `${status}: ${displayValue}`

  // Calculate marker position based on metric type
  // For consistency metrics: high score (100) should be on LEFT (green zone at 0%)
  // For PE range: score is inverted before passing (high position = right), so use directly
  // For other metrics (PEG, debt): invert score so low is on left (good)
  const shouldInvert = !['revenue_consistency', 'income_consistency', 'pe_range'].includes(metricType)
  const markerPosition = shouldInvert ? `${100 - score}%` : `${score}%`

  // Define zone configurations for each metric type
  const getZoneConfig = () => {
    switch (metricType) {
      case 'pe_range':
        // 52-week P/E range: left = low P/E (good), right = high P/E (expensive)
        return [
          { class: 'excellent', width: '25%', label: 'Low' },
          { class: 'good', width: '25%', label: 'Mid-Low' },
          { class: 'fair', width: '25%', label: 'Mid-High' },
          { class: 'poor', width: '25%', label: 'High' }
        ]
      case 'revenue_consistency':
      case 'income_consistency':
        // Consistency: left = poor (score 0), right = excellent (score 100)
        return [
          { class: 'poor', width: '25%', label: 'Poor' },
          { class: 'fair', width: '25%', label: 'Fair' },
          { class: 'good', width: '25%', label: 'Good' },
          { class: 'excellent', width: '25%', label: 'Excellent' }
        ]
      case 'peg':
        return [
          { class: 'excellent', width: '25%', label: '0-1.0' },
          { class: 'good', width: '12.5%', label: '1.0-1.5' },
          { class: 'fair', width: '12.5%', label: '1.5-2.0' },
          { class: 'poor', width: '50%', label: '2.0+' }
        ]
      case 'debt':
        return [
          { class: 'excellent', width: '20%', label: '0-0.5' },
          { class: 'good', width: '20%', label: '0.5-1.0' },
          { class: 'moderate', width: '40%', label: '1.0-2.0' },
          { class: 'high', width: '20%', label: '2.0+' }
        ]
      case 'institutional':
        return [
          { class: 'too-low', width: '20%', label: '0-20%' },
          { class: 'ideal', width: '40%', label: '20-60%' },
          { class: 'too-high', width: '40%', label: '60-100%' }
        ]
      default:
        return [
          { class: 'pass', width: '50%' },
          { class: 'close', width: '25%' },
          { class: 'fail', width: '25%' }
        ]
    }
  }

  const zones = getZoneConfig()

  return (
    <div className="status-bar-container" title={tooltipText}>
      <div className="status-bar" data-metric={metricType}>
        <div
          className="status-marker"
          style={{ left: markerPosition }}
        ></div>
        <div style={{ display: 'flex', width: '100%', height: '100%' }}>
          {zones.map((zone, index) => (
            <div
              key={index}
              className={`status-zone ${zone.class}`}
              style={{ width: zone.width }}
            ></div>
          ))}
        </div>
      </div>
    </div>
  )
}
