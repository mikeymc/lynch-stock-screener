
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Search } from 'lucide-react'
import PortfolioCard from '@/components/PortfolioCard'

const API_BASE = '/api'

export default function AdminPortfolios() {
    const navigate = useNavigate()
    const [portfolios, setPortfolios] = useState([])
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState('')

    useEffect(() => {
        fetchPortfolios()
    }, [])

    const fetchPortfolios = async () => {
        setLoading(true)
        try {
            const response = await fetch(`${API_BASE}/admin/portfolios`, {
                credentials: 'include'
            })
            if (!response.ok) throw new Error('Failed to fetch portfolios')
            const data = await response.json()
            setPortfolios(data.portfolios || [])
        } catch (err) {
            console.error('Error fetching portfolios:', err)
        } finally {
            setLoading(false)
        }
    }

    const filteredPortfolios = portfolios.filter(p =>
        (p.name && p.name.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (p.user_email && p.user_email.toLowerCase().includes(searchQuery.toLowerCase()))
    )

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Portfolios</h1>
                    <p className="text-muted-foreground">Manage and monitor all user portfolios</p>
                </div>
                <div className="relative w-64">
                    <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder="Search portfolios or users..."
                        className="pl-8"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                </div>
            </div>

            {loading ? (
                <div className="flex justify-center p-12">Loading portfolios...</div>
            ) : filteredPortfolios.length === 0 ? (
                <div className="text-center p-12 text-muted-foreground border rounded-lg border-dashed">
                    No portfolios found matching your search.
                </div>
            ) : (
                <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                    {filteredPortfolios.map((portfolio) => (
                        <PortfolioCard
                            key={portfolio.id}
                            portfolio={portfolio}
                            onClick={() => navigate(`/portfolios/${portfolio.id}`)}
                        // No delete prop for now to prevent accidental deletion
                        />
                    ))}
                </div>
            )}
        </div>
    )
}
