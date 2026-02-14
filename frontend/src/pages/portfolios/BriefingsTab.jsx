// ABOUTME: Strategy run briefings tab for autonomous portfolios
// ABOUTME: Displays briefing cards with markdown summaries, trades table, and score-enriched holds

import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
    Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from "@/components/ui/table"
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible"
import { Skeleton } from "@/components/ui/skeleton"
import {
    ChevronDown,
    Filter,
    BarChart3,
    FileText,
    ArrowLeftRight,
    ArrowRight,
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
    const trades = [
        ...sells.map(s => ({ ...s, action: 'SELL' })),
        ...buys.map(b => ({ ...b, action: 'BUY' })),
    ]

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
                {/* Executive Summary (markdown) */}
                {briefing.executive_summary && (
                    <div className="prose prose-sm max-w-none dark:prose-invert">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {briefing.executive_summary}
                        </ReactMarkdown>
                    </div>
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

                {/* Trades Table */}
                {trades.length > 0 && <TradesTable trades={trades} />}

                {/* Holds */}
                {holds.length > 0 && <HoldsSection holds={holds} />}
            </CardContent>
        </Card>
    )
}

function ScoreBadge({ score, status }) {
    if (score == null) return <span className="text-xs text-muted-foreground">—</span>

    const colorClass = status === 'excellent' ? 'text-emerald-600 dark:text-emerald-400'
        : status === 'good' ? 'text-emerald-600/80 dark:text-emerald-400/80'
        : status === 'fair' ? 'text-yellow-600 dark:text-yellow-400'
        : 'text-red-600 dark:text-red-400'

    return (
        <span className={`text-xs font-medium tabular-nums ${colorClass}`}>
            {score.toFixed(0)}
        </span>
    )
}

function TradesTable({ trades }) {
    return (
        <div>
            <h4 className="text-sm font-medium mb-2">Trades</h4>
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead className="w-[60px]">Action</TableHead>
                        <TableHead>Symbol</TableHead>
                        <TableHead className="text-right">Shares</TableHead>
                        <TableHead className="text-right">Price</TableHead>
                        <TableHead className="text-right">Value</TableHead>
                        <TableHead className="text-right">Lynch</TableHead>
                        <TableHead className="text-right">Buffett</TableHead>
                        <TableHead className="text-right">DCF Upside</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {trades.map((trade, i) => (
                        <TableRow key={`${trade.action}-${trade.symbol}-${i}`}>
                            <TableCell>
                                <Badge
                                    variant={trade.action === 'BUY' ? 'success' : 'destructive'}
                                    className="text-[10px] px-1.5 py-0"
                                >
                                    {trade.action}
                                </Badge>
                            </TableCell>
                            <TableCell>
                                <Link
                                    to={`/stock/${trade.symbol}`}
                                    className="font-mono text-sm font-medium text-primary hover:underline"
                                >
                                    {trade.symbol}
                                </Link>
                            </TableCell>
                            <TableCell className="text-right tabular-nums text-sm">
                                {trade.shares ?? '—'}
                            </TableCell>
                            <TableCell className="text-right tabular-nums text-sm">
                                {trade.price != null ? `$${trade.price.toFixed(2)}` : '—'}
                            </TableCell>
                            <TableCell className="text-right tabular-nums text-sm">
                                {trade.position_value != null
                                    ? `$${trade.position_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                                    : '—'}
                            </TableCell>
                            <TableCell className="text-right">
                                <ScoreBadge score={trade.lynch_score} status={trade.lynch_status} />
                            </TableCell>
                            <TableCell className="text-right">
                                <ScoreBadge score={trade.buffett_score} status={trade.buffett_status} />
                            </TableCell>
                            <TableCell className="text-right">
                                <UpsideBadge pct={trade.dcf_upside_pct} />
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </div>
    )
}

function UpsideBadge({ pct }) {
    if (pct == null) return <span className="text-xs text-muted-foreground">—</span>

    const colorClass = pct >= 10 ? 'text-emerald-600 dark:text-emerald-400'
        : pct >= 0 ? 'text-yellow-600 dark:text-yellow-400'
        : 'text-red-600 dark:text-red-400'

    return (
        <span className={`text-xs font-medium tabular-nums ${colorClass}`}>
            {pct >= 0 ? '+' : ''}{pct.toFixed(1)}%
        </span>
    )
}

function HoldsSection({ holds }) {
    const [open, setOpen] = useState(false)

    return (
        <Collapsible open={open} onOpenChange={setOpen}>
            <CollapsibleTrigger className="flex items-center gap-2 text-sm font-medium w-full text-left hover:opacity-80 transition-opacity">
                <ChevronDown className={`h-4 w-4 transition-transform ${open ? '' : '-rotate-90'}`} />
                Holds
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                    {holds.length}
                </Badge>
            </CollapsibleTrigger>
            <CollapsibleContent>
                <div className="mt-2 space-y-2 pl-6">
                    {holds.map((item, i) => (
                        <div key={item.symbol || i} className="flex items-center gap-3">
                            <Link
                                to={`/stock/${item.symbol}`}
                                className="font-mono text-sm font-medium text-primary hover:underline shrink-0 w-16"
                            >
                                {item.symbol}
                            </Link>
                            {item.consensus_verdict && (
                                <Badge
                                    variant={item.consensus_verdict === 'BUY' ? 'success'
                                        : item.consensus_verdict === 'AVOID' ? 'destructive'
                                        : 'secondary'}
                                    className="text-[10px] px-1.5 py-0"
                                >
                                    {item.consensus_verdict}
                                </Badge>
                            )}
                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                {item.lynch_score != null && (
                                    <span>L: <ScoreBadge score={item.lynch_score} status={item.lynch_status} /></span>
                                )}
                                {item.buffett_score != null && (
                                    <span>B: <ScoreBadge score={item.buffett_score} status={item.buffett_status} /></span>
                                )}
                                {item.position_value != null && (
                                    <span className="text-muted-foreground">
                                        ${item.position_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
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

function PipelineStat({ icon: Icon, label, value }) {
    return (
        <div className="flex items-center gap-1.5 shrink-0">
            <Icon className="h-3.5 w-3.5 opacity-60" />
            <span className="font-medium tabular-nums">{value ?? 0}</span>
            <span className="hidden sm:inline opacity-60">{label}</span>
        </div>
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
