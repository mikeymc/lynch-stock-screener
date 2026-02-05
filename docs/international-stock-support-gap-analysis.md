# International Stock Support Gap Analysis

## Overview

This document analyzes the gaps and requirements for supporting international stocks that file 20-F and 6-K forms with the SEC. These are **Foreign Private Issuers (FPIs)** - companies headquartered outside the US but listed on US exchanges (NYSE, NASDAQ) via ADRs or direct listings.

> [!NOTE]
> **20-F vs 6-K Forms**: 20-F is the annual report equivalent (replaces 10-K) and 6-K is the interim report (replaces 10-Q/8-K). FPIs are not required to file quarterly reports, so 6-K filings contain material events and semi-annual reports.

### Scope Clarification

| Category | Examples | SEC Filing Requirements |
|----------|----------|-------------------------|
| **Foreign Private Issuers (FPIs)** | ASML, TSM, NVO, SAP, SHOP | File 20-F (annual) + 6-K (interim) with SEC |
| **Canadian Issuers** | TD, RY, CNQ, ENB | File 40-F (MJDS) + 6-K with SEC |
| **Pure European/Asian Stocks** | Nestle (SWX), Samsung (KRX) | **No SEC filings** - only local exchange filings |

This analysis focuses on **FPIs** (20-F/6-K filers) which are already traded on US exchanges and have SEC filings available.

---

## Current State Analysis

### 1. Stock Discovery (TradingView)

| Aspect | Status | Details |
|--------|--------|---------|
| Region Support | ✅ **Ready** | `tradingview_fetcher.py` already supports `europe` and `asia` regions |
| US FPI Discovery | ✅ **Works** | FPIs like ASML, TSM, NVO already appear in `america` market scans |
| Filter Logic | ⚠️ **Review** | ADR/duplicate filtering may incorrectly exclude legitimate FPIs |

**Finding**: TradingView's `america` market scan includes FPIs listed on NYSE/NASDAQ. No changes needed for discovery.

---

### 2. SEC Filings - Company Facts (EDGAR API)

| Aspect | Status | Details |
|--------|--------|---------|
| 20-F Annual Forms | ✅ **Supported** | `edgar_fetcher.py` line 314: `if entry.get('form') in ['10-K', '20-F']` |
| 6-K Quarterly Forms | ✅ **Supported** | `edgar_fetcher.py` line 389: `if form in ['10-Q', '6-K', '10-K', '20-F', '40-F']` |
| IFRS Fallback | ✅ **Supported** | IFRS namespace used when US-GAAP not available |
| Canadian 40-F | ✅ **Supported** | Handled alongside 20-F for annual reports |

**Finding**: The core EDGAR fetcher already handles 20-F and 6-K forms for extracting EPS, revenue, and financial metrics from company_facts.

---

### 3. Earnings History Table

| Aspect | Status | Details |
|--------|--------|---------|
| Annual Data (20-F) | ✅ **Works** | `parse_eps_history`, `parse_net_income_history` include 20-F forms |
| Quarterly Data (6-K) | ⚠️ **Partial** | 6-K forms handled, but FPIs often report semi-annually, not quarterly |
| Fiscal Period Detection | ⚠️ **Partial** | FPIs may have different fiscal year ends (not Dec 31) |
| IFRS Metrics | ✅ **Supported** | Fallback to IFRS namespaces when US-GAAP unavailable |

**Gap**: The earnings_history table expects quarterly data (Q1-Q4), but many FPIs only report semi-annually (H1, H2). The system may have sparse or missing quarterly rows.

---

### 4. Filing Sections (MD&A, Risk Factors)

| Aspect | Status | Details |
|--------|--------|---------|
| 10-K/10-Q Extraction | ✅ **Works** | `extract_filing_sections` handles 10-K and 10-Q |
| 20-F Extraction | ❌ **Not Supported** | Only handles `'10-K'` and `'10-Q'` filing types |
| 6-K Extraction | ❌ **Not Supported** | Not implemented |

