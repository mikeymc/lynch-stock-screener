
import { useState, useEffect } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Search } from 'lucide-react'
import StrategyCard from '@/components/StrategyCard'

const API_BASE = '/api'

export default function AdminStrategies() {
    const [strategies, setStrategies] = useState([])
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState('')

    useEffect(() => {
        fetchStrategies()
    }, [])

    const fetchStrategies = async () => {
        setLoading(true)
        try {
            const response = await fetch(`${API_BASE}/admin/strategies`, {
                credentials: 'include'
            })
            if (!response.ok) throw new Error('Failed to fetch strategies')
            const data = await response.json()
            setStrategies(data.strategies || [])
        } catch (err) {
            console.error('Error fetching strategies:', err)
        } finally {
            setLoading(false)
        }
    }

    const filteredStrategies = strategies.filter(s =>
        (s.name && s.name.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (s.user_email && s.user_email.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (s.portfolio_name && s.portfolio_name.toLowerCase().includes(searchQuery.toLowerCase()))
    )

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Strategies</h1>
                    <p className="text-muted-foreground">Manage and monitor all user strategies</p>
                </div>
                <div className="relative w-64">
                    <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder="Search strategies or users..."
                        className="pl-8"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                </div>
            </div>

            {loading ? (
                <div className="flex justify-center p-12">Loading strategies...</div>
            ) : filteredStrategies.length === 0 ? (
                <div className="text-center p-12 text-muted-foreground border rounded-lg border-dashed">
                    No strategies found matching your search.
                </div>
            ) : (
                <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                    {filteredStrategies.map((strategy) => (
                        <StrategyCard key={strategy.id} strategy={strategy} />
                    ))}
                </div>
            )}
        </div>
    )
}
