// ABOUTME: Stock reports component displaying SEC filings and filing sections
// ABOUTME: Shows 10-K, 10-Q links and expandable filing content sections

import FilingSections from './FilingSections'

export default function StockReports({ filingsData, loadingFilings, sectionsData, loadingSections }) {
  return (
    <>
      {!loadingFilings && filingsData && (Object.keys(filingsData).length > 0) && (
        <div className="filings-container">
          <h3>SEC Filings</h3>
          <div className="filings-links">
            {filingsData['10-K'] && (
              <div className="filing-item">
                <a href={filingsData['10-K'].url} target="_blank" rel="noopener noreferrer">
                  📄 10-K Annual Report (Filed: {filingsData['10-K'].filed_date})
                </a>
              </div>
            )}
            {filingsData['10-Q']?.map((filing, idx) => (
              <div key={idx} className="filing-item">
                <a href={filing.url} target="_blank" rel="noopener noreferrer">
                  📄 10-Q Quarterly Report (Filed: {filing.filed_date})
                </a>
              </div>
            ))}
          </div>
        </div>
      )}

      {loadingSections && (
        <div className="sections-container">
          <div className="sections-loading">Loading filing sections...</div>
        </div>
      )}

      {!loadingSections && sectionsData && Object.keys(sectionsData).length > 0 && (
        <FilingSections sections={sectionsData} />
      )}
    </>
  )
}
