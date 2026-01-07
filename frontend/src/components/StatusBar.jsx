// ABOUTME: Status bar component that visualizes stock metric scores
// ABOUTME: Displays a solid green progress bar filling left-to-right based on score

export default function StatusBar({ status, score, value, metricType }) {
  const displayValue = typeof value === 'number' ? value.toFixed(2) : (value || 'N/A')
  const tooltipText = `${status}: ${displayValue}`

  // Ensure score is clamped between 0 and 100
  const clampedScore = Math.max(0, Math.min(100, score || 0))

  return (
    <div className="w-full flex flex-col justify-center h-full" title={tooltipText}>
      <div className="relative w-full h-2 bg-zinc-200 rounded-full overflow-hidden">
        {/* Green Progress Fill */}
        <div
          className="absolute top-0 left-0 h-full bg-green-600 rounded-full transition-all duration-300"
          style={{ width: `${clampedScore}%` }}
        />
      </div>
    </div>
  )
}
