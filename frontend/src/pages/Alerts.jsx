import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Bell, Trash2, TrendingUp, TrendingDown, Activity, DollarSign } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'

export default function Alerts() {
    const { user } = useAuth()
    const [alerts, setAlerts] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        fetchAlerts()
    }, [])

    const fetchAlerts = async () => {
        try {
            setLoading(true)
            const response = await fetch('/api/alerts')
            if (response.ok) {
                const data = await response.json()
                setAlerts(data.alerts || [])
            } else {
                throw new Error('Failed to fetch alerts')
            }
        } catch (err) {
            console.error('Error fetching alerts:', err)
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    const deleteAlert = async (alertId) => {
        if (!confirm('Are you sure you want to delete this alert?')) return

        try {
            const response = await fetch(`/api/alerts/${alertId}`, {
                method: 'DELETE'
            })

            if (response.ok) {
                setAlerts(alerts.filter(a => a.id !== alertId))
            } else {
                throw new Error('Failed to delete alert')
            }
        } catch (err) {
            console.error('Error deleting alert:', err)
            // Show toast error here ideally
        }
    }

    const getConditionIcon = (type) => {
        switch (type) {
            case 'price': return <DollarSign className="h-4 w-4" />
            case 'pe_ratio': return <Activity className="h-4 w-4" />
            default: return <Bell className="h-4 w-4" />
        }
    }

    const formatCondition = (alert) => {
        const { condition_type, condition_params } = alert
        const { operator, threshold } = condition_params
        const opStr = operator === 'above' ? '>' : '<'

        if (condition_type === 'price') {
            return `Price ${opStr} $${threshold}`
        } else if (condition_type === 'pe_ratio') {
            return `P/E ${opStr} ${threshold}`
        }
        return `${condition_type} ${opStr} ${threshold}`
    }

    const activeAlerts = alerts.filter(a => a.status === 'active')
    const triggeredAlerts = alerts.filter(a => a.status === 'triggered')

    if (loading && alerts.length === 0) {
        return <div className="p-8 text-center">Loading alerts...</div>
    }

    return (
        <div className="container py-8 max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Alerts</h1>
                    <p className="text-muted-foreground mt-1">
                        Manage your stock alerts and notifications
                    </p>
                </div>
                <Button onClick={fetchAlerts} variant="outline" size="sm">
                    Refresh
                </Button>
            </div>

            <Tabs defaultValue="active" className="w-full">
                <TabsList className="mb-4">
                    <TabsTrigger value="active">
                        Active
                        {activeAlerts.length > 0 && (
                            <Badge variant="secondary" className="ml-2 h-5 min-w-5 px-1">{activeAlerts.length}</Badge>
                        )}
                    </TabsTrigger>
                    <TabsTrigger value="triggered">
                        Triggered
                        {triggeredAlerts.length > 0 && (
                            <Badge variant="destructive" className="ml-2 h-5 min-w-5 px-1">{triggeredAlerts.length}</Badge>
                        )}
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="active" className="space-y-4">
                    {activeAlerts.length === 0 ? (
                        <Card>
                            <CardContent className="py-12 text-center text-muted-foreground">
                                <Bell className="h-12 w-12 mx-auto mb-4 opacity-20" />
                                <p>No active alerts.</p>
                                <p className="text-sm mt-2">Ask the AI agent to set an alert for you.</p>
                            </CardContent>
                        </Card>
                    ) : (
                        activeAlerts.map(alert => (
                            <AlertCard
                                key={alert.id}
                                alert={alert}
                                onDelete={() => deleteAlert(alert.id)}
                                icon={getConditionIcon(alert.condition_type)}
                                conditionText={formatCondition(alert)}
                            />
                        ))
                    )}
                </TabsContent>

                <TabsContent value="triggered" className="space-y-4">
                    {triggeredAlerts.length === 0 ? (
                        <Card>
                            <CardContent className="py-12 text-center text-muted-foreground">
                                <p>No triggered alerts yet.</p>
                            </CardContent>
                        </Card>
                    ) : (
                        triggeredAlerts.map(alert => (
                            <AlertCard
                                key={alert.id}
                                alert={alert}
                                onDelete={() => deleteAlert(alert.id)}
                                icon={getConditionIcon(alert.condition_type)}
                                conditionText={formatCondition(alert)}
                                isTriggered
                            />
                        ))
                    )}
                </TabsContent>
            </Tabs>
        </div>
    )
}

function AlertCard({ alert, onDelete, icon, conditionText, isTriggered }) {
    return (
        <Card>
            <CardHeader className="p-4 flex flex-row items-start justify-between space-y-0">
                <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-full ${isTriggered ? 'bg-red-100 text-red-600 dark:bg-red-900/20' : 'bg-primary/10 text-primary'}`}>
                        {icon}
                    </div>
                    <div>
                        <CardTitle className="text-base font-medium flex items-center gap-2">
                            {alert.symbol}
                            <span className="text-muted-foreground font-normal text-sm mx-1">•</span>
                            {conditionText}
                        </CardTitle>
                        <CardDescription className="text-xs mt-1">
                            Set on {new Date(alert.created_at).toLocaleDateString()}
                        </CardDescription>
                        {isTriggered && alert.message && (
                            <div className="mt-2 text-sm font-medium text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/10 p-2 rounded">
                                {alert.message}
                            </div>
                        )}
                    </div>
                </div>
                <Button
                    variant="ghost"
                    size="icon"
                    className="text-muted-foreground hover:text-destructive h-8 w-8"
                    onClick={onDelete}
                >
                    <Trash2 className="h-4 w-4" />
                </Button>
            </CardHeader>
        </Card>
    )
}
