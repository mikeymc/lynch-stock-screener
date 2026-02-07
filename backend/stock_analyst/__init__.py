# ABOUTME: Character-aware stock analyst package for AI-driven investment analysis
# ABOUTME: Re-exports StockAnalyst and model constants for backward-compatible imports

from stock_analyst.core import StockAnalystCore, AVAILABLE_MODELS, DEFAULT_MODEL, FALLBACK_MODEL
from stock_analyst.analysis import AnalysisMixin
from stock_analyst.generation import GenerationMixin


class StockAnalyst(StockAnalystCore, AnalysisMixin, GenerationMixin):
    pass
