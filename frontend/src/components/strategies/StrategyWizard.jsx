import React, { useState, useEffect } from 'react';
import {
    X, ChevronRight, ChevronLeft, Check, Plus, Trash2,
    HelpCircle, AlertCircle, Info
} from 'lucide-react';

/**
 * Strategy Wizard Component
 * A multi-step wizard for creating autonomous investment strategies.
 */
const StrategyWizard = ({ onClose, onSuccess, initialData = null, mode = 'create' }) => {
    const [step, setStep] = useState(1);

    // Default values
    const defaults = {
        name: '',
        description: '',
        conditions: {
            filters: [],
            require_thesis: true
        },
        consensus_mode: 'both_agree',
        consensus_threshold: 70,
        exit_conditions: {
            profit_target_pct: '',
            stop_loss_pct: '',
            max_hold_days: ''
        },
        portfolio_selection: 'new',
        portfolio_id: 'new',
        position_sizing: {
            method: 'equal_weight',
            max_position_pct: 10.0,
            min_position_value: 500,
            fixed_position_pct: '',
            kelly_fraction: ''
        },
        schedule_cron: '0 9 * * 1-5'
    };

    // Merge initialData with defaults to ensure all fields exist
    const [formData, setFormData] = useState(
        initialData
            ? {
                ...defaults,
                ...initialData,
                conditions: { ...defaults.conditions, ...initialData.conditions },
                exit_conditions: { ...defaults.exit_conditions, ...initialData.exit_conditions },
                position_sizing: { ...defaults.position_sizing, ...initialData.position_sizing }
            }
            : defaults
    );

    const [portfolios, setPortfolios] = useState([]);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(false);

    // Fetch portfolios on mount
    useEffect(() => {
        fetchPortfolios();
    }, []);

    const fetchPortfolios = async () => {
        try {
            const response = await fetch('/api/portfolios');
            if (response.ok) {
                const data = await response.json();
                setPortfolios(data.portfolios || []);
            }
        } catch (err) {
            console.error("Failed to fetch portfolios", err);
        }
    };

    const handleNext = () => {
        if (validateStep(step)) {
            setStep(step + 1);
        }
    };

    const handleBack = () => {
        setStep(step - 1);
    };

    const validateStep = (currentStep) => {
        setError(null);
        if (currentStep === 1) {
            if (!formData.name.trim()) {
                setError("Strategy name is required");
                return false;
            }
        }
        if (currentStep === 3) {
            // Validate position sizing
            if (formData.position_sizing.method === 'fixed_pct' && !formData.position_sizing.fixed_position_pct) {
                setError("Fixed position percentage is required for this method");
                return false;
            }
            if (formData.position_sizing.method === 'kelly' && !formData.position_sizing.kelly_fraction) {
                setError("Kelly fraction is required for this method");
                return false;
            }
            if (!formData.position_sizing.max_position_pct) {
                setError("Max position percentage is required");
                return false;
            }
        }
        return true;
    };

    const handleSubmit = async () => {
        setLoading(true);
        setError(null);
        try {
            const payload = { ...formData };

            // Clean up exit conditions
            if (payload.exit_conditions.profit_target_pct)
                payload.exit_conditions.profit_target_pct = parseFloat(payload.exit_conditions.profit_target_pct);
            if (payload.exit_conditions.stop_loss_pct)
                payload.exit_conditions.stop_loss_pct = parseFloat(payload.exit_conditions.stop_loss_pct);

            // Clean up position sizing
            if (payload.position_sizing.max_position_pct)
                payload.position_sizing.max_position_pct = parseFloat(payload.position_sizing.max_position_pct);
            if (payload.position_sizing.min_position_value)
                payload.position_sizing.min_position_value = parseFloat(payload.position_sizing.min_position_value);
            if (payload.position_sizing.fixed_position_pct)
                payload.position_sizing.fixed_position_pct = parseFloat(payload.position_sizing.fixed_position_pct);
            if (payload.position_sizing.kelly_fraction)
                payload.position_sizing.kelly_fraction = parseFloat(payload.position_sizing.kelly_fraction);

            const url = mode === 'edit' ? `/api/strategies/${initialData.id}` : '/api/strategies';
            const method = mode === 'edit' ? 'PUT' : 'POST';

            const response = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.error || 'Failed to create strategy');
            }

            onSuccess(result);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-background/80 flex items-center justify-center z-50 p-4">
            <div className="bg-card border border-border rounded-xl w-full max-w-4xl h-[80vh] flex flex-col shadow-2xl overflow-hidden">

                {/* Header */}
                <div className="border-b border-border p-6 flex justify-between items-center bg-card">
                    <div>
                        <h2 className="text-xl font-bold text-foreground">{mode === 'edit' ? 'Strategy Configuration' : 'Create Strategy'}</h2>
                        <div className="flex gap-2 mt-2">
                            {[1, 2, 3, 4].map(s => (
                                <div
                                    key={s}
                                    className={`h-1.5 w-8 rounded-full transition-colors ${s <= step ? 'bg-primary' : 'bg-muted'
                                        }`}
                                />
                            ))}
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-muted rounded-full text-muted-foreground hover:text-foreground">
                        <X size={24} />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-8">
                    {error && (
                        <div className="mb-6 p-4 bg-destructive/10 border border-destructive/50 rounded-lg flex items-center gap-3 text-destructive">
                            <AlertCircle size={20} />
                            {error}
                        </div>
                    )}

                    {step === 1 && (
                        <div className="space-y-6 max-w-lg mx-auto">
                            <h3 className="text-2xl font-semibold text-foreground mb-2">The Basics</h3>
                            <div>
                                <label className="block text-muted-foreground mb-2 text-sm">Strategy Name</label>
                                <input
                                    type="text"
                                    value={formData.name}
                                    onChange={e => setFormData({ ...formData, name: e.target.value })}
                                    className="w-full bg-background border border-input rounded-lg p-3 text-foreground focus:border-primary focus:outline-none"
                                    placeholder="e.g., Aggressive Tech Growth"
                                    autoFocus
                                />
                            </div>
                            <div>
                                <label className="block text-muted-foreground mb-2 text-sm">Description</label>
                                <textarea
                                    value={formData.description}
                                    onChange={e => setFormData({ ...formData, description: e.target.value })}
                                    className="w-full bg-background border border-input rounded-lg p-3 text-foreground min-h-[120px] focus:border-primary focus:outline-none"
                                    placeholder="Describe the goal of this strategy..."
                                />
                            </div>
                        </div>
                    )}

                    {step === 2 && (
                        <div className="space-y-8">
                            <h3 className="text-2xl font-semibold text-foreground">Strategy Logic</h3>

                            {/* Analysis Mode (AI Deliberation) */}
                            <div className="bg-muted/50 rounded-xl p-6 border border-border">
                                <h4 className="font-medium text-foreground mb-4 flex items-center gap-2">
                                    <HelpCircle size={18} /> Analysis Mode
                                </h4>
                                <div className="flex items-start justify-between">
                                    <div>
                                        <label className="text-foreground font-medium block mb-1">
                                            Enable AI Deliberation
                                        </label>
                                        <p className="text-sm text-muted-foreground max-w-md">
                                            If enabled, AI agents (Lynch & Buffett) will hold a qualitative debate for each stock.
                                            <br />
                                            <span className="text-orange-400/80 inline-flex items-center gap-1 mt-1">
                                                <AlertCircle size={12} /> Slower execution (~30s per stock) but deeper insights.
                                            </span>
                                        </p>
                                    </div>
                                    <div className="flex items-center">
                                        <button
                                            onClick={() => setFormData({
                                                ...formData,
                                                conditions: { ...formData.conditions, require_thesis: !formData.conditions.require_thesis }
                                            })}
                                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${formData.conditions.require_thesis ? 'bg-primary' : 'bg-muted'
                                                }`}
                                        >
                                            <span
                                                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${formData.conditions.require_thesis ? 'translate-x-6' : 'translate-x-1'
                                                    }`}
                                            />
                                        </button>
                                    </div>
                                </div>
                            </div>

                            <div className="bg-muted/50 rounded-xl p-6 border border-border">
                                <div>
                                    <label className="block text-muted-foreground mb-2 text-sm">Consensus Mode</label>
                                    <select
                                        value={formData.consensus_mode}
                                        onChange={e => setFormData({ ...formData, consensus_mode: e.target.value })}
                                        className="w-full bg-background border border-input rounded-lg p-3 text-foreground"
                                    >
                                        <option value="both_agree">Strict Agreement (Both must buy)</option>
                                        <option value="weighted_confidence">Weighted Confidence</option>
                                        <option value="veto_power">Veto Power (Either can block)</option>
                                    </select>
                                    <p className="text-xs text-muted-foreground mt-2">
                                        Determines how Lynch and Buffett agents agree on a trade.
                                    </p>
                                </div>
                            </div>

                            {/* Exit Conditions */}
                            <div className="bg-muted/50 rounded-xl p-6 border border-border">
                                <h4 className="font-medium text-destructive mb-4">Exit Conditions</h4>
                                <div className="grid grid-cols-3 gap-6">
                                    <div>
                                        <label className="block text-muted-foreground mb-2 text-sm">Profit Target (%)</label>
                                        <input
                                            type="number"
                                            placeholder="e.g. 50"
                                            value={formData.exit_conditions.profit_target_pct}
                                            onChange={e => setFormData({
                                                ...formData,
                                                exit_conditions: { ...formData.exit_conditions, profit_target_pct: e.target.value }
                                            })}
                                            className="w-full bg-background border border-input rounded-lg p-3 text-foreground"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-muted-foreground mb-2 text-sm">Stop Loss (%)</label>
                                        <input
                                            type="number"
                                            placeholder="e.g. -15"
                                            value={formData.exit_conditions.stop_loss_pct}
                                            onChange={e => setFormData({
                                                ...formData,
                                                exit_conditions: { ...formData.exit_conditions, stop_loss_pct: e.target.value }
                                            })}
                                            className="w-full bg-background border border-input rounded-lg p-3 text-foreground"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-muted-foreground mb-2 text-sm">Max Hold Days</label>
                                        <input
                                            type="number"
                                            placeholder="e.g. 365"
                                            value={formData.exit_conditions.max_hold_days}
                                            onChange={e => setFormData({
                                                ...formData,
                                                exit_conditions: { ...formData.exit_conditions, max_hold_days: e.target.value }
                                            })}
                                            className="w-full bg-background border border-input rounded-lg p-3 text-foreground"
                                        />
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {step === 3 && (
                        <div className="space-y-8 max-w-xl mx-auto">
                            <h3 className="text-2xl font-semibold text-foreground">Execution</h3>

                            <div>
                                <label className="block text-muted-foreground mb-2 text-sm">Target Portfolio</label>
                                <select
                                    value={formData.portfolio_id}
                                    onChange={e => setFormData({ ...formData, portfolio_id: e.target.value })}
                                    className="w-full bg-background border border-input rounded-lg p-3 text-foreground"
                                >
                                    <option value="new">✨ Create New Portfolio ("{formData.name || 'Strategy Name'}")</option>
                                    {portfolios.map(p => (
                                        <option key={p.id} value={p.id}>{p.name} (${p.current_value?.toLocaleString()})</option>
                                    ))}
                                </select>
                                <div className="flex items-start gap-2 mt-3 text-xs text-primary bg-primary/10 p-3 rounded-lg border border-primary/20">
                                    <Info size={14} className="mt-0.5" />
                                    Creating a new portfolio allows you to track this strategy's performance in isolation.
                                </div>
                            </div>

                            <div className="bg-muted/50 rounded-xl p-6 border border-border space-y-6">
                                <div>
                                    <h4 className="font-medium text-foreground mb-4">Position Sizing</h4>
                                    <label className="block text-muted-foreground mb-2 text-sm">Method</label>
                                    <select
                                        value={formData.position_sizing.method}
                                        onChange={e => setFormData({
                                            ...formData,
                                            position_sizing: { ...formData.position_sizing, method: e.target.value }
                                        })}
                                        className="w-full bg-background border border-input rounded-lg p-3 text-foreground"
                                    >
                                        <option value="equal_weight">Equal Weight</option>
                                        <option value="conviction_weighted">Conviction Weighted</option>
                                        <option value="fixed_pct">Fixed Percentage</option>
                                        <option value="kelly">Kelly Criterion</option>
                                    </select>
                                    <p className="text-xs text-muted-foreground mt-2">
                                        {formData.position_sizing.method === 'equal_weight' && 'Divide available cash equally among all buys'}
                                        {formData.position_sizing.method === 'conviction_weighted' && 'Higher consensus score = larger position'}
                                        {formData.position_sizing.method === 'fixed_pct' && 'Fixed percentage of portfolio per position'}
                                        {formData.position_sizing.method === 'kelly' && 'Simplified Kelly criterion based on conviction'}
                                    </p>
                                </div>

                                {/* Method-specific fields */}
                                {formData.position_sizing.method === 'fixed_pct' && (
                                    <div>
                                        <label className="block text-muted-foreground mb-2 text-sm">Fixed Position Size (%)</label>
                                        <input
                                            type="number"
                                            step="0.1"
                                            min="0.1"
                                            max="100"
                                            placeholder="e.g. 5.0"
                                            value={formData.position_sizing.fixed_position_pct}
                                            onChange={e => setFormData({
                                                ...formData,
                                                position_sizing: { ...formData.position_sizing, fixed_position_pct: e.target.value }
                                            })}
                                            className="w-full bg-background border border-input rounded-lg p-3 text-foreground"
                                        />
                                        <p className="text-xs text-muted-foreground mt-2">
                                            Percentage of total portfolio to allocate per position
                                        </p>
                                    </div>
                                )}

                                {formData.position_sizing.method === 'kelly' && (
                                    <div>
                                        <label className="block text-muted-foreground mb-2 text-sm">Kelly Fraction</label>
                                        <input
                                            type="number"
                                            step="0.01"
                                            min="0.01"
                                            max="1.0"
                                            placeholder="e.g. 0.25"
                                            value={formData.position_sizing.kelly_fraction}
                                            onChange={e => setFormData({
                                                ...formData,
                                                position_sizing: { ...formData.position_sizing, kelly_fraction: e.target.value }
                                            })}
                                            className="w-full bg-background border border-input rounded-lg p-3 text-foreground"
                                        />
                                        <p className="text-xs text-muted-foreground mt-2">
                                            Fraction of Kelly bet (0.25 = quarter Kelly, conservative)
                                        </p>
                                    </div>
                                )}

                                {/* Common constraints */}
                                <div className="pt-4 border-t border-border">
                                    <h5 className="text-sm font-medium text-muted-foreground mb-4">Position Constraints</h5>
                                    <div className="grid grid-cols-2 gap-4">
                                        <div>
                                            <label className="block text-muted-foreground mb-2 text-sm">Max Position (%)</label>
                                            <input
                                                type="number"
                                                step="0.1"
                                                min="0.1"
                                                max="100"
                                                placeholder="e.g. 10.0"
                                                value={formData.position_sizing.max_position_pct}
                                                onChange={e => setFormData({
                                                    ...formData,
                                                    position_sizing: { ...formData.position_sizing, max_position_pct: e.target.value }
                                                })}
                                                className="w-full bg-background border border-input rounded-lg p-3 text-foreground"
                                            />
                                            <p className="text-xs text-muted-foreground mt-2">
                                                Never exceed this % of portfolio in one stock
                                            </p>
                                        </div>
                                        <div>
                                            <label className="block text-muted-foreground mb-2 text-sm">Min Position Value ($)</label>
                                            <input
                                                type="number"
                                                step="100"
                                                min="0"
                                                placeholder="e.g. 500"
                                                value={formData.position_sizing.min_position_value}
                                                onChange={e => setFormData({
                                                    ...formData,
                                                    position_sizing: { ...formData.position_sizing, min_position_value: e.target.value }
                                                })}
                                                className="w-full bg-background border border-input rounded-lg p-3 text-foreground"
                                            />
                                            <p className="text-xs text-muted-foreground mt-2">
                                                Skip positions below this dollar amount
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div>
                                <label className="block text-muted-foreground mb-2 text-sm">Schedule</label>
                                <select
                                    value={formData.schedule_cron}
                                    onChange={e => setFormData({ ...formData, schedule_cron: e.target.value })}
                                    className="w-full bg-background border border-input rounded-lg p-3 text-foreground"
                                >
                                    <option value="0 9 * * 1-5">Daily at Market Open (9:00 AM)</option>
                                    <option value="0 16 * * 1-5">Daily at Market Close (4:00 PM)</option>
                                    <option value="0 9 * * 1">Weekly (Mondays)</option>
                                </select>
                            </div>
                        </div>
                    )}

                    {step === 4 && (
                        <div className="max-w-xl mx-auto text-center">
                            <h3 className="text-2xl font-semibold text-foreground mb-6">Review Strategy</h3>

                            <div className="bg-muted/50 rounded-xl p-6 text-left space-y-4 mb-8">
                                <div className="flex justify-between border-b border-border pb-3">
                                    <span className="text-muted-foreground">Name</span>
                                    <span className="text-foreground font-medium">{formData.name}</span>
                                </div>
                                <div className="flex justify-between border-b border-border pb-3">
                                    <span className="text-muted-foreground">Consensus</span>
                                    <span className="text-foreground">{formData.consensus_mode}</span>
                                </div>
                                <div className="flex justify-between border-b border-border pb-3">
                                    <span className="text-muted-foreground">Analysis Mode</span>
                                    <span className={formData.conditions.require_thesis ? "text-primary" : "text-muted-foreground"}>
                                        {formData.conditions.require_thesis ? "AI Deliberation (Deep)" : "Heuristic Only (Fast)"}
                                    </span>
                                </div>
                                <div className="flex justify-between border-b border-border pb-3">
                                    <span className="text-muted-foreground">Exit Rules</span>
                                    <span className="text-foreground">
                                        {formData.exit_conditions.profit_target_pct ? `Target: +${formData.exit_conditions.profit_target_pct}%` : 'No Target'}
                                        {' / '}
                                        {formData.exit_conditions.stop_loss_pct ? `Stop: ${formData.exit_conditions.stop_loss_pct}%` : 'No Stop'}
                                    </span>
                                </div>
                                <div className="flex justify-between border-b border-border pb-3">
                                    <span className="text-muted-foreground">Position Sizing</span>
                                    <span className="text-foreground">
                                        {formData.position_sizing.method === 'equal_weight' && 'Equal Weight'}
                                        {formData.position_sizing.method === 'conviction_weighted' && 'Conviction Weighted'}
                                        {formData.position_sizing.method === 'fixed_pct' && `Fixed ${formData.position_sizing.fixed_position_pct || '?'}%`}
                                        {formData.position_sizing.method === 'kelly' && `Kelly (${formData.position_sizing.kelly_fraction || '?'})`}
                                    </span>
                                </div>
                                <div className="flex justify-between border-b border-border pb-3">
                                    <span className="text-muted-foreground">Position Limits</span>
                                    <span className="text-foreground text-sm">
                                        Max: {formData.position_sizing.max_position_pct || '?'}% / Min: ${formData.position_sizing.min_position_value || '?'}
                                    </span>
                                </div>
                                <div className="flex justify-between pb-1">
                                    <span className="text-muted-foreground">Portfolio</span>
                                    <span className="text-foreground">
                                        {formData.portfolio_id === 'new' ? 'Create New' : 'Existing'}
                                    </span>
                                </div>
                            </div>

                            <div className="flex items-center justify-center gap-2 text-primary bg-primary/10 p-4 rounded-lg border border-primary/30">
                                <Check size={20} />
                                <span>Ready to initialize strategy agent</span>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="border-t border-border p-6 bg-card flex justify-between">
                    <button
                        onClick={handleBack}
                        disabled={step === 1}
                        className={`px-6 py-2 rounded-lg flex items-center gap-2 ${step === 1 ? 'opacity-0' : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                            }`}
                    >
                        <ChevronLeft size={20} /> Back
                    </button>

                    {step < 4 ? (
                        <button
                            onClick={handleNext}
                            className="px-6 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg flex items-center gap-2 font-medium"
                        >
                            Next Step <ChevronRight size={20} />
                        </button>
                    ) : (
                        <button
                            onClick={handleSubmit}
                            disabled={loading}
                            className="px-8 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg flex items-center gap-2 font-medium shadow-lg shadow-primary/20"
                        >
                            {loading ? (mode === 'edit' ? 'Updating...' : 'Creating...') : (mode === 'edit' ? 'Update Strategy' : 'Create Strategy')} <Check size={20} />
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

export default StrategyWizard;
