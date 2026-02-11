// ABOUTME: Aggregated news feed from watchlist and portfolio stocks
// ABOUTME: Shows 10 most recent articles with source and timestamp

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Newspaper } from 'lucide-react'

export default function NewsFeed({ articles = [], loading = false }) {
    return (
        <Card>
            <CardHeader className="pb-2">
                <CardTitle className="text-base font-medium flex items-center gap-2">
                    <Newspaper className="h-4 w-4" />
                    News
                </CardTitle>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <Skeleton className="h-24 w-full" />
                ) : articles.length > 0 ? (
                    <div className="space-y-1">
                        {articles.map((article, idx) => (
                            <NewsRow key={article.finnhub_id || idx} article={article} />
                        ))}
                    </div>
                ) : (
                    <EmptyState />
                )}
            </CardContent>
        </Card>
    )
}

function NewsRow({ article }) {
    const handleClick = () => {
        if (article.url) {
            window.open(article.url, '_blank', 'noopener,noreferrer')
        }
    }

    return (
        <button
            onClick={handleClick}
            className="w-full text-left group p-0"
            disabled={!article.url}
        >
            <div className="flex items-start py-1 px-2 rounded hover:bg-accent transition-colors">
                <div className="min-w-0 flex-1">
                    {/* Headline */}
                    <p className="text-sm font-medium line-clamp-2 group-hover:text-primary transition-colors">
                        {article.headline}
                    </p>

                    {/* Meta */}
                    <div className="flex items-center gap-2 mt-1">
                        {article.symbol && (
                            <Badge variant="outline" className="text-xs">
                                {article.symbol}
                            </Badge>
                        )}
                        <span className="text-xs text-muted-foreground">
                            {article.source}
                        </span>
                        <span className="text-xs text-muted-foreground">
                            •
                        </span>
                        <span className="text-xs text-muted-foreground">
                            {formatTimeAgo(article.datetime)}
                        </span>
                    </div>
                </div>
            </div>
        </button>
    )
}

function formatTimeAgo(timestamp) {
    if (!timestamp) return ''
    const date = new Date(timestamp * 1000) // Convert unix timestamp
    const seconds = Math.floor((new Date() - date) / 1000)

    if (seconds < 60) return 'just now'
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ago`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}h ago`
    const days = Math.floor(hours / 24)
    if (days < 7) return `${days}d ago`
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function EmptyState() {
    return (
        <div className="flex flex-col items-center justify-center py-6 text-center">
            <Newspaper className="h-8 w-8 text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground">
                No recent news
            </p>
            <p className="text-xs text-muted-foreground mt-1">
                Add stocks to your watchlist to see their news here
            </p>
        </div>
    )
}
