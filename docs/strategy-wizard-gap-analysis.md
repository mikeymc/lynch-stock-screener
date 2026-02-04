# Strategy Wizard Gap Analysis

**Document Purpose**: Identify gaps between backend capabilities and frontend UI exposure for the autonomous investment strategy system.

**Last Updated**: 2026-02-03

---

## Executive Summary

The strategy execution backend (`strategy_executor.py`) supports rich configuration options for filtering, scoring, consensus, position sizing, and exits. The current wizard (`StrategyWizard.jsx`) exposes approximately **40%** of available configuration surface area. This document catalogs the gaps, provides implementation options, and suggests prioritization.

---

## Gap 1: Universe Filters (Stock Screening)

### Current State
- **Backend Support**: Full filtering system via `ConditionEvaluator.evaluate_universe()`
- **Wizard Exposure**: None (Step 2 has empty filters array, no UI)

### Backend Capabilities

The backend supports filtering on these fields:

| Field | Operators | Example | Maps To DB Column |
|-------|-----------|---------|-------------------|
| `symbol` | `==`, `!=` | Filter single stock | `symbol` |
| `price_vs_52wk_high` | `<`, `>`, `<=`, `>=` | Stocks down 20%+ from highs | `price_change_52w_pct` |
| `market_cap` | `<`, `>`, `<=`, `>=` | Large caps only (>$10B) | `market_cap` |
| `pe_ratio` | `<`, `>`, `<=`, `>=` | Value stocks (PE < 15) | `pe_ratio` |
| `peg_ratio` | `<`, `>`, `<=`, `>=` | Growth at reasonable price | `peg_ratio` |
| `debt_to_equity` | `<`, `>`, `<=`, `>=` | Low leverage (D/E < 0.5) | `debt_to_equity` |
| `price` | `<`, `>`, `<=`, `>=` | Min price filters | `price` |
| `sector` | `==`, `!=` | Sector focus or exclusion | `sector` |

**Example Backend Config:**
```json
{
  "universe": {
    "filters": [
      {"field": "price_vs_52wk_high", "operator": "<=", "value": -20},
      {"field": "market_cap", "operator": ">=", "value": 10000000000},
      {"field": "sector", "operator": "==", "value": "Technology"}
    ]
  }
}
```

### Why This Matters

Universe filtering is the **first step** in the execution pipeline (docs:51-55). Without it:
- Strategies screen the entire universe (expensive, slow)
- Users can't implement sector-specific strategies
- Can't replicate common strategies like "beaten-down large caps"
- Forces users to manually screen via API/SQL before creating strategy

### Implementation Options

#### Option A: Filter Builder UI (Recommended)
**Complexity**: Medium (2-3 hours)

Add a dynamic filter builder in Step 2:
```jsx
{/* In Step 2, before Analysis Mode section */}
<div className="bg-muted/50 rounded-xl p-6 border border-border">
  <h4 className="font-medium mb-4">Stock Screening Filters</h4>
  <p className="text-sm text-muted-foreground mb-4">
    Define which stocks to evaluate. Leave empty to screen all stocks.
  </p>

  {formData.conditions.filters.map((filter, idx) => (
    <FilterRow
      key={idx}
      filter={filter}
      onChange={(updated) => updateFilter(idx, updated)}
      onRemove={() => removeFilter(idx)}
    />
  ))}

  <Button onClick={addFilter}>
    <Plus /> Add Filter
  </Button>
</div>
```

**FilterRow Component:**
- Dropdown for field selection
- Dropdown for operator (context-aware based on field type)
- Input for value (number input for numeric fields, text for sector)
- Remove button

**Pros:**
- Full flexibility, matches backend capabilities
- Familiar pattern (like Airtable/Notion filters)
- Easy to understand visually

**Cons:**
- More complex UI
- Requires validation logic
- Learning curve for new users

#### Option B: Preset Filter Templates
**Complexity**: Low (1 hour)

Provide common filter presets:
```jsx
<select onChange={applyFilterTemplate}>
  <option>Custom (no filters)</option>
  <option value="beaten_down_large_caps">Beaten Down Large Caps (>$10B, -20% from highs)</option>
  <option value="value_stocks">Value Stocks (PE < 15, PEG < 1)</option>
  <option value="tech_growth">Tech Growth (Sector=Technology, PE < 30)</option>
  <option value="low_debt">Low Debt (D/E < 0.5)</option>
</select>
```

