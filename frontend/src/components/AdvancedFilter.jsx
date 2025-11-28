import { useState, useEffect } from 'react'

// Region to country mappings (using 2-letter country codes)
const REGION_COUNTRIES = {
    'USA': ['US'],
    'Canada': ['CA'],
    'Central/South America': ['MX', 'BR', 'AR', 'CL', 'PE', 'CO', 'VE', 'EC', 'BO', 'PY', 'UY', 'CR', 'PA', 'GT', 'HN', 'SV', 'NI'],
    'Europe': ['GB', 'DE', 'FR', 'IT', 'ES', 'NL', 'CH', 'IE', 'BE', 'SE', 'NO', 'DK', 'FI', 'AT', 'PL', 'PT', 'GR', 'CZ', 'HU', 'RO', 'LU', 'IS'],
    'Asia': ['CN', 'JP', 'KR', 'IN', 'SG', 'HK', 'TW', 'TH', 'MY', 'ID', 'PH', 'VN', 'IL'],
    'Other': []
}

export default function AdvancedFilter({ filters, onFiltersChange, isOpen, onToggle }) {
    const [localFilters, setLocalFilters] = useState(filters)

    // Sync local state with props when filters change externally
    useEffect(() => {
        setLocalFilters(filters)
    }, [filters])

    const handleRegionToggle = (region) => {
        const newRegions = localFilters.regions.includes(region)
            ? localFilters.regions.filter(r => r !== region)
            : [...localFilters.regions, region]

        const updatedFilters = { ...localFilters, regions: newRegions }
        setLocalFilters(updatedFilters)
        onFiltersChange(updatedFilters)
    }

    const handleCountryToggle = (country) => {
        const newCountries = localFilters.countries.includes(country)
            ? localFilters.countries.filter(c => c !== country)
            : [...localFilters.countries, country]

        const updatedFilters = { ...localFilters, countries: newCountries }
        setLocalFilters(updatedFilters)
        onFiltersChange(updatedFilters)
    }

    const handleInstOwnershipChange = (type, value) => {
        const numValue = value === '' ? null : parseFloat(value)
        const updatedFilters = {
            ...localFilters,
            institutionalOwnership: {
                ...localFilters.institutionalOwnership,
                [type]: numValue
            }
        }
        setLocalFilters(updatedFilters)
        onFiltersChange(updatedFilters)
    }

    const handleRevenueGrowthChange = (value) => {
        const numValue = value === '' ? null : parseFloat(value)
        const updatedFilters = {
            ...localFilters,
            revenueGrowth: { min: numValue }
        }
        setLocalFilters(updatedFilters)
        onFiltersChange(updatedFilters)
    }

    const handleIncomeGrowthChange = (value) => {
        const numValue = value === '' ? null : parseFloat(value)
        const updatedFilters = {
            ...localFilters,
            incomeGrowth: { min: numValue }
        }
        setLocalFilters(updatedFilters)
        onFiltersChange(updatedFilters)
    }

    const handleDebtToEquityChange = (value) => {
        const numValue = value === '' ? null : parseFloat(value)
        const updatedFilters = {
            ...localFilters,
            debtToEquity: { max: numValue }
        }
        setLocalFilters(updatedFilters)
        onFiltersChange(updatedFilters)
    }

    const handleClearFilters = () => {
        const emptyFilters = {
            countries: [],
            regions: [],
            institutionalOwnership: { min: null, max: null },
            revenueGrowth: { min: null },
            incomeGrowth: { min: null },
            debtToEquity: { max: null }
        }
        setLocalFilters(emptyFilters)
        onFiltersChange(emptyFilters)
    }

    const getActiveFilterCount = () => {
        let count = 0
        if (localFilters.regions.length > 0) count++
        if (localFilters.countries.length > 0) count++
        if (localFilters.institutionalOwnership.min !== null) count++
        if (localFilters.institutionalOwnership.max !== null) count++
        if (localFilters.revenueGrowth.min !== null) count++
        if (localFilters.incomeGrowth.min !== null) count++
        if (localFilters.debtToEquity.max !== null) count++
        return count
    }

    if (!isOpen) return null

    return (
        <div className="advanced-filter-panel">
            <div className="advanced-filter-header">
                <h3>Advanced Filters</h3>
                <button onClick={handleClearFilters} className="clear-filters-button">
                    Clear All
                </button>
            </div>

            <div className="advanced-filter-content">
                {/* Region/Country Filters */}
                <div className="filter-group">
                    <label className="filter-label">Region/Country</label>
                    <div className="filter-chips">
                        {Object.keys(REGION_COUNTRIES).map(region => (
                            <button
                                key={region}
                                onClick={() => handleRegionToggle(region)}
                                className={`filter-chip ${localFilters.regions.includes(region) ? 'active' : ''}`}
                            >
                                {region}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Institutional Ownership */}
                <div className="filter-group">
                    <label className="filter-label">Institutional Ownership (%)</label>
                    <div className="filter-range">
                        <input
                            type="number"
                            placeholder="Min"
                            min="0"
                            max="100"
                            step="1"
                            value={localFilters.institutionalOwnership.min ?? ''}
                            onChange={(e) => handleInstOwnershipChange('min', e.target.value)}
                            className="filter-input"
                        />
                        <span className="range-separator">to</span>
                        <input
                            type="number"
                            placeholder="Max"
                            min="0"
                            max="100"
                            step="1"
                            value={localFilters.institutionalOwnership.max ?? ''}
                            onChange={(e) => handleInstOwnershipChange('max', e.target.value)}
                            className="filter-input"
                        />
                    </div>
                </div>

                {/* Revenue Growth */}
                <div className="filter-group">
                    <label className="filter-label">5Y Revenue Growth (min %)</label>
                    <input
                        type="number"
                        placeholder="e.g., 15"
                        step="0.1"
                        value={localFilters.revenueGrowth.min ?? ''}
                        onChange={(e) => handleRevenueGrowthChange(e.target.value)}
                        className="filter-input"
                    />
                </div>

                {/* Income Growth */}
                <div className="filter-group">
                    <label className="filter-label">5Y Income Growth (min %)</label>
                    <input
                        type="number"
                        placeholder="e.g., 15"
                        step="0.1"
                        value={localFilters.incomeGrowth.min ?? ''}
                        onChange={(e) => handleIncomeGrowthChange(e.target.value)}
                        className="filter-input"
                    />
                </div>

                {/* Debt to Equity */}
                <div className="filter-group">
                    <label className="filter-label">Debt-to-Equity (max)</label>
                    <input
                        type="number"
                        placeholder="e.g., 0.6"
                        step="0.1"
                        value={localFilters.debtToEquity.max ?? ''}
                        onChange={(e) => handleDebtToEquityChange(e.target.value)}
                        className="filter-input"
                    />
                </div>
            </div>
        </div>
    )
}
