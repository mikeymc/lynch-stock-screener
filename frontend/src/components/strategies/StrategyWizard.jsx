import React, { useState, useEffect } from 'react';
import {
    X, ChevronRight, ChevronLeft, Check, Plus, Trash2,
    HelpCircle, AlertCircle, Info
} from 'lucide-react';

/**
 * Strategy Wizard Component
 * A multi-step wizard for creating autonomous investment strategies.
 */
const StrategyWizard = ({ onClose, onSuccess }) => {
    const [step, setStep] = useState(1);
    const [formData, setFormData] = useState({
        name: '',
        description: '',
        // Logic
        conditions: {
            filters: []
        },
        consensus_mode: 'both_agree',
        consensus_threshold: 70,
        exit_conditions: {
            profit_target_pct: '',
            stop_loss_pct: '',
            max_hold_days: ''
        },
        // Execution
        portfolio_selection: 'new',
        portfolio_id: 'new', // 'new' or integer
        position_sizing: {
            method: 'equal_weight'
        },
        schedule_cron: '0 9 * * 1-5'
    });

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
        // Add more validation as needed
        return true;
    };

    const handleSubmit = async () => {
        setLoading(true);
        setError(null);
        try {
            const payload = { ...formData };

            // Clean up numbers
            if (payload.exit_conditions.profit_target_pct)
                payload.exit_conditions.profit_target_pct = parseFloat(payload.exit_conditions.profit_target_pct);
            if (payload.exit_conditions.stop_loss_pct)
                payload.exit_conditions.stop_loss_pct = parseFloat(payload.exit_conditions.stop_loss_pct);

            const response = await fetch('/api/strategies', {
                method: 'POST',
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
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
            <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-4xl h-[80vh] flex flex-col shadow-2xl overflow-hidden">

                {/* Header */}
                <div className="border-b border-slate-700 p-6 flex justify-between items-center bg-slate-900">
                    <div>
                        <h2 className="text-xl font-bold text-white">Create Strategy</h2>
                        <div className="flex gap-2 mt-2">
                            {[1, 2, 3, 4].map(s => (
                                <div
                                    key={s}
                                    className={`h-1.5 w-8 rounded-full transition-colors ${s <= step ? 'bg-blue-500' : 'bg-slate-700'
                                        }`}
                                />
                            ))}
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-full text-slate-400 hover:text-white">
                        <X size={24} />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-8">
                    {error && (
                        <div className="mb-6 p-4 bg-red-900/30 border border-red-800 rounded-lg flex items-center gap-3 text-red-200">
                            <AlertCircle size={20} />
                            {error}
                        </div>
                    )}

                    {step === 1 && (
                        <div className="space-y-6 max-w-lg mx-auto">
                            <h3 className="text-2xl font-semibold text-white mb-2">The Basics</h3>
                            <div>
                                <label className="block text-slate-400 mb-2 text-sm">Strategy Name</label>
                                <input
                                    type="text"
                                    value={formData.name}
                                    onChange={e => setFormData({ ...formData, name: e.target.value })}
                                    className="w-full bg-slate-800 border border-slate-700 rounded-lg p-3 text-white focus:border-blue-500 focus:outline-none"
                                    placeholder="e.g., Aggressive Tech Growth"
                                    autoFocus
                                />
                            </div>
                            <div>
                                <label className="block text-slate-400 mb-2 text-sm">Description</label>
                                <textarea
                                    value={formData.description}
                                    onChange={e => setFormData({ ...formData, description: e.target.value })}
                                    className="w-full bg-slate-800 border border-slate-700 rounded-lg p-3 text-white min-h-[120px] focus:border-blue-500 focus:outline-none"
                                    placeholder="Describe the goal of this strategy..."
                                />
                            </div>
                        </div>
                    )}

                    {step === 2 && (
                        <div className="space-y-8">
                            <h3 className="text-2xl font-semibold text-white">Strategy Logic</h3>

                            {/* Conditions Builder Placeholder */}
                            <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700">
                                <h4 className="font-medium text-blue-400 mb-4 flex items-center gap-2">
                                    <Check size={18} /> Screening Conditions
                                </h4>
                                <div className="text-center py-8 text-slate-500 border border-dashed border-slate-700 rounded-lg">
                                    Condition Builder Coming Soon (Defaulting to All Screened Stocks)
                                </div>
                            </div>

                            {/* Consensus Settings */}
                            <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700 grid grid-cols-2 gap-8">
                                <div>
                                    <label className="block text-slate-400 mb-2 text-sm">Consensus Mode</label>
                                    <select
                                        value={formData.consensus_mode}
                                        onChange={e => setFormData({ ...formData, consensus_mode: e.target.value })}
                                        className="w-full bg-slate-900 border border-slate-700 rounded-lg p-3 text-white"
                                    >
                                        <option value="both_agree">Strict Agreement (Both must buy)</option>
                                        <option value="weighted_confidence">Weighted Confidence</option>
                                        <option value="veto_power">Veto Power (Either can block)</option>
                                    </select>
                                    <p className="text-xs text-slate-500 mt-2">
                                        Determines how Lynch and Buffett agents agree on a trade.
                                    </p>
                                </div>
                                <div>
                                    <label className="block text-slate-400 mb-2 text-sm">
                                        Consensus Threshold ({formData.consensus_threshold})
                                    </label>
                                    <input
                                        type="range"
                                        min="50" max="90" step="5"
                                        value={formData.consensus_threshold}
                                        onChange={e => setFormData({ ...formData, consensus_threshold: parseInt(e.target.value) })}
                                        className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer"
                                    />
                                </div>
                            </div>

                            {/* Exit Conditions */}
                            <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700">
                                <h4 className="font-medium text-red-400 mb-4">Exit Conditions</h4>
                                <div className="grid grid-cols-3 gap-6">
                                    <div>
                                        <label className="block text-slate-400 mb-2 text-sm">Profit Target (%)</label>
                                        <input
                                            type="number"
                                            placeholder="e.g. 50"
                                            value={formData.exit_conditions.profit_target_pct}
                                            onChange={e => setFormData({
                                                ...formData,
                                                exit_conditions: { ...formData.exit_conditions, profit_target_pct: e.target.value }
                                            })}
                                            className="w-full bg-slate-900 border border-slate-700 rounded-lg p-3 text-white"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-slate-400 mb-2 text-sm">Stop Loss (%)</label>
                                        <input
                                            type="number"
                                            placeholder="e.g. -15"
                                            value={formData.exit_conditions.stop_loss_pct}
                                            onChange={e => setFormData({
                                                ...formData,
                                                exit_conditions: { ...formData.exit_conditions, stop_loss_pct: e.target.value }
                                            })}
                                            className="w-full bg-slate-900 border border-slate-700 rounded-lg p-3 text-white"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-slate-400 mb-2 text-sm">Max Hold Days</label>
                                        <input
                                            type="number"
                                            placeholder="e.g. 365"
                                            value={formData.exit_conditions.max_hold_days}
                                            onChange={e => setFormData({
                                                ...formData,
                                                exit_conditions: { ...formData.exit_conditions, max_hold_days: e.target.value }
                                            })}
                                            className="w-full bg-slate-900 border border-slate-700 rounded-lg p-3 text-white"
                                        />
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {step === 3 && (
                        <div className="space-y-8 max-w-xl mx-auto">
                            <h3 className="text-2xl font-semibold text-white">Execution</h3>

                            <div>
                                <label className="block text-slate-400 mb-2 text-sm">Target Portfolio</label>
                                <select
                                    value={formData.portfolio_id}
                                    onChange={e => setFormData({ ...formData, portfolio_id: e.target.value })}
                                    className="w-full bg-slate-800 border border-slate-700 rounded-lg p-3 text-white"
                                >
                                    <option value="new">✨ Create New Portfolio ("{formData.name || 'Strategy Name'}")</option>
                                    {portfolios.map(p => (
                                        <option key={p.id} value={p.id}>{p.name} (${p.current_value?.toLocaleString()})</option>
                                    ))}
                                </select>
                                <div className="flex items-start gap-2 mt-3 text-xs text-blue-400 bg-blue-900/20 p-3 rounded-lg border border-blue-900/50">
                                    <Info size={14} className="mt-0.5" />
                                    Creating a new portfolio allows you to track this strategy's performance in isolation.
                                </div>
                            </div>

                            <div>
                                <label className="block text-slate-400 mb-2 text-sm">Position Sizing</label>
                                <select
                                    value={formData.position_sizing.method}
                                    onChange={e => setFormData({
                                        ...formData,
                                        position_sizing: { ...formData.position_sizing, method: e.target.value }
                                    })}
                                    className="w-full bg-slate-800 border border-slate-700 rounded-lg p-3 text-white"
                                >
                                    <option value="equal_weight">Equal Weight (Divided evenly)</option>
                                    <option value="conviction_weighted">Conviction Weighted (Higher score = More capital)</option>
                                </select>
                            </div>

                            <div>
                                <label className="block text-slate-400 mb-2 text-sm">Schedule</label>
                                <select
                                    value={formData.schedule_cron}
                                    onChange={e => setFormData({ ...formData, schedule_cron: e.target.value })}
                                    className="w-full bg-slate-800 border border-slate-700 rounded-lg p-3 text-white"
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
                            <h3 className="text-2xl font-semibold text-white mb-6">Review Strategy</h3>

                            <div className="bg-slate-800 rounded-xl p-6 text-left space-y-4 mb-8">
                                <div className="flex justify-between border-b border-slate-700 pb-3">
                                    <span className="text-slate-400">Name</span>
                                    <span className="text-white font-medium">{formData.name}</span>
                                </div>
                                <div className="flex justify-between border-b border-slate-700 pb-3">
                                    <span className="text-slate-400">Consensus</span>
                                    <span className="text-white">{formData.consensus_mode} ({formData.consensus_threshold})</span>
                                </div>
                                <div className="flex justify-between border-b border-slate-700 pb-3">
                                    <span className="text-slate-400">Exit Rules</span>
                                    <span className="text-white">
                                        {formData.exit_conditions.profit_target_pct ? `Target: +${formData.exit_conditions.profit_target_pct}%` : 'No Target'}
                                        {' / '}
                                        {formData.exit_conditions.stop_loss_pct ? `Stop: ${formData.exit_conditions.stop_loss_pct}%` : 'No Stop'}
                                    </span>
                                </div>
                                <div className="flex justify-between pb-1">
                                    <span className="text-slate-400">Portfolio</span>
                                    <span className="text-white">
                                        {formData.portfolio_id === 'new' ? 'Create New' : 'Existing'}
                                    </span>
                                </div>
                            </div>

                            <div className="flex items-center justify-center gap-2 text-emerald-400 bg-emerald-900/10 p-4 rounded-lg border border-emerald-900/30">
                                <Check size={20} />
                                <span>Ready to initialize strategy agent</span>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="border-t border-slate-700 p-6 bg-slate-900 flex justify-between">
                    <button
                        onClick={handleBack}
                        disabled={step === 1}
                        className={`px-6 py-2 rounded-lg flex items-center gap-2 ${step === 1 ? 'opacity-0' : 'text-slate-400 hover:text-white hover:bg-slate-800'
                            }`}
                    >
                        <ChevronLeft size={20} /> Back
                    </button>

                    {step < 4 ? (
                        <button
                            onClick={handleNext}
                            className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg flex items-center gap-2 font-medium"
                        >
                            Next Step <ChevronRight size={20} />
                        </button>
                    ) : (
                        <button
                            onClick={handleSubmit}
                            disabled={loading}
                            className="px-8 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg flex items-center gap-2 font-medium shadow-lg shadow-emerald-900/20"
                        >
                            {loading ? 'Creating...' : 'Create Strategy'} <Check size={20} />
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

export default StrategyWizard;