**Pros:**
- Simple, fast to implement
- Guides users toward proven patterns
- Low cognitive load

**Cons:**
- Not flexible
- Limited to predefined templates
- Users can't mix/match criteria

#### Option C: Hybrid Approach (Best of Both)
**Complexity**: Medium-High (3-4 hours)

Start with templates, allow customization:
1. User selects template as starting point
2. Template populates filter builder
3. User can add/remove/modify individual filters

**Pros:**
- Best of both: guidance + flexibility
- Progressive disclosure (simple → advanced)
- Accommodates novice and expert users

**Cons:**
- Most implementation work
- Two UX modes to maintain

### Recommendation

**Implement Option A (Filter Builder)** for these reasons:
1. Already implemented position sizing with similar complexity
2. Filters are core to strategy definition (not optional)
3. Templates can be added later as shortcuts
4. Matches user expectations from similar tools

---

## Gap 2: Scoring Requirements

### Current State
- **Backend Support**: `scoring_requirements` array with per-character min_score thresholds
- **Wizard Exposure**: None (uses backend defaults)

### Backend Capabilities

```json
{
  "scoring_requirements": [
    {"character": "lynch", "min_score": 70},
    {"character": "buffett", "min_score": 70}
  ]
}
```

Controls which stocks proceed from scoring phase (docs:306-314). Default thresholds exist but aren't user-configurable.

### Why This Matters

Different strategies have different risk tolerances:
- **Aggressive**: Lower thresholds (60) to see more opportunities
- **Conservative**: Higher thresholds (80) for high-conviction only
- **Character-specific**: Trust Lynch more (60) than Buffett (75), or vice versa

Without UI exposure, all strategies use same thresholds (hardcoded 70).

### Implementation Options

#### Option A: Simple Sliders (Recommended)
**Complexity**: Low (30 minutes)

Add to Step 2, below Consensus Mode:

```jsx
<div className="bg-muted/50 rounded-xl p-6 border border-border">
  <h4 className="font-medium mb-4">Minimum Score Thresholds</h4>
  <p className="text-sm text-muted-foreground mb-4">
    Only stocks scoring above these thresholds will proceed to deliberation.
  </p>

  <div className="space-y-4">
    <div>
      <label className="flex justify-between mb-2">
        <span>Lynch Minimum Score</span>
        <span className="font-mono">{formData.lynch_min_score}</span>
      </label>
      <input
        type="range"
        min="0"
        max="100"
        step="5"
        value={formData.lynch_min_score}
        onChange={...}
      />
    </div>

    <div>
      <label className="flex justify-between mb-2">
        <span>Buffett Minimum Score</span>
        <span className="font-mono">{formData.buffett_min_score}</span>
      </label>
      <input
        type="range"
        min="0"
        max="100"
        step="5"
        value={formData.buffett_min_score}
        onChange={...}
      />
    </div>
  </div>
</div>
```

**Pros:**
- Visual, intuitive
- Easy to adjust
- Shows current value inline

**Cons:**
- Range inputs have limited styling options
- Harder to set exact values

#### Option B: Number Inputs
**Complexity**: Low (20 minutes)

Simple number inputs instead of sliders:

```jsx
<div className="grid grid-cols-2 gap-4">
  <div>
    <label>Lynch Min Score</label>
    <input type="number" min="0" max="100" step="5" />
  </div>
  <div>
    <label>Buffett Min Score</label>
    <input type="number" min="0" max="100" step="5" />
  </div>
</div>
```

**Pros:**
- Simpler implementation
- Precise control
- Familiar input pattern

**Cons:**
- Less visual
- No sense of "scale" (is 70 high or low?)

#### Option C: Preset Risk Levels
**Complexity**: Low (15 minutes)

Radio buttons with presets:

```jsx
<RadioGroup value={riskLevel} onChange={setRiskLevelPreset}>
  <Radio value="conservative">Conservative (80/80)</Radio>
  <Radio value="moderate">Moderate (70/70)</Radio>
  <Radio value="aggressive">Aggressive (60/60)</Radio>
  <Radio value="custom">Custom...</Radio>
</RadioGroup>

{riskLevel === 'custom' && (
  // Show number inputs
)}
```

**Pros:**
- Guided experience
- Quick setup
- Can still customize

**Cons:**
- Less granular by default
- Extra step for custom values

### Recommendation

