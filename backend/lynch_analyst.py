# ABOUTME: Backwards compatibility wrapper for stock_analyst module
# ABOUTME: Re-exports StockAnalyst as LynchAnalyst for existing code

from stock_analyst import StockAnalyst, AVAILABLE_MODELS, DEFAULT_MODEL

# Backwards compatibility alias
LynchAnalyst = StockAnalyst
