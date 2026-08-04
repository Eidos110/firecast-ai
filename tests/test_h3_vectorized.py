"""Unit tests for the vectorised + cached H3 indexer.

Audit rekomendasi "Geospatial _h3_index_vectorized ke np.vectorize":
verifies that the helper:
- returns the same H3 index as the canonical ``_h3_latlng_to_cell`` shim,
- returns object-str arrays shaped like the input,
- caches repeated (lat, lon, res) tuples (via the lru_cache wrapper),
- handles 2-D AOI grids by flattening and reshaping,
- raises ValueError when lats / lons shape differ.

Skipped entirely when ``h3`` cannot be imported (sandbox without the wheel).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import h3  # noqa: F401

    _HAS_H3 = True
except Exception:
    _HAS_H3 = False


@unittest.skipUnless(_HAS_H3, "h3 not installed — skipping H3 vectorisation tests")
class TestH3IndexVectorized(unittest.TestCase):
    def setUp(self):
        from src.geo_api import _h3_index_cached

        # Clear the cache between tests so hit/miss assertions are deterministic.
        _h3_index_cached.cache_clear()

    def tearDown(self):
        from src.geo_api import _h3_index_cached

        _h3_index_cached.cache_clear()

    def _canonical_index(self, lat, lon, res):
        """Reference H3 index call using the v3/v4 compat entrypoint."""
        from src.geo_api import _h3_latlng_to_cell

        return _h3_latlng_to_cell(lat, lon, res)

    def test_returns_same_as_plain_h3_call(self):
        from src.geo_api import _h3_index_vectorized

        lats = np.array([-6.175, -6.2, -7.0])
        lons = np.array([106.827, 106.85, 107.0])
        result = _h3_index_vectorized(lats, lons, resolution=7)
        self.assertEqual(result.shape, (3,))
        for lat, lon, got in zip(lats, lons, result, strict=True):
            self.assertEqual(got, self._canonical_index(lat, lon, 7))

    def test_handles_2d_grid(self):
        from src.geo_api import _h3_index_vectorized

        lats = np.array([[-6.0, -6.5], [-7.0, -7.5]])
        lons = np.array([[106.0, 106.5], [107.0, 107.5]])
        result = _h3_index_vectorized(lats, lons, resolution=7)
        self.assertEqual(result.shape, (2, 2))
        self.assertEqual(result[0, 0], self._canonical_index(-6.0, 106.0, 7))

    def test_cache_warm_hits_on_repeat(self):
        from src.geo_api import _h3_index_cached, _h3_index_vectorized

        lats = np.array([-6.0])
        lons = np.array([106.0])
        _h3_index_vectorized(lats, lons, 7)
        self.assertEqual(_h3_index_cached.cache_info().misses, 1)
        # Hit the same (lat, lon, res) twice.
        _h3_index_vectorized(lats, lons, 7)
        _h3_index_vectorized(lats, lons, 7)
        info = _h3_index_cached.cache_info()
        self.assertGreaterEqual(info.hits, 2)
        self.assertEqual(info.misses, 1)

    def test_shape_mismatch_raises(self):
        from src.geo_api import _h3_index_vectorized

        with self.assertRaises(ValueError):
            _h3_index_vectorized(np.array([-6.0, -7.0]), np.array([106.0]), 7)

    def test_returns_object_dtype_array(self):
        from src.geo_api import _h3_index_vectorized

        lats = np.array([-6.0])
        lons = np.array([106.0])
        result = _h3_index_vectorized(lats, lons, 7)
        # np.vectorize with otypes=[object] yields object-dtype ndarray whose
        # elements are python str (H3 v3/v4 always returns str cells).
        self.assertEqual(result.dtype, object)
        self.assertIsInstance(result[0], str)


if __name__ == "__main__":
    unittest.main()