**Implement Option A (Sliders)** because:
1. Visual feedback helps users understand scale
2. Step increments (5) prevent over-precision
3. Matches modern UI expectations
4. Can add presets later as shortcuts

---

## Gap 3: Thesis Verdict Requirements

### Current State
- **Backend Support**: `thesis_verdict_required` array specifying acceptable deliberation outcomes
- **Wizard Exposure**: None (defaults to requiring deliberation but accepts any verdict)

### Backend Capabilities

```json
{
  "require_thesis": true,
  "thesis_verdict_required": ["BUY"]
}
```

Controls which deliberation verdicts trigger trades (docs:516-521). Possible verdicts:
- `BUY`: High conviction purchase
- `WATCH`: Interesting but wait
- `AVOID`: Pass on this opportunity

Currently, wizard sets `require_thesis` toggle (line 199) but doesn't expose verdict filtering.

### Why This Matters

Different strategies have different decision criteria:
- **Aggressive**: Accept BUY or WATCH verdicts
- **Conservative**: Only BUY (current implicit default)
- **Research Mode**: Only WATCH (build watchlist without buying)

Without UI control, users can't implement watchlist-only strategies or adjust conviction requirements.

### Implementation Options

#### Option A: Checkbox Group (Recommended)
**Complexity**: Low (20 minutes)

Add below the "Enable AI Deliberation" toggle in Step 2:

```jsx
{formData.conditions.require_thesis && (
  <div className="mt-4 pl-4 border-l-2 border-primary">
    <label className="text-sm font-medium mb-2 block">
      Accept These Verdicts:
    </label>
    <div className="space-y-2">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={verdicts.includes('BUY')}
          onChange={...}
        />
        <span>BUY (High conviction)</span>
      </label>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={verdicts.includes('WATCH')}
          onChange={...}
        />
        <span>WATCH (Interesting, needs monitoring)</span>
      </label>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={verdicts.includes('AVOID')}
          onChange={...}
        />
        <span>AVOID (Pass on opportunity)</span>
      </label>
    </div>
  </div>
)}
```

**Pros:**
- Clear, explicit control
- Can select multiple verdicts
- Shows all available options

**Cons:**
- AVOID is rarely useful (why run strategy to avoid?)
- Might confuse users (when would you want WATCH?)

#### Option B: Radio Group (Simplified)
**Complexity**: Low (15 minutes)

Single choice instead of checkboxes:

```jsx
<RadioGroup value={verdictMode}>
  <Radio value="buy_only">BUY only (Conservative)</Radio>
  <Radio value="buy_or_watch">BUY or WATCH (Flexible)</Radio>
</RadioGroup>
```

**Pros:**
- Simpler decision
- Removes confusing AVOID option
- Clear risk profiles

**Cons:**
- Less flexible
- Can't implement pure watchlist mode

#### Option C: Smart Default + Advanced Option
**Complexity**: Low (25 minutes)

Start simple, expand if needed:

```jsx
<div className="space-y-3">
  <label className="flex items-center gap-2">
    <input
      type="checkbox"
      checked={strictMode}
      onChange={...}
    />
    <span>Strict Mode (BUY verdict only)</span>
  </label>

  {!strictMode && (
    <div className="text-xs text-muted-foreground ml-6">
      Will accept BUY or WATCH verdicts
    </div>
  )}
</div>
```

**Pros:**
- Simple by default (checkbox)
- Progressive disclosure
- Handles 90% of use cases

**Cons:**
- Doesn't support pure watchlist mode
- Binary choice limits flexibility

### Recommendation

**Implement Option A (Checkbox Group)** for these reasons:
1. Maximum flexibility for future use cases
2. Educational (shows what verdicts mean)
3. Low implementation cost
4. Can add explanatory tooltips later

---

## Gap 4: Exit Condition Score Degradation

### Current State
- **Backend Support**: `score_degradation` with per-character thresholds
- **Wizard Exposure**: Partial (profit target, stop loss, max hold days shown; score degradation missing)

### Backend Capabilities

```json
{
  "exit_conditions": {
    "profit_target_pct": 50,
    "stop_loss_pct": -20,
    "max_hold_days": 365,
    "score_degradation": {
      "lynch_below": 40,
      "buffett_below": 40
    }
  }
}
```

Score degradation triggers sell when stock's re-evaluated scores fall below thresholds (docs:375-387). This is **automatic sell on fundamental deterioration**, separate from price-based exits.

