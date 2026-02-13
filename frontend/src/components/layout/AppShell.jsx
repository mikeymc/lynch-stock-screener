// ABOUTME: Main app shell layout with dual sidebars
// ABOUTME: Left sidebar for navigation, right sidebar for chat

import { useState, useEffect, useRef } from 'react'
import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { MessageSquare, Plus, Bell, SlidersHorizontal } from 'lucide-react'
import AnalysisChat from '@/components/AnalysisChat'
import ChatHistory from '@/components/ChatHistory'
import SearchPopover from '@/components/SearchPopover'
import UserAvatar from '@/components/UserAvatar'
import { FeedbackWidget } from '@/components/FeedbackWidget'
import { useChatContext } from '@/context/ChatContext'
import { useAuth } from '@/context/AuthContext'
import { useTheme } from '../theme-provider'
import {
    Sidebar,
    SidebarContent,
    SidebarGroup,
    SidebarGroupContent,
    SidebarGroupLabel,
    SidebarHeader,
    SidebarMenu,
    SidebarMenuButton,
    SidebarMenuItem,
    SidebarProvider,
    SidebarTrigger,
    SidebarInset,
    useSidebar,
} from '@/components/ui/sidebar'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
    ResizableHandle,
    ResizablePanel,
    ResizablePanelGroup,
} from "@/components/ui/resizable"
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'

// Icons
const ChevronDown = () => <span className="text-xs">▼</span>
const ChevronRight = () => <span className="text-xs">▶</span>
const TrendingUp = () => <span>📈</span>

