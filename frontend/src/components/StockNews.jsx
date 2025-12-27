// ABOUTME: News component for displaying stock news articles
// ABOUTME: Two-column layout: news list left (2/3), chat sidebar right (1/3)

import { useRef } from 'react'
import AnalysisChat from './AnalysisChat'

export default function StockNews({ newsData, loading, symbol }) {
    const chatRef = useRef(null)

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
        <div className="reports-layout">
            {/* Left Column - News Content (2/3) */}
            <div className="reports-main-column">
                <div className="section-item">
                    <div className="section-header-simple">
                        <span className="section-title">{articles.length} Articles</span>
                    </div>
                    <div className="section-content">
                        <div className="section-summary">
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
                                            borderBottom: '1px solid rgba(71, 85, 105, 0.5)',
                                            paddingBottom: '12px',
                                            marginBottom: '12px'
                                        }}>
                                            <div style={{ marginBottom: '4px', fontSize: '13px', color: '#94a3b8' }}>
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
                                                        style={{ color: '#60a5fa', textDecoration: 'none' }}
                                                    >
                                                        {article.headline || 'No headline'}
                                                    </a>
                                                ) : (
                                                    <span style={{ color: '#f1f5f9' }}>{article.headline || 'No headline'}</span>
                                                )}
                                            </h3>

                                            {article.summary && (
                                                <p style={{ margin: '0', lineHeight: '1.5', color: '#e2e8f0', fontSize: '14px' }}>
                                                    {article.summary}
                                                </p>
                                            )}
                                        </div>
                                    )
                                })}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Right Column - Chat Sidebar (1/3) */}
            <div className="reports-chat-sidebar">
                <div className="chat-sidebar-content">
                    <AnalysisChat ref={chatRef} symbol={symbol} chatOnly={true} contextType="news" />
                </div>
            </div>
        </div>
    )
}
