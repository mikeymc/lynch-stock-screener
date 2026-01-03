# Monetization Strategy & Cost Analysis

## Executive Summary
This document outlines the "Freemium" model for the Lynch Stock Screener. The goal is to **maximize Daily Active Users (DAU)** with a generous free tier while converting power users to a **$15/month Pro plan**.

---

## 1. Cost Analysis for "Generous" Free Tier

The primary cost driver is AI generation. We must balance user value with operational overhead.

**Unit Costs:**
*   **Premium Model (Gemini 3 Pro):**  `~$0.27` per brief (Deep reasoning, slower)
*   **Standard Model (Gemini 2.5 Flash):** `~$0.02` per brief (Good quality, fast)

### Cost Scenario: 3 Briefs Per Week (Free User)

| Metric                      | Premium Model ($0.27) | Standard Model ($0.02) |
| :-------------------------- | :-------------------- | :--------------------- |
| Monthly Volume (13 briefs)  | ~13                   | ~13                    |
| **Cost Per Free User**      | **$3.51 / mo**        | **$0.26 / mo**         |
| Cost for 1,000 Free Users   | $3,510 / mo           | $260 / mo              |

> [!WARNING]
> Using the Premium Model for free users ($3.51/mo) is unsustainable.
> **Recommendation:** We must use **Gemini 2.5 Flash** for the Free Tier's on-demand briefs.

---

## 2. Proposed Tier Structure

### 🟢 Free Tier: "The Screen"
**Target:** Retail investors, casual browsers.
**Goal:** Hook them with data, convert them with detailed analysis.

| Feature Type | Included Features | Limits |
| :--- | :--- | :--- |
| **Screening** | **Unlimited** Quantitative Screening (Lynch Score) | None |
| **Data** | Live Price History, **Advanced Charts** (Predictions, Trends), Basic Fundamentals | None |
| **AI Analysis** | Basic AI Briefs | **3 per Week** (Flash Model) |
| **Strategy** | Default "Peter Lynch" Strategy | Fixed |

### 🔵 Pro Tier: "The Investor" ($15/mo)
**Target:** Active investors, fundamental analysts.
**Goal:** Provide professional-grade tools and deep insights.

| Feature Type | Included Features | Limits |
| :--- | :--- | :--- |
| **AI Analysis** | **Deep Dive Briefs** (Gemini 3 Pro) | **Unlimited*** (Fair use cap ~50/mo) |
| **Deep Data** | **Transcript Summaries** ("Cliff Notes"), **Material Event Analysis** (AI 8-K) | Unlimited |
| **Customization**| **Strategy Switcher** (Buffett, Burry, Custom), Weight Adjustments | Full Access |
| **Tools** | **Portfolio Tracking**, **Smart Alerts** (e.g. "Score > 80") | Unlimited |

### 🟣 Future "Quant" Tier (Pricing TBD)
**Target:** Specialized traders and quants.
*   **Algorithmic Trading:** Auto-execute based on strategy.
*   **AI Portfolios:** "Build me a high-growth SaaS portfolio".
*   **API Access:** Direct access to screener data.

---

## 3. Implementation Roadmap

### Phase 1: Infrastructure (Immediate)
1.  **User Identity:** Enhance `User` table with `tier` and `subscription_status`.
2.  **Usage Tracking:** New `usage_logs` table to track AI calls per user/day.
3.  **Model Routing:** logic to swap between `flash` (Free) and `pro` (Paid) models.

### Phase 2: User-Facing Features
1.  **Quota Display:** Show "1/3 Free Briefs Used" in the UI.
2.  **Strategy Switcher:** Build the "Buffett/Burry/Custom" selector for Pro users.
3.  **Gatekeeping:** Lock Pro features with an upgrade prompt.

### Phase 3: Payment Integration
1.  **Stripe:** Integrate Checkout for handling $15/mo subscriptions.
