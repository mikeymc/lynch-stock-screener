// ABOUTME: Focused view for Insider Trading activity
import React, { useState, useEffect } from 'react'
import InsiderTradesTable from './InsiderTradesTable'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const API_BASE = '/api'

export default function InsiderTrading({ symbol }) {
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        let active = true
        const fetchData = async () => {
            setLoading(true)
            try {
                // Fetch from outlook endpoint which has extensive data including health checks
                const res = await fetch(`${API_BASE}/stock/${symbol}/outlook`)
                if (res.ok) {
                    const json = await res.json()
                    if (active) setData(json)
                } else {
                    if (active) setError("Failed to load insider trading data")
                }
            } catch (err) {
                if (active) setError(err.message)
            } finally {
                if (active) setLoading(false)
            }
        }
        fetchData()
        return () => { active = false }
    }, [symbol])

    if (loading) return <div className="p-8 text-muted-foreground">Loading insider trading data...</div>
    if (error) return <div className="p-8 text-destructive">Error: {error}</div>
    if (!data) return null

    const { metrics, insider_trades } = data

    // --- Formatters ---
    const formatCurrency = (val) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val)

    // --- Helper for Net Insider Buying ---
    const netBuying = metrics?.insider_net_buying_6m || 0
    const netBuyingText = netBuying > 0 ? 'Net Buying' : (netBuying < 0 ? 'Net Selling' : 'Neutral')

    return (
        <div className="w-full space-y-6">
            <Card>
                <CardHeader>
                    <CardTitle>Insider Trading Activity</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center gap-4 mb-6 p-4 bg-muted/30 rounded-lg border border-border/50">
                        <div>
                            <div className="text-sm text-muted-foreground mb-1">Net Insider Activity (6m)</div>
                            <div className="flex items-baseline gap-3">
                                <span className={`text-3xl font-bold ${netBuying > 0 ? 'text-green-500' : netBuying < 0 ? 'text-red-500' : 'text-muted-foreground'}`}>
                                    {netBuying > 0 ? '+' : ''}{formatCurrency(netBuying)}
                                </span>
                                <span className="text-lg text-muted-foreground font-medium">
                                    {netBuyingText}
                                </span>
                            </div>
                        </div>
                    </div>

                    <InsiderTradesTable trades={insider_trades} />
                    <div className="mt-4 text-xs text-muted-foreground italic">
                        * Only open market transactions shown. 10b5-1 plans are pre-scheduled trades.
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}
