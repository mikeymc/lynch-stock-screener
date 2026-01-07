// ABOUTME: News component for displaying stock news articles
// ABOUTME: Two-column layout: news list left (2/3), chat sidebar right (1/3)

import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"

export default function StockNews({ newsData, loading, symbol }) {

    if (loading) {
        return (
            <div className="loading p-10 text-center">
                Loading news articles...
            </div>
        )
    }

    const articles = newsData?.articles || []

    if (articles.length === 0) {
        return (
            <div className="p-10 text-center text-[#888]">
                <p>No news articles available for this stock.</p>
            </div>
        )
    }

    return (
        <div className="w-full">
            <div className="section-item">
                <div className="section-header-simple">
                    <span className="section-title">{articles.length} Articles</span>
                </div>
                <div className="section-content">
                    <div className="section-summary">
                        <div className="news-list space-y-4">
                            {articles.map((article, index) => {
                                const publishedDate = article.published_date
                                    ? new Date(article.published_date).toLocaleDateString('en-US', {
                                        year: 'numeric',
                                        month: 'short',
                                        day: 'numeric'
                                    })
                                    : 'Unknown date'

                                return (
                                    <Card key={article.id || index}>
                                        <CardHeader className="pb-3">
                                            <div className="flex items-center gap-2 mb-1 text-sm text-muted-foreground">
                                                <span className="font-semibold text-foreground">{article.source || 'Unknown source'}</span>
                                                <span>•</span>
                                                <span>{publishedDate}</span>
                                            </div>
                                            <CardTitle className="text-base leading-snug">
                                                {article.url ? (
                                                    <a
                                                        href={article.url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="text-blue-400 hover:underline hover:text-blue-300"
                                                    >
                                                        {article.headline || 'No headline'}
                                                    </a>
                                                ) : (
                                                    <span className="text-foreground">{article.headline || 'No headline'}</span>
                                                )}
                                            </CardTitle>
                                        </CardHeader>

                                        {article.summary && (
                                            <CardContent>
                                                <p className="text-sm leading-relaxed text-muted-foreground">
                                                    {article.summary}
                                                </p>
                                            </CardContent>
                                        )}
                                    </Card>
                                )
                            })}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
