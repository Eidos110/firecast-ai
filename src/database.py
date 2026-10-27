"""
FireCast Database Module
=====================
SQLite database for prediction history and user data.
Uses SQLModel for simple ORM patterns.
"""

from __future__ import annotations

import contextlib
import logging
import os
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Try to import sqlmodel
try:
    from sqlmodel import Field, Session, SQLModel, create_engine, select
except ImportError:
    Field = None
    SQLModel = None
    create_engine = None
    Session = None
    select = None

# Database URL from environment
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(os.path.dirname(__file__), "..", "data", "firecast.db"),
)

# Database engine (lazy init)
_engine = None
_initialized = False


def _ensure_schema(engine) -> None:
    """Create any missing tables for ``engine`` exactly once.

    Called from :func:`get_engine` so a **fresh checkout** (no committed
    ``data/firecast.db``, e.g. CI runners or a new container) has a usable
    schema from the first query. Without this, ``/api/models/*`` returned
    ``500 no such table: modelversion`` because the tables only existed in a
    developer's local SQLite file.

    Idempotent and non-fatal: failures leave ``_initialized`` False and are
    logged, so sandboxed deployments (no sqlmodel/sqlite) keep degrading to
    the documented 503 instead of crashing.
    """
    global _initialized
    if _initialized or SQLModel is None or engine is None:
        return
    try:
        SQLModel.metadata.create_all(engine)
        _initialized = True
        logger.info("Database schema ready: %s", DATABASE_URL)
    except Exception as e:  # noqa: BLE001 - optional dependency, must not crash
        logger.warning("Failed to initialize database: %s", e)


def get_engine():
    """Get or create the database engine (schema ensured on creation).

    Detects the dialect from ``DATABASE_URL``: SQLite backends use the
    default ``StaticPool``-ish single-connection semantics and reject
    ``pool_size`` / ``max_overflow`` (these kwargs are only valid for
    PostgreSQL/MySQL connection pools).
    """
    global _engine
    if _engine is None and create_engine is not None:
        is_sqlite = DATABASE_URL.startswith("sqlite")
        if is_sqlite:
            # SQLite: ensure parent dir exists, use check_same_thread=False
            # so the engine can be shared across request coroutines.
            db_path = DATABASE_URL.replace("sqlite:///", "")
            with contextlib.suppress(OSError):
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
            _engine = create_engine(
                DATABASE_URL,
                echo=False,
                connect_args={"check_same_thread": False},
            )
        else:
            # PostgreSQL / MySQL: pool size + overflow are meaningful here.
            _engine = create_engine(
                DATABASE_URL,
                echo=False,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,  # Verify connections before use
            )
    # Also covers engines created before this module knew about the schema
    # (e.g. imported and used directly by the model registry).
    _ensure_schema(_engine)
    return _engine


def init_db():
    """Initialize database tables (kept for startup callers; idempotent)."""
    if SQLModel is None:
        return
    _ensure_schema(get_engine())


# Define table classes at module level - SQLAlchemy handles duplicates gracefully
if SQLModel is not None:

    class Prediction(SQLModel, table=True):
        """Fire risk prediction record."""

        __tablename__ = "predictions"
        __table_args__ = {"extend_existing": True}

        id: int | None = Field(default=None, primary_key=True)
        latitude: float = Field(index=True)
        longitude: float = Field(index=True)
        temperature: float
        humidity: float
        wind_speed: float
        wind_direction: float
        rainfall: float = Field(default=0)
        vegetation_type: str = Field(default="Savana")
        overall_risk: float
        risk_level: str
        confidence: float = Field(default=0)
        cnn_probability: float | None = Field(default=None)
        lgbm_probability: float | None = Field(default=None)
        affected_area: float = Field(default=0)
        max_spread_distance: float = Field(default=0)
        model_type: str = Field(default="DEMO")
        created_at: datetime = Field(default_factory=datetime.now)

    class SavedLocation(SQLModel, table=True):
        """Saved/pinned locations."""

        __tablename__ = "locations"
        __table_args__ = {"extend_existing": True}

        id: int | None = Field(default=None, primary_key=True)
        name: str = Field(index=True)
        latitude: float
        longitude: float
        description: str | None = Field(default=None)
        created_at: datetime = Field(default_factory=datetime.now)

    class ModelVersion(SQLModel, table=True):
        """Registered model version."""

        __tablename__ = "model_versions"
        __table_args__ = {"extend_existing": True}

        id: int | None = Field(default=None, primary_key=True)
        model_name: str = Field(index=True)
        version_string: str = Field(index=True)
        file_path: str = Field(index=True)
        model_metadata: str | None = Field(default=None)
        performance_metrics: str | None = Field(default=None)
        is_active: bool = Field(default=True)
        created_at: datetime = Field(default_factory=datetime.now)
        deployed_at: datetime | None = Field(default=None)

