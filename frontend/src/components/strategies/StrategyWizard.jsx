import React, { useState, useEffect } from 'react';
import {
    X, ChevronRight, ChevronLeft, Check, Plus, Trash2,
    HelpCircle, AlertCircle, Info, Eye
} from 'lucide-react';

/**
 * Strategy Wizard Component
 * A multi-step wizard for creating autonomous investment strategies.
 */
const StrategyWizard = ({ onClose, onSuccess, initialData = null, mode = 'create' }) => {
    const [step, setStep] = useState(1);
    const [selectedTemplate, setSelectedTemplate] = useState('');
    const [templates, setTemplates] = useState({});
    const [templatesLoaded, setTemplatesLoaded] = useState(false);

    // Fetch filter templates from backend
    useEffect(() => {
        fetch('/api/strategy-templates')
            .then(r => r.json())
            .then(data => {
                setTemplates(data.templates);
                setTemplatesLoaded(true);
            })
            .catch(err => {
                console.error("Failed to load templates", err);
                setTemplatesLoaded(true);
            });
    }, []);

    // Default values
    const defaults = {
        name: '',
        description: '',
        conditions: {
            filters: [],
            require_thesis: true,
            scoring_requirements: [
                { character: 'lynch', min_score: 60 },
                { character: 'buffett', min_score: 60 }
            ],
            addition_scoring_requirements: [
                { character: 'lynch', min_score: 70 },
                { character: 'buffett', min_score: 70 }
            ],
            thesis_verdict_required: ['BUY']
        },
        consensus_mode: 'both_agree',
        consensus_threshold: 70,
        veto_score_threshold: 30,
        exit_conditions: {
            profit_target_pct: '',
            stop_loss_pct: '',
            max_hold_days: '',
            score_degradation: {
                lynch_below: '',
                buffett_below: ''
            }
        },
        portfolio_selection: 'new',
        portfolio_id: 'new',
        new_portfolio_name: '',
        initial_cash: 100000,
        position_sizing: {
            method: 'equal_weight',
            max_position_pct: 10.0,
            max_positions: 50,
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
    const [previewing, setPreviewing] = useState(false);
    const [previewResults, setPreviewResults] = useState(null);

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
        if (currentStep === 6) {
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

            // Force new portfolio creation and manual schedule for new strategies
            if (mode !== 'edit') {
                payload.portfolio_id = 'new';
                payload.new_portfolio_name = formData.name;
            }
            payload.schedule_cron = null; // Always manual for now as per user request to remove schedule

            // Hard-code thesis verdict requirement if deliberation is enabled
            if (payload.conditions.require_thesis) {
                payload.conditions.thesis_verdict_required = ['BUY'];
            }

            // Clean up exit conditions
            if (payload.exit_conditions.profit_target_pct)
                payload.exit_conditions.profit_target_pct = parseFloat(payload.exit_conditions.profit_target_pct);
            if (payload.exit_conditions.stop_loss_pct)
                payload.exit_conditions.stop_loss_pct = parseFloat(payload.exit_conditions.stop_loss_pct);
            if (payload.exit_conditions.max_hold_days)
                payload.exit_conditions.max_hold_days = parseInt(payload.exit_conditions.max_hold_days);

            if (payload.veto_score_threshold)
                payload.veto_score_threshold = parseFloat(payload.veto_score_threshold);

            if (payload.consensus_threshold)
                payload.consensus_threshold = parseFloat(payload.consensus_threshold);

            // Clean up position sizing
            if (payload.position_sizing.max_position_pct)
                payload.position_sizing.max_position_pct = parseFloat(payload.position_sizing.max_position_pct);
            if (payload.position_sizing.min_position_value)
                payload.position_sizing.min_position_value = parseFloat(payload.position_sizing.min_position_value);
            if (payload.position_sizing.fixed_position_pct)
                payload.position_sizing.fixed_position_pct = parseFloat(payload.position_sizing.fixed_position_pct);
            if (payload.position_sizing.kelly_fraction)
                payload.position_sizing.kelly_fraction = parseFloat(payload.position_sizing.kelly_fraction);
            if (payload.position_sizing.max_positions)
                payload.position_sizing.max_positions = parseInt(payload.position_sizing.max_positions);

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

    const handleTemplateSelect = (e) => {
        const templateKey = e.target.value;
        setSelectedTemplate(templateKey);

        if (templateKey === '') {
            // "Custom" selected - clear filters
            setFormData({
                ...formData,
                conditions: { ...formData.conditions, filters: [] }
            });
        } else {
            // Apply template filters
            const template = templates[templateKey];
            if (template) {
                setFormData({
                    ...formData,
                    conditions: { ...formData.conditions, filters: [...template.filters] }
                });
            }
        }
    };

    const handlePreview = async () => {
        setPreviewing(true);
        setError(null);
        try {
            const payload = {
                conditions: formData.conditions
            };

            const response = await fetch('/api/strategies/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.error || 'Preview failed');
            }

            setPreviewResults(result);
        } catch (err) {
            setError(err.message);
        } finally {
            setPreviewing(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-background/80 flex items-center justify-center z-50 p-4">
            <div className="bg-card border border-border rounded-xl w-full max-w-4xl h-[80vh] flex flex-col shadow-2xl overflow-hidden">

                {/* Header */}
                <div className="border-b border-border p-6 flex justify-between items-center bg-card">
                    <div>
                        <h2 className="text-xl font-bold text-foreground">{mode === 'edit' ? 'Strategy Configuration' : 'Create Autonomous Portfolio'}</h2>
                        <div className="flex gap-2 mt-2">
                            {[1, 2, 3, 4, 5, 6, 7].map(s => (
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

                            <div>
                                <label className="block text-muted-foreground mb-2 text-sm">Initial Cash ($)</label>
                                <input
                                    type="number"
                                    step="1000"
                                    min="1000"
                                    value={formData.initial_cash || 100000}
                                    onChange={e => setFormData({ ...formData, initial_cash: parseInt(e.target.value) || 100000 })}
                                    className="w-full bg-background border border-input rounded-lg p-3 text-foreground focus:border-primary focus:outline-none"
                                />
                                <p className="text-xs text-muted-foreground mt-1">
                                    Paper trading starting balance
                                </p>
                            </div>
                        </div>
                    )}

                    {step === 2 && (
                        <div className="space-y-8">
                            <h3 className="text-2xl font-semibold text-foreground">Universe Filtering</h3>

                            {/* Universe Filters */}
                            <div className="bg-muted/50 rounded-xl p-6 border border-border">
                                <h4 className="font-medium text-foreground mb-4">Stock Screening Filters</h4>

                                {/* Template Selector */}
                                <div className="mb-6">
                                    <label className="block text-muted-foreground mb-2 text-sm">
                                        Filter Template (Optional)
                                    </label>
                                    <select
                                        value={selectedTemplate}
                                        onChange={handleTemplateSelect}
                                        className="w-full bg-background border border-input rounded-lg p-3 text-foreground focus:border-primary focus:outline-none"
                                    >
                                        <option value="">Custom (Build Your Own)</option>
                                        <option value="beaten_down_large_caps">Beaten Down Large Caps</option>
                                        <option value="value_stocks">Value Stocks</option>
                                        <option value="growth_at_reasonable_price">Growth at Reasonable Price (GARP)</option>
                                        <option value="low_debt_stable">Low Debt, Stable Companies</option>
                                        <option value="small_cap_growth">Small Cap Growth</option>
                                        <option value="dividend_value">Dividend Value Plays</option>
                                    </select>

                                    {selectedTemplate && templates[selectedTemplate] && (
                                        <div className="mt-2 p-3 bg-primary/5 border border-primary/20 rounded-lg">
                                            <p className="text-xs text-muted-foreground">
                                                {templates[selectedTemplate].description}
                                            </p>
                                        </div>
                                    )}
                                </div>

                                <p className="text-sm text-muted-foreground mb-4">
                                    Define which stocks to evaluate. Leave empty to screen all stocks.
                                </p>

                                {formData.conditions.filters && formData.conditions.filters.length > 0 && (
                                    <div className="space-y-3 mb-4">
                                        {formData.conditions.filters.map((filter, idx) => (
                                            <div key={idx} className="flex gap-3 items-start bg-background p-3 rounded-lg border border-input">
                                                {/* Field Selection */}
                                                <select
                                                    value={filter.field || ''}
                                                    onChange={e => {
                                                        const newFilters = [...formData.conditions.filters];
                                                        newFilters[idx] = { ...newFilters[idx], field: e.target.value };
                                                        setFormData({
                                                            ...formData,
                                                            conditions: { ...formData.conditions, filters: newFilters }
                                                        });
                                                    }}
                                                    className="flex-1 bg-background border border-input rounded-lg p-2 text-sm text-foreground focus:border-primary focus:outline-none"
                                                >
                                                    <option value="">Select field...</option>
                                                    <option value="price_vs_52wk_high">Price vs 52-Week High (%)</option>
                                                    <option value="market_cap">Market Cap ($)</option>
                                                    <option value="pe_ratio">P/E Ratio</option>
                                                    <option value="peg_ratio">PEG Ratio</option>
                                                    <option value="dividend_yield">Dividend Yield (%)</option>
                                                    <option value="debt_to_equity">Debt/Equity</option>
                                                    <option value="price">Price ($)</option>
                                                    <option value="sector">Sector</option>
                                                </select>

                                                {/* Operator Selection */}
                                                <select
                                                    value={filter.operator || ''}
                                                    onChange={e => {
                                                        const newFilters = [...formData.conditions.filters];
                                                        newFilters[idx] = { ...newFilters[idx], operator: e.target.value };
                                                        setFormData({
                                                            ...formData,
                                                            conditions: { ...formData.conditions, filters: newFilters }
                                                        });
                                                    }}
                                                    className="w-24 bg-background border border-input rounded-lg p-2 text-sm text-foreground focus:border-primary focus:outline-none"
                                                >
                                                    <option value="">Op...</option>
                                                    {filter.field === 'sector' ? (
                                                        <>
                                                            <option value="==">=</option>
                                                            <option value="!=">≠</option>
                                                        </>
                                                    ) : (
                                                        <>
                                                            <option value="<">&lt;</option>
                                                            <option value=">">&gt;</option>
                                                            <option value="<=">≤</option>
                                                            <option value=">=">≥</option>
                                                            <option value="==">=</option>
                                                            <option value="!=">≠</option>
                                                        </>
                                                    )}
                                                </select>

                                                {/* Value Input */}
                                                {filter.field === 'sector' ? (
                                                    <input
                                                        type="text"
                                                        placeholder="e.g. Technology"
                                                        value={filter.value || ''}
                                                        onChange={e => {
                                                            const newFilters = [...formData.conditions.filters];
                                                            newFilters[idx] = { ...newFilters[idx], value: e.target.value };
                                                            setFormData({
                                                                ...formData,
                                                                conditions: { ...formData.conditions, filters: newFilters }
                                                            });
                                                        }}
                                                        className="flex-1 bg-background border border-input rounded-lg p-2 text-sm text-foreground focus:border-primary focus:outline-none"
                                                    />
                                                ) : (
                                                    <input
                                                        type="number"
                                                        step={filter.field === 'market_cap' ? '1000000000' : filter.field === 'price' ? '1' : '0.1'}
                                                        placeholder={
                                                            filter.field === 'price_vs_52wk_high' ? 'e.g. -20' :
                                                                filter.field === 'market_cap' ? 'e.g. 10000000000' :
                                                                    filter.field === 'price' ? 'e.g. 50' :
                                                                        'e.g. 1.5'
                                                        }
                                                        value={filter.value === undefined ? '' : filter.value}
                                                        onChange={e => {
                                                            const newFilters = [...formData.conditions.filters];
                                                            newFilters[idx] = { ...newFilters[idx], value: parseFloat(e.target.value) || '' };
                                                            setFormData({
                                                                ...formData,
                                                                conditions: { ...formData.conditions, filters: newFilters }
                                                            });
                                                        }}
                                                        className="flex-1 bg-background border border-input rounded-lg p-2 text-sm text-foreground focus:border-primary focus:outline-none"
                                                    />
                                                )}

                                                {/* Remove Button */}
                                                <button
                                                    onClick={() => {
                                                        const newFilters = formData.conditions.filters.filter((_, i) => i !== idx);
                                                        setFormData({
                                                            ...formData,
                                                            conditions: { ...formData.conditions, filters: newFilters }
                                                        });
                                                    }}
                                                    className="p-2 text-destructive hover:bg-destructive/10 rounded-lg"
                                                    title="Remove filter"
                                                >
                                                    <Trash2 size={16} />
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                <button
                                    onClick={() => {
                                        setFormData({
                                            ...formData,
                                            conditions: {
                                                ...formData.conditions,
                                                filters: [...(formData.conditions.filters || []), { field: '', operator: '', value: '' }]
                                            }
                                        });
                                    }}
                                    className="px-4 py-2 bg-primary/10 hover:bg-primary/20 text-primary rounded-lg flex items-center gap-2 text-sm font-medium transition-colors"
                                >
                                    <Plus size={16} /> Add Filter
                                </button>
                            </div>
                        </div>
                    )}

                    {step === 3 && (
                        <div className="space-y-8">
                            <h3 className="text-2xl font-semibold text-foreground">Scoring</h3>

                            {/* Scoring Requirements */}
                            <div className="bg-muted/50 rounded-xl p-6 border border-border">
                                <h4 className="font-medium text-foreground mb-4">Minimum Score Thresholds</h4>
                                <p className="text-sm text-muted-foreground mb-6">
                                    Only stocks scoring above these thresholds will proceed to deliberation.
                                </p>

                                <div className="space-y-6">
                                    <div>
                                        <label className="flex justify-between mb-3">
                                            <span className="text-sm text-foreground">Lynch Minimum Score</span>
                                            <span className="font-mono text-sm text-primary font-medium">
                                                {formData.conditions.scoring_requirements?.find(r => r.character === 'lynch')?.min_score || 60}
                                            </span>
                                        </label>
                                        <input
                                            type="range"
                                            min="0"
                                            max="100"
                                            step="5"
                                            value={formData.conditions.scoring_requirements?.find(r => r.character === 'lynch')?.min_score || 60}
                                            onChange={e => {
                                                const newReqs = [...(formData.conditions.scoring_requirements || [])];
                                                const lynchIdx = newReqs.findIndex(r => r.character === 'lynch');
                                                if (lynchIdx >= 0) {
                                                    newReqs[lynchIdx] = { character: 'lynch', min_score: parseInt(e.target.value) };
                                                } else {
                                                    newReqs.push({ character: 'lynch', min_score: parseInt(e.target.value) });
                                                }
                                                setFormData({
                                                    ...formData,
                                                    conditions: { ...formData.conditions, scoring_requirements: newReqs }
                                                });
                                            }}
                                            className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                                        />
                                        <div className="flex justify-between text-xs text-muted-foreground mt-1">
                                            <span>0 (Any)</span>
                                            <span>100 (Perfect)</span>
                                        </div>
                                    </div>

                                    <div>
                                        <label className="flex justify-between mb-3">
                                            <span className="text-sm text-foreground">Buffett Minimum Score</span>
                                            <span className="font-mono text-sm text-primary font-medium">
                                                {formData.conditions.scoring_requirements?.find(r => r.character === 'buffett')?.min_score || 60}
                                            </span>
                                        </label>
                                        <input
                                            type="range"
                                            min="0"
                                            max="100"
                                            step="5"
                                            value={formData.conditions.scoring_requirements?.find(r => r.character === 'buffett')?.min_score || 60}
                                            onChange={e => {
                                                const newReqs = [...(formData.conditions.scoring_requirements || [])];
                                                const buffettIdx = newReqs.findIndex(r => r.character === 'buffett');
                                                if (buffettIdx >= 0) {
                                                    newReqs[buffettIdx] = { character: 'buffett', min_score: parseInt(e.target.value) };
                                                } else {
                                                    newReqs.push({ character: 'buffett', min_score: parseInt(e.target.value) });
                                                }
                                                setFormData({
                                                    ...formData,
                                                    conditions: { ...formData.conditions, scoring_requirements: newReqs }
                                                });
                                            }}
                                            className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                                        />
                                        <div className="flex justify-between text-xs text-muted-foreground mt-1">
                                            <span>0 (Any)</span>
                                            <span>100 (Perfect)</span>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Addition Thresholds */}
                            <div className="bg-muted/50 rounded-xl p-6 border border-border mt-6">
                                <h4 className="font-medium text-foreground mb-4 flex items-center gap-2">
                                    <Plus size={18} /> Position Addition Thresholds
                                </h4>
                                <p className="text-sm text-muted-foreground mb-6">
                                    Higher thresholds required when adding to or rebalancing an existing position.
                                </p>

                                <div className="space-y-6">
                                    <div>
                                        <label className="flex justify-between mb-3">
                                            <span className="text-sm text-foreground">Lynch Addition Score</span>
                                            <span className="font-mono text-sm text-primary font-medium">
                                                {formData.conditions.addition_scoring_requirements?.find(r => r.character === 'lynch')?.min_score || 70}
                                            </span>
                                        </label>
                                        <input
                                            type="range"
                                            min="0"
                                            max="100"
                                            step="5"
                                            value={formData.conditions.addition_scoring_requirements?.find(r => r.character === 'lynch')?.min_score || 70}
                                            onChange={e => {
                                                const newReqs = [...(formData.conditions.addition_scoring_requirements || [])];
                                                const lynchIdx = newReqs.findIndex(r => r.character === 'lynch');
                                                const score = parseInt(e.target.value);
                                                if (lynchIdx >= 0) {
                                                    newReqs[lynchIdx] = { ...newReqs[lynchIdx], min_score: score };
                                                } else {
                                                    newReqs.push({ character: 'lynch', min_score: score });
                                                }
                                                setFormData({
                                                    ...formData,
                                                    conditions: { ...formData.conditions, addition_scoring_requirements: newReqs }
                                                });
                                            }}
                                            className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                                        />
                                    </div>

                                    <div>
                                        <label className="flex justify-between mb-3">
                                            <span className="text-sm text-foreground">Buffett Addition Score</span>
                                            <span className="font-mono text-sm text-primary font-medium">
                                                {formData.conditions.addition_scoring_requirements?.find(r => r.character === 'buffett')?.min_score || 70}
                                            </span>
                                        </label>
                                        <input
                                            type="range"
                                            min="0"
                                            max="100"
                                            step="5"
                                            value={formData.conditions.addition_scoring_requirements?.find(r => r.character === 'buffett')?.min_score || 70}
                                            onChange={e => {
                                                const newReqs = [...(formData.conditions.addition_scoring_requirements || [])];
                                                const buffettIdx = newReqs.findIndex(r => r.character === 'buffett');
                                                const score = parseInt(e.target.value);
                                                if (buffettIdx >= 0) {
                                                    newReqs[buffettIdx] = { ...newReqs[buffettIdx], min_score: score };
                                                } else {
                                                    newReqs.push({ character: 'buffett', min_score: score });
                                                }
                                                setFormData({
                                                    ...formData,
                                                    conditions: { ...formData.conditions, addition_scoring_requirements: newReqs }
                                                });
                                            }}
                                            className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                                        />
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {step === 4 && (
                        <div className="space-y-8">
                            <h3 className="text-2xl font-semibold text-foreground">Thesis & Deliberation</h3>

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

                                <div className="mt-6 pt-6 border-t border-border">
                                    <label className="block text-muted-foreground mb-2 text-sm">Consensus Mode</label>
                                    <select
                                        value={formData.consensus_mode}
                                        onChange={e => setFormData({ ...formData, consensus_mode: e.target.value })}
                                        className="w-full bg-background border border-input rounded-lg p-3 text-foreground focus:border-primary focus:outline-none"
                                    >
                                        <option value="both_agree">Strict Agreement (Both must buy)</option>
                                        <option value="weighted_confidence">Weighted Confidence</option>
                                        <option value="veto_power">Veto Power (Either can block)</option>
                                    </select>
                                    <p className="text-xs text-muted-foreground mt-2">
                                        Determines how Lynch and Buffett agents agree on a trade.
                                    </p>

                                    {formData.consensus_mode === 'weighted_confidence' && (
                                        <div className="mt-6 pt-6 border-t border-border">
                                            <label className="block text-muted-foreground mb-2 text-sm">Consensus Threshold</label>
                                            <input
                                                type="number"
                                                min="0"
                                                max="100"
                                                step="5"
                                                value={formData.consensus_threshold || 70}
                                                onChange={e => setFormData({ ...formData, consensus_threshold: parseInt(e.target.value) || 70 })}
                                                className="w-full bg-background border border-input rounded-lg p-3 text-foreground focus:border-primary focus:outline-none"
                                            />
                                            <p className="text-xs text-muted-foreground mt-2">
                                                Combined score needed for WATCH verdict (80+ = BUY)
                                            </p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    {step === 5 && (
                        <div className="space-y-8">
                            <h3 className="text-2xl font-semibold text-foreground">Exit Conditions</h3>

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
                                            className="w-full bg-background border border-input rounded-lg p-3 text-foreground focus:border-primary focus:outline-none"
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
                                            className="w-full bg-background border border-input rounded-lg p-3 text-foreground focus:border-primary focus:outline-none"
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
                                            className="w-full bg-background border border-input rounded-lg p-3 text-foreground focus:border-primary focus:outline-none"
                                        />
                                    </div>
                                </div>

                                <div className="pt-6 border-t border-border">
                                    <h5 className="text-sm font-medium text-foreground mb-3">Score Degradation Triggers</h5>
                                    <p className="text-xs text-muted-foreground mb-4">
                                        Sell if re-evaluated scores fall below these thresholds.
                                    </p>
                                    <div className="grid grid-cols-2 gap-6">
                                        <div>
                                            <label className="block text-muted-foreground mb-2 text-sm">Lynch Score Below</label>
                                            <input
                                                type="number"
                                                min="0"
                                                max="100"
                                                step="5"
                                                placeholder="e.g. 40"
                                                value={formData.exit_conditions.score_degradation?.lynch_below || ''}
                                                onChange={e => setFormData({
                                                    ...formData,
                                                    exit_conditions: {
                                                        ...formData.exit_conditions,
                                                        score_degradation: {
                                                            ...formData.exit_conditions.score_degradation,
                                                            lynch_below: e.target.value ? parseInt(e.target.value) : ''
                                                        }
                                                    }
                                                })}
                                                className="w-full bg-background border border-input rounded-lg p-3 text-foreground focus:border-primary focus:outline-none"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-muted-foreground mb-2 text-sm">Buffett Score Below</label>
                                            <input
                                                type="number"
                                                min="0"
                                                max="100"
                                                step="5"
                                                placeholder="e.g. 40"
                                                value={formData.exit_conditions.score_degradation?.buffett_below || ''}
                                                onChange={e => setFormData({
                                                    ...formData,
                                                    exit_conditions: {
                                                        ...formData.exit_conditions,
                                                        score_degradation: {
                                                            ...formData.exit_conditions.score_degradation,
                                                            buffett_below: e.target.value ? parseInt(e.target.value) : ''
                                                        }
                                                    }
                                                })}
                                                className="w-full bg-background border border-input rounded-lg p-3 text-foreground focus:border-primary focus:outline-none"
                                            />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {step === 6 && (
                        <div className="space-y-8 max-w-xl mx-auto">
                            <h3 className="text-2xl font-semibold text-foreground">Position Sizing</h3>

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
                                        className="w-full bg-background border border-input rounded-lg p-3 text-foreground focus:border-primary focus:outline-none"
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
                                            className="w-full bg-background border border-input rounded-lg p-3 text-foreground focus:border-primary focus:outline-none"
                                        />
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
                                            className="w-full bg-background border border-input rounded-lg p-3 text-foreground focus:border-primary focus:outline-none"
                                        />
                                    </div>
                                )}

                                <div>
                                    <h4 className="font-medium text-foreground mb-4">Constraints</h4>
                                    <div className="grid grid-cols-2 gap-4">
                                        <div>
                                            <label className="block text-muted-foreground mb-2 text-sm">Max Position (%)</label>
                                            <input
                                                type="number"
                                                step="0.1"
                                                placeholder="e.g. 10.0"
                                                value={formData.position_sizing.max_position_pct}
                                                onChange={e => setFormData({
                                                    ...formData,
                                                    position_sizing: { ...formData.position_sizing, max_position_pct: e.target.value }
                                                })}
                                                className="w-full bg-background border border-input rounded-lg p-3 text-foreground focus:border-primary focus:outline-none"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-muted-foreground mb-2 text-sm">Max Count</label>
                                            <input
                                                type="number"
                                                placeholder="e.g. 20"
                                                value={formData.position_sizing.max_positions}
                                                onChange={e => setFormData({
                                                    ...formData,
                                                    position_sizing: { ...formData.position_sizing, max_positions: e.target.value }
                                                })}
                                                className="w-full bg-background border border-input rounded-lg p-3 text-foreground focus:border-primary focus:outline-none"
                                            />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {step === 7 && (
                        <div className="max-w-xl mx-auto text-center">
                            <h3 className="text-2xl font-semibold text-foreground mb-6">Review Strategy</h3>

                            <div className="bg-muted/50 rounded-xl p-6 text-left space-y-4 mb-8">
                                <div className="flex justify-between border-b border-border pb-3">
                                    <span className="text-muted-foreground">Name</span>
                                    <span className="text-foreground font-medium">{formData.name}</span>
                                </div>
                                <div className="flex justify-between border-b border-border pb-3">
                                    <span className="text-muted-foreground">Initial Cash</span>
                                    <span className="text-foreground font-medium">${formData.initial_cash?.toLocaleString()}</span>
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
                                <div className="flex justify-between">
                                    <span className="text-muted-foreground">Position Sizing</span>
                                    <span className="text-foreground">
                                        {formData.position_sizing.method === 'equal_weight' && 'Equal Weight'}
                                        {formData.position_sizing.method === 'conviction_weighted' && 'Conviction Weighted'}
                                        {formData.position_sizing.method === 'fixed_pct' && `Fixed ${formData.position_sizing.fixed_position_pct}%`}
                                        {formData.position_sizing.method === 'kelly' && `Kelly (${formData.position_sizing.kelly_fraction})`}
                                    </span>
                                </div>
                            </div>

                            <div className="mb-6">
                                <button
                                    onClick={handlePreview}
                                    disabled={previewing}
                                    className="w-full px-6 py-3 bg-muted hover:bg-muted/80 text-foreground rounded-lg flex items-center justify-center gap-2 font-medium border border-border"
                                >
                                    <Eye size={20} />
                                    {previewing ? 'Running Preview...' : 'Preview Stock Selection'}
                                </button>

                                {previewResults && (
                                    <div className="mt-4 bg-muted/50 rounded-lg p-4 text-left">
                                        <h4 className="text-sm font-semibold text-foreground mb-3">
                                            Preview Results: {previewResults.candidates?.length || 0} stocks
                                        </h4>
                                        {previewResults.candidates && previewResults.candidates.length > 0 ? (
                                            <div className="space-y-2 max-h-64 overflow-y-auto">
                                                {previewResults.candidates.map((stock, idx) => (
                                                    <div key={idx} className="flex justify-between items-center p-2 bg-background rounded border border-border">
                                                        <span className="font-medium text-foreground">{stock.symbol}</span>
                                                        <div className="flex gap-3 text-sm">
                                                            <span className="text-muted-foreground">Lynch: {stock.lynch_score}</span>
                                                            <span className="text-muted-foreground">Buffett: {stock.buffett_score}</span>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        ) : (
                                            <p className="text-sm text-muted-foreground">No stocks match.</p>
                                        )}
                                    </div>
                                )}
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

                    {step < 7 ? (
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
