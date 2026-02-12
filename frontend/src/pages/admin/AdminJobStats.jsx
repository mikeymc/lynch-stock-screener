import { useState, useEffect, useMemo } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { formatDistanceToNow, format } from 'date-fns'
import { BarChart3, Clock, CheckCircle2, XCircle, PlayCircle, Loader2, RefreshCw, Activity, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react'
import { Line } from 'react-chartjs-2'
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
    TimeScale
} from 'chart.js'
import 'chartjs-adapter-date-fns'

ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
    TimeScale
)

const API_BASE = '/api'

export default function AdminJobStats() {
    const [hours, setHours] = useState('24')
    const [jobType, setJobType] = useState('all')
    const [data, setData] = useState({ stats: [], jobs: [], time_range: 24 })
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [selectedTrendTypes, setSelectedTrendTypes] = useState(new Set())
    const [sortConfig, setSortConfig] = useState({ key: 'total_runs', direction: 'desc' })
    const [historySortConfig, setHistorySortConfig] = useState({ key: 'id', direction: 'desc' })

    // Update selected types when data changes for the first time
    useEffect(() => {
        if (data.stats.length > 0 && selectedTrendTypes.size === 0) {
            setSelectedTrendTypes(new Set(data.stats.map(s => s.job_type).slice(0, 3)))
        }
    }, [data.stats])

    const jobTypeColors = {
        'full_screening': 'rgb(99, 102, 241)', // Indigo
        'single_stock_refresh': 'rgb(34, 197, 94)', // Green
        'check_alerts': 'rgb(249, 115, 22)', // Orange
        'strategy_execution': 'rgb(236, 72, 153)', // Pink
        'earnings_transcript_refresh': 'rgb(168, 85, 247)', // Purple
        'market_daily_sync': 'rgb(59, 130, 246)', // Blue
        'default': 'rgb(107, 114, 128)' // Gray
    }

    const getJobColor = (type) => jobTypeColors[type] || jobTypeColors.default

    const toggleTrendType = (type) => {
        setSelectedTrendTypes(prev => {
            const next = new Set(prev)
            if (next.has(type)) {
                if (next.size > 1) next.delete(type)
            } else {
                next.add(type)
            }
            return next
        })
    }

    const fetchStats = async (isManual = false) => {
        if (isManual) setRefreshing(true)
        else setLoading(true)

        try {
            const response = await fetch(`${API_BASE}/admin/job_stats?hours=${hours}&job_type=${jobType}`, {
                credentials: 'include'
            })
            if (!response.ok) throw new Error('Failed to fetch job stats')
            const result = await response.json()
            setData(result)
        } catch (err) {
            console.error('Error fetching job stats:', err)
        } finally {
            setLoading(false)
            setRefreshing(false)
        }
    }

    useEffect(() => {
        fetchStats()
    }, [hours, jobType])

    const summaryStats = useMemo(() => {
        const jobs = data.jobs || []
        const completed = jobs.filter(j => j.status === 'completed')
        const failed = jobs.filter(j => j.status === 'failed')
        const running = jobs.filter(j => j.status === 'running' || j.status === 'claimed')

        const totalDuration = completed.reduce((sum, j) => {
            if (j.started_at && j.completed_at) {
                return sum + (new Date(j.completed_at) - new Date(j.started_at))
            }
            return sum
        }, 0)

        const pending = jobs.filter(j => j.status === 'pending')
        const avgDuration = completed.length > 0 ? totalDuration / completed.length : 0
        const successRate = jobs.length > 0 ? (completed.length / jobs.length) * 100 : 0

        return {
            total: jobs.length,
            successRate,
            avgDuration,
            running: running.length,
            pending: pending.length,
            failed: failed.length
        }
    }, [data.jobs])

    const formatDuration = (ms) => {
        if (!ms || ms < 0) return 'N/A'
        const seconds = Math.floor(ms / 1000)
        const minutes = Math.floor(seconds / 60)
        if (minutes > 0) return `${minutes}m ${seconds % 60}s`
        return `${seconds}s`
    }

    const getStatusBadge = (status) => {
        switch (status) {
            case 'completed': return <Badge variant="success" className="bg-green-500/10 text-green-500 border-green-500/20">Completed</Badge>
            case 'failed': return <Badge variant="destructive">Failed</Badge>
            case 'running':
            case 'claimed': return <Badge className="bg-blue-500/10 text-blue-500 border-blue-500/20 animate-pulse">Running</Badge>
            default: return <Badge variant="secondary">{status}</Badge>
        }
    }

    const sortedStats = useMemo(() => {
        const stats = [...(data.stats || [])]
        if (!sortConfig.key) return stats

        return stats.sort((a, b) => {
            let aValue, bValue;

            if (sortConfig.key === 'success_rate') {
                aValue = a.total_runs > 0 ? a.completed_runs / a.total_runs : 0
                bValue = b.total_runs > 0 ? b.completed_runs / b.total_runs : 0
            } else {
                aValue = a[sortConfig.key]
                bValue = b[sortConfig.key]
            }

            if (aValue < bValue) return sortConfig.direction === 'asc' ? -1 : 1
            if (aValue > bValue) return sortConfig.direction === 'asc' ? 1 : -1
            return 0
        })
    }, [data.stats, sortConfig])

    const handleSort = (key) => {
        setSortConfig(prev => ({
            key,
            direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
        }))
    }

    const sortJobs = (jobs, config) => {
        if (!config.key) return jobs
        return [...jobs].sort((a, b) => {
            let aValue, bValue
            if (config.key === 'duration') {
                aValue = a.started_at && a.completed_at ? new Date(a.completed_at) - new Date(a.started_at) : 0
                bValue = b.started_at && b.completed_at ? new Date(b.completed_at) - new Date(b.started_at) : 0
            } else {
                aValue = a[config.key]
                bValue = b[config.key]
            }
            if (aValue < bValue) return config.direction === 'asc' ? -1 : 1
            if (aValue > bValue) return config.direction === 'asc' ? 1 : -1
            return 0
        })
    }

    const sortedJobs = useMemo(() => sortJobs(data.jobs || [], historySortConfig), [data.jobs, historySortConfig])

    const handleHistorySort = (key) => {
        setHistorySortConfig(prev => ({
            key,
            direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
        }))
    }

    const SortIcon = ({ columnKey, config }) => {
        const activeConfig = config || sortConfig
        if (activeConfig.key !== columnKey) return <ArrowUpDown className="ml-1 h-3 w-3" />
        return activeConfig.direction === 'asc'
            ? <ArrowUp className="ml-1 h-3 w-3 text-primary" />
            : <ArrowDown className="ml-1 h-3 w-3 text-primary" />
    }

    // Timeline Calculation
    const timelineData = useMemo(() => {
        const jobs = (data.jobs || []).filter(j => j.started_at)
        if (jobs.length === 0) return null

        const startTimes = jobs.map(j => new Date(j.started_at).getTime())
        const endTimes = jobs.map(j => j.completed_at ? new Date(j.completed_at).getTime() : Date.now())

        const rawMin = Math.min(...startTimes)
        const rawMax = Math.max(...endTimes)

        // Snap start to previous 12-hour mark (00:00, 12:00)
        const startDate = new Date(rawMin)
        startDate.setMinutes(0, 0, 0)
        startDate.setHours(Math.floor(startDate.getHours() / 12) * 12)

        // Snap end to next 12-hour mark
        const endDate = new Date(rawMax)
        endDate.setMinutes(0, 0, 0)
        endDate.setHours(Math.ceil(endDate.getHours() / 12) * 12)

        const minTime = startDate.getTime()
        const maxTime = endDate.getTime()
        const range = maxTime - minTime

        const jobsByType = {}
        jobs.forEach(job => {
            if (!jobsByType[job.job_type]) jobsByType[job.job_type] = []
            jobsByType[job.job_type].push(job)
        })

        return {
            minTime,
            maxTime,
            range,
            jobsByType: Object.entries(jobsByType).sort((a, b) => b[1].length - a[1].length),
            labels: (() => {
                const labels = []
                const interval = 12 * 60 * 60 * 1000 // 12 hours

                let currentTick = minTime
                while (currentTick <= maxTime) {
                    const dateObj = new Date(currentTick)
                    const formatStr = range > 24 * 60 * 60 * 1000 ? 'HH:mm MMM d' : 'HH:mm'
                    labels.push({
                        time: currentTick,
                        text: format(dateObj, formatStr),
                        position: ((currentTick - minTime) / range) * 100
                    })
                    currentTick += interval
                }
                return labels
            })()
        }
    }, [data.jobs])

    const trendChartData = useMemo(() => {
        const jobs = (data.jobs || [])
            .filter(j => j.status === 'completed' && j.started_at && j.completed_at)
            .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))

        const datasets = Array.from(selectedTrendTypes).map(type => {
            const typeJobs = jobs.filter(j => j.job_type === type)
            const color = getJobColor(type)

            return {
                label: type,
                data: typeJobs.map(j => ({
                    x: new Date(j.created_at),
                    y: (new Date(j.completed_at) - new Date(j.started_at)) / (1000 * 60)
                })),
                borderColor: color,
                backgroundColor: color.replace('rgb', 'rgba').replace(')', ', 0.5)'),
                tension: 0.3,
                pointRadius: 2,
                borderWidth: 2
            }
        })

        return { datasets }
    }, [data.jobs, selectedTrendTypes])

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Job Stats</h1>
                    <p className="text-muted-foreground">Background job performance and execution monitoring</p>
                </div>
            </div>

            {/* Summary Cards */}
            <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-6">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Total Jobs</CardTitle>
                        <Activity className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{summaryStats.total}</div>
                        <p className="text-xs text-muted-foreground">in selected timeframe</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Active Jobs</CardTitle>
                        <PlayCircle className="h-4 w-4 text-blue-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{summaryStats.running}</div>
                        <p className="text-xs text-muted-foreground">currently executing</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Pending Jobs</CardTitle>
                        <Clock className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{summaryStats.pending}</div>
                        <p className="text-xs text-muted-foreground">waiting for worker</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Failed Jobs</CardTitle>
                        <XCircle className="h-4 w-4 text-red-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-red-500">{summaryStats.failed}</div>
                        <p className="text-xs text-muted-foreground">in selected timeframe</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Success Rate</CardTitle>
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{summaryStats.successRate.toFixed(1)}%</div>
                        <p className="text-xs text-muted-foreground">completed successfully</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Avg Duration</CardTitle>
                        <Clock className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{formatDuration(summaryStats.avgDuration)}</div>
                        <p className="text-xs text-muted-foreground">per completed job</p>
                    </CardContent>
                </Card>
            </div>
            <Tabs defaultValue="history" className="space-y-6">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <TabsList>
                        <TabsTrigger value="history" className="flex items-center gap-2">
                            <Activity className="h-4 w-4" />
                            Job History
                        </TabsTrigger>
                        <TabsTrigger value="performance" className="flex items-center gap-2">
                            <BarChart3 className="h-4 w-4" />
                            Performance
                        </TabsTrigger>
                        <TabsTrigger value="timeline" className="flex items-center gap-2">
                            <Clock className="h-4 w-4" />
                            Timeline
                        </TabsTrigger>
                    </TabsList>

                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">Range:</span>
                            <Select value={hours} onValueChange={setHours}>
                                <SelectTrigger className="w-[140px]">
                                    <SelectValue placeholder="Time Range" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="1">Last 1 hour</SelectItem>
                                    <SelectItem value="6">Last 6 hours</SelectItem>
                                    <SelectItem value="24">Last 24 hours</SelectItem>
                                    <SelectItem value="168">Last 7 days</SelectItem>
                                    <SelectItem value="720">Last 30 days</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <Button
                            variant="outline"
                            size="icon"
                            onClick={() => fetchStats(true)}
                            disabled={refreshing}
                        >
                            {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                        </Button>
                    </div>
                </div>

                <TabsContent value="performance" className="space-y-6">
                    <div className="grid gap-6 lg:grid-cols-2">
                        {/* Job type stats */}
                        <Card className="col-span-1">
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <BarChart3 className="h-5 w-5" />
                                    Performance by Type
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="relative">
                                    <table className="w-full text-sm text-left">
                                        <thead className="text-xs text-muted-foreground uppercase bg-muted/50 border-b">
                                            <tr>
                                                <th className="px-4 py-3 cursor-pointer hover:text-foreground transition-colors" onClick={() => handleSort('job_type')}>
                                                    <div className="flex items-center">Type <SortIcon columnKey="job_type" /></div>
                                                </th>
                                                <th className="px-4 py-3 cursor-pointer hover:text-foreground transition-colors" onClick={() => handleSort('tier')}>
                                                    <div className="flex items-center">Tier <SortIcon columnKey="tier" /></div>
                                                </th>
                                                <th className="px-4 py-3 text-right cursor-pointer hover:text-foreground transition-colors" onClick={() => handleSort('total_runs')}>
                                                    <div className="flex items-center justify-end">Runs <SortIcon columnKey="total_runs" /></div>
                                                </th>
                                                <th className="px-4 py-3 text-right cursor-pointer hover:text-foreground transition-colors" onClick={() => handleSort('success_rate')}>
                                                    <div className="flex items-center justify-end">Success <SortIcon columnKey="success_rate" /></div>
                                                </th>
                                                <th className="px-4 py-3 text-right cursor-pointer hover:text-foreground transition-colors" onClick={() => handleSort('avg_duration_seconds')}>
                                                    <div className="flex items-center justify-end">Avg Dur <SortIcon columnKey="avg_duration_seconds" /></div>
                                                </th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y">
                                            {sortedStats.map((stat) => (
                                                <tr key={`${stat.job_type}-${stat.tier}`} className="hover:bg-muted/5">
                                                    <td className="px-4 py-3 font-medium">{stat.job_type}</td>
                                                    <td className="px-4 py-3">
                                                        <Badge variant="outline" className="font-mono text-[10px] uppercase">
                                                            {stat.tier}
                                                        </Badge>
                                                    </td>
                                                    <td className="px-4 py-3 text-right font-mono">{stat.total_runs}</td>
                                                    <td className="px-4 py-3 text-right">
                                                        {((stat.completed_runs / stat.total_runs) * 100).toFixed(0)}%
                                                    </td>
                                                    <td className="px-4 py-3 text-right font-mono">
                                                        {formatDuration(stat.avg_duration_seconds * 1000)}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </CardContent>
                        </Card>

                        <Card className="col-span-1">
                            <CardHeader>
                                <div className="flex justify-between items-start">
                                    <CardTitle className="flex items-center gap-2">
                                        <Activity className="h-5 w-5" />
                                        Duration Trends
                                    </CardTitle>
                                    <div className="flex flex-wrap gap-1 max-w-[240px] justify-end">
                                        {data.stats.map(stat => (
                                            <Badge
                                                key={stat.job_type}
                                                variant={selectedTrendTypes.has(stat.job_type) ? "default" : "outline"}
                                                className={`cursor-pointer transition-all text-[10px] px-1.5 py-0 ${selectedTrendTypes.has(stat.job_type)
                                                    ? ""
                                                    : "text-muted-foreground opacity-50 hover:opacity-100"
                                                    }`}
                                                style={{
                                                    borderColor: selectedTrendTypes.has(stat.job_type) ? getJobColor(stat.job_type) : undefined,
                                                    backgroundColor: selectedTrendTypes.has(stat.job_type) ? getJobColor(stat.job_type) : undefined
                                                }}
                                                onClick={() => toggleTrendType(stat.job_type)}
                                            >
                                                {stat.job_type}
                                            </Badge>
                                        ))}
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <div className="h-[250px]">
                                    <Line
                                        data={trendChartData}
                                        options={{
                                            responsive: true,
                                            maintainAspectRatio: false,
                                            scales: {
                                                x: {
                                                    type: 'time',
                                                    time: {
                                                        unit: 'hour',
                                                        stepSize: 12
                                                    },
                                                    ticks: {
                                                        maxRotation: 45,
                                                        minRotation: 45
                                                    },
                                                    grid: {
                                                        display: true,
                                                        color: 'rgba(156, 163, 175, 0.3)', // Significantly more visible
                                                        drawTicks: true,
                                                        lineWidth: 1
                                                    }
                                                },
                                                y: {
                                                    beginAtZero: true,
                                                    title: { display: true, text: 'Minutes' },
                                                    grid: {
                                                        display: true,
                                                        color: 'rgba(156, 163, 175, 0.2)', // More visible
                                                        lineWidth: 1
                                                    }
                                                }
                                            },
                                            plugins: {
                                                legend: {
                                                    display: true,
                                                    position: 'bottom',
                                                    labels: {
                                                        boxWidth: 8,
                                                        padding: 10,
                                                        font: { size: 10 }
                                                    }
                                                }
                                            }
                                        }}
                                    />
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </TabsContent>

                <TabsContent value="timeline">
                    {/* Timeline */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Clock className="h-5 w-5" />
                                Job Execution Timeline
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="overflow-hidden">
                            {!timelineData ? (
                                <div className="flex justify-center p-12 text-muted-foreground">No execution data available</div>
                            ) : (
                                <div className="flex flex-col h-[600px]">
                                    <div className="overflow-y-auto overflow-x-hidden custom-scrollbar flex-1 pr-1" style={{ scrollbarGutter: 'stable' }}>
                                        <div className="relative min-h-full">
                                            <div className="absolute inset-0 pointer-events-none flex gap-4">
                                                <div className="w-40 shrink-0 border-r border-transparent" /> {/* Invisible border to match axis width */}
                                                <div className="flex-1 relative pr-32"> {/* Restored padding for angled labels */}
                                                    {timelineData.labels.map((label, i) => (
                                                        <div
                                                            key={i}
                                                            className="h-full w-px bg-muted-foreground/10 border-l border-muted-foreground/5"
                                                            style={{ left: `${label.position}%`, position: 'absolute' }}
                                                        />
                                                    ))}
                                                </div>
                                            </div>

                                            {/* Timeline Rows */}
                                            <div className="space-y-4 relative">
                                                {timelineData.jobsByType.map(([type, jobs]) => (
                                                    <div key={type} className="flex gap-4 items-center">
                                                        {/* Job Type Label Column */}
                                                        <div className="w-40 shrink-0 text-xs font-semibold text-muted-foreground uppercase tracking-wider truncate" title={type}>
                                                            {type}
                                                        </div>

                                                        {/* Chart Area Column */}
                                                        <div className="flex-1 relative h-8 pr-32">
                                                            {/* Job Bar Container */}
                                                            <div className="relative h-full w-full bg-muted/20 rounded-md overflow-hidden ring-1 ring-inset ring-muted/30">
                                                                {jobs.map((job) => {
                                                                    const start = new Date(job.started_at).getTime()
                                                                    const end = job.completed_at ? new Date(job.completed_at).getTime() : Date.now()
                                                                    const left = ((start - timelineData.minTime) / timelineData.range) * 100
                                                                    const width = ((end - start) / timelineData.range) * 100

                                                                    return (
                                                                        <div
                                                                            key={job.id}
                                                                            className={`absolute top-1 bottom-1 rounded-sm border opacity-80 hover:opacity-100 transition-all cursor-pointer z-10 ${job.status === 'failed' ? 'bg-destructive/80 border-destructive' :
                                                                                (job.status === 'running' || job.status === 'claimed') ? 'bg-blue-500/80 border-blue-400 animate-pulse' :
                                                                                    'bg-indigo-500/80 border-indigo-400'
                                                                                }`}
                                                                            style={{ left: `${left}%`, width: `${Math.max(width, 0.5)}%` }}
                                                                            title={`${job.job_type}: ${job.status}\nDuration: ${formatDuration(end - start)}`}
                                                                        />
                                                                    )
                                                                })}
                                                            </div>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    </div>

                                    {/* Timeline X-Axis - Sticky at bottom */}
                                    <div className="relative pb-14 border-t border-muted/50 bg-background/50 backdrop-blur-sm z-10 shrink-0 pr-1" style={{ scrollbarGutter: 'stable' }}>
                                        <div className="flex gap-4">
                                            {/* Matching spacer for label column */}
                                            <div className="w-40 shrink-0 border-r border-transparent" />

                                            {/* Labels area aligned with chart data */}
                                            <div className="flex-1 relative pr-32"> {/* Match padding */}
                                                {timelineData.labels.map((label, i) => {
                                                    return (
                                                        <div
                                                            key={i}
                                                            className="absolute top-0 flex flex-col items-start"
                                                            style={{ left: `${label.position}%`, width: '0', overflow: 'visible' }}
                                                        >
                                                            <div className="h-1.5 w-px bg-muted-foreground/30 mb-1" />
                                                            <div className="rotate-[30deg] origin-top-left ml-px">
                                                                <span className="text-[10px] font-mono text-muted-foreground whitespace-nowrap pt-1 opacity-80">
                                                                    {label.text}
                                                                </span>
                                                            </div>
                                                        </div>
                                                    )
                                                })}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="history">
                    {/* Recent Jobs Table */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Activity className="h-5 w-5" />
                                Recent Job Executions
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="relative">
                                <table className="w-full text-sm text-left">
                                    <thead className="text-xs text-muted-foreground uppercase bg-muted/50 border-b">
                                        <tr>
                                            <th className="px-4 py-3 cursor-pointer hover:text-foreground transition-colors" onClick={() => handleHistorySort('id')}>
                                                <div className="flex items-center">Job ID <SortIcon columnKey="id" config={historySortConfig} /></div>
                                            </th>
                                            <th className="px-4 py-3 cursor-pointer hover:text-foreground transition-colors" onClick={() => handleHistorySort('job_type')}>
                                                <div className="flex items-center">Type <SortIcon columnKey="job_type" config={historySortConfig} /></div>
                                            </th>
                                            <th className="px-4 py-3">Params</th>
                                            <th className="px-4 py-3 cursor-pointer hover:text-foreground transition-colors" onClick={() => handleHistorySort('status')}>
                                                <div className="flex items-center">Status <SortIcon columnKey="status" config={historySortConfig} /></div>
                                            </th>
                                            <th className="px-4 py-3 text-right cursor-pointer hover:text-foreground transition-colors" onClick={() => handleHistorySort('duration')}>
                                                <div className="flex items-center justify-end">Duration <SortIcon columnKey="duration" config={historySortConfig} /></div>
                                            </th>
                                            <th className="px-4 py-3 text-right cursor-pointer hover:text-foreground transition-colors" onClick={() => handleHistorySort('created_at')}>
                                                <div className="flex items-center justify-end">Created <SortIcon columnKey="created_at" config={historySortConfig} /></div>
                                            </th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y">
                                        {sortedJobs.slice(0, 50).map((job) => {
                                            const duration = job.started_at && job.completed_at
                                                ? new Date(job.completed_at) - new Date(job.started_at)
                                                : null

                                            return (
                                                <tr key={job.id} className="hover:bg-muted/5">
                                                    <td className="px-4 py-3 font-mono text-xs">{job.id}</td>
                                                    <td className="px-4 py-3 font-medium">{job.job_type}</td>
                                                    <td className="px-4 py-3">
                                                        <div className="max-w-[200px] truncate font-mono text-[10px] text-muted-foreground" title={JSON.stringify(job.params)}>
                                                            {JSON.stringify(job.params)}
                                                        </div>
                                                    </td>
                                                    <td className="px-4 py-3">{getStatusBadge(job.status)}</td>
                                                    <td className="px-4 py-3 text-right font-mono">
                                                        {duration ? formatDuration(duration) : 'N/A'}
                                                    </td>
                                                    <td className="px-4 py-3 text-right text-muted-foreground">
                                                        {formatDistanceToNow(new Date(job.created_at), { addSuffix: true })}
                                                    </td>
                                                </tr>
                                            )
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    )
}