**Gap**: The `extract_filing_sections` method in `edgar_fetcher.py` (line 3578) explicitly only handles 10-K and 10-Q. 20-F forms have different item numbering:

| 10-K Item | 20-F Equivalent |
|-----------|-----------------|
| Item 1 (Business) | Item 4 (Information on the Company) |
| Item 1A (Risk Factors) | Item 3D (Risk Factors) |
| Item 7 (MD&A) | Item 5 (Operating and Financial Review) |
| Item 7A (Market Risk) | Item 11 (Quantitative and Qualitative Disclosures) |

---

### 5. SEC Data Fetcher (Orchestration)

| Aspect | Status | Details |
|--------|--------|---------|
| Country Filter | ❌ **Blocks FPIs** | Line 43-45: Skips if `country not in ('US', 'USA', 'UNITED STATES', '')` |
| Filing Types | ❌ **10-K/10-Q Only** | Only fetches sections for 10-K and 10-Q |

**Gap**: `sec_data_fetcher.py` explicitly skips non-US stocks, preventing any FPI from getting filing sections even though they file with the SEC.

```python
# Current blocking code (line 43-45):
if country not in ('US', 'USA', 'UNITED STATES', ''):
    logger.debug(f"[SECDataFetcher][{symbol}] Skipping SEC data (non-US stock: {country})")
    return
```

---

### 6. Analyst Estimates

| Aspect | Status | Details |
|--------|--------|---------|
| Data Source | ✅ **Works** | FinnHub provides estimates for FPIs (ASML, TSM, etc.) |
| TradingView | ✅ **Works** | EPS estimates available for most FPIs |
| Coverage | ⚠️ **Variable** | Some smaller FPIs may have limited analyst coverage |

**Finding**: No changes needed. FinnHub and TradingView already provide analyst estimates for FPIs.

---

### 7. News

| Aspect | Status | Details |
|--------|--------|---------|
| FinnHub API | ✅ **Works** | Uses ticker symbol, works for FPIs on US exchanges |
| International Tickers | ⚠️ **Limited** | May not find news for tickers not on US exchanges |

**Finding**: For FPIs listed on NYSE/NASDAQ, news fetching should work. No changes needed.

---

### 8. Earnings Call Transcripts

| Aspect | Status | Details |
|--------|--------|---------|
| MarketBeat Source | ⚠️ **Partial** | MarketBeat/Quartr may have limited FPI coverage |
| Exchange Detection | ⚠️ **Hardcoded** | `_get_exchange` defaults to NASDAQ |

**Gap**: Transcript scraper may need testing with FPI tickers to verify coverage.

---

### 9. Stock Metrics (Price Data)

| Aspect | Status | Details |
|--------|--------|---------|
| TradingView | ✅ **Works** | Works for all US-listed securities including FPIs |
| yfinance | ✅ **Works** | Works for FPIs with US tickers (ASML, TSM, NVO) |

**Finding**: No changes needed. Price data works for any US-listed security.

---

## Gap Summary

| Component | Gap Severity | Impact |
|-----------|--------------|--------|
| Stock Discovery | ✅ None | FPIs already discoverable |
| Earnings History (Annual) | ✅ None | 20-F data flows through |
| Earnings History (Quarterly) | ⚠️ Low | FPIs may report semi-annually only |
| Filing Sections | 🔴 **High** | No MD&A/Risks extracted from 20-F |
| SEC Data Fetcher | 🔴 **High** | Country filter blocks all FPIs |
| Analyst Estimates | ✅ None | FinnHub works for FPIs |
| News | ✅ None | Works for US-listed FPIs |
| Transcripts | ⚠️ Medium | May need testing/expansion |
| Stock Metrics | ✅ None | TradingView works |

---

## Closure Plan

