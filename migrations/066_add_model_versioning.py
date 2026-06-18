"""
Migration: 066_add_model_versioning.py
Add model versioning system to the database.
"""

from yoyo import step

step(
    """
    ALTER TABLE predictions ADD COLUMN model_version VARCHAR(50) DEFAULT 'v0.1.0';
    """,
    "ALTER TABLE predictions DROP COLUMN model_version",
)

step(
    """
    CREATE TABLE model_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_name VARCHAR(50) NOT NULL,
        version_string VARCHAR(50) NOT NULL,
        file_path VARCHAR(500) NOT NULL,
        metadata TEXT,
        performance_metrics TEXT,
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        deployed_at DATETIME,
        UNIQUE(model_name, version_string)
    );
    """,
    "DROP TABLE model_versions",
)

step(
    """
    CREATE INDEX idx_model_versions_name_active ON model_versions(model_name, is_active);
    """,
    "DROP INDEX idx_model_versions_name_active",
)

step(
    """
    CREATE INDEX idx_predictions_version ON predictions(model_version);
    """,
    "DROP INDEX idx_predictions_version",
)
