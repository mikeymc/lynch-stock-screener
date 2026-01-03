// ABOUTME: Status bar component that visualizes stock metric scores
// ABOUTME: Displays metric-specific color zones with a marker indicating the score position

export default function StatusBar({ status, score, value, metricType, compact = false }) {
  const displayValue = typeof value === 'number' ? value.toFixed(2) : (value || 'N/A')
  const tooltipText = `${status}: ${displayValue}`

  // Calculate marker position - score 0 = left, score 100 = right
  const markerPosition = `${score}%`

  // Check if this metric type uses a gradient
  const useGradient = [].includes(metricType)

  // Check if this metric type uses a solid fill (partial fill, no marker)
  const useSolidFill = ['revenue_consistency', 'income_consistency'].includes(metricType)

  // Check if this metric type uses a full bar with marker
  const useFullBarWithMarker = ['pe_range'].includes(metricType)

  // Get gradient style based on metric type
  const getGradientStyle = () => {
    switch (metricType) {
      case 'pe_range':
        // P/E Range: green (left, low P/E = good) -> red (right, high P/E = expensive)
        return {
          background: 'linear-gradient(to right, #22c55e 0%, #86efac 25%, #fde047 50%, #fb923c 75%, #ef4444 100%)'
        }
      case 'income_consistency':
        // Consistency: red (left, low = bad) -> green (right, high = good)
        return {
          background: 'linear-gradient(to right, #ef4444 0%, #fb923c 25%, #fde047 50%, #86efac 75%, #22c55e 100%)'
        }
      default:
        return {}
    }
  }

  // Define zone configurations for non-gradient metric types
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
    <div className={`status-bar-container ${compact ? 'compact' : ''}`} title={tooltipText}>
      <div className="status-bar" data-metric={metricType}>
        {(useGradient || useFullBarWithMarker) && (
          <div
            className="status-marker"
            style={{ left: markerPosition }}
          ></div>
        )}
        {useGradient ? (
          <div style={{
            width: '100%',
            height: '100%',
            borderRadius: '4px',
            ...getGradientStyle()
          }}></div>
        ) : useSolidFill ? (
          <div style={{
            width: '100%',
            height: '100%',
            borderRadius: '4px',
            backgroundColor: '#1E293B',
            position: 'relative'
          }}>
            <div style={{
              width: markerPosition,
              height: '100%',
              borderRadius: '4px',
              backgroundColor: '#10B981'
            }}></div>
          </div>
        ) : useFullBarWithMarker ? (
          <div style={{
            width: '100%',
            height: '100%',
            borderRadius: '4px',
            backgroundColor: '#60A5FA'
          }}></div>
        ) : (
          <div style={{ display: 'flex', width: '100%', height: '100%' }}>
            {zones.map((zone, index) => (
              <div
                key={index}
                className={`status-zone ${zone.class}`}
                style={{ width: zone.width }}
              ></div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
