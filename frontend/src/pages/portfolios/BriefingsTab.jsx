// ABOUTME: Strategy run briefings tab for autonomous portfolios
// ABOUTME: Displays briefing cards with stats pipeline, trade details, and AI executive summaries

import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible"
import { Skeleton } from "@/components/ui/skeleton"
import { Separator } from "@/components/ui/separator"
import {
    ChevronDown,
    TrendingUp,
    TrendingDown,
    Filter,
    BarChart3,
    FileText,
    ArrowLeftRight,
    ArrowRight,
    Package,
} from 'lucide-react'

const API_BASE = '/api'

export default function BriefingsTab({ portfolioId }) {
    const [briefings, setBriefings] = useState([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        if (!portfolioId) return

        setLoading(true)
        fetch(`${API_BASE}/portfolios/${portfolioId}/briefings`, { credentials: 'include' })
            .then(res => res.json())
            .then(data => {
                setBriefings(data)
                setLoading(false)
            })
            .catch(() => setLoading(false))
    }, [portfolioId])

    if (loading) {
        return (
            <div className="space-y-4">
                {[1, 2].map(i => (
                    <Card key={i}>
                        <CardContent className="pt-6 space-y-3">
                            <Skeleton className="h-4 w-48" />
                            <Skeleton className="h-16 w-full" />
                            <Skeleton className="h-8 w-full" />
                        </CardContent>
                    </Card>
                ))}
            </div>
        )
    }

    if (briefings.length === 0) {
        return (
            <Card>
                <CardContent className="py-12 text-center text-muted-foreground">
                    <FileText className="h-12 w-12 mx-auto mb-4 opacity-20" />
                    <p>No briefings yet. Briefings are generated after each strategy run.</p>
                </CardContent>
            </Card>
        )
    }

    return (
        <div className="space-y-4">
            {briefings.map(briefing => (
                <BriefingCard key={briefing.id} briefing={briefing} />
            ))}
        </div>
    )
}

function BriefingCard({ briefing }) {
    const alpha = briefing.alpha || 0
    const isPositiveAlpha = alpha >= 0
    const date = briefing.generated_at
        ? new Date(briefing.generated_at).toLocaleDateString('en-US', {
            weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
            hour: 'numeric', minute: '2-digit',
        })
        : 'Unknown date'

    const buys = safeParse(briefing.buys_json)
    const sells = safeParse(briefing.sells_json)
    const holds = safeParse(briefing.holds_json)

    return (
        <Card>
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-medium text-muted-foreground">
                        {date}
                    </CardTitle>
                    <div className="flex items-center gap-3">
                        {briefing.portfolio_return_pct != null && (
                            <span className={`text-sm font-medium ${briefing.portfolio_return_pct >= 0
                                    ? 'text-emerald-600 dark:text-emerald-400'
                                    : 'text-red-600 dark:text-red-400'
                                }`}>
                                {briefing.portfolio_return_pct >= 0 ? '+' : ''}
                                {briefing.portfolio_return_pct.toFixed(2)}% return
                            </span>
                        )}
                        <Badge
                            variant={isPositiveAlpha ? 'success' : 'destructive'}
                            className="tabular-nums"
                        >
                            {isPositiveAlpha ? '+' : ''}{alpha.toFixed(2)}% alpha
                        </Badge>
                    </div>
                </div>
            </CardHeader>

            <CardContent className="space-y-4">
                {/* Executive Summary */}
                {briefing.executive_summary && (
                    <p className="text-sm leading-relaxed">
                        {briefing.executive_summary}
                    </p>
                )}

                {/* Stats Pipeline */}
                <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/50 rounded-md px-3 py-2">
                    <PipelineStat icon={Filter} label="Screened" value={briefing.stocks_screened} />
                    <ArrowRight className="h-3 w-3 opacity-40 shrink-0" />
                    <PipelineStat icon={BarChart3} label="Scored" value={briefing.stocks_scored} />
                    <ArrowRight className="h-3 w-3 opacity-40 shrink-0" />
                    <PipelineStat icon={FileText} label="Theses" value={briefing.theses_generated} />
                    <ArrowRight className="h-3 w-3 opacity-40 shrink-0" />
                    <PipelineStat icon={ArrowLeftRight} label="Trades" value={briefing.trades_executed} />
                </div>

                {/* Trade Details */}
                {buys.length > 0 && (
                    <TradeSection
                        title="Buys"
                        items={buys}
                        badgeVariant="success"
                        renderDetail={(item) => (
                            <>
                                {item.shares && item.price && (
                                    <span className="text-xs text-muted-foreground">
                                        {item.shares} shares @ ${item.price.toFixed(2)}
                                    </span>
                                )}
                            </>
                        )}
                    />
                )}

                {sells.length > 0 && (
                    <TradeSection
                        title="Sells"
                        items={sells}
                        badgeVariant="destructive"
                        renderDetail={(item) => (
                            <>
                                {item.shares && item.price && (
                                    <span className="text-xs text-muted-foreground">
                                        {item.shares} shares @ ${item.price.toFixed(2)}
                                    </span>
                                )}
                            </>
                        )}
                    />
                )}

                {holds.length > 0 && (
                    <TradeSection
                        title="Holds"
                        items={holds}
                        badgeVariant="secondary"
                        renderDetail={() => null}
                    />
                )}
            </CardContent>
        </Card>
    )
}

function PipelineStat({ icon: Icon, label, value }) {
    return (
        <div className="flex items-center gap-1.5 shrink-0">
            <Icon className="h-3.5 w-3.5 opacity-60" />
            <span className="font-medium tabular-nums">{value ?? 0}</span>
            <span className="hidden sm:inline opacity-60">{label}</span>
        </div>
    )
}

function TradeSection({ title, items, badgeVariant, renderDetail }) {
    const [open, setOpen] = useState(false)

    return (
        <Collapsible open={open} onOpenChange={setOpen}>
            <CollapsibleTrigger className="flex items-center gap-2 text-sm font-medium w-full text-left hover:opacity-80 transition-opacity">
                <ChevronDown className={`h-4 w-4 transition-transform ${open ? '' : '-rotate-90'}`} />
                {title}
                <Badge variant={badgeVariant} className="text-[10px] px-1.5 py-0">
                    {items.length}
                </Badge>
            </CollapsibleTrigger>
            <CollapsibleContent>
                <div className="mt-2 space-y-2 pl-6">
                    {items.map((item, i) => (
                        <div key={item.symbol || i} className="flex items-start gap-2">
                            <Link
                                to={`/stock/${item.symbol}`}
                                className="font-mono text-sm font-medium text-primary hover:underline shrink-0"
                            >
                                {item.symbol}
                            </Link>
                            <div className="flex flex-col gap-0.5">
                                {renderDetail(item)}
                                {item.reasoning && (
                                    <span className="text-xs text-muted-foreground leading-snug">
                                        {item.reasoning}
                                    </span>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            </CollapsibleContent>
        </Collapsible>
    )
}

function safeParse(jsonStr) {
    if (!jsonStr) return []
    try {
        return JSON.parse(jsonStr)
    } catch {
        return []
    }
}