### Why This Matters

Exit conditions are critical risk management:
- **Profit target**: Locks in gains
- **Stop loss**: Limits losses
- **Score degradation**: Exits when thesis breaks (even if price unchanged)

Without score degradation UI, users can't implement "sell when fundamentals deteriorate" logic.

### Current UI (Step 2, lines 232-275)

Shows profit target, stop loss, max hold days in a 3-column grid. Score degradation is completely missing.

### Implementation Options

#### Option A: Add to Existing Grid (Recommended)
**Complexity**: Low (30 minutes)

Expand the Exit Conditions section:

```jsx
<div className="bg-muted/50 rounded-xl p-6 border border-border">
  <h4 className="font-medium text-destructive mb-4">Exit Conditions</h4>

  {/* Existing price-based exits */}
  <div className="grid grid-cols-3 gap-6 mb-6">
    <div>
      <label>Profit Target (%)</label>
      <input type="number" placeholder="e.g. 50" />
    </div>
    <div>
      <label>Stop Loss (%)</label>
      <input type="number" placeholder="e.g. -15" />
    </div>
    <div>
      <label>Max Hold Days</label>
      <input type="number" placeholder="e.g. 365" />
    </div>
  </div>

  {/* NEW: Score-based exits */}
  <div className="pt-6 border-t border-border">
    <h5 className="text-sm font-medium mb-4">Score Degradation Triggers</h5>
    <p className="text-xs text-muted-foreground mb-4">
      Sell if re-evaluated scores fall below these thresholds (checks fundamentals, not price)
    </p>
    <div className="grid grid-cols-2 gap-6">
      <div>
        <label>Lynch Score Below</label>
        <input
          type="number"
          min="0"
          max="100"
          step="5"
          placeholder="e.g. 40"
          value={formData.exit_conditions.score_degradation?.lynch_below || ''}
          onChange={...}
        />
      </div>
      <div>
        <label>Buffett Score Below</label>
        <input
          type="number"
          min="0"
          max="100"
          step="5"
          placeholder="e.g. 40"
          value={formData.exit_conditions.score_degradation?.buffett_below || ''}
          onChange={...}
        />
      </div>
    </div>
  </div>
</div>
```

**Pros:**
- Logical grouping (all exits together)
- Clear separation (price vs fundamentals)
- Matches backend structure

**Cons:**
- Makes exit section taller
- Two different mental models (price % vs score points)

#### Option B: Separate Exit Strategies Section
**Complexity**: Medium (45 minutes)

Split into two sections:

```jsx
{/* Price-Based Exits */}
<div className="bg-muted/50 rounded-xl p-6 border border-border">
  <h4>Price-Based Exits</h4>
  {/* profit target, stop loss, max hold */}
</div>

{/* Fundamental Exits */}
<div className="bg-muted/50 rounded-xl p-6 border border-border">
  <h4>Fundamental Deterioration Exits</h4>
  {/* score degradation */}
</div>
```

**Pros:**
- Clearer conceptual separation
- More space for explanations
- Easier to understand two different exit types

**Cons:**
- More vertical space
- Fragments related concepts

#### Option C: Collapsible Advanced Section
**Complexity**: Medium (40 minutes)

Keep simple exits visible, hide advanced:

```jsx
<div className="bg-muted/50 rounded-xl p-6 border border-border">
  <h4>Exit Conditions</h4>

  {/* Basic exits always visible */}
  <div className="grid grid-cols-3 gap-6">
    {/* profit, stop, hold */}
  </div>

  {/* Advanced collapsible */}
  <Collapsible>
    <CollapsibleTrigger>
      <Button variant="ghost" size="sm">
        <ChevronDown /> Advanced: Score Degradation
      </Button>
    </CollapsibleTrigger>
    <CollapsibleContent>
      {/* score degradation inputs */}
    </CollapsibleContent>
  </Collapsible>
</div>
```

**Pros:**
- Progressive disclosure
- Doesn't overwhelm beginners
- Keeps related concepts together

**Cons:**
- Hidden by default (might be missed)
- Extra interaction required

### Recommendation

**Implement Option A (Add to Grid)** because:
1. Score degradation is important enough to be visible
2. Matches backend's flat structure
3. Clear labeling prevents confusion
4. Sets precedent for other advanced features

---

