// ABOUTME: Help and onboarding page for new users
// ABOUTME: Provides guides, explanations, and screenshots for app features

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export default function Help() {
    const [activeTab, setActiveTab] = useState("quick-start")

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
            id: "overview",
            title: "Overview Tab",
            section: "Stock Analysis"
        },
        {
            id: "analysis",
            title: "Brief & Analysis",
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
                                    <p className="text-sm">
                                        papertree.ai is a stock screening and analysis tool that helps you discover investment opportunities using time-tested strategies from legendary investors like Peter Lynch and Warren Buffett.
                                    </p>
                                    <p className="text-sm">
                                        The app automatically screens thousands of stocks, scores them based on fundamental analysis, and provides detailed reports with AI-powered insights. It also enables chatting with an AI agent who is steeped in Lynch and Buffett's approaches who can provide deep and broad analysis and take actions on behalf of the user. It defaults to the Lynch configuration.
                                    </p>
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
                                    <CardTitle>Advanced Filters</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Click the filter icon in the top-right to access advanced filtering options including:
                                    </p>
                                    <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside ml-2">
                                        <li>Geographic region (USA, Canada, Europe, Asia, etc.)</li>
                                        <li>Market cap range</li>
                                        <li>Institutional ownership</li>
                                        <li>Revenue and earnings growth thresholds</li>
                                        <li>Debt-to-equity limits</li>
                                    </ul>
                                    <img
                                        src="/help/filter-by-quality.png"
                                        alt="Advanced Filter Panel"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
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
                                <h3 className="text-lg font-medium">Brief & Analysis</h3>
                                <p className="text-sm text-muted-foreground">
                                    Character-specific investment narrative from your chosen investor's perspective.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>Company Brief</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        The Brief tab provides a character-specific narrative as if you're hearing directly from Lynch or Buffett about the company. It covers what the company does, its competitive position, key strengths and concerns, and investment considerations—all through the lens of your selected investment philosophy.
                                    </p>
                                    <img
                                        src="/help/brief.png"
                                        alt="Company Brief with Character Analysis"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
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
                                    <CardTitle>Financial Charts & Editorial</CardTitle>
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
                                        alt="Financial Charts and Editorial"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
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
                                        The AI agent has access to powerful tools and can autonomously fetch data, perform analysis, generate charts, create alerts, and more. You can ask simple questions or complex multi-step requests on both the main page and individual stock detail pages.
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
                                    Switch between different legendary investor perspectives.
                                </p>
                            </div>
                            <div className="border-t" />

                            <Card>
                                <CardHeader>
                                    <CardTitle>Available Characters</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div>
                                        <h4 className="font-medium text-sm mb-1">Peter Lynch (Default)</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Growth at a reasonable price (GARP). Looks for companies with strong earnings growth at reasonable valuations, low institutional ownership, and manageable debt.
                                        </p>
                                    </div>
                                    <div>
                                        <h4 className="font-medium text-sm mb-1">Warren Buffett</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Quality-focused. Seeks excellent businesses with durable competitive advantages (wide moats), high returns on equity, strong margins, and the ability to reinvest earnings profitably.
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
                                    <CardTitle>Switching Styles</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Change your investment style in Settings → Investment Style. This affects how stocks are scored and how the AI discusses them.
                                    </p>
                                    <img
                                        src="/help/investment-character.png"
                                        alt="Investment Style Settings"
                                        className="rounded-lg border-2 border-muted-foreground/30 w-full"
                                    />
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