function AppShellContent({
    filter, setFilter,
    algorithm, setAlgorithm,
    summary = {},
    watchlistCount = 0,
    showAdvancedFilters, setShowAdvancedFilters,
    activeCharacter = 'lynch',
    featureFlags = {}
}) {
    const { isMobile, setOpenMobile } = useSidebar()
    const { user } = useAuth()
    const { conversations, removeConversation, activeConversationId, setActiveConversationId } = useChatContext()
    const { theme } = useTheme()
    const [feedbackOpen, setFeedbackOpen] = useState(false)
    const [alertsCount, setAlertsCount] = useState(0)

    // ... existing content ...

    const [isDark, setIsDark] = useState(false)
    useEffect(() => {
        if (theme === 'system') {
            setIsDark(window.matchMedia('(prefers-color-scheme: dark)').matches)
        } else {
            setIsDark(['dark', 'midnight', 'classic2'].includes(theme))
        }
    }, [theme])

    const handleNewChat = () => {
        // Setting activeConversationId to null triggers AnalysisChat to create a new conversation
        setActiveConversationId(null)
    }

    const handleDeleteConversation = async (conversationId) => {
        if (!confirm('Delete this conversation? This cannot be undone.')) {
            return
        }

        try {
            const response = await fetch(`/api/agent/conversation/${conversationId}`, {
                method: 'DELETE',
                credentials: 'include'
            })

            if (response.ok) {
                removeConversation(conversationId)
                // If deleting the active conversation, clear it
                if (activeConversationId === conversationId) {
                    setActiveConversationId(null)
                }
            } else {
                console.error('Failed to delete conversation')
            }
        } catch (error) {
            console.error('Error deleting conversation:', error)
        }
    }

    const onNavClick = () => {
        if (isMobile) {
            setOpenMobile(false)
        }
    }
    const location = useLocation()
    const navigate = useNavigate()
    const { symbol } = useParams()
    const [chatOpen, setChatOpen] = useState(false)
    const [screenerOpen, setScreenerOpen] = useState(true)
    const [filterOpen, setFilterOpen] = useState(true)
    const [analysisOpen, setAnalysisOpen] = useState(true)
    const [chatsOpen, setChatsOpen] = useState(true) // State for chat history collapsible
    const {
        alertsEnabled = false,
        economyLinkEnabled = false,
        dashboardEnabled = false,
        redditEnabled = false
    } = featureFlags

    const lastSyncRef = useRef(null)

    useEffect(() => {
        if (!alertsEnabled) return // Don't fetch counts if disabled

        const fetchUpdates = async () => {
            try {
                // Poll for both alerts and price updates
                const url = lastSyncRef.current
                    ? `/api/alerts?since=${encodeURIComponent(lastSyncRef.current)}`
                    : '/api/alerts'

                const response = await fetch(url)
                if (response.ok) {
                    const data = await response.json()
                    // Count triggered alerts
                    const triggered = (data.alerts || []).filter(a => a.status === 'triggered').length
                    setAlertsCount(triggered)

                    // Update timestamp for next poll
                    if (data.timestamp) {
                        lastSyncRef.current = data.timestamp
                    }

                    // Dispatch price updates if any
                    if (data.updates && data.updates.length > 0) {
                        console.log(`Received ${data.updates.length} stock updates`)
                        window.dispatchEvent(new CustomEvent('price-updates', {
                            detail: { updates: data.updates }
                        }))
                    }
                }
            } catch (error) {
                console.error('Error fetching updates:', error)
            }
        }
        fetchUpdates()
        // Poll every minute
        const interval = setInterval(fetchUpdates, 60000)
        return () => clearInterval(interval)
    }, [alertsEnabled])


    // Detect screen size for responsive chat sidebar - initialize synchronously if possible
    const [isLargeScreen, setIsLargeScreen] = useState(() => {
        if (typeof window !== 'undefined') {
            return window.matchMedia('(min-width: 1024px)').matches
        }
        return false
    })

    useEffect(() => {
        const mediaQuery = window.matchMedia('(min-width: 1024px)')
        const handler = (e) => setIsLargeScreen(e.matches)
        mediaQuery.addEventListener('change', handler)
        return () => mediaQuery.removeEventListener('change', handler)
    }, [])

    const isStockDetail = location.pathname.startsWith('/stock/')
    const isEconomyPage = location.pathname === '/economy'
    const isDashboard = location.pathname === '/dashboard'
    const isStocksPage = location.pathname === '/'

    const getCount = (statusKey) => {
        if (!summary) return 0
        const map = {
            'PASS': 'passCount',
            'CLOSE': 'closeCount',
            'FAIL': 'failCount',
            'STRONG_BUY': 'strong_buy_count',
            'BUY': 'buy_count',
            'HOLD': 'hold_count',
            'CAUTION': 'caution_count',
            'AVOID': 'avoid_count'
        }
        return summary[map[statusKey]] || 0
    }

    // Determine chat context
    const chatSymbol = isStockDetail ? symbol : null
    const chatContext = isStockDetail ? 'general' : 'market' // 'market' context for main page
    const formattedCharacter = activeCharacter ? activeCharacter.charAt(0).toUpperCase() + activeCharacter.slice(1) : 'Lynch'
    const chatTitle = formattedCharacter

    return (
        <div className="flex h-screen w-full overflow-hidden">
            {/* Left Sidebar - Navigation */}
            <Sidebar className="border-r">
                <SidebarHeader className="p-4">
                    <div
                        className="flex items-center gap-2 cursor-pointer"
                        onClick={() => {
                            navigate('/')
                            onNavClick()
                        }}
                    >
                        <img
                            src={`/icons/bonsai_${isDark ? 'white' : 'black'}.png`}
                            className="h-8 w-8 object-contain"
                            alt="Logo"
                        />
                        <span className="font-semibold text-lg tracking-tight">papertree.ai</span>
                    </div>
                </SidebarHeader>

                <SidebarContent className="overflow-x-hidden">
                    <ScrollArea className="h-full">

                        {/* Primary Navigation - Always Visible */}
                        <SidebarGroup>
                            <SidebarGroupContent>
                                <SidebarMenu>
                                    <SidebarMenuItem>
                                        <SidebarMenuButton
                                            onClick={() => {
                                                navigate('/')
                                                setFilter('all')
                                                onNavClick()
                                            }}
                                            isActive={isStocksPage && filter === 'all'}
                                            className="pl-4 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                        >
                                            <span>All Stocks</span>
                                        </SidebarMenuButton>
                                    </SidebarMenuItem>
                                    <SidebarMenuItem>
                                        <SidebarMenuButton
                                            onClick={() => {
                                                navigate('/')
                                                setFilter('watchlist')
                                                onNavClick()
                                            }}
                                            isActive={filter === 'watchlist'}
                                            className="pl-4 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                        >
                                            <span className="flex-1">Watchlist</span>
                                            {watchlistCount > 0 && (
                                                <span className="text-xs text-muted-foreground opacity-50">{watchlistCount}</span>
                                            )}
                                        </SidebarMenuButton>
                                    </SidebarMenuItem>
                                    <SidebarMenuItem>
                                        <SidebarMenuButton
                                            onClick={() => {
                                                navigate('/portfolios')
                                                onNavClick()
                                            }}
                                            isActive={location.pathname === '/portfolios'}
                                            className="pl-4 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                        >
                                            <span className="flex-1">Portfolios</span>
                                        </SidebarMenuButton>
                                    </SidebarMenuItem>
                                    {economyLinkEnabled && (
                                        <SidebarMenuItem>
                                            <SidebarMenuButton
                                                onClick={() => {
                                                    navigate('/economy')
                                                    onNavClick()
                                                }}
                                                isActive={isEconomyPage}
                                                className="pl-4 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                            >
                                                <span>Economy</span>
                                            </SidebarMenuButton>
                                        </SidebarMenuItem>
                                    )}
                                    {dashboardEnabled && (
                                        <SidebarMenuItem>
                                            <SidebarMenuButton
                                                onClick={() => {
                                                    navigate('/dashboard')
                                                    onNavClick()
                                                }}
                                                isActive={isDashboard}
                                                className="pl-4 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                            >
                                                <span>Dashboard</span>
                                            </SidebarMenuButton>
                                        </SidebarMenuItem>
                                    )}
                                    <SidebarMenuItem>
                                        <SidebarMenuButton
                                            onClick={() => {
                                                navigate('/earnings')
                                                onNavClick()
                                            }}
                                            isActive={location.pathname === '/earnings'}
                                            className="pl-4 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                        >
                                            <span>Earnings Calendar</span>
                                        </SidebarMenuButton>
                                    </SidebarMenuItem>
                                </SidebarMenu>
                            </SidebarGroupContent>
                        </SidebarGroup>



                        {/* Filter Section - Only show on Stocks page */}
                        {isStocksPage && (
                            <Collapsible open={filterOpen} onOpenChange={setFilterOpen}>
                                <SidebarGroup>
                                    <CollapsibleTrigger asChild>
                                        <SidebarGroupLabel className="cursor-pointer hover:bg-accent flex items-center justify-between px-4 py-2">
                                            <span>Filter</span>
                                            {filterOpen ? <ChevronDown /> : <ChevronRight />}
                                        </SidebarGroupLabel>
                                    </CollapsibleTrigger>
                                    <CollapsibleContent>
                                        <SidebarGroupContent>
                                            <SidebarMenu>

                                                <SidebarMenuItem>
                                                    <SidebarMenuButton
                                                        onClick={() => {
                                                            navigate('/')
                                                            setFilter('STRONG_BUY')
                                                            onNavClick()
                                                        }}
                                                        isActive={filter === 'STRONG_BUY'}
                                                        className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                                    >
                                                        <span className="flex-1">Excellent</span>
                                                        <span className="text-xs text-muted-foreground opacity-50">{getCount('STRONG_BUY')}</span>
                                                    </SidebarMenuButton>
                                                </SidebarMenuItem>
                                                <SidebarMenuItem>
                                                    <SidebarMenuButton
                                                        onClick={() => {
                                                            navigate('/')
                                                            setFilter('BUY')
                                                            onNavClick()
                                                        }}
                                                        isActive={filter === 'BUY'}
                                                        className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                                    >
                                                        <span className="flex-1">Good</span>
                                                        <span className="text-xs text-muted-foreground opacity-50">{getCount('BUY')}</span>
                                                    </SidebarMenuButton>
                                                </SidebarMenuItem>
                                                <SidebarMenuItem>
                                                    <SidebarMenuButton
                                                        onClick={() => {
                                                            navigate('/')
                                                            setFilter('HOLD')
                                                            onNavClick()
                                                        }}
                                                        isActive={filter === 'HOLD'}
                                                        className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                                    >
                                                        <span className="flex-1">Fair</span>
                                                        <span className="text-xs text-muted-foreground opacity-50">{getCount('HOLD')}</span>
                                                    </SidebarMenuButton>
                                                </SidebarMenuItem>
                                                <SidebarMenuItem>
                                                    <SidebarMenuButton
                                                        onClick={() => {
                                                            navigate('/')
                                                            setFilter('CAUTION')
                                                            onNavClick()
                                                        }}
                                                        isActive={filter === 'CAUTION'}
                                                        className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                                    >
                                                        <span className="flex-1">Weak</span>
                                                        <span className="text-xs text-muted-foreground opacity-50">{getCount('CAUTION')}</span>
                                                    </SidebarMenuButton>
                                                </SidebarMenuItem>
                                                <SidebarMenuItem>
                                                    <SidebarMenuButton
                                                        onClick={() => {
                                                            navigate('/')
                                                            setFilter('AVOID')
                                                            onNavClick()
                                                        }}
                                                        isActive={filter === 'AVOID'}
                                                        className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                                    >
                                                        <span className="flex-1">Poor</span>
                                                        <span className="text-xs text-muted-foreground opacity-50">{getCount('AVOID')}</span>
                                                    </SidebarMenuButton>
                                                </SidebarMenuItem>
                                            </SidebarMenu>
                                        </SidebarGroupContent>
                                    </CollapsibleContent>
                                </SidebarGroup>
                            </Collapsible>
                        )}

                        {/* Analysis Section - Only show when stock is selected */}
                        {isStockDetail && symbol && (
                            <Collapsible open={analysisOpen} onOpenChange={setAnalysisOpen}>
                                <SidebarGroup>
                                    <CollapsibleTrigger asChild>
                                        <SidebarGroupLabel className="cursor-pointer hover:bg-accent flex items-center justify-between px-4 py-2">
                                            <span>{symbol}</span>
                                            {analysisOpen ? <ChevronDown /> : <ChevronRight />}
                                        </SidebarGroupLabel>
                                    </CollapsibleTrigger>
                                    <CollapsibleContent>
                                        <SidebarGroupContent>
                                            <SidebarMenu>
                                                <SidebarMenuItem>
                                                    <SidebarMenuButton
                                                        onClick={() => {
                                                            navigate(`/stock/${symbol}?tab=overview`)
                                                            onNavClick()
                                                        }}
                                                        isActive={location.search.includes('tab=overview') || (!location.search && location.pathname === `/stock/${symbol}`)}
                                                        className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                                    >
                                                        <span>Overview</span>
                                                    </SidebarMenuButton>
                                                </SidebarMenuItem>
                                                <SidebarMenuItem>
                                                    <SidebarMenuButton
                                                        onClick={() => {
                                                            navigate(`/stock/${symbol}?tab=analysis`)
                                                            onNavClick()
                                                        }}
                                                        isActive={location.search.includes('tab=analysis')}
                                                        className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                                    >
                                                        <span>Thesis</span>
                                                    </SidebarMenuButton>
                                                </SidebarMenuItem>
                                                <SidebarMenuItem>
                                                    <SidebarMenuButton
                                                        onClick={() => {
                                                            navigate(`/stock/${symbol}?tab=charts`)
                                                            onNavClick()
                                                        }}
                                                        isActive={location.search.includes('tab=charts')}
                                                        className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                                    >
                                                        <span>Financials</span>
                                                    </SidebarMenuButton>
                                                </SidebarMenuItem>
                                                <SidebarMenuItem>
                                                    <SidebarMenuButton
                                                        onClick={() => {
                                                            navigate(`/stock/${symbol}?tab=sentiment`)
                                                            onNavClick()
                                                        }}
                                                        isActive={location.search.includes('tab=sentiment')}
                                                        className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                                    >
                                                        <span>Wall Street Sentiment</span>
                                                    </SidebarMenuButton>
                                                </SidebarMenuItem>
                                                <SidebarMenuItem>
                                                    <SidebarMenuButton
                                                        onClick={() => {
                                                            navigate(`/stock/${symbol}?tab=insider`)
                                                            onNavClick()
                                                        }}
                                                        isActive={location.search.includes('tab=insider')}
                                                        className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                                    >
                                                        <span>Insider Trades</span>
                                                    </SidebarMenuButton>
                                                </SidebarMenuItem>
                                                <SidebarMenuItem>
                                                    <SidebarMenuButton
                                                        onClick={() => {
                                                            navigate(`/stock/${symbol}?tab=health`)
                                                            onNavClick()
                                                        }}
                                                        isActive={location.search.includes('tab=health')}
                                                        className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                                    >
                                                        <span>Business Health</span>
                                                    </SidebarMenuButton>
                                                </SidebarMenuItem>
                                                <SidebarMenuItem>
                                                    <SidebarMenuButton
                                                        onClick={() => {
                                                            navigate(`/stock/${symbol}?tab=dcf`)
                                                            onNavClick()
                                                        }}
                                                        isActive={location.search.includes('tab=dcf')}
                                                        className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                                    >
                                                        <span>DCF Analysis</span>
                                                    </SidebarMenuButton>
                                                </SidebarMenuItem>
                                                <SidebarMenuItem>
                                                    <SidebarMenuButton
                                                        onClick={() => {
                                                            navigate(`/stock/${symbol}?tab=news`)
                                                            onNavClick()
                                                        }}
                                                        isActive={location.search.includes('tab=news')}
                                                        className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                                    >
                                                        <span>News</span>
                                                    </SidebarMenuButton>
                                                </SidebarMenuItem>
                                                <SidebarMenuItem>
                                                    <SidebarMenuButton
                                                        onClick={() => {
                                                            navigate(`/stock/${symbol}?tab=transcripts`)
                                                            onNavClick()
                                                        }}
                                                        isActive={location.search.includes('tab=transcripts')}
                                                        className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                                    >
                                                        <span>Earnings Transcript</span>
                                                    </SidebarMenuButton>
                                                </SidebarMenuItem>
                                                {redditEnabled && (
                                                    <SidebarMenuItem>
                                                        <SidebarMenuButton
                                                            onClick={() => {
                                                                navigate(`/stock/${symbol}?tab=reddit`)
                                                                onNavClick()
                                                            }}
                                                            isActive={location.search.includes('tab=reddit')}
                                                            className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
                                                        >
                                                            <span>Reddit</span>
                                                        </SidebarMenuButton>
                                                    </SidebarMenuItem>
                                                )}
                                            </SidebarMenu>
                                        </SidebarGroupContent>
                                    </CollapsibleContent>
                                </SidebarGroup>
                            </Collapsible>
                        )}

                        {/* Chat History Section */}
                        <Collapsible open={chatsOpen} onOpenChange={setChatsOpen} style={{ maxWidth: '100%', overflow: 'hidden' }}>
                            <SidebarGroup className="overflow-x-hidden">
                                <CollapsibleTrigger asChild>
                                    <SidebarGroupLabel className="cursor-pointer hover:bg-accent flex items-center justify-between px-4 py-2">
                                        <span>Chats</span>
                                        {chatsOpen ? <ChevronDown /> : <ChevronRight />}
                                    </SidebarGroupLabel>
                                </CollapsibleTrigger>
                                <CollapsibleContent>
                                    <ChatHistory
                                        onSelectConversation={onNavClick}
                                        onDeleteConversation={handleDeleteConversation}
                                    />
                                </CollapsibleContent>
                            </SidebarGroup>
                        </Collapsible>
                    </ScrollArea>
                </SidebarContent>

                {/* Settings and Help at bottom */}
                <div className="mt-auto border-t p-2">
                    <SidebarMenu>
                        <SidebarMenuItem>
                            <SidebarMenuButton onClick={() => {
                                navigate('/help')
                                onNavClick()
                            }}>
                                <span>Help</span>
                            </SidebarMenuButton>
                        </SidebarMenuItem>
                        <SidebarMenuItem>
                            <SidebarMenuButton onClick={() => {
                                navigate('/settings')
                                onNavClick()
                            }}>
                                <span>Settings</span>
                            </SidebarMenuButton>
                        </SidebarMenuItem>
                        <SidebarMenuItem>
                            <SidebarMenuButton onClick={() => {
                                setFeedbackOpen(true)
                                onNavClick()
                            }}>
                                <span>Send Feedback</span>
                            </SidebarMenuButton>
                        </SidebarMenuItem>
                        <SidebarMenuItem>
                            <SidebarMenuButton asChild>
                                <a href="mailto:info@papertree.ai">
                                    <span>info@papertree.ai</span>
                                </a>
                            </SidebarMenuButton>
                        </SidebarMenuItem>
                    </SidebarMenu>
                </div>
            </Sidebar>

            {/* Main Content */}
            <SidebarInset className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
                {/* Top bar with triggers */}
                <header className="flex h-12 items-center justify-between border-b px-4 shrink-0">
                    {/* Left side - Sidebar trigger, Search, and Filter */}
                    <div className="flex items-center gap-2">
                        <SidebarTrigger className="h-10 w-10 [&_svg]:size-[18px]" />
                        <SearchPopover onSelect={(sym) => navigate(`/stock/${sym}`)} />
                        <Button
                            variant="ghost"
                            size="icon"
                            className={`text-muted-foreground hover:text-foreground h-10 w-10 [&_svg]:size-5 ${showAdvancedFilters ? 'bg-accent text-accent-foreground' : ''}`}
                            onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
                        >
                            <SlidersHorizontal />
                        </Button>
                    </div>

                    {/* Right side - Alerts and Avatar */}
                    <div className="flex items-center gap-2">
                        {alertsEnabled && (
                            <Button
                                variant="ghost"
                                size="icon"
                                className="relative h-10 w-10 [&_svg]:size-[18px]"
                                onClick={() => navigate('/alerts')}
                            >
                                <Bell />
                                {alertsCount > 0 && (
                                    <span className="absolute top-1 right-1 h-2.5 w-2.5 rounded-full bg-red-600 border-2 border-background"></span>
                                )}
                            </Button>
                        )}

                        {/* Chat toggle - only show on small screens */}
                        {!isLargeScreen && (
                            <Sheet open={chatOpen} onOpenChange={setChatOpen}>
                                <SheetTrigger asChild>
                                    <Button variant="ghost" size="icon">
                                        <MessageSquare className="h-5 w-5" />
                                    </Button>
                                </SheetTrigger>
                                <SheetContent side="right" className="w-[400px] sm:w-[540px] p-0">
                                    <SheetHeader className="px-4 py-3 border-b">
                                        <SheetTitle>{chatTitle}</SheetTitle>
                                    </SheetHeader>
                                    <div className="flex flex-col h-[calc(100%-60px)]">
                                        <AnalysisChat
                                            symbol={chatSymbol}
                                            chatOnly={true}
                                            contextType={chatContext}
                                            activeCharacter={activeCharacter}
                                        />
                                    </div>
                                </SheetContent>
                            </Sheet>
                        )}
                        <UserAvatar />
                    </div>
                </header>

                {/* Page content - with resizable panels on large screens */}
                <ResizablePanelGroup id="app-shell-layout-v8" direction="horizontal" className="flex-1 overflow-hidden">
                    <ResizablePanel id="main-content-panel" defaultSize={60} order={1}>
                        {/* Main content */}
                        <main className="h-full overflow-auto p-4 min-w-0 scrollbar-hide">
                            <div className="max-w-screen-lg mx-auto">
                                <Outlet />
                            </div>
                        </main>
                    </ResizablePanel>

                    {isLargeScreen && (
                        <>
                            <ResizableHandle />
                            <ResizablePanel id="chat-sidebar-panel" defaultSize={40} order={2}>
                                <aside className="h-full border-l bg-background flex flex-col">
                                    <div className="px-4 py-3 border-b flex items-center justify-between shrink-0">
                                        <h2 className="font-semibold">{chatTitle}</h2>
                                    </div>
                                    <div className="flex-1 overflow-hidden">
                                        <AnalysisChat
                                            symbol={chatSymbol}
                                            chatOnly={true}
                                            contextType={chatContext}
                                            activeCharacter={activeCharacter}
                                        />
                                    </div>
                                </aside>
                            </ResizablePanel>
                        </>
                    )}
                </ResizablePanelGroup>
                <FeedbackWidget isOpen={feedbackOpen} onClose={() => setFeedbackOpen(false)} />
            </SidebarInset>
        </div>
    )
}

export default function AppShell(props) {
    return (
        <SidebarProvider>
            <AppShellContent {...props} />
        </SidebarProvider>
    )
}
