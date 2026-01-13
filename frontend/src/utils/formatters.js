/**
 * Format a large number as currency with suffixes (K, M, B, T)
 * @param {number} value - The value to format
 * @param {boolean} showCurrencySymbol - Whether to show the currency symbol
 * @returns {string} Formatted string
 */
export function formatLargeCurrency(value, showCurrencySymbol = true) {
    if (value === null || value === undefined) return '-';

    // Handle strings that might be passed accidentally
    const num = Number(value);
    if (isNaN(num)) return '-';

    const symbol = showCurrencySymbol ? '$' : '';
    const absValue = Math.abs(num);

    if (absValue >= 1e12) {
        return `${symbol}${(num / 1e12).toFixed(2)}T`;
    }
    if (absValue >= 1e9) {
        return `${symbol}${(num / 1e9).toFixed(2)}B`;
    }
    if (absValue >= 1e6) {
        return `${symbol}${(num / 1e6).toFixed(2)}M`;
    }
    if (absValue >= 1e3) {
        return `${symbol}${(num / 1e3).toFixed(2)}K`;
    }

    return `${symbol}${num.toFixed(2)}`;
}
