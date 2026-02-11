// ABOUTME: Summary of active investment strategies for dashboard
// ABOUTME: Shows strategy status and last run info or CTA to create strategy

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Zap, Plus, ArrowRight, CheckCircle2, AlertCircle, Clock } from 'lucide-react'

export default function StrategiesSummary({ strategies = [], onNavigate, loading = false }) {
    const hasStrategies = strategies.length > 0

    return (
        <Card>
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                        <Zap className="h-4 w-4" />
                        Strategies
                    </CardTitle>
                    <Button variant="ghost" size="sm" onClick={onNavigate}>
                        Manage <ArrowRight className="h-4 w-4 ml-1" />
                    </Button>
                </div>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <Skeleton className="h-24 w-full" />
                ) : hasStrategies ? (
                    <div className="space-y-2">
                        {strategies.slice(0, 4).map(strategy => (
                            <StrategyRow key={strategy.id} strategy={strategy} />
                        ))}
                        {strategies.length > 4 && (
                            <p className="text-xs text-muted-foreground text-center pt-1">
                                +{strategies.length - 4} more strategies
                            </p>
                        )}
                    </div>
                ) : (
                    <EmptyState onNavigate={onNavigate} />
                )}
            </CardContent>
        </Card>
    )
}

function StrategyRow({ strategy }) {
    const status = strategy.last_status || 'pending'
    const StatusIcon = status === 'completed' ? CheckCircle2 : status === 'failed' ? AlertCircle : Clock

    return (
        <div className="flex items-center justify-between py-2 px-2 rounded bg-muted/50">
            <div className="flex items-center gap-2 min-w-0">
                <StatusIcon className={`h-4 w-4 flex-shrink-0 ${getStatusColor(status)}`} />
                <span className="font-medium text-sm truncate">{strategy.name}</span>
            </div>
            <div className="flex items-center gap-2">
                {strategy.last_run && (
                    <span className="text-xs text-muted-foreground">
                        {formatTimeAgo(strategy.last_run)}
                    </span>
                )}
                <Badge
                    variant={strategy.enabled ? 'default' : 'secondary'}
                    className="text-xs"
                >
                    {strategy.enabled ? 'Active' : 'Paused'}
                </Badge>
            </div>
        </div>
    )
}

function getStatusColor(status) {
    switch (status) {
        case 'completed':
            return 'text-green-500'
        case 'failed':
            return 'text-red-500'
        case 'running':
            return 'text-blue-500'
        default:
            return 'text-muted-foreground'
    }
}

function formatTimeAgo(dateStr) {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    const seconds = Math.floor((new Date() - date) / 1000)

    if (seconds < 60) return 'just now'
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ago`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}h ago`
    const days = Math.floor(hours / 24)
    return `${days}d ago`
}

function EmptyState({ onNavigate }) {
    return (
        <div className="flex flex-col items-center justify-center py-6 text-center">
            <Zap className="h-8 w-8 text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground mb-3">
                Automate your investment rules with strategies
            </p>
            <Button onClick={onNavigate} size="sm">
                <Plus className="h-4 w-4 mr-1" />
                Create Strategy
            </Button>
        </div>
    )
}
