# ABOUTME: Shared scoring logic and character configuration resolution
# ABOUTME: Ensures consistency across dashboard, stocks, and screening sessions

import logging
from app import deps
from stock_vectors import DEFAULT_ALGORITHM_CONFIG

logger = logging.getLogger(__name__)

def resolve_scoring_config(user_id, character_id_override=None):
    """
    Unified logic to determine the active character and their 
    algorithm configuration (weights and thresholds).
    
    Args:
        user_id: ID of the authenticated user
        character_id_override: Optional character ID (e.g. from query params)
        
    Returns:
        tuple: (character_id: str, config: dict)
    """
    # 1. Resolve character_id
    # Prefer override (query param), then fallback to database setting, then default
    character_id = character_id_override or deps.db.get_user_character(user_id) or 'lynch'
    
    # 2. Fetch all configurations for the user
    # Note: get_algorithm_configs returns list of configs for all characters
    configs = deps.db.get_algorithm_configs()
    
    # 3. Default config if character specific not found
    config = DEFAULT_ALGORITHM_CONFIG.copy()
    
    # 4. Map DB fields to algorithm keys based on character
    if character_id == 'lynch':
        lynch_cfg = next((c for c in configs if c.get('character') == 'lynch'), None)
        if lynch_cfg:
            config = {
                'peg_excellent': lynch_cfg.get('peg_excellent', 1.0),
                'peg_good': lynch_cfg.get('peg_good', 1.5),
                'peg_fair': lynch_cfg.get('peg_fair', 2.0),
                'debt_excellent': lynch_cfg.get('debt_excellent', 0.5),
                'debt_good': lynch_cfg.get('debt_good', 1.0),
                'debt_moderate': lynch_cfg.get('debt_moderate', 2.0),
                'inst_own_min': lynch_cfg.get('inst_own_min', 0.20),
                'inst_own_max': lynch_cfg.get('inst_own_max', 0.60),
                'weight_peg': lynch_cfg.get('weight_peg', 0.50),
                'weight_consistency': lynch_cfg.get('weight_consistency', 0.25),
                'weight_debt': lynch_cfg.get('weight_debt', 0.15),
                'weight_ownership': lynch_cfg.get('weight_ownership', 0.10),
            }
    
    elif character_id == 'buffett':
        buffett_cfg = next((c for c in configs if c.get('character') == 'buffett'), None)
        if buffett_cfg:
            # Map DB field names to scoring logic keys
            config = {
                'weight_roe': buffett_cfg.get('weight_roe', 0.35),
                'weight_consistency': buffett_cfg.get('weight_consistency', 0.25),
                'weight_earnings_consistency': buffett_cfg.get('weight_consistency', 0.25), # StockEvaluator key
                'weight_debt_earnings': buffett_cfg.get('weight_debt_to_earnings', 0.20), # vectorized key
                'weight_debt_to_earnings': buffett_cfg.get('weight_debt_to_earnings', 0.20), # StockEvaluator key
                'weight_gross_margin': buffett_cfg.get('weight_gross_margin', 0.20),
                
                # Zero out Lynch weights to ensure character purity
                'weight_peg': 0.0,
                'weight_debt': 0.0,
                'weight_ownership': 0.0,
                
                # Thresholds
                'roe_excellent': buffett_cfg.get('roe_excellent', 20.0),
                'roe_good': buffett_cfg.get('roe_good', 15.0),
                'roe_fair': buffett_cfg.get('roe_fair', 10.0),
                
                'debt_to_earnings_excellent': buffett_cfg.get('debt_to_earnings_excellent', 3.0),
                'debt_to_earnings_good': buffett_cfg.get('debt_to_earnings_good', 5.0),
                'debt_to_earnings_fair': buffett_cfg.get('debt_to_earnings_fair', 8.0),
                
                'gross_margin_excellent': buffett_cfg.get('gross_margin_excellent', 50.0),
                'gross_margin_good': buffett_cfg.get('gross_margin_good', 40.0),
                'gross_margin_fair': buffett_cfg.get('gross_margin_fair', 30.0),
            }
        else:
            # Fallback Buffett defaults if no record exists
            config = {
                'weight_roe': 0.35, 'weight_consistency': 0.25, 
                'weight_earnings_consistency': 0.25,
                'weight_debt_earnings': 0.20, 'weight_debt_to_earnings': 0.20,
                'weight_gross_margin': 0.20,
                'weight_peg': 0.0, 'weight_debt': 0.0, 'weight_ownership': 0.0,
                'roe_excellent': 20.0, 'roe_good': 15.0, 'roe_fair': 10.0,
                'debt_to_earnings_excellent': 3.0, 'debt_to_earnings_good': 5.0, 'debt_to_earnings_fair': 8.0,
                'gross_margin_excellent': 50.0, 'gross_margin_good': 40.0, 'gross_margin_fair': 30.0,
            }
            
    return character_id, config