else:
    # Dummy classes for type hints when sqlmodel is not available
    class Prediction:
        pass

    class SavedLocation:
        pass

    class ModelVersion:
        pass


def log_prediction(
    latitude: float,
    longitude: float,
    temperature: float,
    humidity: float,
    wind_speed: float,
    wind_direction: float,
    overall_risk: float,
    risk_level: str,
    rainfall: float = 0,
    vegetation_type: str = "Savana",
    confidence: float = 0,
    cnn_probability: float | None = None,
    lgbm_probability: float | None = None,
    affected_area: float = 0,
    max_spread_distance: float = 0,
    model_name: str = "DEMO",
) -> int | None:
    """Log a prediction to the database."""
    if SQLModel is None:
        logger.debug("sqlmodel not available, skipping prediction log")
        return None

    try:
        init_db()
        engine = get_engine()
        if engine is None:
            return None

        prediction = Prediction(
            latitude=latitude,
            longitude=longitude,
            temperature=temperature,
            humidity=humidity,
            wind_speed=wind_speed,
            wind_direction=wind_direction,
            rainfall=rainfall,
            vegetation_type=vegetation_type,
            overall_risk=overall_risk,
            risk_level=risk_level,
            confidence=confidence,
            cnn_probability=cnn_probability,
            lgbm_probability=lgbm_probability,
            affected_area=affected_area,
            max_spread_distance=max_spread_distance,
            model_type=model_name,
            created_at=datetime.now(),
        )

        with Session(engine) as session:
            session.add(prediction)
            session.commit()
            pred_id = prediction.id

        logger.debug("Logged prediction id=%s", pred_id)
        return pred_id

    except Exception as e:
        logger.warning("Failed to log prediction: %s", e)
        return None


def get_predictions(limit: int = 50, risk_level: str | None = None) -> list:
    """Get recent predictions from database."""
    if SQLModel is None:
        return []

    try:
        engine = get_engine()
        if engine is None:
            return []

        with Session(engine) as session:
            stmt = select(Prediction).order_by(Prediction.created_at.desc()).limit(limit)
            if risk_level:
                stmt = stmt.where(Prediction.risk_level == risk_level)
            results = session.exec(stmt).all()
            return list(results)

    except Exception as e:
        logger.warning("Failed to get predictions: %s", e)
        return []


def save_location(
    name: str,
    latitude: float,
    longitude: float,
    description: str | None = None,
) -> int | None:
    """Save a location to the database."""
    if SQLModel is None:
        return None

    try:
        init_db()
        engine = get_engine()
        if engine is None:
            return None

        location = SavedLocation(
            name=name,
            latitude=latitude,
            longitude=longitude,
            description=description,
            created_at=datetime.now(),
        )

        with Session(engine) as session:
            session.add(location)
            session.commit()
            loc_id = location.id

        return loc_id

    except Exception as e:
        logger.warning("Failed to save location: %s", e)
        return None


def get_saved_locations() -> list:
    """Get all saved locations."""
    if SQLModel is None:
        return []

    try:
        engine = get_engine()
        if engine is None:
            return []

        with Session(engine) as session:
            stmt = select(SavedLocation).order_by(SavedLocation.created_at.desc())
            results = session.exec(stmt).all()
            return list(results)

    except Exception as e:
        logger.warning("Failed to get saved locations: %s", e)
        return []


