# DCF Analysis Primer: WACC & Terminal Value

## Part 1: WACC (Weighted Average Cost of Capital)

### What is WACC?

WACC is the **discount rate** used in DCF analysis. It represents the average rate of return a company must pay to finance its assets, weighted by the proportion of debt and equity.

**Why it matters**: This is the rate investors expect to earn for the risk they're taking. Higher risk = higher WACC = lower valuation.

### The Formula

```
WACC = (E/V × Re) + (D/V × Rd × (1 - Tc))

Where:
E = Market value of equity
D = Market value of debt
V = E + D (total value)
Re = Cost of equity
Rd = Cost of debt
Tc = Corporate tax rate
```

### Step-by-Step Calculation

#### Step 1: Find Market Value of Equity (E)

```
E = Share Price × Shares Outstanding
```

**Example (AAPL):**
- Share price: $267
- Shares outstanding: 15.2B
- E = $267 × 15.2B = **$4,058B**

#### Step 2: Find Market Value of Debt (D)

Look at the balance sheet for:
- Long-term debt
- Short-term debt
- Current portion of long-term debt

**Example (AAPL):**
- Total debt: ~$111B
- D = **$111B**

#### Step 3: Calculate Cost of Equity (Re) using CAPM

```
Re = Rf + β × (Rm - Rf)

Where:
Rf = Risk-free rate (10-year Treasury yield)
β = Beta (stock's volatility vs. market)
Rm = Expected market return
(Rm - Rf) = Market risk premium
```

**Example (AAPL):**
- Rf = 4.5% (current 10-year Treasury)
- β = 1.25 (from Yahoo Finance or Bloomberg)
- Market risk premium = 7% (historical average)
- Re = 4.5% + 1.25 × 7% = **13.25%**

**Where to find Beta:**
- Yahoo Finance → Statistics tab
- Morningstar
- Bloomberg Terminal

#### Step 4: Calculate Cost of Debt (Rd)

```
Rd = Interest Expense / Total Debt
```

**Example (AAPL):**
- Interest expense: $3.9B (from income statement)
- Total debt: $111B
- Rd = $3.9B / $111B = **3.5%**

**Alternative**: Look at the company's bond yields (if publicly traded)

#### Step 5: Find Tax Rate (Tc)

```
Tc = Income Tax Expense / Pre-tax Income
```

**Example (AAPL):**
- Effective tax rate: ~15% (from 10-K)
- Tc = **15%**

#### Step 6: Calculate WACC

```
E/V = $4,058B / ($4,058B + $111B) = 97.3%
D/V = $111B / ($4,058B + $111B) = 2.7%

WACC = (0.973 × 13.25%) + (0.027 × 3.5% × (1 - 0.15))
     = 12.89% + 0.08%
     = 12.97%
```

**Round to**: **13%** for AAPL

### Practical Shortcuts

For most companies:
- **Low debt, stable company**: WACC ≈ 8-10%
- **Moderate debt, average risk**: WACC ≈ 10-12%
- **High debt or high risk**: WACC ≈ 12-15%
- **Startups/speculative**: WACC ≈ 15-20%+

**Rule of thumb**: If you don't want to calculate, use **10%** as a conservative baseline.

---

## Part 2: Terminal Value

### What is Terminal Value?

Terminal value represents the value of all cash flows **beyond** your projection period (typically year 5). It usually accounts for 60-80% of total DCF value.

**Why it matters**: Small changes in terminal assumptions can dramatically change your valuation.

### Two Methods

#### Method 1: Perpetual Growth Model (Gordon Growth)

**Formula:**
```
Terminal Value = FCF(final year) × (1 + g) / (WACC - g)

Where:
g = Perpetual growth rate
```

**Example (AAPL):**
- Year 5 FCF: $150B
- g = 2.5% (long-term GDP growth)
- WACC = 13%
- TV = $150B × 1.025 / (0.13 - 0.025) = **$1,464B**

**Choosing g:**
- **Conservative**: 2-2.5% (GDP growth)
- **Moderate**: 3-4% (if company can grow faster than economy)
- **Aggressive**: 5%+ (rarely justified)

**Warning**: g must be < WACC, or the formula breaks (negative denominator)

#### Method 2: Exit Multiple

**Formula:**
```
Terminal Value = FCF(final year) × Exit Multiple
```

**Example (AAPL):**
- Year 5 FCF: $150B
- Exit multiple: 15x (based on industry average)
- TV = $150B × 15 = **$2,250B**