## Gap 5: Consensus Threshold (weighted_confidence mode)

### Current State
- **Backend Support**: `consensus_threshold` field (float, default 70.0)
- **Wizard Exposure**: Hardcoded in defaults, not user-adjustable

### Backend Capabilities

For `weighted_confidence` consensus mode:
```python
combined_score = (lynch.score * lynch_weight) + (buffett.score * buffett_weight)
if combined_score >= 80:
    verdict = 'BUY'
elif combined_score >= threshold:  # <-- User-configurable
    verdict = 'WATCH'
else:
    verdict = 'AVOID'
```

The `consensus_threshold` separates WATCH from AVOID (docs:411-420).

### Why This Matters

Consensus mode is selected (Step 2, line 216) but threshold isn't configurable:
- User selects "Weighted Confidence" mode
- Wizard uses default threshold (70)
- No way to adjust sensitivity

### Implementation Options

#### Option A: Conditional Input (Recommended)
**Complexity**: Low (15 minutes)

Show threshold input only when weighted_confidence selected:

```jsx
<select value={formData.consensus_mode} onChange={...}>
  <option value="both_agree">Strict Agreement</option>
  <option value="weighted_confidence">Weighted Confidence</option>
  <option value="veto_power">Veto Power</option>
</select>

{formData.consensus_mode === 'weighted_confidence' && (
  <div className="mt-4 pl-4 border-l-2 border-primary">
    <label>Consensus Threshold</label>
    <input
      type="number"
      min="0"
      max="100"
      step="5"
      value={formData.consensus_threshold}
      onChange={...}
    />
    <p className="text-xs text-muted-foreground mt-1">
      Combined score needed for WATCH verdict (80+ = BUY)
    </p>
  </div>
)}
```

**Pros:**
- Only shows when relevant
- Context-aware UI
- Low complexity

**Cons:**
- Easy to miss if collapsed/hidden
- Requires understanding of weighted mode

#### Option B: Always Show with Tooltip
**Complexity**: Low (20 minutes)

Always show threshold, explain when it applies:

```jsx
<div>
  <label className="flex items-center gap-2">
    Consensus Threshold
    <Tooltip>
      <TooltipTrigger><HelpCircle size={14} /></TooltipTrigger>
      <TooltipContent>
        Used in Weighted Confidence mode to separate WATCH from AVOID
      </TooltipContent>
    </Tooltip>
  </label>
  <input type="number" ... />
</div>
```

**Pros:**
- Always visible
- Educational tooltip
- Consistent UI

**Cons:**
- Clutters UI when not needed
- Might confuse users in other modes

### Recommendation

**Implement Option A (Conditional)** for these reasons:
1. Matches pattern from position sizing (method-specific fields)
2. Reduces cognitive load (only show when relevant)
3. Can add tooltip if users get confused

---

## Gap 6: Advanced Schedule Control

### Current State
- **Backend Support**: Full cron syntax via `schedule_cron` field
- **Wizard Exposure**: 3 preset options (Step 3, lines 318-327)

### Backend Capabilities

Accepts any valid cron string (docs:241):
```json
{
  "schedule_cron": "0 9 * * 1-5"  // 9 AM weekdays
}
```

### Why This Matters

Users might want:
- Multiple runs per day (9 AM + 4 PM)
- Weekly only (Mondays)
- Custom times (11 AM, after morning volatility)
- Disabled/manual only (empty/null)

Current presets cover common cases but no customization.

### Implementation Options

#### Option A: Preset + Custom Input
**Complexity**: Low (25 minutes)

```jsx
<select value={scheduleMode} onChange={...}>
  <option value="daily_open">Daily at Market Open (9:00 AM)</option>
  <option value="daily_close">Daily at Market Close (4:00 PM)</option>
  <option value="weekly">Weekly (Mondays)</option>
  <option value="custom">Custom cron...</option>
  <option value="manual">Manual only (no schedule)</option>
</select>

{scheduleMode === 'custom' && (
  <input
    type="text"
    placeholder="0 9 * * 1-5"
    value={formData.schedule_cron}
    onChange={...}
  />
)}
```

**Pros:**
- Accommodates most users with presets
- Power users can customize
- Supports manual-only mode

**Cons:**
- Cron syntax is obscure
- No validation/help for custom input

#### Option B: Time Picker + Day Selector
**Complexity**: High (2-3 hours)