# ---------------------------------------------------------------------------
# Retention policy (Audit priority: Database & Persistence)
# ---------------------------------------------------------------------------
# The ``Prediction`` table grows unbounded in long-lived deployments (HF
# Spaces persistent disk or a local laptop). Compact it via an
# explicit purge call rather than auto-VACUUM, which would block the SQLite
# event loop on large tables. The default retention is 30 days; override via
#   FIRECAST_PREDICTION_RETENTION_DAYS=14  (env)
# or pass ``days`` explicitly. The function returns a dict suitable for admin
# telemetry. Backend-agnostic: noop bila sqlmodel/sqlite missing.
#
# Invoke from a CLI/admin script or a platform cron; there is no scheduler
# wired into the API process by default.
# ---------------------------------------------------------------------------


def _default_retention_days() -> int:
    """Read retention policy from env (portable, backend-agnostic)."""
    raw = os.environ.get("FIRECAST_PREDICTION_RETENTION_DAYS")
    if not raw:
        return 30
    try:
        days = int(raw)
        return days if days > 0 else 30
    except ValueError:
        logger.warning("Invalid FIRECAST_PREDICTION_RETENTION_DAYS=%r, fallback to 30", raw)
        return 30


def purge_old_predictions(days: int | None = None) -> dict[str, Any]:
    """Delete Prediction rows older than ``days`` days (default env override).

    Returns:
        {"deleted": int, "retained_after": int, "days": int} on success.
        {"enabled": False, ...} bila sqlmodel missing or engine unavailable.
    """
    if SQLModel is None:
        return {"enabled": False, "deleted": 0, "reason": "sqlmodel unavailable"}

    retention_days = days if days is not None else _default_retention_days()
    cutoff = datetime.now() - timedelta(days=retention_days)

    try:
        engine = get_engine()
        if engine is None:
            return {"enabled": False, "deleted": 0, "reason": "no engine"}

        from sqlalchemy import delete, func

        with Session(engine) as session:
            # COUNT(*) instead of materialising every row: the table can hold
            # millions of predictions on a long-lived deployment.
            count_before = int(session.exec(select(func.count()).select_from(Prediction)).one())
            session.execute(delete(Prediction).where(Prediction.created_at < cutoff))
            session.commit()
            count_after = int(session.exec(select(func.count()).select_from(Prediction)).one())

        # VACUUM cannot run inside a transaction. SQLAlchemy opens one
        # implicitly unless AUTOCOMMIT is requested, which made the previous
        # best-effort call fail silently. Only SQLite needs this step.
        if engine.dialect.name == "sqlite":  # pragma: no cover - dialect branch
            try:
                with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                    conn.exec_driver_sql("VACUUM")
            except Exception as e:  # pragma: no cover - VACUUM is best-effort
                logger.debug("VACUUM skipped: %s", e)

        logger.info(
            "purge_old_predictions: deleted %d/%d rows (retention=%d days)",
            count_before - count_after,
            count_before,
            retention_days,
        )
        return {
            "enabled": True,
            "deleted": count_before - count_after,
            "retained_after": count_after,
            "days": retention_days,
        }

    except Exception as e:
        logger.warning("purge_old_predictions failed: %s", e)
        return {"enabled": False, "deleted": 0, "reason": str(e)}


def prediction_stats() -> dict[str, Any]:
    """Return row count + oldest/newest timestamps for the Prediction table."""
    if SQLModel is None:
        return {"enabled": False, "rows": 0}

    try:
        engine = get_engine()
        if engine is None:
            return {"enabled": False, "rows": 0, "reason": "no engine"}

        from sqlalchemy import func

        with Session(engine) as session:
            count, oldest, newest = session.exec(
                select(
                    func.count(),
                    func.min(Prediction.created_at),
                    func.max(Prediction.created_at),
                ).select_from(Prediction)
            ).one()
            return {
                "enabled": True,
                "rows": int(count),
                "oldest": oldest.isoformat() if oldest else None,
                "newest": newest.isoformat() if newest else None,
            }
    except Exception as e:
        logger.warning("prediction_stats failed: %s", e)
        return {"enabled": False, "rows": 0, "reason": str(e)}


if __name__ == "__main__":
    init_db()
    logger.info(f"Database: {DATABASE_URL}")
    preds = get_predictions(limit=5)
    logger.info(f"Recent predictions: {len(preds)}")
