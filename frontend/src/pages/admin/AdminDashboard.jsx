import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { RefreshCw, CheckCircle, XCircle, Clock, AlertCircle, ExternalLink } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

const API_BASE = '/api'

export default function AdminDashboard() {
    const navigate = useNavigate()
    const [jobs, setJobs] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [lastRefreshed, setLastRefreshed] = useState(new Date())

    const fetchJobs = async () => {
        setLoading(true)
        setError(null)
        try {
            // Note: backend endpoint needs to be implemented or we usage existing /api/jobs
            // The plan says GET /api/admin/background_jobs
            const response = await fetch(`${API_BASE}/admin/background_jobs`, {
                credentials: 'include'
            })

            if (!response.ok) throw new Error('Failed to fetch jobs')
            const data = await response.json()
            setJobs(data.jobs || [])
        } catch (err) {
            console.error('Error fetching jobs:', err)
            setError(err.message)
        } finally {
            setLoading(false)
            setLastRefreshed(new Date())
        }
    }

    useEffect(() => {
        fetchJobs()
        const interval = setInterval(fetchJobs, 10000) // Poll every 10s
        return () => clearInterval(interval)
    }, [])

    const getStatusColor = (status) => {
        switch (status) {
            case 'completed': return 'success' // or default badge green
            case 'failed': return 'destructive'
            case 'processing': return 'default' // blue
            case 'pending': return 'secondary'
            case 'cancelled': return 'outline'
            default: return 'outline'
        }
    }

    const getStatusIcon = (status) => {
        switch (status) {
            case 'completed': return <CheckCircle className="h-4 w-4 text-green-500" />
            case 'failed': return <XCircle className="h-4 w-4 text-red-500" />
            case 'processing': return <RefreshCw className="h-4 w-4 animate-spin text-blue-500" />
            case 'pending': return <Clock className="h-4 w-4 text-muted-foreground" />
            case 'cancelled': return <AlertCircle className="h-4 w-4 text-muted-foreground" />
            default: return <Clock className="h-4 w-4" />
        }
    }

    // Group jobs by type for summary
    const jobTypes = jobs.reduce((acc, job) => {
        const type = job.job_type || 'unknown'
        acc[type] = (acc[type] || 0) + 1
        return acc
    }, {})

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">System Status</h1>
                    <p className="text-muted-foreground">Monitor background jobs and system health</p>
                </div>
                <div className="flex items-center gap-4">
                    <span className="text-sm text-muted-foreground">
                        Updated {formatDistanceToNow(lastRefreshed, { addSuffix: true })}
                    </span>
                    <Button variant="outline" size="sm" onClick={fetchJobs} disabled={loading}>
                        <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </Button>
                </div>
            </div>

            {/* Stats Cards */}
            <div className="grid gap-4 md:grid-cols-3">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Active Workers</CardTitle>
                        <ActivityIcon className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">--</div>
                        <p className="text-xs text-muted-foreground">Worker monitoring not yet implemented</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Pending Jobs</CardTitle>
                        <Clock className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            {jobs.filter(j => j.status === 'pending').length}
                        </div>
                        <p className="text-xs text-muted-foreground">Waiting for processing</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Failed (24h)</CardTitle>
                        <AlertCircle className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            {jobs.filter(j => j.status === 'failed').length}
                        </div>
                        <p className="text-xs text-muted-foreground">Jobs failed in last 24h</p>
                    </CardContent>
                </Card>
            </div>

            {/* Recent Jobs Table */}
            <Card>
                <CardHeader>
                    <CardTitle>Recent Background Jobs</CardTitle>
                </CardHeader>
                <CardContent>
                    {loading && jobs.length === 0 ? (
                        <div className="flex justify-center p-8">
                            <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
                        </div>
                    ) : error ? (
                        <div className="text-red-500 p-4">Error: {error}</div>
                    ) : jobs.length === 0 ? (
                        <div className="text-muted-foreground text-center p-8">No recent jobs found</div>
                    ) : (
                        <div className="rounded-md border">
                            <div className="grid grid-cols-6 border-b bg-muted/50 p-3 text-sm font-medium">
                                <div>Type</div>
                                <div>Status</div>
                                <div className="col-span-2">Params</div>
                                <div>Created</div>
                                <div>Duration</div>
                            </div>
                            <div className="divide-y">
                                {jobs.map((job) => (
                                    <div key={job.id} className="grid grid-cols-6 p-3 text-sm items-center hover:bg-muted/5">
                                        <div className="font-medium">{job.job_type}</div>
                                        <div className="flex items-center gap-2">
                                            {getStatusIcon(job.status)}
                                            <span className="capitalize">{job.status}</span>
                                        </div>
                                        <div className="col-span-2 flex items-center gap-2 text-muted-foreground text-xs" title={JSON.stringify(job.params)}>
                                            <span className="truncate flex-1">{JSON.stringify(job.params)}</span>
                                            {job.params?.strategy_id && (
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-6 w-6 shrink-0 hover:text-primary"
                                                    onClick={() => navigate(`/strategies/${job.params.strategy_id}`)}
                                                >
                                                    <ExternalLink className="h-3 w-3" />
                                                </Button>
                                            )}
                                            {job.params?.portfolio_id && (
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-6 w-6 shrink-0 hover:text-primary"
                                                    onClick={() => navigate(`/portfolios/${job.params.portfolio_id}`)}
                                                >
                                                    <ExternalLink className="h-3 w-3" />
                                                </Button>
                                            )}
                                        </div>
                                        <div className="text-muted-foreground text-xs">
                                            {formatDistanceToNow(new Date(job.created_at), { addSuffix: true })}
                                        </div>
                                        <div className="text-muted-foreground text-xs">
                                            {job.finished_at && job.started_at
                                                ? ((new Date(job.finished_at) - new Date(job.started_at)) / 1000).toFixed(1) + 's'
                                                : '-'}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}

function ActivityIcon(props) {
    return (
        <svg
            {...props}
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
        </svg>
    )
}
