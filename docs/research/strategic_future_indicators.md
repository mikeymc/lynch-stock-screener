
# Strategic Future Indicators: A Value Investing Approach

## Executive Summary
You asked for a strategic altitude check. Based on the philosophies of Peter Lynch, Warren Buffett, and Benjamin Graham, we should not just "ingest everything." Instead, we should focus on **high-signal, low-noise indicators** that serve as proxies for future business health and management confidence.

## Proposed Indicators (Ranked by Strategic Value)

### 1. The "Skin in the Game" Signal (Lynch & Buffett)
*   **Metric:** **Net Insider Buying (Last 6 Months)**
*   **Why:** Lynch famously said, "Insiders might sell their shares for any number of reasons, but they buy them for only one: they think the price will rise."
*   **Data Strategy:** Use `yfinance` (`insider_transactions`). We confirmed it provides names and positions (e.g., "ADAMS KATHERINE L", "General Counsel"), allowing us to highlight C-suite activity.

### 2. The "Stuff in the Warehouse" Warning (Lynch)
*   **Metric:** **Inventory Growth vs. Sales Growth Spread**
*   **Why:** A classic Lynch red flag. If Inventory is growing faster than Sales, it predicts write-downs.
*   **Sector Nuance:** ONLY calculate for sectors: 'Consumer Cyclical', 'Technology - Hardware', 'Industrials', 'Basic Materials', 'Consumer Defensive'. Ignored for Software/Services.

### 3. The "Moat Durability" Sparkline (Buffett)
*   **Metric:** **Gross Margin Stability (5-Year)**
*   **Why:** stable margins = pricing power (moat). Volatile margins = commodity.
*   **UI Visualization:** Small inline chart (`_ ▂ ▃ ▄ ▅ _`) to visualize stability without clutter.

### 4. Valuation + Growth Reality (GARP)
*   **Concept:** **GARP (Growth At A Reasonable Price)**
*   **Metric:** **Forward PEG Ratio**
*   **Why:** A strategy combining "Value" (low P/E) and "Growth" (high earnings growth). PEG < 1.0 is the classic signal.

### 5. Sentiment Context: "The Word on the Street"
*   **Concept:** Contrarian signals or "scuttlebutt" checks.
*   **Sources Consulted:**
    *   **Reddit (Recommended Phase 2):** Best free source. `PRAW` library allows easy access to r/ValueInvesting discussions.
    *   **StockTwits:** Free API is very limited/deprecated. Reliable sentiment requires paid tools (~$10k/mo).
    *   **Google Trends:** `pytrends` exists but is "unofficial" and prone to rate-limiting/blocking. Good for "consumer brand" checks (e.g. "Crocs") but hard to scale for all stocks reliably.
    *   **Glassdoor:** No public API anymore. Scraping is fragile.
    *   **Seeking Alpha:** Great content but strict anti-scraping/paid API.
*   **Strategy:** Start with **Reddit (Phase 2)**. It offers the most "honest" retail investor sentiment that complements our fundamental data.

## Recommendation
Proceed with **Insider Buying** (Phase 1), **Inventory/Sales Spread** (Phase 1), and **Forward PEG / GARP** (Phase 1).
**Reddit Sentiment** is the best "Word on the Street" candidate. Recommend tabling for Phase 2 to focus on getting the core financials right first.
