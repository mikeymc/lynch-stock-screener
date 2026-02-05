import { useState, useEffect } from 'react'
import { Check, ChevronDown, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuTrigger,
    DropdownMenuSeparator,
    DropdownMenuLabel,
} from '@/components/ui/dropdown-menu'

// Country code to full name mapping
const COUNTRY_NAMES = {
    'US': 'United States',
    'CA': 'Canada',
    'CN': 'China',
    'GB': 'United Kingdom',
    'IL': 'Israel',
    'NL': 'Netherlands',
    'CH': 'Switzerland',
    'IE': 'Ireland',
    'TW': 'Taiwan',
    'KY': 'Cayman Islands',
    'DE': 'Germany',
    'FR': 'France',
    'JP': 'Japan',
    'IN': 'India',
    'AU': 'Australia',
    'BR': 'Brazil',
    'MX': 'Mexico',
    'ES': 'Spain',
    'IT': 'Italy',
    'KR': 'South Korea',
    'SE': 'Sweden',
    'SG': 'Singapore',
    'NO': 'Norway',
    'DK': 'Denmark',
    'FI': 'Finland',
    'BE': 'Belgium',
    'AT': 'Austria',
    'HK': 'Hong Kong',
    'NZ': 'New Zealand',
    'AR': 'Argentina',
    'CL': 'Chile',
    'CO': 'Colombia',
    'PE': 'Peru',
    'GR': 'Greece',
    'PT': 'Portugal',
    'PL': 'Poland',
    'CZ': 'Czech Republic',
    'HU': 'Hungary',
    'RO': 'Romania',
    'TH': 'Thailand',
    'MY': 'Malaysia',
    'ID': 'Indonesia',
    'PH': 'Philippines',
    'VN': 'Vietnam',
    'ZA': 'South Africa',
    'LU': 'Luxembourg',
    'BM': 'Bermuda',
    'VG': 'British Virgin Islands',
    'PA': 'Panama',
    'JE': 'Jersey',
    'AE': 'United Arab Emirates',
    'UY': 'Uruguay',
    'TR': 'Turkey',
}

export default function CountryFilter({ selectedCountries, onChange }) {
    const [countries, setCountries] = useState([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchCountries()
    }, [])

    const fetchCountries = async () => {
        try {
            const response = await fetch('/api/countries')
            const data = await response.json()
            setCountries(data.countries || [])
        } catch (error) {
            console.error('Error fetching countries:', error)
        } finally {
            setLoading(false)
        }
    }

    // Group countries
    const usCountry = countries.find(c => c.code === 'US')
    const popularFPIs = countries
        .filter(c => c.code !== 'US')
        .slice(0, 8) // Top 8 non-US countries
    const otherCountries = countries
        .filter(c => c.code !== 'US')
        .slice(8)
    // Already sorted by count DESC from API, no need to re-sort

    const isSelected = (code) => selectedCountries.includes(code)
    const allSelected = selectedCountries.length === 0

    const toggleCountry = (code) => {
        if (isSelected(code)) {
            onChange(selectedCountries.filter(c => c !== code))
        } else {
            onChange([...selectedCountries, code])
        }
    }

    const selectAll = () => onChange([])
    const selectUSOnly = () => onChange(['US'])
    const selectFPIsOnly = () => onChange(countries.filter(c => c.code !== 'US').map(c => c.code))
    const clearSelection = () => onChange([])

    const getButtonLabel = () => {
        if (allSelected) return 'All Countries'
        if (selectedCountries.length === 1 && selectedCountries[0] === 'US') return 'US Only'
        if (selectedCountries.length === 1) return COUNTRY_NAMES[selectedCountries[0]] || selectedCountries[0]
        return `${selectedCountries.length} Countries`
    }

    const getCountryName = (code) => COUNTRY_NAMES[code] || code

    const CountryItem = ({ country, showCount = true }) => (
        <button
            className="flex items-center justify-between w-full px-2 py-1.5 text-sm hover:bg-accent rounded-sm"
            onClick={() => toggleCountry(country.code)}
        >
            <span className="flex items-center gap-2">
                <div className="w-4 h-4 flex items-center justify-center">
                    {(allSelected || isSelected(country.code)) && (
                        <Check className="h-3.5 w-3.5 text-primary" />
                    )}
                </div>
                <span>{getCountryName(country.code)}</span>
            </span>
            {showCount && (
                <span className="text-muted-foreground text-xs">
                    {country.count.toLocaleString()}
                </span>
            )}
        </button>
    )

    if (loading) {
        return (
            <Button variant="outline" size="sm" disabled>
                Loading...
            </Button>
        )
    }

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2">
                    {getButtonLabel()}
                    <ChevronDown className="h-4 w-4 opacity-50" />
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-64 max-h-[400px] overflow-y-auto">
                {/* Quick Actions */}
                <div className="p-2 space-y-1">
                    <Button
                        variant={allSelected ? 'default' : 'ghost'}
                        size="sm"
                        className="w-full justify-start"
                        onClick={selectAll}
                    >
                        All Countries ({countries.reduce((sum, c) => sum + c.count, 0).toLocaleString()})
                    </Button>
                    <Button
                        variant={selectedCountries.length === 1 && selectedCountries[0] === 'US' ? 'default' : 'ghost'}
                        size="sm"
                        className="w-full justify-start"
                        onClick={selectUSOnly}
                    >
                        US Only ({usCountry?.count.toLocaleString() || 0})
                    </Button>
                    <Button
                        variant="ghost"
                        size="sm"
                        className="w-full justify-start"
                        onClick={selectFPIsOnly}
                    >
                        FPIs Only ({countries.filter(c => c.code !== 'US').reduce((sum, c) => sum + c.count, 0).toLocaleString()})
                    </Button>
                    {selectedCountries.length > 0 && (
                        <Button
                            variant="ghost"
                            size="sm"
                            className="w-full justify-start text-muted-foreground hover:text-foreground"
                            onClick={selectAll}
                        >
                            <X className="h-4 w-4 mr-2" />
                            Reset to All
                        </Button>
                    )}
                </div>

                <DropdownMenuSeparator />

                {/* US */}
                {usCountry && (
                    <>
                        <DropdownMenuLabel className="text-xs text-muted-foreground">
                            United States
                        </DropdownMenuLabel>
                        <div className="px-2 pb-2">
                            <CountryItem country={usCountry} />
                        </div>
                        <DropdownMenuSeparator />
                    </>
                )}

                {/* Popular FPIs */}
                {popularFPIs.length > 0 && (
                    <>
                        <DropdownMenuLabel className="text-xs text-muted-foreground">
                            Popular FPIs
                        </DropdownMenuLabel>
                        <div className="px-2 pb-2 space-y-0.5">
                            {popularFPIs.map(country => (
                                <CountryItem key={country.code} country={country} />
                            ))}
                        </div>
                        <DropdownMenuSeparator />
                    </>
                )}

                {/* Other Countries */}
                {otherCountries.length > 0 && (
                    <>
                        <DropdownMenuLabel className="text-xs text-muted-foreground">
                            Other Countries
                        </DropdownMenuLabel>
                        <div className="px-2 pb-2 space-y-0.5">
                            {otherCountries.map(country => (
                                <CountryItem key={country.code} country={country} />
                            ))}
                        </div>
                    </>
                )}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}
