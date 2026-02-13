import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Input } from "@/components/ui/input"
import { Lightbulb, Search, ArrowLeft } from 'lucide-react'

export default function ThesesPage() {
    const navigate = useNavigate()
    const [thesesData, setThesesData] = useState({ theses: [], total_count: 0 })
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [searchQuery, setSearchQuery] = useState('')

    useEffect(() => {
        const fetchTheses = async () => {
            try {
                setLoading(true)
                // Fetch more theses for the full page
                const response = await fetch('/api/dashboard/theses?limit=100&days=30')
                if (response.ok) {
                    const data = await response.json()
                    setThesesData(data.recent_theses || { theses: [], total_count: 0 })
                } else {
                    setError('Failed to load theses')
                }
            } catch (err) {
                console.error('Error fetching theses:', err)
                setError('Failed to load theses')
            } finally {
                setLoading(false)
            }
        }

        fetchTheses()
    }, [])

    const filteredTheses = thesesData.theses.filter(item =>
        item.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.thesis.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.verdict.toLowerCase().includes(searchQuery.toLowerCase())
    )

    return (
        <div className="container mx-auto py-8 max-w-5xl space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Investment Theses</h1>
                    <p className="text-muted-foreground">Comprehensive collection of recent character analyst theses</p>
                </div>
                <div className="relative w-72">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                        type="search"
                        placeholder="Search ticker, company, or thesis..."
                        className="pl-8 bg-background"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                </div>
            </div>

            <Card className="border-none shadow-md bg-card/50 backdrop-blur-sm">
                <CardContent className="p-0">
                    {loading ? (
                        <div className="p-8 space-y-4">
                            {[...Array(8)].map((_, i) => (
                                <Skeleton key={i} className="h-16 w-full" />
                            ))}
                        </div>
                    ) : error ? (
                        <div className="p-12 text-center text-destructive">{error}</div>
                    ) : filteredTheses.length > 0 ? (
                        <div className="overflow-x-auto">
                            <table className="w-full text-left border-collapse">
                                <thead>
                                    <tr className="border-b bg-muted/50">
                                        <th className="p-4 font-semibold text-sm">Company</th>
                                        <th className="p-4 font-semibold text-sm text-center">Analyst</th>
                                        <th className="p-4 font-semibold text-sm">Thesis Snippet</th>
                                        <th className="p-4 font-semibold text-sm text-center">Verdict</th>
                                        <th className="p-4 font-semibold text-sm text-right">Generated</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredTheses.map((item, idx) => (
                                        <tr
                                            key={`${item.symbol}-${idx}`}
                                            onClick={() => navigate(`/stock/${item.symbol}?tab=analysis&character=${item.character_id}`)}
                                            className="border-b hover:bg-accent/40 cursor-pointer transition-colors"
                                        >
                                            <td className="p-4">
                                                <div className="flex flex-col">
                                                    <span className="font-bold text-base">{item.symbol}</span>
                                                    <span className="text-xs text-muted-foreground truncate max-w-[150px]">
                                                        {item.name}
                                                    </span>
                                                </div>
                                            </td>
                                            <td className="p-4 text-center">
                                                <Badge variant="secondary" className="text-[10px] font-medium capitalize">
                                                    {item.character_id}
                                                </Badge>
                                            </td>
                                            <td className="p-4 text-sm text-muted-foreground/80">
                                                <div className="line-clamp-2 max-w-md italic">
                                                    "{cleanThesisSnippet(item.thesis)}"
                                                </div>
                                            </td>
                                            <td className="p-4 text-center">
                                                <Badge
                                                    variant="outline"
                                                    className={`font-bold px-3 py-1 ${getVerdictColor(item.verdict)}`}
                                                >
                                                    {item.verdict}
                                                </Badge>
                                            </td>
                                            <td className="p-4 text-right text-xs text-muted-foreground whitespace-nowrap">
                                                {formatDate(item.generated_at)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    ) : (
                        <div className="p-12 text-center flex flex-col items-center gap-3">
                            <Lightbulb className="h-12 w-12 text-muted-foreground/30" />
                            <p className="text-muted-foreground">No theses found matching your search.</p>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}

function cleanThesisSnippet(text) {
    if (!text) return ''
    // Remove markdown symbols and trim
    return text.replace(/[#*`_\[\]]/g, '').slice(0, 200).trim() + (text.length > 200 ? '...' : '')
}

function getVerdictColor(verdict) {
    switch (verdict) {
        case 'BUY':
            return 'border-green-500 text-green-500 bg-green-500/10'
        case 'WATCH':
            return 'border-yellow-500 text-yellow-500 bg-yellow-500/10'
        case 'AVOID':
            return 'border-red-500 text-red-500 bg-red-500/10'
        default:
            return 'border-muted text-muted-foreground bg-muted/10'
    }
}

function formatDate(dateStr) {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
    })
}
