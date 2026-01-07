import { useState, useEffect } from 'react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'

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

    const handleInstOwnershipChange = (value) => {
        const numValue = value === '' ? null : parseFloat(value)
        const updatedFilters = {
            ...localFilters,
            institutionalOwnership: { max: numValue }
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

    const handleMarketCapChange = (value) => {
        const numValue = value === '' ? null : parseFloat(value)
        const updatedFilters = {
            ...localFilters,
            marketCap: { max: numValue }
        }
        setLocalFilters(updatedFilters)
        onFiltersChange(updatedFilters)
    }

    const handleClearFilters = () => {
        const emptyFilters = {
            countries: [],
            regions: [],
            institutionalOwnership: { max: null },
            revenueGrowth: { min: null },
            incomeGrowth: { min: null },
            debtToEquity: { max: null },
            marketCap: { max: null }
        }
        setLocalFilters(emptyFilters)
        onFiltersChange(emptyFilters)
    }

    const getActiveFilterCount = () => {
        let count = 0
        if (localFilters.regions.length > 0) count++
        if (localFilters.countries.length > 0) count++
        if (localFilters.institutionalOwnership?.max !== null) count++
        if (localFilters.revenueGrowth.min !== null) count++
        if (localFilters.incomeGrowth.min !== null) count++
        if (localFilters.debtToEquity.max !== null) count++
        if (localFilters.marketCap?.max !== null) count++
        return count
    }

    if (!isOpen) return null

    return (
        <div className="bg-card rounded-lg border p-4 mb-4">
            <div className="flex flex-wrap gap-4">
                {/* Region/Country Filters */}
                <div className="flex flex-col gap-2">
                    <Label className="text-sm font-medium">Region</Label>
                    <div className="flex flex-wrap gap-2">
                        {Object.keys(REGION_COUNTRIES).map(region => (
                            <Button
                                key={region}
                                variant={localFilters.regions.includes(region) ? 'default' : 'outline'}
                                size="sm"
                                onClick={() => handleRegionToggle(region)}
                            >
                                {region}
                            </Button>
                        ))}
                    </div>
                </div>

                {/* Institutional Ownership */}
                <div className="flex flex-col gap-1">
                    <Label className="text-sm font-medium">Inst. Own (max%)</Label>
                    <Input
                        type="number"
                        placeholder="75"
                        min="0"
                        max="100"
                        step="1"
                        value={localFilters.institutionalOwnership?.max ?? ''}
                        onChange={(e) => handleInstOwnershipChange(e.target.value)}
                        className="w-20"
                    />
                </div>

                {/* Revenue Growth */}
                <div className="flex flex-col gap-1">
                    <Label className="text-sm font-medium">Rev. Growth (min%)</Label>
                    <Input
                        type="number"
                        placeholder="15"
                        step="0.1"
                        value={localFilters.revenueGrowth.min ?? ''}
                        onChange={(e) => handleRevenueGrowthChange(e.target.value)}
                        className="w-20"
                    />
                </div>

                {/* Income Growth */}
                <div className="flex flex-col gap-1">
                    <Label className="text-sm font-medium">Inc. Growth (min%)</Label>
                    <Input
                        type="number"
                        placeholder="15"
                        step="0.1"
                        value={localFilters.incomeGrowth.min ?? ''}
                        onChange={(e) => handleIncomeGrowthChange(e.target.value)}
                        className="w-20"
                    />
                </div>

                {/* Debt to Equity */}
                <div className="flex flex-col gap-1">
                    <Label className="text-sm font-medium">D/E (max)</Label>
                    <Input
                        type="number"
                        placeholder="0.6"
                        step="0.1"
                        value={localFilters.debtToEquity.max ?? ''}
                        onChange={(e) => handleDebtToEquityChange(e.target.value)}
                        className="w-20"
                    />
                </div>

                {/* Market Cap */}
                <div className="flex flex-col gap-1">
                    <Label className="text-sm font-medium">Mkt Cap (max $B)</Label>
                    <Input
                        type="number"
                        placeholder="10"
                        step="0.1"
                        value={localFilters.marketCap?.max ?? ''}
                        onChange={(e) => handleMarketCapChange(e.target.value)}
                        className="w-20"
                    />
                </div>

                <div className="flex items-end">
                    <Button variant="ghost" size="sm" onClick={handleClearFilters}>
                        Reset
                    </Button>
                </div>
            </div>
        </div>
    )
}
