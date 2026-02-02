// ABOUTME: Paper trading portfolios page with portfolio management and trade execution
// ABOUTME: Displays portfolio cards, holdings, transactions, and performance charts

import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { Separator } from "@/components/ui/separator"
import {
    Plus,
    Trash2,
    TrendingUp,
    TrendingDown,
    Wallet,
    ArrowLeft,
    DollarSign,
    Activity,
    Clock,
    LineChart,
    AlertCircle,
    CheckCircle2,
    Briefcase,
    ArrowUpRight,
    ArrowDownRight
} from 'lucide-react'
import { useAuth } from '@/context/AuthContext'

// Format currency with commas and 2 decimal places
const formatCurrency = (value) => {
    if (value === null || value === undefined) return '$0.00'
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value)
}

// Format percentage with sign
const formatPercent = (value) => {
    if (value === null || value === undefined) return '0.00%'
    const sign = value >= 0 ? '+' : ''
    return `${sign}${value.toFixed(2)}%`
}

// Format date for display
const formatDate = (dateStr) => {
    if (!dateStr) return '-'
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    })
}

export default function Portfolios() {
    const { user } = useAuth()
    const { id } = useParams()
    const navigate = useNavigate()
    const [portfolios, setPortfolios] = useState([])
    const [selectedPortfolio, setSelectedPortfolio] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    // Create portfolio dialog state
    const [createDialogOpen, setCreateDialogOpen] = useState(false)
    const [newPortfolioName, setNewPortfolioName] = useState('')
    const [newPortfolioInitialCash, setNewPortfolioInitialCash] = useState('100000')
    const [creating, setCreating] = useState(false)

    useEffect(() => {
        fetchPortfolios()
    }, [])

    // Handle deep linking to specific portfolio
    useEffect(() => {
        if (id) {
            fetchPortfolioById(id)
        } else {
            setSelectedPortfolio(null)
        }
    }, [id])

    const fetchPortfolioById = async (portfolioId) => {
        try {
            setLoading(true)
            const response = await fetch(`/api/portfolios/${portfolioId}`)
            if (response.ok) {
                const data = await response.json()
                setSelectedPortfolio(data)
            } else {
                console.error('Failed to fetch specific portfolio')
            }
        } catch (err) {
            console.error('Error fetching specific portfolio:', err)
        } finally {
            setLoading(false)
        }
    }

    const fetchPortfolios = async () => {
        try {
            setLoading(true)
            const response = await fetch('/api/portfolios')
            if (response.ok) {
                const data = await response.json()
                setPortfolios(data.portfolios || [])
            } else if (response.status === 401) {
                setError('Please log in to view portfolios')
            } else {
                throw new Error('Failed to fetch portfolios')
            }
        } catch (err) {
            console.error('Error fetching portfolios:', err)
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    const createPortfolio = async () => {
        if (!newPortfolioName.trim()) return

        setCreating(true)
        try {
            const response = await fetch('/api/portfolios', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: newPortfolioName.trim(),
                    initial_cash: parseFloat(newPortfolioInitialCash) || 100000
                })
            })

            if (response.ok) {
                const portfolio = await response.json()
                setPortfolios([portfolio, ...portfolios])
                setCreateDialogOpen(false)
                setNewPortfolioName('')
                setNewPortfolioInitialCash('100000')
            } else {
                throw new Error('Failed to create portfolio')
            }
        } catch (err) {
            console.error('Error creating portfolio:', err)
        } finally {
            setCreating(false)
        }
    }

    const deletePortfolio = async (portfolioId) => {
        if (!confirm('Delete this portfolio and all its transactions? This cannot be undone.')) return

        try {
            const response = await fetch(`/api/portfolios/${portfolioId}`, {
                method: 'DELETE'
            })

            if (response.ok) {
                setPortfolios(portfolios.filter(p => p.id !== portfolioId))
                if (selectedPortfolio?.id === portfolioId) {
                    setSelectedPortfolio(null)
                }
            } else {
                throw new Error('Failed to delete portfolio')
            }
        } catch (err) {
            console.error('Error deleting portfolio:', err)
        }
    }

    const selectPortfolio = async (portfolio) => {
        try {
            const response = await fetch(`/api/portfolios/${portfolio.id}`)
            if (response.ok) {
                const data = await response.json()
                setSelectedPortfolio(data)
            }
        } catch (err) {
            console.error('Error fetching portfolio details:', err)
        }
    }

    const refreshSelectedPortfolio = async () => {
        if (!selectedPortfolio) return
        await selectPortfolio(selectedPortfolio)
    }

    if (loading && portfolios.length === 0) {
        return (
            <div className="container py-8 max-w-5xl mx-auto">
                <div className="mb-8">
                    <Skeleton className="h-9 w-48" />
                </div>
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {[1, 2, 3].map(i => (
                        <Skeleton key={i} className="h-40 rounded-xl" />
                    ))}
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="container py-8 max-w-5xl mx-auto">
                <Card className="border-destructive/50 bg-destructive/5">
                    <CardContent className="py-12 text-center">
                        <AlertCircle className="h-12 w-12 mx-auto mb-4 text-destructive opacity-50" />
                        <p className="text-destructive">{error}</p>
                    </CardContent>
                </Card>
            </div>
        )
    }

    // Show portfolio detail view
    if (selectedPortfolio) {
        return (
            <PortfolioDetail
                portfolio={selectedPortfolio}
                onBack={() => navigate('/portfolios')}
                onRefresh={refreshSelectedPortfolio}
                onDelete={() => deletePortfolio(selectedPortfolio.id)}
            />
        )
    }

    // Portfolio list view
    return (
        <div className="container py-8 max-w-5xl mx-auto">
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Portfolios</h1>
                    <p className="text-muted-foreground mt-1">Manage your paper trading portfolios</p>
                </div>
                <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
                    <DialogTrigger asChild>
                        <Button>
                            <Plus className="h-4 w-4 mr-2" />
                            New Portfolio
                        </Button>
                    </DialogTrigger>
                    <DialogContent>
                        <DialogHeader>
                            <DialogTitle>Create New Portfolio</DialogTitle>
                            <DialogDescription>
                                Start a new paper trading portfolio with virtual cash.
                            </DialogDescription>
                        </DialogHeader>
                        <div className="space-y-4 py-4">
                            <div className="space-y-2">
                                <Label htmlFor="name">Portfolio Name</Label>
                                <Input
                                    id="name"
                                    placeholder="e.g., Tech Growth, Value Picks"
                                    value={newPortfolioName}
                                    onChange={(e) => setNewPortfolioName(e.target.value)}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="cash">Initial Cash</Label>
                                <div className="relative">
                                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
                                    <Input
                                        id="cash"
                                        type="number"
                                        className="pl-7"
                                        value={newPortfolioInitialCash}
                                        onChange={(e) => setNewPortfolioInitialCash(e.target.value)}
                                    />
                                </div>
                            </div>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
                                Cancel
                            </Button>
                            <Button onClick={createPortfolio} disabled={creating || !newPortfolioName.trim()}>
                                {creating ? 'Creating...' : 'Create Portfolio'}
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            </div>

            {portfolios.length === 0 ? (
                <Card className="border-dashed">
                    <CardContent className="py-16 text-center">
                        <Briefcase className="h-16 w-16 mx-auto mb-4 text-muted-foreground/30" />
                        <h3 className="text-lg font-medium mb-2">No portfolios yet</h3>
                        <p className="text-muted-foreground mb-6 max-w-sm mx-auto">
                            Create your first paper trading portfolio to start practicing investment strategies.
                        </p>
                        <Button onClick={() => setCreateDialogOpen(true)}>
                            <Plus className="h-4 w-4 mr-2" />
                            Create Your First Portfolio
                        </Button>
                    </CardContent>
                </Card>
            ) : (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {portfolios.map(portfolio => (
                        <PortfolioCard
                            key={portfolio.id}
                            portfolio={portfolio}
                            onClick={() => selectPortfolio(portfolio)}
                            onDelete={() => deletePortfolio(portfolio.id)}
                        />
                    ))}
                </div>
            )}
        </div>
    )
}

