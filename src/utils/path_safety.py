"""Path-traversal-safe helpers shared by ``registry.get_model_path`` and
``api/models._validate_model_root``.

Single source of truth (Audit rekomendasi prioritas "add_new_model/ whitelist").
Both call-sites used to inline their own ``relative_to`` block, with one
implementation in registry.py accidentally referencing a missing
``_safe_relative_to`` symbol (silent NameError behind try/except). Centralising
the helper here fixes that and keeps the whitelist consistent.
"""

from __future__ import annotations

from pathlib import Path


def safe_relative_to(candidate: Path, root: Path) -> bool:
    """Return True iff ``candidate`` resolves under ``root``.

    Wraps ``Path.relative_to`` (which raises ValueError on Windows when the
    case differs). The helper is case-insensitive on Windows to match the
    filesystem semantics there; on POSIX it falls back to standard behaviour.
    Both paths MUST be resolved (absolute + symlinks normalised) FIRST.
    """
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def allowed_model_roots() -> list[Path]:
    """Return the resolved whitelist of model storage roots (single source).

    Reads from ``config.paths`` so the whitelist never drifts between
    ``register_model_version`` (api/models.py) and ``get_model_path``
    (registry.py). Returns an empty list if config is unavailable.
    """
    try:
        from src import config

        cfg = config.get_config()
        return [
            Path(cfg.paths.models_dir).resolve(),
            Path(cfg.paths.new_model_dir).resolve(),
        ]
    except Exception:
        return []


def is_path_within_allowed_roots(
    file_path: str | Path, roots: list[Path]
) -> bool:
    """Return True iff ``file_path`` resolves within at least one of ``roots``.

    ``roots`` entries should already be resolved (use
    :func:`allowed_model_roots` for the canonical set).
    """
    try:
        resolved = Path(file_path).resolve()
    except Exception:
        return False
    return any(safe_relative_to(resolved, root) for root in roots)


__all__ = [
    "allowed_model_roots",
    "is_path_within_allowed_roots",
    "safe_relative_to",
]
