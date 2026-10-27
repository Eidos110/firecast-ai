"""One-shot migration script: convert feature CSVs → Parquet (ROADMAP §2-I).

Usage::

    python scripts/migrate_to_parquet.py

The script looks for known-large CSVs under ``data/`` and writes a snappy-
compressed Parquet twin next to each (same stem, ``.parquet`` suffix).
``src/data_loader.py`` prefers the Parquet twin when present, so dropping
the file in *is* the migration — no further code edits or flag flips
needed. Re-running the script overwrites existing Parquet outputs in
place, which is safe because the source CSV is read fresh each time.

Dtype note: Parquet preserves pandas dtypes natively, so ``time`` stays a
``datetime64`` column and the downstream ``pd.to_datetime`` conversion in
``src/geo/services.py:_trend_load_df`` becomes a no-op. This is intentional
and prevents a class of "timestamp parsed as string" bugs after migration.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

# Repo root is the parent of ``scripts/``. Adding to sys.path lets us import
# ``src.config`` so we migrate exactly the same files the runtime reads
# (no drift between "what the script thinks is large" and "what the app
# actually loads").
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("migrate_to_parquet")


def _csv_to_parquet(csv_path: Path) -> tuple[Path, int, int] | None:
    """Convert one CSV → Parquet, returning ``(out_path, csv_bytes, parquet_bytes)``.

    Returns ``None`` when the CSV is missing so callers can keep iterating
    without try/except clutter.
    """
    if not csv_path.exists():
        logger.warning("Skipping %s — file not found", csv_path)
        return None

    if csv_path.suffix != ".csv":
        logger.warning("Skipping %s — not a CSV", csv_path)
        return None

    parquet_path = csv_path.with_suffix(".parquet")
    logger.info("Reading %s (%d MB)", csv_path.name, csv_path.stat().st_size // (1024 * 1024))
    df = pd.read_csv(csv_path)

    # snappy is the default and gives a good CPU/size tradeoff. No need for
    # explicit ``index=False`` — pandas does not store the row index by default.
    df.to_parquet(parquet_path, compression="snappy")
    csv_bytes = csv_path.stat().st_size
    parquet_bytes = parquet_path.stat().st_size
    logger.info(
        "  → wrote %s (%d MB; ratio=%.2fx smaller)",
        parquet_path.name,
        parquet_bytes // (1024 * 1024),
        csv_bytes / max(parquet_bytes, 1),
    )
    return parquet_path, csv_bytes, parquet_bytes


def main() -> int:
    """Convert the canonical feature CSVs. Returns exit code (0 = OK)."""
    from src import config  # noqa: WPS433 (intentional lazy import after sys.path seed)

    candidates = [
        # ``config.DATA_PATH`` — the big processed features CSV used by
        # ``/predict``, ``/analytics/trend``, and ``/predict/aoi``.
        Path(config.DATA_PATH),
        # ``processed_features_path`` — same file under a different alias in
        # legacy code paths; `_csv_to_parquet` dedupes via the same-stem
        # check so listing it twice is harmless.
        Path(config.get_config().paths.processed_features_path),
    ]

    converted = 0
    for csv_path in candidates:
        result = _csv_to_parquet(csv_path)
        if result is not None:
            converted += 1

    if converted == 0:
        logger.error("No CSVs were converted. Check that data/ exists and contains .csv files.")
        return 1

    logger.info("Done. %d file(s) converted to Parquet.", converted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