**Choosing the multiple:**
1. Look at current FCF multiples for comparable companies
2. Use historical average for the industry
3. Adjust for company quality (higher for better companies)

**Typical ranges:**
- **Mature, stable**: 10-15x FCF
- **Growth companies**: 15-25x FCF
- **High growth tech**: 25-40x FCF

---

## Which Method to Use?

| Situation | Recommended Method | Why |
|-----------|-------------------|-----|
| Mature, stable company | Perpetual Growth | Predictable, steady growth |
| Cyclical business | Exit Multiple | Easier to estimate average multiple |
| High-growth company | Exit Multiple | Growth will slow, multiple compression |
| Uncertain future | Both (average them) | Reduces single-method risk |

---

## Common Mistakes

### WACC Mistakes

1. **Using book value of debt instead of market value**
   - ❌ Wrong: Use balance sheet debt
   - ✅ Right: Use market value (or fair value from footnotes)

2. **Forgetting the tax shield on debt**
   - ❌ Wrong: WACC = (E/V × Re) + (D/V × Rd)
   - ✅ Right: WACC = (E/V × Re) + (D/V × Rd × (1 - Tc))

3. **Using outdated risk-free rate**
   - ❌ Wrong: Using 2% from 2020
   - ✅ Right: Current 10-year Treasury yield

4. **Ignoring capital structure changes**
   - If company is paying down debt or issuing shares, adjust E/V and D/V

### Terminal Value Mistakes

1. **Using too high a growth rate**
   - ❌ Wrong: g = 7% (higher than GDP)
   - ✅ Right: g = 2-3% (sustainable long-term)

2. **Inconsistent assumptions**
   - If you project 15% growth for 5 years, then assume 2% perpetual growth, there's an implicit slowdown you're not modeling

3. **Forgetting to discount terminal value**
   - Terminal value is at Year 5, so you must discount it back to present:
   ```
   PV of TV = TV / (1 + WACC)^5
   ```

4. **Using exit multiple from peak valuations**
   - Don't use 2021 tech multiples (40x+) as your exit multiple
   - Use long-term averages

---

## Sensitivity Analysis is Critical

Because WACC and terminal assumptions are uncertain, **always run sensitivity analysis**:

### Example Sensitivity Table

| WACC → | 8% | 10% | 12% | 14% |
|--------|-----|-----|-----|-----|
| **g = 2%** | $450 | $380 | $320 | $275 |
| **g = 2.5%** | $475 | $400 | $340 | $290 |
| **g = 3%** | $505 | $425 | $360 | $310 |

This shows you the range of possible values and how sensitive your valuation is to assumptions.

---

## Practical Example: Full DCF for AAPL

### Inputs
- Current FCF: $100B
- Growth rate (5 years): 5%
- Terminal growth: 2.5%
- WACC: 13%

### Projections
| Year | FCF | Discount Factor | PV |
|------|-----|----------------|-----|
| 1 | $105B | 1.13 | $93B |
| 2 | $110B | 1.28 | $86B |
| 3 | $116B | 1.44 | $80B |
| 4 | $122B | 1.63 | $75B |
| 5 | $128B | 1.84 | $69B |

**Sum of PV**: $403B

### Terminal Value
```
TV = $128B × 1.025 / (0.13 - 0.025) = $1,250B
PV of TV = $1,250B / 1.84 = $679B
```

### Total Value
```
Enterprise Value = $403B + $679B = $1,082B
Value per share = $1,082B / 15.2B shares = $71
```

**Current price**: $267
**Implied**: Overvalued (or our assumptions are too conservative)

---

## Key Takeaways

1. **WACC typically ranges 8-15%** for most companies
2. **Terminal growth should be 2-3%** (GDP growth rate)
3. **Terminal value is 60-80% of total value** - get this right!
4. **Always run sensitivity analysis** - single-point estimates are misleading
5. **Be conservative** - it's better to undervalue than overvalue
6. **Compare to market multiples** - if your DCF gives you 5x P/E and the market is 25x, something's wrong

## Resources for Data

- **Beta**: Yahoo Finance, Morningstar, Bloomberg
- **Risk-free rate**: [treasury.gov](https://www.treasury.gov/resource-center/data-chart-center/interest-rates/)
- **Debt levels**: Company 10-K, balance sheet
- **Tax rate**: Company 10-K, income tax footnote
- **Industry multiples**: Damodaran's website, CapIQ, Bloomberg