function PortfolioCard({ portfolio, onClick, onDelete }) {
    // Use pre-computed values from backend (now includes live prices)
    const totalValue = portfolio.total_value || portfolio.initial_cash || 100000
    const initialCash = portfolio.initial_cash || 100000
    const gainLoss = portfolio.gain_loss ?? (totalValue - initialCash)
    const gainLossPercent = portfolio.gain_loss_percent ?? (initialCash > 0 ? (gainLoss / initialCash) * 100 : 0)
    const isPositive = gainLoss >= 0

    return (
        <Card
            className="cursor-pointer transition-all hover:shadow-md hover:border-primary/30 group relative"
            onClick={onClick}
        >
            <Button
                variant="ghost"
                size="icon"
                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity h-8 w-8 text-muted-foreground hover:text-destructive z-10"
                onClick={(e) => {
                    e.stopPropagation()
                    onDelete()
                }}
            >
                <Trash2 className="h-4 w-4" />
            </Button>
            <CardHeader className="pb-2">
                <CardTitle className="text-lg font-semibold truncate pr-8">
                    {portfolio.name}
                </CardTitle>
                <CardDescription className="text-xs">
                    Created {new Date(portfolio.created_at).toLocaleDateString()}
                    {portfolio.strategy_id && (
                        <Button
                            variant="link"
                            className="p-0 h-auto text-xs ml-2 text-primary"
                            onClick={(e) => {
                                e.stopPropagation()
                                window.location.href = `/strategies/${portfolio.strategy_id}`
                            }}
                        >
                            View Strategy
                        </Button>
                    )}
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="space-y-3">
                    <div>
                        <p className="text-2xl font-bold tracking-tight">
                            {formatCurrency(totalValue)}
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        <Badge
                            variant={isPositive ? "default" : "destructive"}
                            className={`${isPositive
                                ? 'bg-emerald-500/10 text-emerald-600 hover:bg-emerald-500/20 dark:bg-emerald-500/20 dark:text-emerald-400'
                                : 'bg-red-500/10 text-red-600 hover:bg-red-500/20 dark:bg-red-500/20 dark:text-red-400'
                                }`}
                        >
                            {isPositive ? (
                                <TrendingUp className="h-3 w-3 mr-1" />
                            ) : (
                                <TrendingDown className="h-3 w-3 mr-1" />
                            )}
                            {formatPercent(gainLossPercent)}
                        </Badge>
                        <span className={`text-sm ${isPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                            {formatCurrency(gainLoss)}
                        </span>
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}

function PortfolioDetail({ portfolio, onBack, onRefresh, onDelete }) {
    const [activeTab, setActiveTab] = useState('holdings')
    const [transactions, setTransactions] = useState([])
    const [valueHistory, setValueHistory] = useState([])
    const [loadingTransactions, setLoadingTransactions] = useState(false)
    const [loadingHistory, setLoadingHistory] = useState(false)

    const totalValue = portfolio.total_value || 0
    const initialCash = portfolio.initial_cash || 100000
    const gainLoss = portfolio.gain_loss || 0
    const gainLossPercent = portfolio.gain_loss_percent || 0
    const cash = portfolio.cash || 0
    const holdingsValue = portfolio.holdings_value || 0
    const holdings = portfolio.holdings || {}
    const isPositive = gainLoss >= 0

    useEffect(() => {
        if (activeTab === 'transactions') {
            fetchTransactions()
        } else if (activeTab === 'performance') {
            fetchValueHistory()
        }
    }, [activeTab, portfolio.id])

    const fetchTransactions = async () => {
        setLoadingTransactions(true)
        try {
            const response = await fetch(`/api/portfolios/${portfolio.id}/transactions`)
            if (response.ok) {
                const data = await response.json()
                setTransactions(data.transactions || [])
            }
        } catch (err) {
            console.error('Error fetching transactions:', err)
        } finally {
            setLoadingTransactions(false)
        }
    }

    const fetchValueHistory = async () => {
        setLoadingHistory(true)
        try {
            const response = await fetch(`/api/portfolios/${portfolio.id}/value-history`)
            if (response.ok) {
                const data = await response.json()
                setValueHistory(data.snapshots || [])
            }
        } catch (err) {
            console.error('Error fetching value history:', err)
        } finally {
            setLoadingHistory(false)
        }
    }

    return (
        <div className="container py-8 max-w-5xl mx-auto">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="icon" onClick={onBack}>
                        <ArrowLeft className="h-5 w-5" />
                    </Button>
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight">{portfolio.name}</h1>
                        <p className="text-sm text-muted-foreground">
                            Created {new Date(portfolio.created_at).toLocaleDateString()}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {portfolio.strategy_id && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => window.location.href = `/strategies/${portfolio.strategy_id}`}
                        >
                            <Activity className="h-4 w-4 mr-2" />
                            View Strategy
                        </Button>
                    )}
                    <Button variant="ghost" size="icon" className="text-muted-foreground hover:text-destructive" onClick={onDelete}>
                        <Trash2 className="h-5 w-5" />
                    </Button>
                </div>
            </div>

            {/* Summary Cards */}
            <div className="grid gap-4 md:grid-cols-4 mb-6">
                <Card>
                    <CardContent className="pt-6">
                        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                            <DollarSign className="h-4 w-4" />
                            Total Value
                        </div>
                        <p className="text-2xl font-bold">{formatCurrency(totalValue)}</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="pt-6">
                        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                            <Wallet className="h-4 w-4" />
                            Cash
                        </div>
                        <p className="text-2xl font-bold">{formatCurrency(cash)}</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="pt-6">
                        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                            <Activity className="h-4 w-4" />
                            Holdings
                        </div>
                        <p className="text-2xl font-bold">{formatCurrency(holdingsValue)}</p>
                    </CardContent>
                </Card>
                <Card className={isPositive ? 'border-emerald-500/30' : 'border-red-500/30'}>
                    <CardContent className="pt-6">
                        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                            {isPositive ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                            Gain/Loss
                        </div>
                        <p className={`text-2xl font-bold ${isPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                            {formatCurrency(gainLoss)}
                        </p>
                        <p className={`text-sm ${isPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                            {formatPercent(gainLossPercent)}
                        </p>
                    </CardContent>
                </Card>
            </div>

            {/* Tabs */}
            <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                <TabsList className="mb-4">
                    <TabsTrigger value="holdings">Holdings</TabsTrigger>
                    <TabsTrigger value="trade">Trade</TabsTrigger>
                    <TabsTrigger value="transactions">Transactions</TabsTrigger>
                    <TabsTrigger value="performance">Performance</TabsTrigger>
                </TabsList>

                <TabsContent value="holdings">
                    <HoldingsTab portfolio={portfolio} />
                </TabsContent>

                <TabsContent value="trade">
                    <TradeTab
                        portfolioId={portfolio.id}
                        cash={cash}
                        holdings={holdings}
                        onTradeComplete={onRefresh}
                    />
                </TabsContent>

                <TabsContent value="transactions">
                    <TransactionsTab
                        transactions={transactions}
                        loading={loadingTransactions}
                    />
                </TabsContent>

                <TabsContent value="performance">
                    <PerformanceTab
                        snapshots={valueHistory}
                        loading={loadingHistory}
                        initialCash={initialCash}
                    />
                </TabsContent>
            </Tabs>
        </div>
    )
}

function HoldingsTab({ portfolio }) {
    // Check if we have detailed holdings data
    const holdingsDetailed = portfolio?.holdings_detailed || []

    if (holdingsDetailed.length === 0) {
        return (
            <Card>
                <CardContent className="py-12 text-center text-muted-foreground">
                    <Activity className="h-12 w-12 mx-auto mb-4 opacity-20" />
                    <p>No holdings yet. Start trading to build your portfolio.</p>
                </CardContent>
            </Card>
        )
    }

    return (
        <Card>
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead>Symbol</TableHead>
                        <TableHead className="text-right">Shares</TableHead>
                        <TableHead className="text-right">Purchase Price</TableHead>
                        <TableHead className="text-right">Current Price</TableHead>
                        <TableHead className="text-right">Total Cost</TableHead>
                        <TableHead className="text-right">Current Value</TableHead>
                        <TableHead className="text-right">Gain/Loss</TableHead>
                        <TableHead className="text-right">Yield %</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {holdingsDetailed.map((holding) => {
                        const isPositive = holding.gain_loss >= 0
                        return (
                            <TableRow key={holding.symbol}>
                                <TableCell className="font-medium">{holding.symbol}</TableCell>
                                <TableCell className="text-right">{holding.quantity}</TableCell>
                                <TableCell className="text-right">{formatCurrency(holding.avg_purchase_price)}</TableCell>
                                <TableCell className="text-right">{formatCurrency(holding.current_price)}</TableCell>
                                <TableCell className="text-right">{formatCurrency(holding.total_cost)}</TableCell>
                                <TableCell className="text-right">{formatCurrency(holding.current_value)}</TableCell>
                                <TableCell className={`text-right font-medium ${isPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                                    {formatCurrency(holding.gain_loss)}
                                </TableCell>
                                <TableCell className={`text-right font-medium ${isPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                                    {formatPercent(holding.gain_loss_percent)}
                                </TableCell>
                            </TableRow>
                        )
                    })}
                </TableBody>
            </Table>
        </Card>
    )
}

function TradeTab({ portfolioId, cash, holdings, onTradeComplete }) {
    const [symbol, setSymbol] = useState('')
    const [quantity, setQuantity] = useState('')
    const [transactionType, setTransactionType] = useState('BUY')
    const [note, setNote] = useState('')
    const [submitting, setSubmitting] = useState(false)
    const [result, setResult] = useState(null)

    const handleSubmit = async (e) => {
        e.preventDefault()
        if (!symbol.trim() || !quantity) return

        setSubmitting(true)
        setResult(null)

        try {
            const response = await fetch(`/api/portfolios/${portfolioId}/trade`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbol: symbol.toUpperCase().trim(),
                    transaction_type: transactionType,
                    quantity: parseInt(quantity),
                    note: note.trim() || undefined
                })
            })

            const data = await response.json()

            if (data.success) {
                setResult({ type: 'success', message: `Successfully ${transactionType === 'BUY' ? 'bought' : 'sold'} ${quantity} shares of ${symbol.toUpperCase()} at ${formatCurrency(data.price_per_share)}` })
                setSymbol('')
                setQuantity('')
                setNote('')
                onTradeComplete()
            } else {
                setResult({ type: 'error', message: data.error || 'Trade failed' })
            }
        } catch (err) {
            setResult({ type: 'error', message: 'Failed to execute trade' })
        } finally {
            setSubmitting(false)
        }
    }

    const maxSellQuantity = holdings?.[symbol.toUpperCase()] || 0

    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-lg">Execute Trade</CardTitle>
                <CardDescription>
                    Available cash: {formatCurrency(cash)}
                </CardDescription>
            </CardHeader>
            <CardContent>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="grid gap-4 md:grid-cols-3">
                        <div className="space-y-2">
                            <Label htmlFor="symbol">Symbol</Label>
                            <Input
                                id="symbol"
                                placeholder="e.g., AAPL"
                                value={symbol}
                                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                                className="uppercase"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="type">Action</Label>
                            <Select value={transactionType} onValueChange={setTransactionType}>
                                <SelectTrigger>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="BUY">
                                        <span className="flex items-center gap-2">
                                            <ArrowUpRight className="h-4 w-4 text-emerald-500" />
                                            Buy
                                        </span>
                                    </SelectItem>
                                    <SelectItem value="SELL">
                                        <span className="flex items-center gap-2">
                                            <ArrowDownRight className="h-4 w-4 text-red-500" />
                                            Sell
                                        </span>
                                    </SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="quantity">Shares</Label>
                            <Input
                                id="quantity"
                                type="number"
                                min="1"
                                placeholder="Number of shares"
                                value={quantity}
                                onChange={(e) => setQuantity(e.target.value)}
                            />
                            {transactionType === 'SELL' && symbol && maxSellQuantity > 0 && (
                                <p className="text-xs text-muted-foreground">
                                    You own {maxSellQuantity} shares
                                </p>
                            )}
                        </div>
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="note">Note (optional)</Label>
                        <Input
                            id="note"
                            placeholder="e.g., Bought on earnings dip"
                            value={note}
                            onChange={(e) => setNote(e.target.value)}
                        />
                    </div>

                    {result && (
                        <div className={`flex items-center gap-2 p-3 rounded-lg ${result.type === 'success'
                            ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                            : 'bg-red-500/10 text-red-600 dark:text-red-400'
                            }`}>
                            {result.type === 'success' ? (
                                <CheckCircle2 className="h-4 w-4" />
                            ) : (
                                <AlertCircle className="h-4 w-4" />
                            )}
                            <span className="text-sm">{result.message}</span>
                        </div>
                    )}

                    <Button
                        type="submit"
                        disabled={submitting || !symbol.trim() || !quantity}
                        className={transactionType === 'BUY'
                            ? 'bg-emerald-600 hover:bg-emerald-700'
                            : 'bg-red-600 hover:bg-red-700'
                        }
                    >
                        {submitting ? 'Processing...' : `${transactionType === 'BUY' ? 'Buy' : 'Sell'} ${symbol.toUpperCase() || 'Stock'}`}
                    </Button>
                </form>
            </CardContent>
        </Card>
    )
}

function TransactionsTab({ transactions, loading }) {
    if (loading) {
        return (
            <Card>
                <CardContent className="py-8">
                    <div className="space-y-3">
                        {[1, 2, 3].map(i => (
                            <Skeleton key={i} className="h-12 w-full" />
                        ))}
                    </div>
                </CardContent>
            </Card>
        )
    }

    if (transactions.length === 0) {
        return (
            <Card>
                <CardContent className="py-12 text-center text-muted-foreground">
                    <Clock className="h-12 w-12 mx-auto mb-4 opacity-20" />
                    <p>No transactions yet.</p>
                </CardContent>
            </Card>
        )
    }

    return (
        <Card>
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead>Date</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Symbol</TableHead>
                        <TableHead className="text-right">Shares</TableHead>
                        <TableHead className="text-right">Price</TableHead>
                        <TableHead className="text-right">Total</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {transactions.map(tx => (
                        <TableRow key={tx.id}>
                            <TableCell className="text-muted-foreground text-sm">
                                {formatDate(tx.executed_at)}
                            </TableCell>
                            <TableCell>
                                <Badge
                                    variant="outline"
                                    className={tx.transaction_type === 'BUY'
                                        ? 'border-emerald-500/50 text-emerald-600 dark:text-emerald-400'
                                        : 'border-red-500/50 text-red-600 dark:text-red-400'
                                    }
                                >
                                    {tx.transaction_type}
                                </Badge>
                            </TableCell>
                            <TableCell className="font-medium">{tx.symbol}</TableCell>
                            <TableCell className="text-right">{tx.quantity}</TableCell>
                            <TableCell className="text-right">{formatCurrency(tx.price_per_share)}</TableCell>
                            <TableCell className="text-right font-medium">
                                {formatCurrency(tx.total_value)}
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </Card>
    )
}

function PerformanceTab({ snapshots, loading, initialCash }) {
    if (loading) {
        return (
            <Card>
                <CardContent className="py-8">
                    <Skeleton className="h-64 w-full" />
                </CardContent>
            </Card>
        )
    }

    if (snapshots.length === 0) {
        return (
            <Card>
                <CardContent className="py-12 text-center text-muted-foreground">
                    <LineChart className="h-12 w-12 mx-auto mb-4 opacity-20" />
                    <p>No performance data yet.</p>
                    <p className="text-sm mt-1">Portfolio snapshots are taken every 15 minutes during market hours.</p>
                </CardContent>
            </Card>
        )
    }

    // Simple text-based chart representation
    const maxValue = Math.max(...snapshots.map(s => s.total_value), initialCash)
    const minValue = Math.min(...snapshots.map(s => s.total_value), initialCash)
    const range = maxValue - minValue || 1

    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-lg">Portfolio Value Over Time</CardTitle>
                <CardDescription>
                    {snapshots.length} data points
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="space-y-2">
                    {/* Mini chart visualization */}
                    <div className="h-32 flex items-end gap-1 border-b pb-2">
                        {snapshots.slice(-50).map((snapshot, i) => {
                            const height = ((snapshot.total_value - minValue) / range) * 100
                            const isPositive = snapshot.total_value >= initialCash
                            return (
                                <div
                                    key={i}
                                    className={`flex-1 min-w-1 rounded-t transition-all ${isPositive
                                        ? 'bg-emerald-500/60 hover:bg-emerald-500'
                                        : 'bg-red-500/60 hover:bg-red-500'
                                        }`}
                                    style={{ height: `${Math.max(height, 5)}%` }}
                                    title={`${formatDate(snapshot.snapshot_at)}: ${formatCurrency(snapshot.total_value)}`}
                                />
                            )
                        })}
                    </div>
                    <div className="flex justify-between text-xs text-muted-foreground">
                        <span>{formatDate(snapshots[0]?.snapshot_at)}</span>
                        <span>{formatDate(snapshots[snapshots.length - 1]?.snapshot_at)}</span>
                    </div>
                </div>

                <Separator className="my-6" />

                {/* Stats summary */}
                <div className="grid grid-cols-3 gap-4 text-center">
                    <div>
                        <p className="text-sm text-muted-foreground">Starting Value</p>
                        <p className="font-semibold">{formatCurrency(initialCash)}</p>
                    </div>
                    <div>
                        <p className="text-sm text-muted-foreground">Current Value</p>
                        <p className="font-semibold">{formatCurrency(snapshots[snapshots.length - 1]?.total_value)}</p>
                    </div>
                    <div>
                        <p className="text-sm text-muted-foreground">Peak Value</p>
                        <p className="font-semibold">{formatCurrency(maxValue)}</p>
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}
