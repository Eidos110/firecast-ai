"""
FireCast i18n (Internationalization) Utility
=====================================
Simple dictionary-based translation system for English/Indonesian.
"""

import json
import os
from functools import lru_cache
from typing import Dict

# Path to locales directory
_LOCALES_DIR = os.path.join(os.path.dirname(__file__), "..", "locales")


@lru_cache(maxsize=2)
def _load_locale(locale: str) -> Dict[str, str]:
    """Load translation file from locales directory (cached)."""
    locale_file = os.path.join(_LOCALES_DIR, f"{locale}.json")
    if not os.path.exists(locale_file):
        return {}
    with open(locale_file, "r", encoding="utf-8") as f:
        return json.load(f)


def get_text(key: str, locale: str = "id") -> str:
    """Get translated text for a key.

    Args:
        key: Translation key (e.g., 'app_title', 'risk_low').
        locale: Locale code ('en' for English, 'id' for Indonesian).

    Returns:
        Translated string if found, otherwise returns the key itself.
    """
    if not key:
        return ""
    translations = _load_locale(locale)
    return translations.get(key, key)


def set_locale(locale: str) -> None:
    """Validate that a locale file exists.

    Args:
        locale: Locale code to validate.

    Returns:
        True if locale is valid, False otherwise.
    """
    if locale not in ("en", "id"):
        return False
    translations = _load_locale(locale)
    return bool(translations)


def get_available_locales() -> list[str]:
    """Get list of available locale codes."""
    return ["en", "id"]
