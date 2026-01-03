# Monetization Strategy: Hybrid Pre-Compute Model

## Executive Summary
This strategy shifts from a "Quota-based" model to a "Content-based" model. We leverage the fixed cost of pre-computing the "Best" stocks to offer a generous Free tier, while reserving **Interactivity**, **Immediacy**, and **Breadth** for the Paid tier.

---

## 1. Operational Cost Analysis

### The "Fixed Cost" Base (Free & Paid)
We treat the top-rated stocks as "Broadcast Content" (one-to-many).
*   **Target:** Top 1,000 Stocks (Excellent/Good) + Popular Tickers (TSLA, NVDA).
*   **Model:** **Gemini 3 Pro** (Highest Quality).
*   **Frequency:** Quarterly (on 10-Q update) + Monthly Refresh (Price/News).
*   **Cost:** ~$90/month (Quarterly cycle) or ~$270/month (Monthly cycle).
*   **Flash Optimization:** We can use Gemini 2.5 Flash for the "Monthly News Refresh" to lower this significantly.

### The "Marginal Cost" (Paid Only)
We treat the long-tail and on-demand actions as "Unicast Content" (one-to-one).
*   **On-Demand Regeneration:** $0.27 per Pro call.
*   **Unlimited Chat:** ~$0.02 per message (Flash) or ~$0.20 (Pro).
*   **Long-Tail Stocks:** The other 4,000 stocks are only generated if requested.

---

## 2. Updated Tier Structure

### 🟢 Free Tier: "Broadcast Only"
*   **Screening:** Unlimited.
*   **Analysis:** Access to the **Top 1,000 Pre-computed Briefs**.
    *   *Limitation:* These are static. User sees "Generated: 14 days ago".
    *   *Regeneration:* **Disabled**.
*   **Chat:** Limited.
    *   *Allow:* "Ask a question about this brief" (using brief context, not full SEC).
    *   *Limit:* 5 messages/day (Flash model).
*   **Missing Out:** Can't analyze a "Fair" or "Poor" stock.

### 🔵 Pro Tier ($15/mo): "Interactive & Real-Time"
*   **Analysis:**
    *   **Unlimited Access** to all 5,000+ stocks.
    *   **On-Demand:** "Regenerate Now" button (Get today's news/price impact).
*   **Chat:** Unlimited (Flash) or High-Cap (Pro).
*   **Signals:** Real-time 8-K summaries, Material Events.
*   **Customization:** Strategy switcher (Buffett/Burry), Alerts.

---

## 3. "Pressure to Convert" Analysis
**Fear:** "If Free users get Pro-quality briefs for top stocks, why pay?"

**The Pressure Points:**
1.  **"What about NOW?":** A pre-computed brief from 2 weeks ago doesn't know about yesterday's scandal. Paid users hit "Regenerate" to see the impact.
2.  **"What about MY stock?":** Users rarely own *only* the Top 1000. They want to check their specific holdings, even if they score "Fair".
3.  **"Drill Down":** The static brief is a monologue. Chat is a dialogue. Limiting Free chat drives conversion for curious investors.

---

## 4. Cost Feasibility (User Questions)

> **Q:** "At 50/mo (paid), what's our expected operational cost?"
*   50 Pro Briefs = **$13.50** (leaving $1.50 margin).
*   **Risk:** This is too tight.
*   **Mitigation:** We assume most paid requests will be cached or satisfied by Flash. "Regenerate" is the expensive action. We might cap "Regenerate with Pro" to 10/month, and "Regenerate with Flash" to unlimited.

> **Q:** "Can we run 2.5 Flash for all 5000 stocks?"
*   **Cost:** 5,000 * $0.02 = **$100**.
*   **Verdict:** **YES.** We can pre-compute *Basic* briefs for *all* stocks weekly for ~$400/mo.
*   **Strategy:** Free users see "Flash" briefs. Paid users can "Upgrade this Brief to Pro" ($0.27 cost).

---

## 5. Final Recommendation
1.  **Base Layer:** Run **Gemini 2.5 Flash** on **ALL 5,000 stocks** weekly. Cost: ~$400/mo.
2.  **Premium Layer:** Run **Gemini 3 Pro** on **Top 500** stocks. Cost: ~$135/mo.
3.  **Free Tier:** Sees Flash briefs (and the Pro ones where available).
4.  **Paid Tier:** Can click "Deep Dive" on *any* stock to trigger a $0.27 Pro generation.

This solves all problems:
*   Free tier is "complete" (all stocks covered).
*   Paid tier has clear value ("Deep Dive" intelligence).
*   Costs are capped and predictable.
