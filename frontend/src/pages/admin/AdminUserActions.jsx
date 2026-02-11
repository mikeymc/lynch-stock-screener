import { useState, useEffect } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatDistanceToNow } from 'date-fns'
import { Activity, List, Users } from 'lucide-react'

const API_BASE = '/api'

export default function AdminUserActions() {
    const [events, setEvents] = useState([])
    const [stats, setStats] = useState([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchEvents()
    }, [])

    const fetchEvents = async () => {
        setLoading(true)
        try {
            const response = await fetch(`${API_BASE}/admin/user_actions`, {
                credentials: 'include'
            })
            if (!response.ok) throw new Error('Failed to fetch user events')
            const data = await response.json()
            setEvents(data.events || [])
            setStats(data.stats || [])
        } catch (err) {
            console.error('Error fetching user events:', err)
        } finally {
            setLoading(false)
        }
    }

    const getEventColor = (type) => {
        if (type.includes('error') || type.includes('fail')) return 'destructive'
        if (type.includes('create') || type.includes('success')) return 'success'
        if (type.includes('update') || type.includes('edit')) return 'default' // blue
        return 'secondary'
    }

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">User Actions</h1>
                    <p className="text-muted-foreground">Audit log of user activities and system events</p>
                </div>
            </div>

            <Tabs defaultValue="activity" className="space-y-6">
                <TabsList>
                    <TabsTrigger value="activity" className="flex items-center gap-2">
                        <List className="h-4 w-4" />
                        Recent Activity
                    </TabsTrigger>
                    <TabsTrigger value="stats" className="flex items-center gap-2">
                        <Users className="h-4 w-4" />
                        API Usage Statistics
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="activity">
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Activity className="h-5 w-5" />
                                Recent Activity
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            {loading ? (
                                <div className="flex justify-center p-8">Loading events...</div>
                            ) : events.length === 0 ? (
                                <div className="text-center p-8 text-muted-foreground">No recent user activity found.</div>
                            ) : (
                                <div className="relative overflow-x-auto">
                                    <table className="w-full text-sm text-left">
                                        <thead className="text-xs text-muted-foreground uppercase bg-muted/50 border-b">
                                            <tr>
                                                <th className="px-4 py-3">Path</th>
                                                <th className="px-4 py-3">User</th>
                                                <th className="px-4 py-3">Details</th>
                                                <th className="px-4 py-3">Time</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y">
                                            {events.map((event) => (
                                                <tr key={event.id} className="bg-background hover:bg-muted/5">
                                                    <td className="px-4 py-3 font-medium text-xs font-mono">
                                                        {event.path}
                                                    </td>
                                                    <td className="px-4 py-3 truncate max-w-[200px]" title={event.user_email}>
                                                        {event.user_name || event.user_email || 'System'}
                                                    </td>
                                                    <td className="px-4 py-3 text-muted-foreground truncate max-w-[400px]">
                                                        {JSON.stringify(event.details || {})}
                                                    </td>
                                                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                                                        {formatDistanceToNow(new Date(event.created_at), { addSuffix: true })}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="stats">
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Activity className="h-5 w-5" />
                                API Usage Statistics
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            {loading ? (
                                <div className="flex justify-center p-8">Loading stats...</div>
                            ) : stats.length === 0 ? (
                                <div className="text-center p-8 text-muted-foreground">No user statistics found.</div>
                            ) : (
                                <div className="relative overflow-x-auto">
                                    <table className="w-full text-sm text-left">
                                        <thead className="text-xs text-muted-foreground uppercase bg-muted/50 border-b">
                                            <tr>
                                                <th className="px-4 py-3">User</th>
                                                <th className="px-4 py-3 text-right">Total Hits</th>
                                                <th className="px-4 py-3 text-right">Last Activity</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y">
                                            {stats.map((stat) => (
                                                <tr key={stat.user_id} className="bg-background hover:bg-muted/5">
                                                    <td className="px-4 py-3 font-medium">
                                                        <div>{stat.name || 'Unnamed User'}</div>
                                                        <div className="text-xs text-muted-foreground">{stat.email}</div>
                                                    </td>
                                                    <td className="px-4 py-3 text-right font-mono">
                                                        {stat.total_hits.toLocaleString()}
                                                    </td>
                                                    <td className="px-4 py-3 text-right text-muted-foreground">
                                                        {stat.last_activity
                                                            ? formatDistanceToNow(new Date(stat.last_activity), { addSuffix: true })
                                                            : 'Never'}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    )
}
