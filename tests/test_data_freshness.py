"""Parquet twin freshness guard (audit 2026-08-23, HIGH H2).

``src/data_loader._resolve_tabular`` PREFERS the ``.parquet`` twin when it
exists, so a stale parquet silently shadows a freshly-regenerated CSV: the
CSVs were updated 2026-08-21 while the parquet twins were still from
2026-08-04 — every offline evaluation ran on 17-day-old data without warning.

``data/*.parquet`` is gitignored, so this guard is a no-op on fresh clones /
CI and only bites on workstations where a stale twin actually exists.

Fix when red: ``python scripts/migrate_to_parquet.py``
"""

from __future__ import annotations

import unittest
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# (csv, parquet twin) pairs the runtime reads via _resolve_tabular.
TWINS = [
    ("firecast_data_readymodelling_final_V3.csv", "firecast_data_readymodelling_final_V3.parquet"),
    ("processed_firecast_features_v3.csv", "processed_firecast_features_v3.parquet"),
]

# FAT/round-trip tolerance: parquet must not be OLDER than its CSV.
MTIME_TOLERANCE_S = 5


class TestParquetTwinFreshness(unittest.TestCase):
    def test_parquet_not_older_than_csv(self):
        saw_any = False
        for csv_name, pq_name in TWINS:
            csv_path = DATA_DIR / csv_name
            pq_path = DATA_DIR / pq_name
            if not (csv_path.exists() and pq_path.exists()):
                continue
            saw_any = True
            with self.subTest(file=csv_name):
                age_gap = csv_path.stat().st_mtime - pq_path.stat().st_mtime
                self.assertLessEqual(
                    age_gap,
                    MTIME_TOLERANCE_S,
                    f"{pq_name} is {age_gap / 86400:.1f} days older than {csv_name}; "
                    "run scripts/migrate_to_parquet.py to refresh the twin "
                    "(_resolve_tabular prefers parquet, so evaluations read stale data)",
                )
        if not saw_any:
            self.skipTest("no parquet twins present (fresh clone / CI)")


if __name__ == "__main__":
    unittest.main()
