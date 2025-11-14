// ABOUTME: Status bar component that visualizes stock metric scores
// ABOUTME: Displays a three-zone bar (pass/close/fail) with a marker indicating the score position

export default function StatusBar({ status, score, value }) {
  const displayValue = typeof value === 'number' ? value.toFixed(2) : 'N/A'
  const tooltipText = `${status}: ${displayValue}`

  // Invert position: score 100 (best) = left (0%), score 0 (worst) = right (100%)
  const markerPosition = `${100 - score}%`

  return (
    <div className="status-bar-container" title={tooltipText}>
      <div className="status-bar">
        <div className="status-zone pass"></div>
        <div className="status-zone close"></div>
        <div className="status-zone fail"></div>
        <div
          className="status-marker"
          style={{ left: markerPosition }}
        ></div>
      </div>
    </div>
  )
}
