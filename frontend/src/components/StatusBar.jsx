// ABOUTME: Status bar component that visualizes stock metric scores
// ABOUTME: Displays metric-specific color zones with a marker indicating the score position

export default function StatusBar({ status, score, value, metricType }) {
  const displayValue = typeof value === 'number' ? value.toFixed(2) : 'N/A'
  const tooltipText = `${status}: ${displayValue}`

  // Invert position: score 100 (best) = left (0%), score 0 (worst) = right (100%)
  const markerPosition = `${100 - score}%`

  // Define zone configurations for each metric type
  const getZoneConfig = () => {
    switch (metricType) {
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
