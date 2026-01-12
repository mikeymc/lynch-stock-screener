// ABOUTME: Status bar component that visualizes stock metric scores
// ABOUTME: Displays a solid green progress bar filling left-to-right based on score

export default function StatusBar({ status, score, value, metricType, compact = false }) {
  const displayValue = typeof value === 'number' ? value.toFixed(2) : (value || 'N/A')
  const tooltipText = `${status}: ${displayValue}`

  // Ensure score is clamped between 0 and 100
  const clampedScore = Math.max(0, Math.min(100, score || 0))
  // Ensure there's always a tiny visible bar (2%) even for 0% score
  const visualScore = Math.max(2, clampedScore)

  // Determine color based on metric type
  let barColor = "bg-green-600"
  if (metricType === 'pe_range') {
    // PE Range: lower is usually better (but we map score 0-100 where higher is "better" or "safer"? 
    // Actually the backend likely already normalizes this since it's a "score". 
    // If it's just raw position % (0 = low PE, 100 = high PE), we might want a different color.
    // Assuming 'score' is "goodness", green is fine. If it's just value...
    // Let's stick to blue for "Range" to differentiate from "Growth" (Green).
    barColor = "bg-blue-600"
  } else if (metricType === 'revenue_consistency' || metricType === 'income_consistency') {
    barColor = "bg-emerald-600"
  }

  const heightClass = compact ? "h-1.5" : "h-2"

  return (
    <div className="w-full flex flex-col justify-center h-full" title={tooltipText}>
      <div className={`relative w-full ${heightClass} bg-muted rounded-full overflow-hidden`}>
        {/* Progress Fill */}
        <div
          className={`absolute top-0 left-0 h-full ${barColor} rounded-full transition-all duration-300`}
          style={{ width: `${visualScore}%` }}
        />
      </div>
    </div>
  )
}