Build visual cron editor:
```jsx
<div>
  <label>Run Time</label>
  <input type="time" value="09:00" onChange={...} />

  <label>Run Days</label>
  <CheckboxGroup>
    <Checkbox value="1">Monday</Checkbox>
    <Checkbox value="2">Tuesday</Checkbox>
    {/* ... */}
  </CheckboxGroup>
</div>
```

Then construct cron from selections.

**Pros:**
- User-friendly, no cron knowledge needed
- Visual, clear
- Prevents invalid cron

**Cons:**
- High complexity
- Limited to simple schedules
- Can't express complex patterns

### Recommendation

**Implement Option A (Preset + Custom)** for these reasons:
1. Low effort for high value
2. Presets cover 95% of use cases
3. Escape hatch for power users
4. Can add visual builder later if demand

---

## Gap 7: Manual Execution from UI

### Current State
- **Backend Support**: Strategies can be executed via `StrategyExecutor.execute_strategy(id)`
- **Wizard/UI Exposure**: No manual trigger button

### Current Behavior

Strategies execute on schedule via GitHub Actions (docs:699-706). No way to manually run from UI except:
1. SSH into server
2. Run Python script
3. Or trigger via API call

### Why This Matters

Users want to:
- **Test** strategy before enabling schedule
- **Force run** after config changes to see immediate results
- **Debug** without waiting for next scheduled run
- **Backfill** missed runs if scheduler failed

### Implementation Options

#### Option A: Add "Run Now" Button to Detail Page
**Complexity**: Medium (1 hour)

On StrategyDetail page, add button near "Configure":

```jsx
<Button
  variant="outline"
  size="sm"
  onClick={handleManualRun}
  disabled={running}
>
  <PlayCircle className="h-4 w-4 mr-2" />
  {running ? 'Running...' : 'Run Now'}
</Button>
```

Backend endpoint:
```python
@app.route('/api/strategies/<int:strategy_id>/run', methods=['POST'])
@require_user_auth
def manual_run_strategy(user_id, strategy_id):
    """Manually trigger a strategy run."""
    # Verify ownership
    strategy = db.get_strategy(strategy_id)
    if strategy['user_id'] != user_id:
        return jsonify({'error': 'Unauthorized'}), 403

    # Execute async
    executor = StrategyExecutor(db)
    result = executor.execute_strategy(strategy_id)

    return jsonify(result)
```

**Pros:**
- Simple, obvious location
- Immediate feedback
- Useful for testing

**Cons:**
- Blocks UI during execution (can be slow)
- No way to see live progress
- Could overwhelm server if spammed

#### Option B: Queue for Background Execution
**Complexity**: Medium-High (2 hours)

Instead of synchronous execution, queue job:

```python
@app.route('/api/strategies/<int:strategy_id>/run', methods=['POST'])
def manual_run_strategy(user_id, strategy_id):
    # Create background job
    job_id = db.create_background_job(
        job_type='strategy_execution',
        params={'strategy_id': strategy_id}
    )

    return jsonify({
        'message': 'Run queued',
        'job_id': job_id
    })
```

Frontend polls for completion or uses WebSocket for updates.

**Pros:**
- Non-blocking UI
- Leverages existing worker infrastructure
- Can show progress/logs
- Scales better

**Cons:**
- More complex implementation
- Requires polling or WebSocket
- Delayed feedback

#### Option C: Test Mode (Dry Run)
**Complexity**: Medium (1.5 hours)

Add dry-run mode that simulates without executing trades:

```python
executor.execute_strategy(
    strategy_id=strategy_id,
    dry_run=True  # <-- New parameter
)
```

Returns decisions without creating transactions.

**Pros:**
- Safe for testing
- Useful for validation
- No risk of unwanted trades

**Cons:**
- Doesn't test full path
- More backend complexity
- Still need real run eventually

### Recommendation

**Implement Option B (Background Queue)** because:
1. Reuses existing worker infrastructure (`backend/worker.py`)
2. Non-blocking, better UX for slow runs
3. Enables future features (progress bars, cancellation)
4. Production-grade approach

---

## Gap 8: Portfolio Creation Flow

### Current State
- **Backend Support**: Creates portfolio if `portfolio_id === 'new'` (app.py:681-684)
- **Wizard Exposure**: Works but has limitations

### Current Behavior (Step 3, lines 324-340)

