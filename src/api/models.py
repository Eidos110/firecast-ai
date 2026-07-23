"""
Model-version management router for FireCast.

Endpoints are mounted under prefix ``/api/models`` (see :mod:`src.geo_api`
``include_router``). Per AGENTS.md §"Panduan API": do NOT add another
``prefix=`` here (causes double-prefix bug → 404). All endpoints require a
valid ``X-API-Key`` header (``get_api_key`` dependency from :mod:`src.auth`).

Audit Fase 1h fixes:
- list_models raises ``HTTPException`` instead of returning
  ``{"status": "error"}`` under HTTP 200 (a 200 with error body breaks
  OpenAPI clients and makes life-support monitoring blind to failures).
- register / activate now use Pydantic request bodies (not query params) so
  metadata & performance_metrics survive serialization through JSON.
- ``register_model`` validates the submitted ``file_path`` against the same
  whitelist used by :func:`get_model_path` (``models/`` and
  ``add_new_model/``) to prevent path-traversal registration attacks.
- Adds the missing ``select`` import (previously undefined → NameError at
  request time on repos with a populated DB).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src import config
from src.auth import get_api_key
from src.database import ModelVersion, Session, get_engine, select
from src.models.registry import (
    activate_model_version,
    get_active_model_version,
    get_model_versions,
    register_model_version,
)

router = APIRouter(prefix="/api/models", tags=["models"])


# ── Request bodies (Pydantic) ──────────────────────────────────────────


class ActivateVersionBody(BaseModel):
    version: str = Field(..., description="Version string of the model to activate.")


class RegisterModelBody(BaseModel):
    model_name: str = Field(..., description="Logical model name, e.g. 'lgb'.")
    version: str = Field(..., description="Version string for this upload.")
    file_path: str = Field(
        ...,
        description=(
            "Repository-relative path to the model file. Must resolve under "
            "either models/ or add_new_model/ (path-traversal protection)."
        ),
    )
    metadata: dict | None = None
    performance_metrics: dict | None = None


# ── Helpers ────────────────────────────────────────────────────────────


def _validate_model_root(file_path: str) -> None:
    """Reject file_path that escapes the whitelisted model directories.

    Mirrors the whitelist enforced by :func:`get_model_path` so a model
    registered here can later be retrieved. Raises HTTP 400 on violation.
    """
    try:
        cfg = config.get_config()
        allowed_roots = [
            Path(cfg.paths.models_dir).resolve(),
            Path(cfg.paths.new_model_dir).resolve(),
        ]
        resolved = Path(file_path).resolve()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resolve file_path {file_path!r}: {exc}",
        )

    # Path must be inside one of the whitelisted roots (case-insensitive
    # on Windows). ``Path.relative_to`` raises ValueError otherwise.
    ok = False
    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            ok = True
            break
        except ValueError:
            continue
    if not ok:
        raise HTTPException(
            status_code=400,
            detail=(
                f"file_path {file_path!r} is outside the allowed model roots "
                f"{[str(r) for r in allowed_roots]}. Path traversal is blocked."
            ),
        )


# ── Routes ────────────────────────────────────────────────────────────


@router.get("/")
async def list_models(api_key: str = Depends(get_api_key)):
    """List all models and their versions.

    Returns ``{"models": <name->versions>, "count": <n>}``.
    Raises ``HTTPException`` (503) if the DB engine is unavailable, and 500
    on internal errors (audit Fase 1h — never return error body under 200).
    """
    engine = get_engine()
    if engine is None or Session is None or select is None:
        raise HTTPException(
            status_code=503,
            detail="Model registry unavailable: database not configured.",
        )
    try:
        with Session(engine) as db:
            stmt = select(ModelVersion.model_name).distinct()
            results = db.exec(stmt).all()
            model_names = [r for r in results]

            response: dict[str, Any] = {}
            for name in model_names:
                response[name] = get_model_versions(name)

            return {"models": response, "count": sum(len(v) for v in response.values())}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Internal error listing models: {exc}",
        )


@router.get("/{model_name}")
async def list_model_versions(model_name: str, api_key: str = Depends(get_api_key)):
    """List versions for a specific model."""
    versions = get_model_versions(model_name)
    return {"model": model_name, "versions": versions, "count": len(versions)}


@router.get("/{model_name}/active")
async def get_active_version(model_name: str, api_key: str = Depends(get_api_key)):
    """Get currently active version for a model."""
    version = get_active_model_version(model_name)
    if version is None:
        raise HTTPException(status_code=404, detail="Active version not found")
    return version


@router.post("/{model_name}/activate")
async def activate_version(
    model_name: str,
    body: ActivateVersionBody,
    api_key: str = Depends(get_api_key),
):
    """Activate a specific version for a model.

    Body: ``{"version": "<version_string>"}`` (Pydantic, JSON body — not
    query params).
    """
    success = activate_model_version(model_name, body.version)
    if not success:
        raise HTTPException(400, detail="Failed to activate version")
    return {"status": "success", "model": model_name, "version": body.version}


@router.post("/register")
async def register_model(
    body: RegisterModelBody,
    api_key: str = Depends(get_api_key),
):
    """Register a new model version.

    Body: ``RegisterModelBody`` (Pydantic JSON). Validates ``file_path`` is
    inside ``models/`` or ``add_new_model/`` to prevent path-traversal.
    """
    _validate_model_root(body.file_path)

    success = register_model_version(
        model_name=body.model_name,
        version=body.version,
        file_path=body.file_path,
        metadata=body.metadata,
        performance_metrics=body.performance_metrics,
    )
    if not success:
        raise HTTPException(400, detail="Failed to register model")
    return {"status": "success", "model": body.model_name, "version": body.version}
