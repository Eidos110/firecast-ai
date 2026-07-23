"""
Model registry module.
Provides functions to register, retrieve, and manage model versions.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Import ModelVersion from database to avoid duplicate class definitions
from src import config  # noqa: E402
from src.database import ModelVersion  # noqa: E402


def get_active_model_version(model_name: str) -> Any | None:
    """
    Get the active version for a specific model.
    """
    try:
        from sqlmodel import Session

        from src.database import get_engine, init_db, select

        init_db()
        engine = get_engine()
        if engine is None:
            return None

        with Session(engine) as session:
            stmt = (
                select(ModelVersion)
                .where(
                    ModelVersion.model_name == model_name,
                    ModelVersion.is_active == True,
                )
                .order_by(ModelVersion.created_at.desc())
                .limit(1)
            )
            result = session.exec(stmt).first()
            return result

    except Exception as e:
        logger.warning(f"Failed to get active version for {model_name}: {e}")
        return None


def get_model_path(model_name: str, version: str | None = None) -> str | None:
    """Get the file path for a model version, with path traversal protection."""
    try:
        from sqlmodel import Session

        from src.database import get_engine, init_db, select

        init_db()
        engine = get_engine()
        if engine is None:
            return None

        with Session(engine) as session:
            if version:
                stmt = (
                    select(ModelVersion.file_path)
                    .where(
                        ModelVersion.model_name == model_name,
                        ModelVersion.version_string == version,
                        ModelVersion.is_active == True,
                    )
                    .limit(1)
                )
            else:
                stmt = (
                    select(ModelVersion.file_path)
                    .where(
                        ModelVersion.model_name == model_name,
                        ModelVersion.is_active == True,
                    )
                    .order_by(ModelVersion.created_at.desc())
                    .limit(1)
                )
            result = session.exec(stmt).first()

            # Validate path to prevent directory traversal.
            # The whitelist must mirror ``register_model_version``'s allowed
            # roots (audit Fase 1g): both ``models/`` (legacy CNN+LGBM stack)
            # AND ``add_new_model/`` (new stacking: lgb/xgb/meta/causal_gru) are
            # legitimate storage locations. A model registered under
            # ``add_new_model/`` would otherwise be silently inaccessible here.
            if result:
                try:
                    cfg = config.get_config()
                    allowed_roots = [
                        Path(cfg.paths.models_dir).resolve(),
                        Path(cfg.paths.new_model_dir).resolve(),
                    ]
                    file_path_resolved = Path(result).resolve()
                    # Ensure the resolved path is within at least one root.
                    if any(_safe_relative_to(file_path_resolved, root) for root in allowed_roots):
                        return str(file_path_resolved)
                    logger.error(
                        f"Path traversal detected (or path outside whitelist): "
                        f"{result} is not under {allowed_roots}"
                    )
                    return None
                except Exception as e:
                    logger.error(f"Error validating model path: {e}")
                    return None
            return None

    except Exception as e:
        logger.warning(f"Failed to get model path for {model_name}: {e}")
        return None


def register_model_version(
    model_name: str,
    version: str,
    file_path: str,
    metadata: dict[str, Any] | None = None,
    performance_metrics: dict[str, Any] | None = None,
) -> bool:
    """Register a new model version."""
    try:
        from sqlmodel import Session

        from src.database import get_engine, init_db

        init_db()
        engine = get_engine()
        if engine is None:
            return False

        metadata_json = json.dumps(metadata) if metadata else None
        performance_json = json.dumps(performance_metrics) if performance_metrics else None

        new_version = ModelVersion(
            model_name=model_name,
            version_string=version,
            file_path=file_path,
            model_metadata=metadata_json,
            performance_metrics=performance_json,
            created_at=datetime.now(),
        )

        with Session(engine) as session:
            session.add(new_version)
            session.commit()

        logger.info(f"Registered model {model_name} version {version}")
        return True

    except Exception as e:
        logger.warning(f"Failed to register model {model_name} version {version}: {e}")
        return False


def get_model_versions(model_name: str, limit: int = 10) -> list[Any]:
    """Get model versions for a specific model."""
    try:
        from sqlmodel import Session

        from src.database import get_engine, init_db, select

        init_db()
        engine = get_engine()
        if engine is None:
            return []

        with Session(engine) as session:
            stmt = (
                select(ModelVersion)
                .where(ModelVersion.model_name == model_name)
                .order_by(ModelVersion.created_at.desc())
                .limit(limit)
            )
            results = session.exec(stmt).all()
            return list(results)

    except Exception as e:
        logger.warning(f"Failed to get model versions for {model_name}: {e}")
        return []


def activate_model_version(model_name: str, version: str) -> bool:
    """Activate a specific version for a model."""
    try:
        from sqlmodel import Session, update

        from src.database import get_engine, init_db

        init_db()
        engine = get_engine()
        if engine is None:
            return False

        with Session(engine) as session:
            # Deactivate all versions for this model
            stmt = (
                update(ModelVersion)
                .where(ModelVersion.model_name == model_name)
                .values(is_active=False)
            )
            session.execute(stmt)

            # Activate the specified version
            stmt = (
                update(ModelVersion)
                .where(
                    ModelVersion.model_name == model_name,
                    ModelVersion.version_string == version,
                )
                .values(is_active=True, deployed_at=datetime.now())
            )
            session.execute(stmt)
            session.commit()

        logger.info(f"Activated {model_name} version {version}")
        return True

    except Exception as e:
        logger.warning(f"Failed to activate {model_name} version {version}: {e}")
        return False