User can select existing portfolio or create new. New portfolio:
- Uses strategy name as portfolio name
- Gets $100k initial cash (hardcoded)
- No way to customize initial cash amount
- No way to set portfolio name separately

### Why This Matters

Users might want:
- Different portfolio names (e.g., "Aggressive Tech" strategy → "Tech Portfolio")
- Custom initial amounts ($50k, $250k, etc.)
- To see portfolio will be created before confirming strategy

### Implementation Options

#### Option A: Expand New Portfolio Section
**Complexity**: Low (30 minutes)

When user selects "Create New Portfolio":

```jsx
{formData.portfolio_id === 'new' && (
  <div className="mt-4 space-y-4 p-4 bg-background rounded-lg border">
    <div>
      <label>Portfolio Name</label>
      <input
        type="text"
        value={formData.new_portfolio_name || formData.name}
        onChange={...}
        placeholder={formData.name}
      />
      <p className="text-xs text-muted-foreground mt-1">
        Defaults to strategy name
      </p>
    </div>

    <div>
      <label>Initial Cash</label>
      <input
        type="number"
        step="1000"
        value={formData.initial_cash || 100000}
        onChange={...}
      />
      <p className="text-xs text-muted-foreground mt-1">
        Paper trading starting balance
      </p>
    </div>
  </div>
)}
```

**Pros:**
- More control
- Sets expectations clearly
- Low complexity

**Cons:**
- More fields to fill
- Might overwhelm simple use case

#### Option B: Keep Simple, Add Edit Link
**Complexity**: Low (20 minutes)

Keep current behavior, add link to edit portfolio after creation:

```jsx
<p className="text-xs text-muted-foreground mt-2">
  A new portfolio will be created with $100k starting balance.
  <button className="text-primary underline ml-1" onClick={...}>
    Customize
  </button>
</p>
```

**Pros:**
- Simple by default
- Progressive disclosure
- Doesn't clutter UI

**Cons:**
- Customization hidden
- Extra step for power users

### Recommendation

**Implement Option A (Expand Section)** because:
1. Initial cash is important decision
2. Users expect control over portfolio setup
3. Low implementation cost
4. Aligns with strategy importance

---

## Gap 9: Backtest/Preview Capability

### Current State
- **Backend Support**: None (would require new implementation)
- **Wizard/UI Exposure**: N/A

### What's Missing

No way to:
- Test strategy against historical data before enabling
- Preview which stocks would be selected with current config
- Understand expected behavior before risking capital (even paper)

### Why This Matters

Users can't validate strategy logic until it runs live. This creates:
- Trial-and-error configuration
- Risk of poorly configured strategies executing
- No confidence in strategy before enabling

### Implementation Options

#### Option A: Preview Mode (Lightweight)
**Complexity**: Medium (2-3 hours)

Add "Preview Results" button in wizard Step 4:

```jsx
<Button
  variant="outline"
  onClick={handlePreview}
  disabled={previewing}
>
  <Eye className="h-4 w-4 mr-2" />
  Preview Stock Selection
</Button>

{previewResults && (
  <div className="mt-4 p-4 bg-muted rounded-lg">
    <h5>Preview Results (based on current market data)</h5>
    <ul>
      {previewResults.map(stock => (
        <li>{stock.symbol} - Lynch: {stock.lynch_score}, Buffett: {stock.buffett_score}</li>
      ))}
    </ul>
  </div>
)}
```

Backend endpoint runs filtering + scoring without executing trades or generating theses.

**Pros:**
- Fast (no thesis generation)
- Validates filters work as expected
- Catches obvious config errors

**Cons:**
- Doesn't test full pipeline
- No thesis preview
- Point-in-time only

#### Option B: Full Backtest Engine
**Complexity**: Very High (2-3 days)

Build comprehensive backtesting system:
- Run strategy against historical data
- Simulate trades and portfolio performance
- Generate performance metrics vs benchmark
- Show hypothetical P&L

**Pros:**
- Validates strategy thoroughly
- Builds confidence
- Enables optimization

**Cons:**
- Major implementation effort
- Requires historical price data
- Need to mock thesis generation (expensive to regenerate)
- Complex edge cases (market hours, corporate actions)

#### Option C: Dry Run (Test with Current Data)
**Complexity**: Medium (1.5 hours)

Add "Test Run" mode that executes full pipeline without persisting transactions:

```python
result = executor.execute_strategy(
    strategy_id=strategy_id,
    dry_run=True
)

# Returns: decisions made, but transactions rolled back
```