### Phase 1: Enable FPI SEC Processing (High Priority)

**Goal**: Allow SEC data fetching for Foreign Private Issuers

#### 1.1 Modify SEC Data Fetcher Country Filter

**File**: `backend/sec_data_fetcher.py`

Change the country filter to check if the company has SEC filings rather than just checking country:

```python
# Instead of blocking by country, check if CIK exists (means they file with SEC)
cik = self.edgar_fetcher.get_cik_for_ticker(symbol)
if not cik:
    logger.debug(f"[SECDataFetcher][{symbol}] Skipping SEC data (no CIK found)")
    return
```

**Effort**: Small (~1 hour)

#### 1.2 Add 20-F Section Extraction

**File**: `backend/edgar_fetcher.py`

Extend `extract_filing_sections` to handle 20-F forms:

1. Add new branch for `filing_type == '20-F'`
2. Map 20-F items to equivalent sections:
   - Item 4 → business
   - Item 3D → risk_factors  
   - Item 5 → mda
   - Item 11 → market_risk

**Effort**: Medium (~4 hours)

---

### Phase 2: Quarterly Data Handling (Medium Priority)

**Goal**: Handle semi-annual reporting patterns

#### 2.1 Update Earnings History for Semi-Annual Periods

**File**: `backend/edgar_fetcher.py`

Add support for H1/H2 period types in quarterly earnings parsing, recognizing that some FPIs only file 6-K twice per year.

**Effort**: Medium (~4 hours)

---

### Phase 3: Transcript Coverage (Low Priority)

**Goal**: Verify and expand transcript coverage for FPIs

#### 3.1 Test Transcript Scraper with FPIs

Test MarketBeat/Quartr coverage for major FPIs:
- ASML, TSM, NVO, SAP, SHOP

**Effort**: Small (~2 hours testing)

---

## Testing Strategy

### Verification Queries

After implementation, run these queries to verify FPI support:

```sql
-- Check if FPIs have filing sections
SELECT symbol, section_name, filing_type, filing_date 
FROM filing_sections 
WHERE symbol IN ('ASML', 'TSM', 'NVO', 'SAP');

-- Check FPI earnings history
SELECT symbol, fiscal_year, fiscal_quarter, revenue, eps 
FROM earnings_history 
WHERE symbol IN ('ASML', 'TSM', 'NVO', 'SAP')
ORDER BY symbol, fiscal_year DESC, fiscal_quarter DESC;
```

### Test Tickers

| Ticker | Company | Country | Exchange | Notes |
|--------|---------|---------|----------|-------|
| ASML | ASML Holding | Netherlands | NASDAQ | Semiconductor equipment |
| TSM | Taiwan Semiconductor | Taiwan | NYSE | Largest semiconductor foundry |
| NVO | Novo Nordisk | Denmark | NYSE | Pharmaceuticals |
| SAP | SAP SE | Germany | NYSE | Enterprise software |
| SHOP | Shopify | Canada | NYSE | E-commerce (40-F filer) |

---

## Out of Scope

The following are explicitly **out of scope** for this initiative:

1. **Pure European/Asian stocks** not listed on US exchanges (no SEC filings)
2. **Real-time European market data** (would require additional data providers)
3. **Non-English filings** (20-F must be in English per SEC rules)
4. **Currency conversion** for non-USD financials

---

## Estimated Total Effort

| Phase | Description | Effort |
|-------|-------------|--------|
| Phase 1 | Enable FPI SEC Processing | 5 hours |
| Phase 2 | Semi-Annual Reporting | 4 hours |
| Phase 3 | Transcript Testing | 2 hours |
| **Total** | | **11 hours** |

---

## Next Steps

1. Review and approve this gap analysis
2. Prioritize Phase 1 (SEC data fetcher + 20-F sections)
3. Test with sample FPI tickers (ASML, TSM, NVO)
4. Monitor for any edge cases or additional gaps
