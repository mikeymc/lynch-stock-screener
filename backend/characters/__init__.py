# ABOUTME: Characters module for investment philosophy personas
# ABOUTME: Provides CharacterConfig dataclass and loader for Lynch, Buffett, etc.

from .config import CharacterConfig, ScoringWeight, Threshold
from .loader import CharacterLoader, get_character, list_characters

__all__ = [
    'CharacterConfig',
    'ScoringWeight',
    'Threshold',
    'CharacterLoader',
    'get_character',
    'list_characters',
]
