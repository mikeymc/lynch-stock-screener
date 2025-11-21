# ABOUTME: WACC (Weighted Average Cost of Capital) calculator for DCF analysis
# ABOUTME: Calculates discount rate based on company's capital structure and risk profile

from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

def calculate_wacc(
    stock_metrics: Dict,
    risk_free_rate: float = 0.045,  # Current 10-year Treasury ~4.5%
    market_risk_premium: float = 0.07  # Historical equity risk premium ~7%
) -> Optional[Dict]:
    """
    Calculate WACC (Weighted Average Cost of Capital) for a stock.
    
    Formula: WACC = (E/V × Re) + (D/V × Rd × (1 - Tc))
    
    Where:
        E = Market value of equity
        D = Market value of debt
        V = E + D (total value)
        Re = Cost of equity (from CAPM)
        Rd = Cost of debt
        Tc = Corporate tax rate
    
    Args:
        stock_metrics: Dictionary containing stock financial data
        risk_free_rate: Risk-free rate (default: 4.5%)
        market_risk_premium: Market risk premium (default: 7%)
    
    Returns:
        Dictionary with WACC and component breakdown, or None if insufficient data
    """
    try:
        # Extract required data
        market_cap = stock_metrics.get('market_cap')
        beta = stock_metrics.get('beta')
        total_debt = stock_metrics.get('total_debt', 0)  # Default to 0 if missing
        interest_expense = stock_metrics.get('interest_expense')
        tax_rate = stock_metrics.get('effective_tax_rate')
        
        # Validate minimum required data
        if not market_cap or market_cap <= 0:
            logger.warning("Cannot calculate WACC: missing or invalid market cap")
            return None
        
        # Apply fallbacks for missing data
        if beta is None or beta <= 0:
            beta = 1.0  # Market average
            logger.info(f"Using default beta: {beta}")
        
        if total_debt is None:
            total_debt = 0
        
        if tax_rate is None or tax_rate < 0 or tax_rate > 1:
            tax_rate = 0.21  # US corporate tax rate
            logger.info(f"Using default tax rate: {tax_rate}")
        
        # Calculate cost of equity using CAPM
        # Re = Rf + β × (Rm - Rf)
        cost_of_equity = risk_free_rate + (beta * market_risk_premium)
        
        # Cap cost of equity at reasonable bounds (5% - 25%)
        cost_of_equity = max(0.05, min(0.25, cost_of_equity))
        
        # Calculate cost of debt
        if total_debt > 0 and interest_expense and interest_expense > 0:
            cost_of_debt = interest_expense / total_debt
        elif total_debt > 0:
            # Estimate cost of debt at 5% if interest expense missing
            cost_of_debt = 0.05
            logger.info(f"Estimating cost of debt: {cost_of_debt}")
        else:
            cost_of_debt = 0
        
        # Cap cost of debt at reasonable bounds (1% - 15%)
        cost_of_debt = max(0.01, min(0.15, cost_of_debt))
        
        # Calculate weights
        total_value = market_cap + total_debt
        equity_weight = market_cap / total_value
        debt_weight = total_debt / total_value
        
        # Calculate WACC
        wacc = (equity_weight * cost_of_equity) + (debt_weight * cost_of_debt * (1 - tax_rate))
        
        # Cap WACC at reasonable bounds (5% - 20%)
        wacc = max(0.05, min(0.20, wacc))
        
        result = {
            'wacc': round(wacc * 100, 2),  # Convert to percentage
            'cost_of_equity': round(cost_of_equity * 100, 2),
            'cost_of_debt': round(cost_of_debt * 100, 2),
            'after_tax_cost_of_debt': round(cost_of_debt * (1 - tax_rate) * 100, 2),
            'equity_weight': round(equity_weight * 100, 1),
            'debt_weight': round(debt_weight * 100, 1),
            'beta': round(beta, 2),
            'tax_rate': round(tax_rate * 100, 1),
            'components': {
                'risk_free_rate': round(risk_free_rate * 100, 2),
                'market_risk_premium': round(market_risk_premium * 100, 2),
                'market_cap': market_cap,
                'total_debt': total_debt,
                'interest_expense': interest_expense
            }
        }
        
        logger.info(f"Calculated WACC: {result['wacc']}%")
        return result
        
    except Exception as e:
        logger.error(f"Error calculating WACC: {e}")
        return None
