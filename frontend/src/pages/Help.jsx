// ABOUTME: Help and onboarding page for new users
// ABOUTME: Provides guides, explanations, and screenshots for app features

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

import { useAuth } from "../context/AuthContext"

const API_BASE = '/api'

export default function Help() {
    const { user, checkAuth } = useAuth()
    const [activeTab, setActiveTab] = useState("quick-start")
    const [hasTriggeredOnboarding, setHasTriggeredOnboarding] = useState(false)

    // Mark onboarding as complete when visiting this page
    useEffect(() => {
        if (user && !user.has_completed_onboarding && !hasTriggeredOnboarding) {
            setHasTriggeredOnboarding(true) // Prevent multiple calls
            fetch(`${API_BASE}/user/complete_onboarding`, {
                method: 'POST',
                credentials: 'include'
            })
                .then(() => {
                    // Refresh local user state so we don't get redirected back here
                    checkAuth()
                })
                .catch(err => {
                    console.error('Failed to complete onboarding:', err)
                    setHasTriggeredOnboarding(false) // Allow retry on error? Or keep blocked to prevent spam?
                    // If it's a 405 or persistent error, retry might just spam. Better to keep it blocked for this session.
                })
        }
    }, [user, checkAuth, hasTriggeredOnboarding])

    const sidebarItems = [
        {
            id: "quick-start",
            title: "Quick Start Guide",
            section: "Getting Started"
        },
        {
            id: "stock-scores",
            title: "Stock Scores",
            section: "Getting Started"
        },
        {
            id: "filtering",
            title: "Filtering & Search",
            section: "Getting Started"
        },
        {
            id: "watchlist",
            title: "Watchlist",
            section: "Getting Started"
        },
        {
            id: "expertise-level",
            title: "Expertise Level",
            section: "Getting Started"
        },
        {
            id: "overview",
            title: "Overview Tab",
            section: "Stock Analysis"
        },
        {
            id: "analysis",
            title: "Thesis & Analysis",
            section: "Stock Analysis"
        },
        {
            id: "financials",
            title: "Financials & Charts",
            section: "Stock Analysis"
        },
        {
            id: "dcf",
            title: "DCF Valuation",
            section: "Stock Analysis"
        },
        {
            id: "news",
            title: "News & Sentiment",
            section: "Stock Analysis"
        },
        {
            id: "chat",
            title: "What You Can Ask",
            section: "Chat Assistant"
        },
        {
            id: "chat-context",
            title: "Chat Context",
            section: "Chat Assistant"
        },
        {
            id: "investment-styles",
            title: "Investment Styles",
            section: "Chat Assistant"
        },
        {
            id: "multiple-characters",
            title: "Multiple Characters",
            section: "Chat Assistant"
        },
        {
            id: "portfolios",
            title: "Portfolios",
            section: "Portfolio Management"
        },
        {
            id: "manual-trading",
            title: "Manual Trading",
            section: "Portfolio Management"
        },
        {
            id: "automated-trading",
            title: "Automated Trading",
            section: "Portfolio Management"
        },
        {
            id: "setting-alerts",
            title: "Setting Alerts via Chat",
            section: "Alerts & Automation"
        },
        {
            id: "automated-trade-actions",
            title: "Automated Trade Actions",
            section: "Alerts & Automation"
        },
        {
            id: "tuning",
            title: "Algorithm Tuning",
            section: "Advanced"
        },
        {
            id: "advanced-filters",
            title: "Custom Filters",
            section: "Advanced"
        },
    ]

    // Group items by section
    const sections = sidebarItems.reduce((acc, item) => {
        if (!acc[item.section]) {
            acc[item.section] = []
        }
        acc[item.section].push(item)
        return acc
    }, {})

    return (
        <div className="space-y-6 p-10 pb-16 block">
            <div className="space-y-0.5">
                <h2 className="text-2xl font-bold tracking-tight">Help & Guide</h2>
                <p className="text-muted-foreground">
                    Learn how to use papertree.ai to find and analyze investment opportunities.
                </p>
            </div>
            <div className="border-t my-6" />
            <div className="flex flex-col space-y-8 lg:flex-row lg:space-x-12 lg:space-y-0">
                <aside className="-mx-4 lg:w-1/5">
                    <nav className="flex flex-col space-y-1">
                        {Object.entries(sections).map(([sectionName, items]) => (
                            <div key={sectionName} className="mb-4">
                                <div className="px-3 py-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                                    {sectionName}
                                </div>
                                {items.map((item) => (
                                    <Button
                                        key={item.id}
                                        variant="ghost"
                                        className={cn(
                                            "justify-start hover:bg-muted font-normal w-full text-left",
                                            activeTab === item.id && "bg-muted hover:bg-muted font-medium"
                                        )}
                                        onClick={() => setActiveTab(item.id)}
                                    >
                                        {item.title}
                                    </Button>
                                ))}
                            </div>
                        ))}
                    </nav>
                </aside>
                <div className="flex-1 lg:max-w-4xl">
                    {activeTab === "quick-start" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Quick Start Guide</h3>
                                <p className="text-sm text-muted-foreground">
                                    Get up and running with papertree.ai in 5 minutes.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>What is papertree.ai?</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div className="space-y-2">
                                        <h4 className="font-medium text-sm">The Problem: Drowning in Data</h4>
                                        <p className="text-sm text-muted-foreground">
                                            The modern market offers unlimited data but very little wisdom. Investors are constantly bombarded with noise, biased speculation, and herd mentality. Most platforms exacerbate this by drowning you in charts and raw numbers, optimizing for technical trading rather than fundamental understanding.
                                        </p>
                                    </div>

                                    <div className="space-y-2">
                                        <h4 className="font-medium text-sm">Our Philosophy: Discipline Over Data</h4>
                                        <p className="text-sm text-muted-foreground">
                                            We are opinionated and focused. Instead of giving you every signal in the universe, we democratize access to the minds of the greatest investors who ever lived. Imagine having direct access to the discipline, patience, and rigorous criteria of Peter Lynch or Warren Buffett—applied instantly to every stock in the market.
                                        </p>
                                    </div>

                                    <div className="space-y-2">
                                        <h4 className="font-medium text-sm">How It Works: Quantitative Rigor + AI Insight</h4>
                                        <p className="text-sm text-muted-foreground">We combine two powerful layers of analysis to help you build a winning thesis:</p>
                                        <ul className="text-sm text-muted-foreground space-y-2 list-disc list-inside ml-2">
                                            <li>
                                                <strong className="text-foreground">The Screen (Quantitative):</strong> First, we apply a coarse-grained, "tuneable" algorithm to thousands of stocks. This mercilessly filters the market based on the hard numbers—growth rates, debt ratios, and valuations—that mattered most to the legends.
                                            </li>
                                            <li>
                                                <strong className="text-foreground">The Agent (Qualitative):</strong> Once a candidate is found, our AI Agent takes over. It analyzes annual reports, earnings calls, insider trading, and macro data <em>through the specific lens</em> of your chosen investor. It doesn't just summarize news, SEC filings, and earnings calls; it evaluates them, asking: <em>"Does this company have a durable moat?"</em> or <em>"Is this a misunderstanding that creates a buying opportunity?"</em>
                                            </li>
                                        </ul>
                                    </div>

                                    <div className="space-y-2">
                                        <h4 className="font-medium text-sm">The Result</h4>
                                        <p className="text-sm text-muted-foreground">
                                            By putting the discipline of the masters directly into your hands, we help you ignore the noise and focus on what actually drives long-term returns: fundamental value.
                                        </p>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Your First Steps</CardTitle>
                                    <CardDescription>Here's how to get started</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div>
                                        <h4 className="font-medium mb-2">1. Browse Pre-Screened Stocks</h4>
                                        <p className="text-sm text-muted-foreground mb-3">
                                            The main page shows stocks that have already been analyzed and scored. Browse the list to find interesting opportunities.
                                        </p>
                                        <img
                                            src="/help/stock-list-view.png"
                                            alt="Stock List View"
                                            className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                        />
                                    </div>

                                    <div>
                                        <h4 className="font-medium mb-2">2. Search for Stocks</h4>
                                        <p className="text-sm text-muted-foreground mb-3">
                                            Use the search bar in the top header to quickly find any stock by symbol or company name.
                                        </p>
                                        <img
                                            src="/help/search-bar.png"
                                            alt="Search Bar"
                                            className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                        />
                                    </div>

                                    <div>
                                        <h4 className="font-medium mb-2">3. Filter by Quality</h4>
                                        <p className="text-sm text-muted-foreground mb-3">
                                            Use the sidebar to filter stocks by rating: Excellent, Good, Neutral, Weak, or Poor.
                                        </p>
                                        <img
                                            src="/help/sidebar-filters.png"
                                            alt="Sidebar Filters"
                                            className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                        />
                                    </div>

                                    <div>
                                        <h4 className="font-medium mb-2">4. Click a Stock for Details</h4>
                                        <p className="text-sm text-muted-foreground mb-3">
                                            Click any stock card to see comprehensive analysis including financials, valuation, news, and AI insights.
                                        </p>
                                        <img
                                            src="/help/stock-details.png"
                                            alt="Stock Detail Page"
                                            className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                        />
                                    </div>

                                    <div>
                                        <h4 className="font-medium mb-2">5. Ask the AI Assistant</h4>
                                        <p className="text-sm text-muted-foreground mb-3">
                                            Use the chat panel on the right to ask questions about stocks or market conditions. The AI adapts to your chosen investment style.
                                        </p>
                                        <img
                                            src="/help/chat-panel.png"
                                            alt="Chat Panel"
                                            className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                        />
                                    </div>
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "stock-scores" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Understanding Stock Scores</h3>
                                <p className="text-sm text-muted-foreground">
                                    Learn what the ratings mean and how stocks are evaluated.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>Rating System</CardTitle>
                                    <CardDescription>What the scores mean</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <p className="text-sm font-medium">
                                        The rating system is character-specific: in Lynch mode, stocks are rated based on Lynch's metrics, while in Buffett mode they're rated based on Buffett's metrics. The app defaults to Lynch mode.
                                    </p>
                                    <div className="space-y-3">
                                        <div className="flex items-start gap-3">
                                            <div className="w-20 h-8 bg-green-600 rounded flex items-center justify-center text-white text-xs font-medium shrink-0">
                                                Excellent
                                            </div>
                                            <p className="text-sm text-muted-foreground">
                                                Strong fundamentals across multiple criteria. High growth, reasonable valuation, solid balance sheet.
                                            </p>
                                        </div>
                                        <div className="flex items-start gap-3">
                                            <div className="w-20 h-8 bg-green-500 rounded flex items-center justify-center text-white text-xs font-medium shrink-0">
                                                Good
                                            </div>
                                            <p className="text-sm text-muted-foreground">
                                                Generally solid fundamentals with some standout qualities. Worth deeper investigation.
                                            </p>
                                        </div>
                                        <div className="flex items-start gap-3">
                                            <div className="w-20 h-8 bg-yellow-500 rounded flex items-center justify-center text-white text-xs font-medium shrink-0">
                                                Neutral
                                            </div>
                                            <p className="text-sm text-muted-foreground">
                                                Mixed signals. Some positive qualities, some concerns. Requires careful analysis.
                                            </p>
                                        </div>
                                        <div className="flex items-start gap-3">
                                            <div className="w-20 h-8 bg-orange-500 rounded flex items-center justify-center text-white text-xs font-medium shrink-0">
                                                Weak
                                            </div>
                                            <p className="text-sm text-muted-foreground">
                                                Multiple concerning indicators. May be risky or overvalued.
                                            </p>
                                        </div>
                                        <div className="flex items-start gap-3">
                                            <div className="w-20 h-8 bg-red-500 rounded flex items-center justify-center text-white text-xs font-medium shrink-0">
                                                Poor
                                            </div>
                                            <p className="text-sm text-muted-foreground">
                                                Significant red flags. Poor fundamentals or very high valuation.
                                            </p>
                                        </div>
                                    </div>
                                    <p className="text-sm text-muted-foreground italic border-t pt-3">
                                        <strong>Important:</strong> These scores are a coarse-grained first pass screen. A stock with an 'Excellent' score may look poor under deeper scrutiny, while a lower-scored stock might reveal hidden value. This is where AI analysis and your own research become critical.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Key Evaluation Criteria</CardTitle>
                                    <CardDescription>What each investment style emphasizes</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div>
                                        <h4 className="font-medium mb-2">Lynch Mode (Default)</h4>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            Peter Lynch focused on growth at a reasonable price (GARP). Key metrics include:
                                        </p>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li><strong>PEG Ratio</strong> - Price/Earnings to Growth ratio. Below 1.0 is ideal.</li>
                                            <li><strong>P/E Ratio</strong> - Looking for reasonable valuations relative to growth.</li>
                                            <li><strong>Revenue & Earnings Growth</strong> - Consistent 5-year growth trends.</li>
                                            <li><strong>Debt/Equity</strong> - Manageable debt levels (below 1.0 preferred).</li>
                                            <li><strong>Institutional Ownership</strong> - Lower can indicate undiscovered opportunities.</li>
                                            <li><strong>Dividend Yield</strong> - Bonus for income, though not required.</li>
                                        </ul>
                                    </div>
                                    <div className="border-t pt-3">
                                        <h4 className="font-medium mb-2">Buffett Mode</h4>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            Warren Buffett emphasized quality businesses with durable competitive advantages. Key metrics include:
                                        </p>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li><strong>Return on Equity (ROE)</strong> - High ROE (above 15%) indicates efficient capital use.</li>
                                            <li><strong>Gross Margin</strong> - Wide margins (above 40%) suggest pricing power.</li>
                                            <li><strong>Owner Earnings</strong> - True cash generated for shareholders.</li>
                                            <li><strong>Debt/Earnings</strong> - Ability to pay off debt from earnings (below 4 years ideal).</li>
                                            <li><strong>Revenue & Earnings Growth</strong> - Steady, predictable growth.</li>
                                            <li><strong>Dividend Yield</strong> - Not required, but appreciated for quality companies.</li>
                                        </ul>
                                    </div>
                                    <p className="text-sm text-muted-foreground italic border-t pt-3">
                                        Both modes also evaluate revenue consistency, income consistency, and valuation trends. The app defaults to Lynch mode.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Score Cards on Stock Pages</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <p className="text-sm text-muted-foreground mb-3">
                                        Each stock detail page shows individual scores for different criteria, helping you understand strengths and weaknesses.
                                    </p>
                                    <img
                                        src="/help/overview.png"
                                        alt="Score Cards and Metrics"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "filtering" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Filtering & Search</h3>
                                <p className="text-sm text-muted-foreground">
                                    Find exactly what you're looking for with powerful filters.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>Quick Search</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Use the search bar in the top header to quickly find any stock by symbol or company name.
                                    </p>
                                    <img
                                        src="/help/search-bar.png"
                                        alt="Search Bar with Autocomplete"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Sidebar Filters</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Filter stocks by rating (Excellent, Good, Neutral, Weak, Poor) using the left sidebar.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        Each filter shows the count of stocks matching that criteria.
                                    </p>
                                    <img
                                        src="/help/filter-by-quality.png"
                                        alt="Active Sidebar Filters"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Advanced Metric-Based Filters</CardTitle>
                                    <CardDescription>Filter by financial metrics and fundamental characteristics</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <p className="text-sm text-muted-foreground">
                                        Click the filter icon (sliders icon) in the top toolbar to open the advanced filters panel. These filters let you refine the scored stock list by specific financial metrics and characteristics.
                                    </p>
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Geographic Filters</h4>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li><strong>Region</strong> - Filter by geographic region (USA, Canada, Europe, Asia, Central/South America, Other)</li>
                                            <li><strong>Country</strong> - Filter by specific country codes (e.g., US, CA, GB, DE)</li>
                                        </ul>
                                    </div>
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Financial Metric Filters</h4>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li><strong>Institutional Ownership %</strong> - Maximum percentage owned by institutions (e.g., ≤ 75%)</li>
                                            <li><strong>Revenue Growth %</strong> - Minimum 5-year compound annual growth rate (e.g., ≥ 15%)</li>
                                            <li><strong>Income Growth %</strong> - Minimum 5-year earnings growth rate (e.g., ≥ 15%)</li>
                                            <li><strong>Debt to Equity</strong> - Maximum debt-to-equity ratio (e.g., ≤ 0.6)</li>
                                            <li><strong>Market Cap ($B)</strong> - Maximum market capitalization in billions (e.g., ≤ 10)</li>
                                            <li><strong>P/E Ratio</strong> - Maximum price-to-earnings ratio (e.g., ≤ 25)</li>
                                        </ul>
                                    </div>
                                    <div className="border-t pt-3">
                                        <h4 className="font-medium text-sm mb-2">How Advanced Filters Work</h4>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            Advanced filters use <strong>AND logic</strong>—all active filters must pass for a stock to appear in results. This is different from sidebar filters which are based on overall recommendation status.
                                        </p>
                                        <p className="text-sm text-muted-foreground">
                                            <strong>Key difference:</strong> Sidebar filters judge quality of recommendation; advanced filters judge quality of underlying financials.
                                        </p>
                                    </div>
                                    <div className="border-t pt-3">
                                        <h4 className="font-medium text-sm mb-2">Filter Persistence</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Your advanced filter settings are automatically saved and synced across sessions. They remain active until you change or clear them.
                                        </p>
                                    </div>
                                    <img
                                        src="/help/advanced-filters-panel.png"
                                        alt="Advanced Filters Panel"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full mt-3"
                                    />
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "watchlist" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Building Your Watchlist</h3>
                                <p className="text-sm text-muted-foreground">
                                    Save stocks you're interested in for quick access.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>Adding to Watchlist</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Click the star icon on any stock card to add it to your watchlist. The star will fill in when the stock is saved.
                                    </p>
                                    <img
                                        src="/help/watchlist-star.png"
                                        alt="Watchlist Star Icon"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Viewing Your Watchlist</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Click "Watchlist" in the left sidebar under the Filter section to see only your saved stocks.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        The watchlist count shows how many stocks you've saved.
                                    </p>
                                    <img
                                        src="/help/sidebar-filters.png"
                                        alt="Watchlist Filter in Sidebar"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Managing Watchlist Items</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Remove items from your watchlist by clicking the filled star icon again. Your watchlist is automatically saved.
                                    </p>
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "expertise-level" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Expertise Level</h3>
                                <p className="text-sm text-muted-foreground">
                                    Customize how analyses and conversations are communicated based on your investing knowledge.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>What is Expertise Level?</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Expertise level adjusts the communication style of all AI-generated content including thesis analyses, chart commentary, and chat responses. This ensures you get explanations that match your current knowledge level—whether you're learning the basics or want advanced technical insights.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        Your expertise setting is applied consistently across all features, creating a tailored experience that grows with your investing journey.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>The Three Levels</CardTitle>
                                    <CardDescription>Choose the level that matches your current knowledge</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Learning</h4>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            <strong>Best for:</strong> Those new to investing or still building foundational knowledge.
                                        </p>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            <strong>Communication style:</strong> Uses simpler terms, avoids jargon, and provides clear explanations for concepts. Educational tone that helps you understand not just what the data shows, but why it matters and how to interpret it.
                                        </p>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>Defines financial terms when first introduced</li>
                                            <li>Explains the reasoning behind investment concepts</li>
                                            <li>Uses analogies and examples to clarify complex ideas</li>
                                            <li>Focuses on building intuition and understanding</li>
                                        </ul>
                                    </div>
                                    <div className="border-t pt-3">
                                        <h4 className="font-medium text-sm mb-2">Practicing (Default)</h4>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            <strong>Best for:</strong> Those who understand the basics and want to deepen their analytical skills.
                                        </p>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            <strong>Communication style:</strong> Balances accessibility with depth. Assumes familiarity with common metrics (P/E, ROE, debt-to-equity) while providing nuanced analysis and context. More detailed evaluation of trade-offs and considerations.
                                        </p>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>Uses standard financial terminology without over-explanation</li>
                                            <li>Explores multiple perspectives and considerations</li>
                                            <li>Discusses both quantitative metrics and qualitative factors</li>
                                            <li>Highlights nuances and edge cases in analysis</li>
                                        </ul>
                                    </div>
                                    <div className="border-t pt-3">
                                        <h4 className="font-medium text-sm mb-2">Expert</h4>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            <strong>Best for:</strong> Seasoned investors comfortable with technical language and advanced concepts.
                                        </p>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            <strong>Communication style:</strong> Concise, technical, and focused on unique insights. Assumes deep understanding of financial analysis and skips basic explanations. Emphasizes non-obvious observations and sophisticated analytical points.
                                        </p>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>Uses precise financial terminology and industry jargon</li>
                                            <li>Focuses on edge cases, subtleties, and counter-arguments</li>
                                            <li>Highlights uncommon insights and second-order effects</li>
                                            <li>Dense, efficient communication without redundancy</li>
                                        </ul>
                                    </div>
                                    <img
                                        src="/help/expertise-levels.png"
                                        alt="Expertise Level Settings"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full mt-3"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>What Changes with Expertise Level</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground mb-2">
                                        Your expertise setting affects:
                                    </p>
                                    <ul className="text-sm text-muted-foreground space-y-2 list-disc list-inside ml-2">
                                        <li><strong>Thesis & Analysis</strong> - The investment narrative adjusts its explanatory depth and terminology</li>
                                        <li><strong>Chart Commentary</strong> - Financial chart analysis matches your analytical sophistication</li>
                                        <li><strong>Chat Responses</strong> - The AI agent tailors explanations to your knowledge level</li>
                                        <li><strong>Technical Language</strong> - Balance between accessibility and precision shifts appropriately</li>
                                    </ul>
                                    <p className="text-sm text-muted-foreground mt-3">
                                        Note: Your expertise level is independent of your character selection (Lynch vs Buffett). Both settings work together—character determines the investment philosophy, expertise determines how it's communicated.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Changing Your Expertise Level</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Go to Settings → Expertise Level to change your setting. Your new level applies immediately to all future analyses and conversations.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        Feel free to adjust this as your knowledge grows or if you want to explore concepts from a different depth. There's no wrong choice—pick what helps you learn and make decisions most effectively.
                                    </p>
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "overview" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Overview Tab</h3>
                                <p className="text-sm text-muted-foreground">
                                    Understand the key metrics and snapshot view of any stock.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>Stock Overview</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        The Overview tab provides a quick snapshot of the company with essential metrics at a glance.
                                    </p>
                                    <img
                                        src="/help/overview.png"
                                        alt="Overview Tab with Key Metrics"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Key Metrics Explained</CardTitle>
                                    <CardDescription>What you'll see on stock cards and detail pages</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div>
                                        <h4 className="font-medium mb-2">Lynch Mode Metrics</h4>
                                        <div className="space-y-2 text-sm">
                                            <div>
                                                <strong>P/E Ratio</strong> - Price-to-earnings ratio. Lower can indicate better value.
                                            </div>
                                            <div>
                                                <strong>PEG Ratio</strong> - P/E divided by growth rate. Below 1.0 is attractive.
                                            </div>
                                            <div>
                                                <strong>Debt/Equity</strong> - Financial leverage. Below 1.0 indicates conservative debt use.
                                            </div>
                                            <div>
                                                <strong>Dividend Yield</strong> - Annual dividend as percentage of price.
                                            </div>
                                            <div>
                                                <strong>Institutional Ownership</strong> - Percentage owned by institutions.
                                            </div>
                                            <div>
                                                <strong>5Y Revenue/Income Growth</strong> - Compound annual growth rates over 5 years.
                                            </div>
                                        </div>
                                    </div>
                                    <div className="border-t pt-3">
                                        <h4 className="font-medium mb-2">Buffett Mode Metrics</h4>
                                        <div className="space-y-2 text-sm">
                                            <div>
                                                <strong>P/E Ratio</strong> - Price-to-earnings ratio.
                                            </div>
                                            <div>
                                                <strong>ROE (Return on Equity)</strong> - How efficiently the company uses shareholder capital. Above 15% is strong.
                                            </div>
                                            <div>
                                                <strong>Debt/Earnings</strong> - Years needed to pay off debt with current earnings. Below 4 years is healthy.
                                            </div>
                                            <div>
                                                <strong>Dividend Yield</strong> - Annual dividend as percentage of price.
                                            </div>
                                            <div>
                                                <strong>Gross Margin</strong> - Profitability after cost of goods. Above 40% indicates pricing power.
                                            </div>
                                            <div>
                                                <strong>Owner Earnings</strong> - Cash available to shareholders after reinvestment.
                                            </div>
                                            <div>
                                                <strong>5Y Revenue/Income Growth</strong> - Compound annual growth rates over 5 years.
                                            </div>
                                        </div>
                                    </div>
                                    <p className="text-sm text-muted-foreground italic border-t pt-3">
                                        Both modes also show consistency scores for revenue and income growth, and P/E range position.
                                    </p>
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "analysis" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Thesis & Analysis</h3>
                                <p className="text-sm text-muted-foreground">
                                    Character-specific investment narrative from your chosen investor's perspective.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>Company Thesis</CardTitle>
                                    <CardDescription>Analysis tailored to your selected character</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        The Thesis tab provides a character-specific narrative as if you're hearing directly from Lynch or Buffett about the company. It covers what the company does, its competitive position, key strengths and concerns, and investment considerations—all through the lens of your selected investment philosophy.
                                    </p>
                                    <img
                                        src="/help/brief.png"
                                        alt="Company Thesis with Character Analysis"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Character-Specific Perspectives</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Peter Lynch's Focus</h4>
                                        <p className="text-sm text-muted-foreground">
                                            When viewing a thesis in Lynch mode, the analysis emphasizes:
                                        </p>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>Growth prospects and earnings acceleration</li>
                                            <li>PEG ratio and valuation relative to growth</li>
                                            <li>Whether the company is undiscovered by institutions</li>
                                            <li>Debt management and financial conservatism</li>
                                            <li>Story behind the business and growth drivers</li>
                                        </ul>
                                    </div>
                                    <div className="border-t pt-3">
                                        <h4 className="font-medium text-sm mb-2">Warren Buffett's Focus</h4>
                                        <p className="text-sm text-muted-foreground">
                                            When viewing a thesis in Buffett mode, the analysis emphasizes:
                                        </p>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>Durable competitive advantages and economic moats</li>
                                            <li>Return on equity and capital efficiency</li>
                                            <li>Predictability and consistency of earnings</li>
                                            <li>Management quality and capital allocation</li>
                                            <li>Owner earnings and intrinsic value growth</li>
                                        </ul>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Cached Per Character</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Each thesis is generated and cached separately for each character. This means you can switch between Lynch and Buffett to see how the same company looks through different investment lenses.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        Use the refresh button to regenerate the thesis if you want an updated analysis incorporating new information, or if you've switched characters and want to see that character's perspective.
                                    </p>
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "financials" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Financials & Charts</h3>
                                <p className="text-sm text-muted-foreground">
                                    Visualize historical performance with character-specific editorial analysis.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>Financial Charts & Character Commentary</CardTitle>
                                    <CardDescription>Data visualization with tailored editorial perspective</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        The Financials tab displays charts showing revenue, earnings, and other key metrics over time. More importantly, it provides character-specific editorial commentary on the company's financial performance, informed by quarterly and annual reports, SEC material event filings, company news, analyst sentiment, and business health indicators.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        This narrative helps you understand not just what the numbers show, but what they mean through the perspective of Lynch or Buffett.
                                    </p>
                                    <img
                                        src="/help/financials.png"
                                        alt="Financial Charts with Character Editorial"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Character-Specific Chart Analysis</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <p className="text-sm text-muted-foreground mb-2">
                                        The chart commentary changes based on your selected character, emphasizing different aspects of the financial data:
                                    </p>
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Peter Lynch's Analysis</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Lynch-mode chart commentary focuses on growth trends, earnings acceleration, PEG ratio trends, and whether the company is maintaining reasonable valuations as it grows.
                                        </p>
                                    </div>
                                    <div className="border-t pt-3">
                                        <h4 className="font-medium text-sm mb-2">Warren Buffett's Analysis</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Buffett-mode chart commentary emphasizes return on equity trends, margin stability, earnings consistency, and signs of sustainable competitive advantages in the financial data.
                                        </p>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Unified Narrative Across Sections</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        The chart analysis is organized into sections (growth, cash flow, valuation), but maintains a cohesive narrative throughout. All sections share the same underlying data context—material events, earnings transcripts, news articles—ensuring consistent character-specific interpretation.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        Your selected character's voice and priorities remain consistent across all sections, helping you develop a complete picture through that investment philosophy's lens.
                                    </p>
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "dcf" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">DCF Valuation</h3>
                                <p className="text-sm text-muted-foreground">
                                    Estimate intrinsic value with flexible discounted cash flow analysis.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>What is DCF?</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Discounted Cash Flow (DCF) analysis estimates what a company is worth based on its expected future cash flows, discounted back to present value.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>How the DCF Tool Works</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        The DCF section pre-loads calculable data like WACC (Weighted Average Cost of Capital) and terminal growth rate based on the company's financials.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        You can manually adjust expected growth rates and override the pre-loaded WACC and terminal growth rates to test different scenarios.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        Alternatively, you can request an AI-generated DCF estimation that provides conservative, base case, and optimistic projections along with detailed explanations and resultant valuations for each scenario.
                                    </p>
                                    <img
                                        src="/help/dcf.png"
                                        alt="DCF Analysis Tool"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "news" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">News & Sentiment</h3>
                                <p className="text-sm text-muted-foreground">
                                    Stay informed with recent news and analyst opinions.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>Recent News</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        The News tab aggregates recent articles and press releases about the company.
                                    </p>
                                    <img
                                        src="/help/news.png"
                                        alt="News Feed"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Wall Street Sentiment</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        See analyst ratings, price targets, and institutional sentiment to gauge market consensus.
                                    </p>
                                    <img
                                        src="/help/wall-street-sentiment.png"
                                        alt="Wall Street Sentiment Analysis"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Insider Trading Activity</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Track insider trading with a focus on open market buys and sells by company executives and directors. Insider buying can signal confidence in the company's prospects, while heavy selling might indicate concerns. The app highlights these transactions to help you gauge insider sentiment.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        Open market purchases (as opposed to exercise of stock options) are particularly noteworthy, as they represent insiders putting their own money at risk.
                                    </p>
                                    <img
                                        src="/help/earnings-call-transcript.png"
                                        alt="Insider Trading Activity"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "chat" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">The AI Agent</h3>
                                <p className="text-sm text-muted-foreground">
                                    An agentic assistant that can research, analyze, and take action on your behalf.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>What Can the Agent Do?</CardTitle>
                                    <CardDescription>It's more than just Q&A—the agent can perform tasks</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <p className="text-sm text-muted-foreground">
                                        The AI agent has access to powerful tools and can autonomously fetch data, perform analysis, generate charts, create alerts, execute trades, and more. All responses reflect your selected character's investment philosophy (Peter Lynch or Warren Buffett).
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        You can ask simple questions or complex multi-step requests on both the main page and individual stock detail pages. Use <code className="bg-muted px-1 py-0.5 rounded text-xs">@lynch</code> or <code className="bg-muted px-1 py-0.5 rounded text-xs">@buffett</code> to switch perspectives mid-conversation.
                                    </p>

                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Research & Discovery</h4>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>"Find me 5 technology stocks with PEG ratios under 1 and revenue growth above 20%"</li>
                                            <li>"What are the top 3 dividend-paying stocks in the healthcare sector?"</li>
                                            <li>"Show me stocks similar to NVIDIA but cheaper"</li>
                                            <li>"Which stocks in my watchlist have recent insider buying?"</li>
                                        </ul>
                                    </div>

                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Deep Analysis</h4>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>"Compare Apple, Microsoft, and Google across valuation and profitability metrics"</li>
                                            <li>"Analyze Tesla's cash flow trends over the last 5 years"</li>
                                            <li>"What did management say about margins in the latest earnings call?"</li>
                                            <li>"Summarize the risk factors from Amazon's 10-K filing"</li>
                                            <li>"How does Shopify's ROE compare to its industry peers?"</li>
                                        </ul>
                                    </div>

                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Charts & Visualization</h4>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>"Show me AAPL's historical P/E ratio over the last 10 years"</li>
                                            <li>"Chart Costco's revenue growth vs profit margin"</li>
                                            <li>"Plot the 10-year treasury yield over the past 2 years"</li>
                                        </ul>
                                    </div>

                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Alerts & Monitoring</h4>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>"Alert me when Google's P/E drops below 20"</li>
                                            <li>"Set up a notification if Tesla's RSI goes above 70"</li>
                                            <li>"What alerts do I have configured?"</li>
                                            <li>"Delete my alert for NVDA"</li>
                                        </ul>
                                    </div>

                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Economic Context</h4>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>"What's the current GDP growth rate?"</li>
                                            <li>"Show me the yield curve spread trend"</li>
                                            <li>"How has unemployment changed this year?"</li>
                                            <li>"Is the VIX elevated right now?"</li>
                                        </ul>
                                    </div>

                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Investment Guidance</h4>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>"Would Peter Lynch like this company?"</li>
                                            <li>"What would Warren Buffett think about this valuation?"</li>
                                            <li>"Help me understand this company's competitive moat"</li>
                                            <li>"What are the biggest risks I should consider?"</li>
                                        </ul>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Where to Chat</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        The chat panel is always available on the right side of the screen (or via the chat icon on mobile). On the main page, you can ask about markets, screening strategies, or economy-wide topics. On individual stock pages, the agent has full context about that stock for detailed analysis.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        Your conversations are saved and accessible from the "Chats" section in the left sidebar. You can start new chats or continue previous ones anytime.
                                    </p>
                                    <img
                                        src="/help/chat-panel.png"
                                        alt="Chat Panel with Active Conversation"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "chat-context" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Advanced Agent Features</h3>
                                <p className="text-sm text-muted-foreground">
                                    How the agent adapts to context and takes multi-step actions.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>Context-Aware Intelligence</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">On the Main Page</h4>
                                        <p className="text-sm text-muted-foreground">
                                            The agent can discuss market conditions, sectors, screening strategies, economic indicators, and help you discover new stocks. It has access to the full database and can perform complex multi-stock analysis.
                                        </p>
                                    </div>
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">On a Stock Detail Page</h4>
                                        <p className="text-sm text-muted-foreground">
                                            The agent has full context about that specific stock and can dive deep into financials, SEC filings, earnings transcripts, insider activity, news, and competitive positioning. It can autonomously fetch and synthesize information from multiple sources.
                                        </p>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Multi-Step Reasoning</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        The agent can break down complex requests into multiple steps. For example, if you ask "Find tech stocks with insider buying and compare them," it will:
                                    </p>
                                    <ol className="text-sm text-muted-foreground space-y-1 list-decimal list-inside ml-2">
                                        <li>Screen for technology sector stocks</li>
                                        <li>Filter for recent insider buying activity</li>
                                        <li>Fetch key metrics for each stock</li>
                                        <li>Present a comparison table</li>
                                        <li>Provide analysis from your chosen investment perspective</li>
                                    </ol>
                                    <p className="text-sm text-muted-foreground mt-3">
                                        You can ask follow-up questions and the agent maintains the conversation context, allowing for iterative exploration.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Managing Conversations</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        All conversations are automatically saved and accessible from the "Chats" section in the left sidebar navigation. You can:
                                    </p>
                                    <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                        <li>Start new chats for different topics or stocks</li>
                                        <li>Resume previous conversations with full context</li>
                                        <li>Switch between conversations without losing progress</li>
                                        <li>Delete old conversations you no longer need</li>
                                    </ul>
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "investment-styles" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Investment Styles</h3>
                                <p className="text-sm text-muted-foreground">
                                    Switch between different legendary investor perspectives to analyze stocks.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>Active Characters</CardTitle>
                                    <CardDescription>Both Peter Lynch and Warren Buffett are now available</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div>
                                        <h4 className="font-medium text-sm mb-1 flex items-center gap-2">
                                            <span className="bg-blue-500 text-white px-2 py-0.5 rounded text-xs font-bold">PL</span>
                                            Peter Lynch (Default)
                                        </h4>
                                        <p className="text-sm text-muted-foreground">
                                            Growth at a reasonable price (GARP). Looks for companies with strong earnings growth at reasonable valuations, low institutional ownership, and manageable debt. His signature metric is the PEG ratio.
                                        </p>
                                    </div>
                                    <div>
                                        <h4 className="font-medium text-sm mb-1 flex items-center gap-2">
                                            <span className="bg-green-600 text-white px-2 py-0.5 rounded text-xs font-bold">WB</span>
                                            Warren Buffett
                                        </h4>
                                        <p className="text-sm text-muted-foreground">
                                            Quality-focused. Seeks excellent businesses with durable competitive advantages (wide moats), high returns on equity, strong margins, and the ability to reinvest earnings profitably. Emphasizes ROE and owner earnings.
                                        </p>
                                    </div>
                                    <div className="opacity-60">
                                        <h4 className="font-medium text-sm mb-1">Benjamin Graham <span className="text-xs italic">(Coming Soon)</span></h4>
                                        <p className="text-sm text-muted-foreground">
                                            Deep value investing pioneer. Emphasizes margin of safety, buying assets below intrinsic value, and focusing on financial strength over growth.
                                        </p>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>How Characters Affect Analysis</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Each character uses different scoring weights and emphasizes different metrics:
                                    </p>
                                    <ul className="text-sm text-muted-foreground space-y-2 list-disc list-inside ml-2">
                                        <li><strong>Lynch</strong> - Heavily weights PEG ratio (50%), earnings consistency (25%), and debt-to-equity (15%)</li>
                                        <li><strong>Buffett</strong> - Heavily weights ROE (40%), earnings consistency (30%), and debt-to-earnings (20%)</li>
                                    </ul>
                                    <p className="text-sm text-muted-foreground mt-3">
                                        The same stock can receive different scores depending on which character you select. This helps you see opportunities through different lenses.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Switching Between Characters</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground mb-2">
                                        There are two ways to switch characters:
                                    </p>
                                    <div>
                                        <h4 className="font-medium text-sm mb-1">1. Character Toggle Buttons</h4>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            Use the PL/WB toggle buttons in the chat panel to switch your default character. This affects all future analysis, scoring, and chat responses.
                                        </p>
                                    </div>
                                    <div>
                                        <h4 className="font-medium text-sm mb-1">2. @ Mentions in Chat</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Type <code className="bg-muted px-1 py-0.5 rounded text-xs">@lynch</code> or <code className="bg-muted px-1 py-0.5 rounded text-xs">@buffett</code> in any message to temporarily switch perspectives for that conversation.
                                        </p>
                                    </div>
                                    <img
                                        src="/help/investment-character.png"
                                        alt="Character Selection in Chat"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full mt-3"
                                    />
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "multiple-characters" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Multiple Investment Characters</h3>
                                <p className="text-sm text-muted-foreground">
                                    Switch between legendary investor perspectives to analyze stocks through different philosophies.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>Peter Lynch vs Warren Buffett</CardTitle>
                                    <CardDescription>Two distinct investment philosophies</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div>
                                        <h4 className="font-medium text-sm mb-2 flex items-center gap-2">
                                            <span className="bg-blue-500 text-white px-2 py-0.5 rounded text-xs font-bold">PL</span>
                                            Peter Lynch - Growth at Reasonable Price (GARP)
                                        </h4>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            Peter Lynch's approach focuses on finding growing companies at reasonable valuations. He looks for hidden gems before institutions discover them.
                                        </p>
                                        <p className="text-sm text-muted-foreground mb-2"><strong>Key focus areas:</strong></p>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li><strong>PEG Ratio</strong> - His signature metric. Below 1.0 means growth at a bargain</li>
                                            <li><strong>Earnings Consistency</strong> - Reliable, predictable growth patterns</li>
                                            <li><strong>Debt-to-Equity</strong> - Prefers companies with manageable debt loads</li>
                                            <li><strong>Institutional Ownership</strong> - Lower ownership can indicate undiscovered opportunities</li>
                                        </ul>
                                    </div>
                                    <div className="border-t pt-3">
                                        <h4 className="font-medium text-sm mb-2 flex items-center gap-2">
                                            <span className="bg-green-600 text-white px-2 py-0.5 rounded text-xs font-bold">WB</span>
                                            Warren Buffett - Quality & Durable Advantages
                                        </h4>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            Warren Buffett seeks exceptional businesses with durable competitive advantages (moats) that can compound value over decades.
                                        </p>
                                        <p className="text-sm text-muted-foreground mb-2"><strong>Key focus areas:</strong></p>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li><strong>Return on Equity (ROE)</strong> - His primary quality indicator. Above 20% is excellent</li>
                                            <li><strong>Earnings Consistency</strong> - Steady, predictable earnings power</li>
                                            <li><strong>Debt-to-Earnings</strong> - Conservative debt levels relative to earnings</li>
                                            <li><strong>Gross Margin</strong> - Wide margins indicate pricing power and moats</li>
                                        </ul>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Switching Characters</CardTitle>
                                    <CardDescription>Change perspective anytime during your analysis</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Character Selection Buttons</h4>
                                        <p className="text-sm text-muted-foreground mb-3">
                                            Use the character toggle buttons in the chat panel to switch between Peter Lynch (PL) and Warren Buffett (WB). Your selection affects all analysis going forward.
                                        </p>
                                        <img
                                            src="/help/character-selection.png"
                                            alt="Character Selection Toggle"
                                            className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                        />
                                    </div>
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">@ Mentions for Quick Switching</h4>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            Type <code className="bg-muted px-1 py-0.5 rounded text-xs">@lynch</code> or <code className="bg-muted px-1 py-0.5 rounded text-xs">@buffett</code> in your chat messages to quickly switch perspectives mid-conversation.
                                        </p>
                                        <p className="text-sm text-muted-foreground mb-3">
                                            Examples:
                                        </p>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>"<code className="bg-muted px-1 py-0.5 rounded text-xs">@buffett</code> What's the ROE for this company?"</li>
                                            <li>"How does this look from a <code className="bg-muted px-1 py-0.5 rounded text-xs">@lynch</code> perspective?"</li>
                                            <li>"<code className="bg-muted px-1 py-0.5 rounded text-xs">@buffett</code> analyze the competitive moat"</li>
                                        </ul>
                                        <img
                                            src="/help/at-mention-chat.png"
                                            alt="Using @ Mentions in Chat"
                                            className="rounded-lg border-2 border-muted-foreground/30 w-full mt-3"
                                        />
                                    </div>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>What Changes with Character Selection</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Your selected character affects multiple aspects of the analysis:
                                    </p>
                                    <ul className="text-sm text-muted-foreground space-y-2 list-disc list-inside ml-2">
                                        <li><strong>Stock Scores</strong> - Scoring weights and thresholds change to reflect each character's priorities</li>
                                        <li><strong>Thesis & Analysis</strong> - AI-generated thesis reflects the character's investment philosophy and concerns</li>
                                        <li><strong>Chart Analysis</strong> - Financial chart commentary emphasizes different metrics per character</li>
                                        <li><strong>Chat Responses</strong> - The AI agent answers questions from that character's perspective</li>
                                        <li><strong>Metric Visibility</strong> - Stock detail pages highlight metrics relevant to the selected character</li>
                                    </ul>
                                    <div className="mt-4 pt-3 border-t">
                                        <h4 className="font-medium text-sm mb-2">Visual Indicators</h4>
                                        <p className="text-sm text-muted-foreground mb-3">
                                            Chat messages show character avatars (PL for Lynch, WB for Buffett) so you always know which perspective you're viewing.
                                        </p>
                                        <img
                                            src="/help/character-avatar.png"
                                            alt="Character Avatar in Messages"
                                            className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                        />
                                    </div>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Default Character Preference</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Your character selection is saved as your default preference. When you return to the app, it will remember your last selected character.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        You can change this anytime using the character toggle buttons or @ mentions.
                                    </p>
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "portfolios" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Portfolios</h3>
                                <p className="text-sm text-muted-foreground">
                                    Create and manage paper trading portfolios to test your investment strategies.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>What are Portfolios?</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Portfolios are paper trading accounts that let you test investment strategies without risking real money. Track your trades, monitor performance, and learn from your decisions in a risk-free environment.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        Each portfolio starts with virtual cash (default $100,000) and maintains a complete history of all trades and performance over time.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Creating a Portfolio</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground mb-2">
                                        To create a new portfolio:
                                    </p>
                                    <ol className="text-sm text-muted-foreground space-y-1 list-decimal list-inside ml-2">
                                        <li>Navigate to the Portfolios page from the left sidebar</li>
                                        <li>Click "Create Portfolio"</li>
                                        <li>Enter a descriptive name</li>
                                        <li>Optionally set initial cash (defaults to $100,000)</li>
                                        <li>Click "Create" to start trading</li>
                                    </ol>
                                    <img
                                        src="/help/portfolio-create-dialog.png"
                                        alt="Create Portfolio Dialog"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full mt-3"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Portfolio Overview</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        The portfolio list shows all your portfolios with key metrics at a glance:
                                    </p>
                                    <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                        <li><strong>Total Value</strong> - Current cash + holdings value</li>
                                        <li><strong>Gain/Loss %</strong> - Performance relative to initial cash</li>
                                        <li><strong>Holdings Count</strong> - Number of different positions</li>
                                    </ul>
                                    <img
                                        src="/help/portfolio-list.png"
                                        alt="Portfolio List View"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full mt-3"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Portfolio Detail View</CardTitle>
                                    <CardDescription>Four tabs for complete portfolio management</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Holdings Tab</h4>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            View all your current positions with detailed information:
                                        </p>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>Symbol and company name</li>
                                            <li>Number of shares held</li>
                                            <li>Average purchase price</li>
                                            <li>Current market price</li>
                                            <li>Total cost basis</li>
                                            <li>Current value</li>
                                            <li>Gain/loss amount and percentage</li>
                                        </ul>
                                        <img
                                            src="/help/portfolio-detail-holdings.png"
                                            alt="Holdings Tab"
                                            className="rounded-lg border-2 border-muted-foreground/30 w-full mt-3"
                                        />
                                    </div>
                                    <div className="border-t pt-3">
                                        <h4 className="font-medium text-sm mb-2">Trade Tab</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Execute buy and sell orders directly from this tab. See the Manual Trading section for details.
                                        </p>
                                    </div>
                                    <div className="border-t pt-3">
                                        <h4 className="font-medium text-sm mb-2">Transactions Tab</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Complete history of all trades including symbol, type (BUY/SELL), quantity, price, total value, timestamp, and optional notes.
                                        </p>
                                    </div>
                                    <div className="border-t pt-3">
                                        <h4 className="font-medium text-sm mb-2">Performance Tab</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Track your portfolio value over time with a mini-chart showing historical snapshots. See how your strategy performs across different market conditions.
                                        </p>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Managing Portfolios</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        You can create multiple portfolios to test different strategies simultaneously. Each portfolio operates independently with its own cash balance, holdings, and transaction history.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        To delete a portfolio, use the delete option from the portfolio detail page. This action is permanent and removes all associated transactions and history.
                                    </p>
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "manual-trading" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Manual Trading</h3>
                                <p className="text-sm text-muted-foreground">
                                    Execute buy and sell orders through the portfolio interface.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>How to Execute Trades</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground mb-2">
                                        From any portfolio's Trade tab:
                                    </p>
                                    <ol className="text-sm text-muted-foreground space-y-1 list-decimal list-inside ml-2">
                                        <li>Enter the stock symbol (e.g., AAPL, MSFT)</li>
                                        <li>Enter the quantity (number of shares)</li>
                                        <li>Select BUY or SELL</li>
                                        <li>Optionally add a note for your records</li>
                                        <li>Click "Execute Trade"</li>
                                    </ol>
                                    <img
                                        src="/help/portfolio-trade-tab.png"
                                        alt="Trade Tab Form"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full mt-3"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Market Hours & Price Execution</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Extended Trading Hours</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Trades can be executed during extended market hours: <strong>4 AM - 8 PM ET, weekdays only</strong>. This includes pre-market, regular market, and after-hours sessions.
                                        </p>
                                        <p className="text-sm text-muted-foreground mt-2">
                                            Attempting to trade outside these hours will result in an error message.
                                        </p>
                                    </div>
                                    <div className="border-t pt-3">
                                        <h4 className="font-medium text-sm mb-2">Live Price Execution</h4>
                                        <p className="text-sm text-muted-foreground">
                                            All trades execute at the current market price at the time of order. The system fetches live prices from market data providers with a database fallback if live data is unavailable.
                                        </p>
                                        <p className="text-sm text-muted-foreground mt-2">
                                            The execution price is shown in the transaction confirmation and recorded in your transaction history.
                                        </p>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Trade Validation</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        The system validates all trades before execution:
                                    </p>
                                    <ul className="text-sm text-muted-foreground space-y-2 list-disc list-inside ml-2">
                                        <li><strong>Buy Orders</strong> - Checks that you have sufficient cash to complete the purchase</li>
                                        <li><strong>Sell Orders</strong> - Verifies you own enough shares of the stock to sell</li>
                                        <li><strong>Market Hours</strong> - Ensures trading occurs during valid market hours</li>
                                        <li><strong>Price Availability</strong> - Confirms current price data is available</li>
                                    </ul>
                                    <p className="text-sm text-muted-foreground mt-3">
                                        If validation fails, you'll receive a clear error message explaining the issue.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Transaction History & Notes</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Every trade is recorded in the Transactions tab with complete details including timestamp, symbol, type, quantity, execution price, and total value.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        Use the optional note field to document your reasoning for each trade. This helps you review your decision-making process later and learn from both successful and unsuccessful trades.
                                    </p>
                                    <img
                                        src="/help/portfolio-transactions.png"
                                        alt="Transaction History"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full mt-3"
                                    />
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "automated-trading" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Automated Trading</h3>
                                <p className="text-sm text-muted-foreground">
                                    Execute trades through the AI agent or automated alert triggers.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>Two Paths to Automated Trading</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">1. Direct Agent Trades</h4>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            Command the AI agent to execute trades immediately via chat. The agent can buy or sell stocks in your portfolios during market hours.
                                        </p>
                                        <p className="text-sm text-muted-foreground mb-2"><strong>Example commands:</strong></p>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>"Buy 10 shares of AAPL in my Tech Portfolio"</li>
                                            <li>"Sell 5 shares of MSFT from my Growth Portfolio"</li>
                                            <li>"Purchase 20 shares of NVDA in my main portfolio"</li>
                                        </ul>
                                    </div>
                                    <div className="border-t pt-3">
                                        <h4 className="font-medium text-sm mb-2">2. Alert-Triggered Trades</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Set up conditional trades that execute automatically when specific market conditions are met. See the Alerts & Automation section for details.
                                        </p>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Agent Portfolio Management</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground mb-2">
                                        The AI agent can help manage your portfolios through natural language:
                                    </p>
                                    <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                        <li><strong>Create portfolios:</strong> "Create a new portfolio called Growth Strategy with $50,000"</li>
                                        <li><strong>Check status:</strong> "What's the current value of my Tech Portfolio?"</li>
                                        <li><strong>View holdings:</strong> "Show me what stocks are in my Conservative Portfolio"</li>
                                        <li><strong>Review performance:</strong> "How is my Dividend Portfolio performing?"</li>
                                    </ul>
                                    <img
                                        src="/help/agent-trade-chat.png"
                                        alt="Agent Trade Execution via Chat"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full mt-3"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Trade Execution & Confirmation</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        When the agent executes a trade:
                                    </p>
                                    <ol className="text-sm text-muted-foreground space-y-1 list-decimal list-inside ml-2">
                                        <li>It checks that the portfolio exists and you own it</li>
                                        <li>Verifies market hours (4 AM - 8 PM ET, weekdays)</li>
                                        <li>Fetches the current market price</li>
                                        <li>Validates sufficient cash (buy) or shares (sell)</li>
                                        <li>Records the transaction with execution details</li>
                                        <li>Confirms the trade in chat with price and total value</li>
                                    </ol>
                                    <p className="text-sm text-muted-foreground mt-3">
                                        All agent trades appear in your transaction history with automatically generated notes identifying them as agent-initiated.
                                    </p>
                                    <img
                                        src="/help/agent-trade-confirmation.png"
                                        alt="Portfolio with Agent Trade Notes"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full mt-3"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Important Notes</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <ul className="text-sm text-muted-foreground space-y-2 list-disc list-inside ml-2">
                                        <li>Agent trades execute immediately at market prices—there's no "undo" button</li>
                                        <li>All validation rules apply just like manual trades (market hours, sufficient funds, etc.)</li>
                                        <li>Be specific about portfolio names to avoid confusion if you have multiple portfolios</li>
                                        <li>Trade notes are automatically generated but you can view and understand them in transaction history</li>
                                    </ul>
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "setting-alerts" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Setting Alerts via Chat</h3>
                                <p className="text-sm text-muted-foreground">
                                    Create custom alerts using natural language to monitor stocks and market conditions.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>How Alerts Work</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Alerts let you monitor specific conditions and get notified when they occur. Simply describe what you want to watch in natural language, and the AI agent will create an alert that continuously monitors the condition.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        A background worker periodically checks your alert conditions. When a condition is met, the alert triggers and you're notified.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Creating Alerts</CardTitle>
                                    <CardDescription>Use natural language to describe conditions</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <p className="text-sm text-muted-foreground mb-2">
                                        To create an alert, simply tell the AI agent what you want to monitor:
                                    </p>
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Price-Based Alerts</h4>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>"Alert me when AAPL price drops below $145"</li>
                                            <li>"Notify me if Google's stock goes above $180"</li>
                                            <li>"Tell me when Tesla reaches $250"</li>
                                        </ul>
                                    </div>
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Metric-Based Alerts</h4>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>"Alert me when MSFT's P/E ratio falls below 20"</li>
                                            <li>"Notify me if institutional ownership goes above 80%"</li>
                                            <li>"Tell me when the PEG ratio drops under 1.0"</li>
                                        </ul>
                                    </div>
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Technical Indicator Alerts</h4>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>"Alert me if NVDA's RSI goes above 70"</li>
                                            <li>"Notify me when the 50-day MA crosses the 200-day MA"</li>
                                        </ul>
                                    </div>
                                    <img
                                        src="/help/alert-creation-chat.png"
                                        alt="Creating Alert via Chat"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full mt-3"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>How the AI Interprets Conditions</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        The agent parses your natural language description and stores it as a custom condition. The system uses LLM evaluation to understand complex conditions beyond simple thresholds.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        This means you can describe sophisticated conditions like "when earnings growth accelerates" or "if the company announces a dividend increase" and the system will interpret and monitor them intelligently.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Managing Your Alerts</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground mb-2">
                                        You can manage alerts through chat commands:
                                    </p>
                                    <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                        <li>"What alerts do I have configured?"</li>
                                        <li>"Show me my active alerts"</li>
                                        <li>"Delete my alert for NVDA"</li>
                                        <li>"Remove the P/E alert for Apple"</li>
                                    </ul>
                                    <p className="text-sm text-muted-foreground mt-3">
                                        When an alert triggers, you'll see a notification and the alert's status changes to 'triggered' in your alert list.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Alert Monitoring</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        A background worker continuously checks your alert conditions at regular intervals. This ensures you don't miss important market movements even when you're not actively using the app.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        Alerts remain active until they trigger or you manually delete them. Once triggered, an alert won't trigger again unless you recreate it.
                                    </p>
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "automated-trade-actions" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Automated Trade Actions</h3>
                                <p className="text-sm text-muted-foreground">
                                    Combine alerts with trading actions to execute conditional trades automatically.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>Alerts + Trading Actions</CardTitle>
                                    <CardDescription>Execute trades when conditions are met</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        You can create alerts that automatically execute trades when triggered. This lets you implement conditional trading strategies like "buy the dip" or "take profits at target price" without manual intervention.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        The alert continuously monitors the condition, and when it's met, the system automatically executes your specified trade in the designated portfolio.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Creating Alert-Triggered Trades</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <p className="text-sm text-muted-foreground mb-2">
                                        To create an alert with a trading action, specify both the condition and the action in your chat message:
                                    </p>
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Buy Actions</h4>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>"Buy 5 shares of MSFT in my Tech Portfolio when price drops to $380"</li>
                                            <li>"Purchase 10 shares of AAPL in my Growth Portfolio if it falls below $140"</li>
                                            <li>"Add 20 shares of NVDA to my portfolio when RSI drops under 30"</li>
                                        </ul>
                                    </div>
                                    <div>
                                        <h4 className="font-medium text-sm mb-2">Sell Actions</h4>
                                        <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                            <li>"Sell 10 shares of TSLA when price reaches $300"</li>
                                            <li>"Sell all my Google shares if P/E ratio exceeds 35"</li>
                                            <li>"Take profits on AMD when it hits $180"</li>
                                        </ul>
                                    </div>
                                    <img
                                        src="/help/alert-with-trade-action.png"
                                        alt="Alert with Trade Action"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full mt-3"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>How It Works</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <ol className="text-sm text-muted-foreground space-y-2 list-decimal list-inside ml-2">
                                        <li>The AI agent parses your message to extract the condition, action type (buy/sell), quantity, and portfolio</li>
                                        <li>The system creates an alert with the trading action stored as metadata</li>
                                        <li>A background worker continuously monitors the alert condition</li>
                                        <li>When the condition triggers, the worker validates the trade (market hours, sufficient cash/shares)</li>
                                        <li>If validation passes, the trade executes automatically at current market price</li>
                                        <li>The transaction is recorded with a special note: "[Action] (Triggered by Alert ID)"</li>
                                    </ol>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Trade Validation & Safety</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground mb-2">
                                        Even automated trades go through the same validation as manual trades:
                                    </p>
                                    <ul className="text-sm text-muted-foreground space-y-2 list-disc list-inside ml-2">
                                        <li><strong>Market Hours</strong> - Trades only execute during extended market hours (4 AM - 8 PM ET, weekdays)</li>
                                        <li><strong>Sufficient Funds</strong> - Buy orders require available cash in the portfolio</li>
                                        <li><strong>Sufficient Shares</strong> - Sell orders require owning enough shares</li>
                                        <li><strong>Price Availability</strong> - Current market price must be available</li>
                                    </ul>
                                    <p className="text-sm text-muted-foreground mt-3">
                                        If validation fails (e.g., insufficient funds or outside market hours), the trade won't execute and you'll receive an error message. The alert remains active and will retry on the next check if conditions still match.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Transaction History</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Alert-triggered trades appear in your portfolio's transaction history with a special note format that identifies them as automated:
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        <code className="bg-muted px-2 py-1 rounded text-xs">"[Your action note] (Triggered by Alert 123)"</code>
                                    </p>
                                    <p className="text-sm text-muted-foreground mt-3">
                                        This lets you track which trades were automated versus manual, and review the performance of your conditional strategies.
                                    </p>
                                    <img
                                        src="/help/alert-triggered-transaction.png"
                                        alt="Transaction from Triggered Alert"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full mt-3"
                                    />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Important Considerations</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <ul className="text-sm text-muted-foreground space-y-2 list-disc list-inside ml-2">
                                        <li>Alert-triggered trades execute automatically—make sure you have sufficient funds/shares before setting them up</li>
                                        <li>Alerts trigger once and then become inactive. If you want recurring conditional trades, you'll need to recreate the alert after it triggers</li>
                                        <li>Be specific about portfolio names to avoid trades executing in the wrong portfolio</li>
                                        <li>Monitor your portfolios regularly to ensure automated trades align with your strategy</li>
                                        <li>You can delete an alert before it triggers to cancel the pending automated trade</li>
                                    </ul>
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "tuning" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Algorithm Tuning</h3>
                                <p className="text-sm text-muted-foreground">
                                    Customize the scoring algorithm's weights and thresholds to match your investment philosophy.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>What is Algorithm Tuning?</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        The algorithm tuning feature allows you to adjust the weights and thresholds of the algorithms that underpin the stock screening and scoring mechanism.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        The system comes pre-configured with settings optimized for each investment style (Lynch, Buffett, etc.), but you have full control to customize them.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Manual Tuning</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        You can manually adjust the relative importance (weights) of different criteria like growth, valuation, profitability, and financial health. You can also modify thresholds—for example, changing what P/E ratio qualifies as "good" or "poor."
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        This gives you granular control over how stocks are evaluated and ranked.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Automated Optimization</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Alternatively, you can use an automated data science-based search to find and backtest configurations against 5-10 years of historical stock market performance.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        The system will test various combinations of weights and thresholds, evaluating how they would have performed historically, and suggest optimized configurations tailored to your goals.
                                    </p>
                                    <p className="text-sm text-muted-foreground italic">
                                        <strong>Note:</strong> This is an advanced feature. Most users should start with the preset investment styles before diving into custom tuning.
                                    </p>
                                    <img
                                        src="/help/auto-optimization.png"
                                        alt="Algorithm Tuning Interface"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "advanced-filters" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Custom Filters</h3>
                                <p className="text-sm text-muted-foreground">
                                    Create precise screening criteria with advanced filters.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>Advanced Filter Options</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div>
                                        <h4 className="font-medium text-sm mb-1">Geographic Filters</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Filter by region (USA, Canada, Europe, Asia) or specific countries.
                                        </p>
                                    </div>
                                    <div>
                                        <h4 className="font-medium text-sm mb-1">Market Cap Range</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Focus on large-caps, mid-caps, small-caps, or custom ranges.
                                        </p>
                                    </div>
                                    <div>
                                        <h4 className="font-medium text-sm mb-1">Growth Thresholds</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Set minimum revenue or earnings growth rates to find high-growth companies.
                                        </p>
                                    </div>
                                    <div>
                                        <h4 className="font-medium text-sm mb-1">Financial Health</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Filter by debt-to-equity ratio or institutional ownership levels.
                                        </p>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Accessing Advanced Filters</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Click the filter icon in the top-right corner of the main page to open the advanced filter panel.
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        Your filter preferences are saved automatically.
                                    </p>
                                    <img
                                        src="/help/filter-by-quality.png"
                                        alt="Advanced Filter Panel"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
                                </CardContent>
                            </Card>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