**Pros:**
- Tests full pipeline including theses
- Real current data
- Catches edge cases

**Cons:**
- Slow (thesis generation takes time)
- Costs API credits
- Only tests current moment

### Recommendation

**Implement Option A (Preview)** first for these reasons:
1. Low-hanging fruit, high value
2. Catches 80% of config errors
3. Fast enough for wizard workflow
4. Can add Option C later as "Test Run" button on detail page

---

## Priority Recommendation

Based on user impact and implementation effort:

### Tier 1: Must Have (Complete strategy creation experience)
1. **Universe Filters** (Option A: Filter Builder) - Core functionality, blocking many use cases
2. **Score Degradation Exits** (Option A: Add to Grid) - Critical risk management
3. **Manual Execution** (Option B: Background Queue) - Required for testing

**Estimated Total**: 4-5 hours

### Tier 2: Should Have (Improves flexibility)
4. **Scoring Requirements** (Option A: Sliders) - Risk tolerance control
5. **Thesis Verdict Requirements** (Option A: Checkboxes) - Decision criteria control
6. **Portfolio Creation** (Option A: Expand Section) - Better control

**Estimated Total**: 1.5 hours

### Tier 3: Nice to Have (Polish & advanced features)
7. **Consensus Threshold** (Option A: Conditional) - Fine-tuning weighted mode
8. **Schedule Control** (Option A: Preset + Custom) - Flexibility
9. **Preview Mode** (Option A: Lightweight Preview) - Validation

**Estimated Total**: 2-3 hours

### Not Recommended (Yet)
- **Full Backtest Engine**: Too complex, low ROI for current stage
- **Visual Cron Editor**: Over-engineered for use case

---

## Implementation Sequence

Suggested order to minimize rework:

### Phase 1: Core Completion (Session 1)
1. Universe Filters (filter builder UI)
2. Scoring Requirements (sliders)
3. Thesis Verdict Requirements (checkboxes)
4. Score Degradation Exits (add to grid)

**Why together**: All Step 2 (Strategy Logic) enhancements

### Phase 2: Execution Controls (Session 2)
5. Portfolio Creation (expand section)
6. Manual Execution (background queue + API)

**Why together**: Both Step 3 (Execution) related

### Phase 3: Polish (Session 3)
7. Consensus Threshold (conditional input)
8. Schedule Control (preset + custom)
9. Preview Mode (lightweight)

**Why together**: All refinements, non-blocking

---

## Technical Considerations

### Backward Compatibility

Existing strategies may have:
- Empty `filters` arrays
- Missing `scoring_requirements`
- Missing `score_degradation` in exits
- Old `position_sizing` schemas

**Solution**: Wizard's `initialData` merge (lines 23-45) handles this by providing defaults for missing fields.

### Validation Requirements

New fields need validation:
- Filters: Valid operators for field types
- Scores: 0-100 range
- Cron: Valid syntax (or use presets only)
- Portfolio: Name uniqueness

**Solution**: Add to `validateStep()` function (lines 98-112)

### API Changes Required

For Gaps 7-9:
- New endpoint: `POST /api/strategies/:id/run`
- New endpoint: `POST /api/strategies/:id/preview`
- Update: `POST /api/strategies` to accept new_portfolio_name, initial_cash

### Database Schema Changes

**None required** - All fields already exist in `investment_strategies` table (docs:107-122). Frontend is just exposing existing backend capabilities.

---

## Questions for Discussion

1. **Universe Filters**: Should we start with presets or go straight to builder?
2. **Manual Execution**: Is background queue overkill, or should we do sync first?
3. **Preview**: How important is this vs just testing with small amounts?
4. **Backtest**: Is this a future requirement, or should we prioritize it?

---

## Conclusion

The strategy wizard currently exposes ~40% of backend capabilities. The remaining 60% includes:

- **Critical gaps** (filters, exits) that block common use cases
- **Important gaps** (scoring, portfolio setup) that limit flexibility
- **Nice-to-have gaps** (preview, backtest) that improve confidence

Implementing **Tier 1 + Tier 2** (~6 hours total) would bring the wizard to ~90% feature parity with the backend, covering all essential configuration scenarios while leaving polish and advanced features for later iterations.

The gaps are well-documented in backend code and docs, making implementation straightforward - it's primarily UI work, not backend changes.
