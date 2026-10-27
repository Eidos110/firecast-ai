"""Unit tests for :mod:`src.geo.services` aggregation helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.geo import services


class TestTrendAggregation(unittest.TestCase):
    def test_csv_without_score_or_label_columns_does_not_raise(self):
        """Missing probability/label columns fall back to zero scores.

        The old default Series used a fresh RangeIndex, so ``.loc[grp.index]``
        raised KeyError as soon as the filtered frame kept its original index.
        """
        frame = pd.DataFrame(
            {
                "lat": [-2.5, -2.5, -2.5, -2.5],
                "lon": [112.0, 112.0, 112.0, 112.0],
                "time": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-02", "2026-01-02"]),
                "value": [1.0, 2.0, 3.0, 4.0],
            }
        )
        with patch.object(services, "_trend_get_df", return_value=frame):
            result = services._trend_compute(-2.5, 112.0, days=7, radius_km=25.0)

        self.assertEqual(len(result["series"]), 2)
        self.assertEqual([row["count"] for row in result["series"]], [2, 2])
        for row in result["series"]:
            self.assertEqual(row["fire_rate"], 0.0)
            self.assertEqual(row["p50"], 0.0)


if __name__ == "__main__":
    unittest.main()
