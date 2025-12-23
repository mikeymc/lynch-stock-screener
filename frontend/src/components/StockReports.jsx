// ABOUTME: Stock reports component displaying filing sections with AI summaries
// ABOUTME: SEC Filings links are now integrated into section headers

import FilingSections from './FilingSections'

export default function StockReports({ symbol, filingsData, loadingFilings, sectionsData, loadingSections }) {
  return (
    <>
      {loadingSections && (
        <div className="sections-container">
          <div className="sections-loading">Loading filing sections...</div>
        </div>
      )}

      {!loadingSections && sectionsData && Object.keys(sectionsData).length > 0 && (
        <FilingSections
          sections={sectionsData}
          symbol={symbol}
          filingsData={filingsData}
        />
      )}
    </>
  )
}
