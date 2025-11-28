"""
Country code mapping utility

Maps full country names to 2-letter ISO country codes for consistent storage.
"""

# Mapping of full country names to 2-letter ISO codes
COUNTRY_CODE_MAP = {
    # North America
    'United States': 'US',
    'United States of America': 'US',
    'USA': 'US',
    'Canada': 'CA',
    'Mexico': 'MX',
    
    # Central/South America
    'Brazil': 'BR',
    'Argentina': 'AR',
    'Chile': 'CL',
    'Peru': 'PE',
    'Colombia': 'CO',
    'Venezuela': 'VE',
    'Ecuador': 'EC',
    'Bolivia': 'BO',
    'Paraguay': 'PY',
    'Uruguay': 'UY',
    'Costa Rica': 'CR',
    'Panama': 'PA',
    'Guatemala': 'GT',
    'Honduras': 'HN',
    'El Salvador': 'SV',
    'Nicaragua': 'NI',
    
    # Europe
    'United Kingdom': 'GB',
    'Great Britain': 'GB',
    'UK': 'GB',
    'Germany': 'DE',
    'France': 'FR',
    'Italy': 'IT',
    'Spain': 'ES',
    'Netherlands': 'NL',
    'Switzerland': 'CH',
    'Ireland': 'IE',
    'Belgium': 'BE',
    'Sweden': 'SE',
    'Norway': 'NO',
    'Denmark': 'DK',
    'Finland': 'FI',
    'Austria': 'AT',
    'Poland': 'PL',
    'Portugal': 'PT',
    'Greece': 'GR',
    'Czech Republic': 'CZ',
    'Czechia': 'CZ',
    'Hungary': 'HU',
    'Romania': 'RO',
    'Luxembourg': 'LU',
    'Iceland': 'IS',
    
    # Asia
    'China': 'CN',
    'Japan': 'JP',
    'South Korea': 'KR',
    'Korea': 'KR',
    'India': 'IN',
    'Singapore': 'SG',
    'Hong Kong': 'HK',
    'Taiwan': 'TW',
    'Thailand': 'TH',
    'Malaysia': 'MY',
    'Indonesia': 'ID',
    'Philippines': 'PH',
    'Vietnam': 'VN',
    'Israel': 'IL',
    
    # Oceania
    'Australia': 'AU',
    'New Zealand': 'NZ',
    
    # Middle East
    'Saudi Arabia': 'SA',
    'United Arab Emirates': 'AE',
    'UAE': 'AE',
    'Qatar': 'QA',
    'Kuwait': 'KW',
    'Turkey': 'TR',
}


def normalize_country_code(country: str) -> str:
    """
    Convert country name to 2-letter ISO code
    
    Args:
        country: Full country name or existing code
        
    Returns:
        2-letter country code, or original string if not found
    """
    if not country:
        return ''
    
    # If already a 2-letter code, return as-is
    if len(country) == 2 and country.isupper():
        return country
    
    # Look up in mapping
    return COUNTRY_CODE_MAP.get(country, country)
