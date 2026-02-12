// ABOUTME: Summary of triggered and pending alerts for dashboard
// ABOUTME: Shows CTA to set up alerts if none exist

import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Bell, Plus, ArrowRight, AlertCircle, Clock } from 'lucide-react'

export default function AlertsSummary({ onNavigate }) {
    const [alerts, setAlerts] = useState({})
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        const fetchAlerts = async () => {
            try {
                setLoading(true)
                const response = await fetch('/api/dashboard/alerts')
                if (response.ok) {
                    const data = await response.json()
                    setAlerts(data.alerts || {})
                } else {
                    setError('Failed to load alerts')
                }
            } catch (err) {
                console.error('Error fetching alerts:', err)
                setError('Failed to load alerts')
            } finally {
                setLoading(false)
            }
        }

        fetchAlerts()
    }, [])

    const triggered = alerts.triggered || []
    const pending = alerts.pending || []
    const hasAlerts = triggered.length > 0 || pending.length > 0

    return (
        <Card>
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                        <Bell className="h-4 w-4" />
                        Alerts
                    </CardTitle>
                    <Button variant="ghost" size="sm" onClick={onNavigate}>
                        Manage <ArrowRight className="h-4 w-4 ml-1" />
                    </Button>
                </div>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <Skeleton className="h-24 w-full" />
                ) : error ? (
                    <div className="h-24 flex items-center justify-center text-sm text-muted-foreground border border-dashed rounded-lg bg-muted/20">
                        {error}
                    </div>
                ) : hasAlerts ? (
                    <div className="space-y-3">
                        {/* Pending alerts */}
                        {pending.length > 0 && (
                            <div>
                                <div className="flex items-center gap-1 text-xs text-muted-foreground mb-2">
                                    <Clock className="h-3 w-3" />
                                    Pending ({alerts.total_pending || pending.length})
                                </div>
                                <div className="space-y-1">
                                    {pending.slice(0, 3).map(alert => (
                                        <AlertRow key={alert.id} alert={alert} />
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Triggered alerts */}
                        {triggered.length > 0 && (
                            <div>
                                <div className="flex items-center gap-1 text-xs text-red-500 mb-2">
                                    <AlertCircle className="h-3 w-3" />
                                    Triggered ({alerts.total_triggered || triggered.length})
                                </div>
                                <div className="space-y-1">
                                    {triggered.slice(0, 3).map(alert => (
                                        <AlertRow key={alert.id} alert={alert} isTriggered />
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                ) : (
                    <EmptyState onNavigate={onNavigate} />
                )}
            </CardContent>
        </Card>
    )
}

function AlertRow({ alert, isTriggered }) {
    const conditionText = formatCondition(alert)

    return (
        <div className={`flex items-center justify-between py-1.5 px-2 rounded ${isTriggered ? 'bg-red-500/10' : 'bg-muted/50'}`}>
            <div className="flex items-center gap-2">
                <span className="font-medium text-sm">{alert.symbol}</span>
                <span className="text-xs text-muted-foreground">{conditionText}</span>
            </div>
        </div>
    )
}

function formatCondition(alert) {
    // Prioritize descriptive strings from the backend
    if (alert.condition_description) return alert.condition_description
    if (alert.message) return alert.message

    const type = alert.condition_type
    const params = alert.condition_params || {}
    const price = params.price ?? params.threshold

    switch (type) {
        case 'price_above':
            return `Above $${price}`
        case 'price_below':
            return `Below $${price}`
        case 'pct_change':
            return `${params.direction === 'up' ? '↑' : '↓'} ${params.percent}%`
        default:
            return type
    }
}

function EmptyState({ onNavigate }) {
    return (
        <div className="flex flex-col items-center justify-center py-6 text-center">
            <Bell className="h-8 w-8 text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground mb-3">
                Get notified when stocks hit your targets
            </p>
            <Button onClick={onNavigate} size="sm">
                <Plus className="h-4 w-4 mr-1" />
                Create Alert
            </Button>
        </div>
    )
}
