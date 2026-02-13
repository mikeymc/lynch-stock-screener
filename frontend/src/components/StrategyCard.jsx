import { useNavigate } from 'react-router-dom'
import { TrendingUp, TrendingDown, Folder } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { format } from 'date-fns'

const LiveSignal = () => (
    <span className="bg-yellow-400 h-2 w-2 rounded-full mr-2 inline-block shadow-sm" />
)

export default function StrategyCard({ strategy }) {
    const navigate = useNavigate()

    // Format percentages
    const formatPct = (val) => {
        if (val === null || val === undefined) return 'N/A'
        const num = parseFloat(val)
        return (num > 0 ? '+' : '') + num.toFixed(2) + '%'
    }

    const alpha = strategy.alpha || 0
    const alphaColor = alpha > 0 ? 'text-green-600' : alpha < 0 ? 'text-red-600' : 'text-muted-foreground'

    return (
        <Card
            className="cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => navigate(`/strategies/${strategy.id}`)}
        >
            <CardHeader className="pb-3">
                <div className="flex justify-between items-start">
                    <div>
                        <CardTitle className="text-lg font-semibold">{strategy.name}</CardTitle>
                        <CardDescription className="flex flex-col gap-1 mt-1">
                            <div className="flex items-center gap-1">
                                <Folder className="h-3 w-3" />
                                {strategy.portfolio_name}
                            </div>
                            {strategy.user_email && (
                                <div className="flex items-center gap-1 text-xs text-muted-foreground/80">
                                    <span className="font-medium">User:</span> {strategy.user_email}
                                </div>
                            )}
                        </CardDescription>
                    </div>
                    <Badge variant={strategy.enabled ? "success" : "destructive"} className="flex items-center">
                        {strategy.enabled && <LiveSignal />}
                        {strategy.enabled ? 'Active' : 'Paused'}
                    </Badge>
                </div>
            </CardHeader>
            <CardContent>
                <div className="space-y-4">
                    {/* Performance Summary */}
                    <div className="grid grid-cols-2 gap-4 text-sm">
                        <div className="space-y-1">
                            <span className="text-muted-foreground text-xs">Returns</span>
                            <div className="font-medium flex items-center">
                                {formatPct(strategy.portfolio_return_pct)}
                            </div>
                        </div>
                        <div className="space-y-1">
                            <span className="text-muted-foreground text-xs">Alpha vs SPY</span>
                            <div className={`font-medium flex items-center ${alphaColor}`}>
                                {alpha > 0 ? <TrendingUp className="h-3 w-3 mr-1" /> : <TrendingDown className="h-3 w-3 mr-1" />}
                                {formatPct(alpha)}
                            </div>
                        </div>
                    </div>

                    <div className="pt-2 border-t flex flex-col gap-2">
                        <div className="flex justify-between text-xs">
                            <span className="text-muted-foreground">Last Run</span>
                            <span className="font-medium">
                                {strategy.last_run_date
                                    ? format(new Date(strategy.last_run_date), 'MMM d, h:mm a')
                                    : 'Never'}
                            </span>
                        </div>
                        {strategy.last_run_status && (
                            <div className="flex justify-between text-xs">
                                <span className="text-muted-foreground">Status</span>
                                <Badge variant="outline" className="text-[10px] h-5 capitalize">
                                    {strategy.last_run_status}
                                </Badge>
                            </div>
                        )}
                    </div>
                </div>
            </CardContent>
            <CardFooter className="bg-muted/30 p-3">
                <Button
                    variant="ghost"
                    className="w-full h-8 text-xs text-muted-foreground hover:text-primary"
                >
                    View Details
                </Button>
            </CardFooter>
        </Card>
    )
}
