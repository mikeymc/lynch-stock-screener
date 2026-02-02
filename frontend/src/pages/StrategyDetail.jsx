import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Play, Settings, Activity, Calendar, DollarSign, TrendingUp, TrendingDown, MessageSquare, Wallet } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import ReactMarkdown from 'react-markdown'
import { format } from 'date-fns'
import { Line } from 'react-chartjs-2'

function StrategyDetail() {
    const { id } = useParams()
    const navigate = useNavigate()
    const [strategy, setStrategy] = useState(null)
    const [performance, setPerformance] = useState([])
    const [runs, setRuns] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [activeRunId, setActiveRunId] = useState(null)

    useEffect(() => {
        const fetchDetail = async () => {
            try {
                const response = await fetch(`/api/strategies/${id}`)
                if (!response.ok) {
                    throw new Error('Failed to fetch strategy details')
                }
                const data = await response.json()
                setStrategy(data.strategy)
                setPerformance(data.performance)
                setRuns(data.runs)
                if (data.runs.length > 0) {
                    setActiveRunId(data.runs[0].id)
                }
            } catch (err) {
                console.error(err)
                setError(err.message)
            } finally {
                setLoading(false)
            }
        }
        fetchDetail()
    }, [id])

    // Chart Data Preparation
    const chartData = {
        labels: performance.map(p => format(new Date(p.snapshot_date), 'MMM d')),
        datasets: [
            {
                label: 'Portfolio Return',
                data: performance.map(p => p.portfolio_return_pct),
                borderColor: 'rgb(34, 197, 94)', // Green
                backgroundColor: 'rgba(34, 197, 94, 0.1)',
                fill: true,
                tension: 0.3
            },
            {
                label: 'S&P 500',
                data: performance.map(p => p.spy_return_pct),
                borderColor: 'rgb(148, 163, 184)', // Slate
                borderDash: [5, 5],
                fill: false,
                tension: 0.3
            }
        ]
    }

    const chartOptions = {
        responsive: true,
        plugins: {
            legend: {
                position: 'top',
            },
            tooltip: {
                mode: 'index',
                intersect: false,
            },
        },
        scales: {
            y: {
                title: {
                    display: true,
                    text: 'Return (%)'
                }
            }
        }
    }

    if (loading) return <DetailSkeleton />
    if (error) return <div className="p-10 text-center text-red-500">Error: {error}</div>
    if (!strategy) return <div className="p-10 text-center">Strategy not found</div>

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="icon" onClick={() => navigate('/strategies')}>
                        <ArrowLeft className="h-4 w-4" />
                    </Button>
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight">{strategy.name}</h1>
                        <p className="text-muted-foreground">{strategy.description || 'Autonomous Investment Strategy'}</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Badge variant={strategy.enabled ? "success" : "secondary"}>
                        {strategy.enabled ? 'Active' : 'Paused'}
                    </Badge>
                    <Button variant="outline" size="sm" onClick={() => navigate(`/portfolios/${strategy.portfolio_id}`)}>
                        <Wallet className="h-4 w-4 mr-2" />
                        View Portfolio
                    </Button>
                    <Button variant="outline" size="sm">
                        <Settings className="h-4 w-4 mr-2" />
                        Configure
                    </Button>
                    <Button size="sm">
                        <Play className="h-4 w-4 mr-2" />
                        Run Now
                    </Button>
                </div>
            </div>

            {/* Metrics Overview */}
            <div className="grid gap-4 md:grid-cols-4">
                <MetricCard
                    title="Total Return"
                    value={performance.length > 0 ? `${performance[performance.length - 1].portfolio_return_pct?.toFixed(2)}%` : '0%'}
                    icon={<DollarSign className="h-4 w-4 text-muted-foreground" />}
                />
                <MetricCard
                    title="Alpha vs SPY"
                    value={performance.length > 0 ? `${performance[performance.length - 1].alpha?.toFixed(2)}%` : '0%'}
                    icon={<Activity className="h-4 w-4 text-muted-foreground" />}
                />
                <MetricCard
                    title="Total Runs"
                    value={runs.length}
                    icon={<Play className="h-4 w-4 text-muted-foreground" />}
                />
                <MetricCard
                    title="Last Run"
                    value={runs.length > 0 ? format(new Date(runs[0].started_at), 'MMM d') : '-'}
                    icon={<Calendar className="h-4 w-4 text-muted-foreground" />}
                />
            </div>

            {/* Main Content Tabs */}
            <Tabs defaultValue="performance" className="space-y-4">
                <TabsList>
                    <TabsTrigger value="performance">Performance</TabsTrigger>
                    <TabsTrigger value="history">Run History</TabsTrigger>
                    <TabsTrigger value="decisions">Decisions Log</TabsTrigger>
                </TabsList>

                <TabsContent value="performance" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle>Performance vs Benchmark</CardTitle>
                            <CardDescription>Comparing strategy returns against S&P 500 (SPY)</CardDescription>
                        </CardHeader>
                        <CardContent className="h-[400px]">
                            {performance.length > 0 ? (
                                <Line data={chartData} options={chartOptions} />
                            ) : (
                                <div className="h-full flex items-center justify-center text-muted-foreground">
                                    No performance data available yet.
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="history">
                    <Card>
                        <CardHeader>
                            <CardTitle>Execution History</CardTitle>
                            <CardDescription>Recent strategy execution runs</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Date</TableHead>
                                        <TableHead>Status</TableHead>
                                        <TableHead>Screened</TableHead>
                                        <TableHead>Scored</TableHead>
                                        <TableHead>Trades</TableHead>
                                        <TableHead>Actions</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {runs.map((run) => (
                                        <TableRow key={run.id}>
                                            <TableCell>{format(new Date(run.started_at), 'MMM d, yyyy HH:mm')}</TableCell>
                                            <TableCell>
                                                <Badge variant={run.status === 'completed' ? 'success' : 'default'} className="capitalize">
                                                    {run.status}
                                                </Badge>
                                            </TableCell>
                                            <TableCell>{run.stocks_screened}</TableCell>
                                            <TableCell>{run.stocks_scored}</TableCell>
                                            <TableCell>{run.trades_executed}</TableCell>
                                            <TableCell>
                                                <Button variant="ghost" size="sm" onClick={() => setActiveRunId(run.id)}>
                                                    View
                                                </Button>
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                    {runs.length === 0 && (
                                        <TableRow>
                                            <TableCell colSpan={6} className="text-center py-6 text-muted-foreground">
                                                No runs recorded yet.
                                            </TableCell>
                                        </TableRow>
                                    )}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="decisions">
                    <DecisionsView runId={activeRunId} runs={runs} onRunChange={setActiveRunId} />
                </TabsContent>
            </Tabs>
        </div>
    )
}

function MetricCard({ title, value, icon }) {
    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{title}</CardTitle>
                {icon}
            </CardHeader>
            <CardContent>
                <div className="text-2xl font-bold">{value}</div>
            </CardContent>
        </Card>
    )
}

function DetailSkeleton() {
    return (
        <div className="space-y-6">
            <div className="flex justify-between">
                <Skeleton className="h-10 w-64" />
                <Skeleton className="h-10 w-32" />
            </div>
            <div className="grid gap-4 md:grid-cols-4">
                {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-24 w-full" />)}
            </div>
            <Skeleton className="h-[400px] w-full" />
        </div>
    )
}

function DecisionsView({ runId, runs, onRunChange }) {
    const [decisions, setDecisions] = useState([])
    const [loading, setLoading] = useState(false)
    const [filter, setFilter] = useState('ALL')

    useEffect(() => {
        if (!runId) return

        const fetchDecisions = async () => {
            setLoading(true)
            try {
                const url = `/api/strategies/runs/${runId}/decisions`;
                const response = await fetch(url)
                if (response.ok) {
                    const data = await response.json()
                    setDecisions(data)
                }
            } catch (error) {
                console.error("Failed to fetch decisions", error)
            } finally {
                setLoading(false)
            }
        }
        fetchDecisions()
    }, [runId])

    const filteredDecisions = decisions.filter(d => {
        if (filter === 'ALL') return true
        if (filter === 'BUY') return d.final_decision === 'BUY'
        if (filter === 'SKIP') return d.final_decision === 'SKIP' || d.final_decision === 'HOLD' || d.final_decision === 'AVOID' || d.final_decision === 'WATCH'
        if (filter === 'SELL') return d.final_decision === 'SELL'
        return true
    })

    if (!runId && runs.length === 0) {
        return <div className="p-8 text-center text-muted-foreground">No runs available to view decisions.</div>
    }

    if (!runId) {
        return <div className="p-8 text-center text-muted-foreground">Select a run to view decisions.</div>
    }

    return (
        <div className="grid grid-cols-12 gap-6">
            {/* Sidebar: Run Selector */}
            <div className="col-span-3 border-r pr-4 h-[600px]">
                <h3 className="font-semibold mb-4 px-2">Select Run</h3>
                <ScrollArea className="h-full">
                    <div className="space-y-1">
                        {runs.map(run => (
                            <div
                                key={run.id}
                                className={`px-3 py-2 rounded-md text-sm cursor-pointer hover:bg-accent ${run.id === runId ? 'bg-accent font-medium' : ''}`}
                                onClick={() => onRunChange(run.id)}
                            >
                                <div className="flex justify-between">
                                    <span>{format(new Date(run.started_at), 'MMM d, HH:mm')}</span>
                                    <span className="text-muted-foreground">{run.trades_executed} trades</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </ScrollArea>
            </div>

            {/* Main: Decisions List */}
            <div className="col-span-9">
                <div className="flex justify-between items-center mb-4">
                    <h3 className="font-semibold">Decisions Log ({filteredDecisions.length})</h3>
                    <Tabs value={filter} onValueChange={setFilter} className="w-[400px]">
                        <TabsList className="grid w-full grid-cols-4">
                            <TabsTrigger value="ALL">All</TabsTrigger>
                            <TabsTrigger value="BUY">Buy</TabsTrigger>
                            <TabsTrigger value="SKIP">Skip</TabsTrigger>
                            <TabsTrigger value="SELL">Sell</TabsTrigger>
                        </TabsList>
                    </Tabs>
                </div>

                {loading ? (
                    <div className="space-y-4">
                        <Skeleton className="h-32 w-full" />
                        <Skeleton className="h-32 w-full" />
                    </div>
                ) : filteredDecisions.length === 0 ? (
                    <div className="text-center p-8 text-muted-foreground border rounded-lg border-dashed">
                        No decisions found for this filter.
                    </div>
                ) : (
                    <div className="space-y-4">
                        {filteredDecisions.map(decision => (
                            <DecisionCard key={decision.id} decision={decision} />
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}

function DecisionCard({ decision }) {
    const isBuy = decision.final_decision === 'BUY'
    const isSkip = decision.final_decision === 'SKIP' || decision.final_decision === 'HOLD'
    const [showDeliberation, setShowDeliberation] = useState(false)

    // Truncate logic
    // Prefer thesis_full for AI runs, fallback to decision_reasoning (heuristic)
    const rawReasoning = decision.thesis_full || decision.decision_reasoning || ''
    const isLong = rawReasoning.length > 300

    return (
        <Card className={`border-l-4 ${isBuy ? 'border-l-green-500' : 'border-l-muted'}`}>
            <CardHeader className="py-3">
                <div className="flex justify-between items-center">
                    <div className="flex items-center gap-2">
                        <Badge variant="outline" className="font-bold">{decision.symbol}</Badge>
                    </div>
                    <Badge variant={isBuy ? 'success' : 'secondary'}>
                        {decision.final_decision}
                    </Badge>
                </div>
            </CardHeader>
            <CardContent className="py-3 pt-0 text-sm">
                <div className="grid grid-cols-2 gap-4 mb-3">
                    <div className="bg-muted/30 p-2 rounded">
                        <span className="font-semibold text-xs block mb-1">LYNCH</span>
                        <div className="flex justify-between">
                            <span>Score: {decision.lynch_score?.toFixed(0)}</span>
                            <span className="text-muted-foreground">{decision.lynch_status}</span>
                        </div>
                    </div>
                    <div className="bg-muted/30 p-2 rounded">
                        <span className="font-semibold text-xs block mb-1">BUFFETT</span>
                        <div className="flex justify-between">
                            <span>Score: {decision.buffett_score?.toFixed(0)}</span>
                            <span className="text-muted-foreground">{decision.buffett_status}</span>
                        </div>
                    </div>
                </div>

                {decision.decision_reasoning && (
                    <div className="bg-muted/50 p-3 rounded-md mb-2 border border-border">
                        <div className="flex justify-between items-center mb-2">
                            <div className="flex items-center gap-2 text-muted-foreground">
                                <MessageSquare className="h-3 w-3" />
                                <span className="font-bold text-[10px] uppercase tracking-wider">Deliberation</span>
                            </div>
                            {isLong && (
                                <Badge
                                    variant="outline"
                                    className={`text-[10px] font-bold px-2 py-0 border-transparent ${decision.consensus_verdict === 'BUY' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' :
                                        decision.consensus_verdict === 'AVOID' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                                            'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-400'
                                        }`}
                                >
                                    Consensus: {decision.consensus_verdict || decision.final_decision}
                                </Badge>
                            )}
                        </div>

                        {isLong ? (
                            <Button
                                variant="outline"
                                size="sm"
                                className="w-full text-xs h-7 font-bold border-primary/40 text-primary bg-white dark:bg-slate-900 shadow-sm hover:bg-primary hover:text-primary-foreground transition-all"
                                onClick={() => setShowDeliberation(true)}
                            >
                                Review deliberation
                            </Button>
                        ) : (
                            <p className="text-foreground leading-relaxed whitespace-pre-line text-xs">
                                {rawReasoning}
                            </p>
                        )}
                    </div>
                )}

                <Dialog open={showDeliberation} onOpenChange={setShowDeliberation}>
                    <DialogContent className="max-w-3xl max-h-[85vh] p-0 flex flex-col overflow-hidden border-border bg-background shadow-2xl">
                        <DialogHeader className="p-6 pb-4 border-b">
                            <div className="flex items-center gap-3">
                                <div className="p-2 rounded-lg bg-primary text-primary-foreground">
                                    <MessageSquare size={20} />
                                </div>
                                <div>
                                    <DialogTitle className="text-xl font-bold">Analysis Deliberation: {decision.symbol}</DialogTitle>
                                    <DialogDescription>
                                        Qualitative debate between Lynch and Buffett agents
                                    </DialogDescription>
                                </div>
                            </div>
                        </DialogHeader>
                        <ScrollArea className="h-[calc(85vh-180px)] w-full border-b">
                            <div className="p-8 prose prose-sm max-w-none dark:prose-invert">
                                <ReactMarkdown>{rawReasoning}</ReactMarkdown>
                            </div>
                        </ScrollArea>
                        <DialogFooter className="border-t p-4 px-6 bg-muted/30">
                            <Button variant="outline" size="sm" onClick={() => setShowDeliberation(false)}>
                                Close
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            </CardContent>
        </Card>
    )
}

export default StrategyDetail
