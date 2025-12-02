// ABOUTME: News component for displaying stock news articles
// ABOUTME: Shows news in chronological order with headline, summary, source, and date

export default function StockNews({ newsData, loading }) {
    if (loading) {
        return (
            <div className="loading" style={{ padding: '40px', textAlign: 'center' }}>
                Loading news articles...
            </div>
        )
    }

    const articles = newsData?.articles || []

    if (articles.length === 0) {
        return (
            <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>
                <p>No news articles available for this stock.</p>
            </div>
        )
    }

    return (
        <div className="stock-news-container" style={{ padding: '20px' }}>
            <h2 style={{ marginBottom: '20px', color: '#fff' }}>News Articles ({articles.length})</h2>
            <div className="news-list">
                {articles.map((article, index) => {
                    const publishedDate = article.published_date
                        ? new Date(article.published_date).toLocaleDateString('en-US', {
                            year: 'numeric',
                            month: 'short',
                            day: 'numeric'
                        })
                        : 'Unknown date'

                    return (
                        <div key={article.id || index} className="news-article" style={{
                            borderBottom: '1px solid #444',
                            paddingBottom: '12px',
                            marginBottom: '12px'
                        }}>
                            <div style={{ marginBottom: '4px', fontSize: '13px', color: '#aaa' }}>
                                <span style={{ fontWeight: '600' }}>{article.source || 'Unknown source'}</span>
                                {' • '}
                                <span>{publishedDate}</span>
                            </div>

                            <h3 style={{ margin: '0 0 6px 0', fontSize: '16px', lineHeight: '1.3', fontWeight: '600' }}>
                                {article.url ? (
                                    <a
                                        href={article.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        style={{ color: '#5ba3f5', textDecoration: 'none' }}
                                    >
                                        {article.headline || 'No headline'}
                                    </a>
                                ) : (
                                    <span style={{ color: '#fff' }}>{article.headline || 'No headline'}</span>
                                )}
                            </h3>

                            {article.summary && (
                                <p style={{ margin: '0', lineHeight: '1.5', color: '#ddd', fontSize: '14px' }}>
                                    {article.summary}
                                </p>
                            )}
                        </div>
                    )
                })}
            </div>
        </div>
    )
}
