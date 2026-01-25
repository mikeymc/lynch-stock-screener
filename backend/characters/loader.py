# ABOUTME: Loads and caches character configurations
# ABOUTME: Provides get_character() and list_characters() convenience functions

import logging
from typing import Dict, List, Optional

from .config import CharacterConfig

logger = logging.getLogger(__name__)

# Character registry - populated by importing character modules
_characters: Dict[str, CharacterConfig] = {}
_loaded = False


def register_character(config: CharacterConfig) -> None:
    """Register a character configuration."""
    errors = config.validate()
    if errors:
        logger.warning(f"Character '{config.id}' has validation errors: {errors}")
    
    # Only log if this is a new registration
    if config.id not in _characters:
        logger.info(f"Registered character: {config.id} ({config.name})")
    
    _characters[config.id] = config


def get_character(character_id: str) -> Optional[CharacterConfig]:
    """Get a character configuration by ID.

    Args:
        character_id: The character identifier (e.g., 'lynch', 'buffett')

    Returns:
        CharacterConfig or None if not found
    """
    _ensure_characters_loaded()
    return _characters.get(character_id)


def list_characters() -> List[CharacterConfig]:
    """List all available characters.

    Returns:
        List of CharacterConfig objects
    """
    _ensure_characters_loaded()
    return list(_characters.values())


def get_default_character() -> CharacterConfig:
    """Get the default character (Lynch).

    Returns:
        The default CharacterConfig
    """
    _ensure_characters_loaded()
    return _characters.get('lynch') or list(_characters.values())[0]


def _ensure_characters_loaded() -> None:
    """Ensure character modules are imported and registered."""
    global _loaded
    if _loaded:
        return

    # Import character modules to trigger registration
    from . import lynch  # noqa: F401
    from . import buffett  # noqa: F401
    
    _loaded = True


class CharacterLoader:
    """Class-based interface for loading characters.

    Provides the same functionality as the module-level functions,
    but can be instantiated for dependency injection.
    """

    def __init__(self):
        _ensure_characters_loaded()

    def get(self, character_id: str) -> Optional[CharacterConfig]:
        """Get a character by ID."""
        return get_character(character_id)

    def list(self) -> List[CharacterConfig]:
        """List all available characters."""
        return list_characters()

    def get_default(self) -> CharacterConfig:
        """Get the default character."""
        return get_default_character()
