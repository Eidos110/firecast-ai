"""
FireCast Database Module
=====================
SQLite database for prediction history and user data.
Uses SQLModel for simple ORM patterns.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import sqlmodel
try:
    from sqlmodel import Field, SQLModel, create_engine, Session, select, update
except ImportError:
    Field = None
    SQLModel = None
    create_engine = None
    Session = None
    select = None
    update = None

# Database URL from environment
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(os.path.dirname(__file__), "..", "data", "firecast.db"),
)

# Database engine (lazy init)
_engine = None
_initialized = False


def get_engine():
    """Get or create the database engine."""
    global _engine
    if _engine is None and create_engine is not None:
        db_path = DATABASE_URL.replace("sqlite:///", "")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        # Configure connection pooling and health checks
        _engine = create_engine(
            DATABASE_URL,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Verify connections before use
        )
    return _engine


def init_db():
    """Initialize database tables."""
    global _initialized
    if _initialized or SQLModel is None:
        return

    try:
        engine = get_engine()
        if engine:
            SQLModel.metadata.create_all(engine)
            _initialized = True
            logger.info("Database initialized: %s", DATABASE_URL)
    except Exception as e:
        logger.warning("Failed to initialize database: %s", e)


# Define table classes at module level - SQLAlchemy handles duplicates gracefully
if SQLModel is not None:

    class Prediction(SQLModel, table=True):
        """Fire risk prediction record."""

        __tablename__ = "predictions"
        __table_args__ = {"extend_existing": True}

        id: Optional[int] = Field(default=None, primary_key=True)
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
        cnn_probability: Optional[float] = Field(default=None)
        lgbm_probability: Optional[float] = Field(default=None)
        affected_area: float = Field(default=0)
        max_spread_distance: float = Field(default=0)
        model_type: str = Field(default="DEMO")
        created_at: datetime = Field(default_factory=datetime.now)

    class SavedLocation(SQLModel, table=True):
        """Saved/pinned locations."""

        __tablename__ = "locations"
        __table_args__ = {"extend_existing": True}

        id: Optional[int] = Field(default=None, primary_key=True)
        name: str = Field(index=True)
        latitude: float
        longitude: float
        description: Optional[str] = Field(default=None)
        created_at: datetime = Field(default_factory=datetime.now)

    class ModelVersion(SQLModel, table=True):
        """Registered model version."""

        __tablename__ = "model_versions"
        __table_args__ = {"extend_existing": True}

        id: Optional[int] = Field(default=None, primary_key=True)
        model_name: str = Field(index=True)
        version_string: str = Field(index=True)
        file_path: str = Field(index=True)
        model_metadata: Optional[str] = Field(default=None)
        performance_metrics: Optional[str] = Field(default=None)
        is_active: bool = Field(default=True)
        created_at: datetime = Field(default_factory=datetime.now)
        deployed_at: Optional[datetime] = Field(default=None)

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
    cnn_probability: Optional[float] = None,
    lgbm_probability: Optional[float] = None,
    affected_area: float = 0,
    max_spread_distance: float = 0,
    model_name: str = "DEMO",
) -> Optional[int]:
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


def get_predictions(limit: int = 50, risk_level: Optional[str] = None) -> list:
    """Get recent predictions from database."""
    if SQLModel is None:
        return []

    try:
        engine = get_engine()
        if engine is None:
            return []

        with Session(engine) as session:
            stmt = (
                select(Prediction).order_by(Prediction.created_at.desc()).limit(limit)
            )
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
    description: Optional[str] = None,
) -> Optional[int]:
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


if __name__ == "__main__":
    init_db()
    logger.info(f"Database: {DATABASE_URL}")
    preds = get_predictions(limit=5)
    logger.info(f"Recent predictions: {len(preds)}")
