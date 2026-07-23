"""Unit tests for the FireCast design-token theme module (Fase 5).

Covers:
- ``theme.get_risk_level`` boundary behaviour at the four thresholds
  (0.3 / 0.5 / 0.7 / 1.0) and extreme inputs (negative, NaN, string, None).
- ``theme.get_risk_color`` / ``get_risk_label`` / ``get_risk_icon`` consistency.
- ``theme.serialize_for_js`` shape (used by the React component kit).
- ``theme.get_css_variables`` emits dark + light palette blocks + a11y focus ring.

These tests guard the ``RISK_THRESHOLDS`` single source of truth (Fase 4)
against silent regressions and against the historical drift between the
Streamlit shell (Indonesian-tier keys) and the React kit (English labels).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure repo root is importable when run via plain `python -m unittest`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import unittest

from frontend.utils import theme


class TestRiskLevelBoundaries(unittest.TestCase):
    """Mirror the spec in tokens.json: <0.3 rendah, <0.5 sedang, <0.7 tinggi, else sangat_tinggi."""

    def test_rendah_inclusive_lower(self):
        self.assertEqual(theme.get_risk_level(0.0), "rendah")
        self.assertEqual(theme.get_risk_level(0.29), "rendah")

    def test_sedang_boundary(self):
        self.assertEqual(theme.get_risk_level(0.3), "sedang")
        self.assertEqual(theme.get_risk_level(0.49), "sedang")

    def test_tinggi_boundary(self):
        self.assertEqual(theme.get_risk_level(0.5), "tinggi")
        self.assertEqual(theme.get_risk_level(0.69), "tinggi")

    def test_sangat_tinggi_boundary(self):
        self.assertEqual(theme.get_risk_level(0.7), "sangat_tinggi")
        self.assertEqual(theme.get_risk_level(1.0), "sangat_tinggi")
        self.assertEqual(theme.get_risk_level(0.9999), "sangat_tinggi")

    def test_negative_score_clamps_to_rendah(self):
        # Implementations use `score < 0.3` so negative values also land in rendah.
        self.assertEqual(theme.get_risk_level(-0.1), "rendah")

    def test_above_one_still_extreme(self):
        # Defensive: callers may feed unclamped probabilities.
        self.assertEqual(theme.get_risk_level(1.5), "sangat_tinggi")

    def test_none_falls_back_to_rendah(self):
        # float(None or 0.0) == 0.0 -> rendah; matches documented contract.
        self.assertEqual(theme.get_risk_level(None), "rendah")

    def test_non_numeric_string_raises(self):
        # The current contract raises ValueError on a string that is not
        # falsy; documented so callers upstream always coerce first. This test
        # locks the behaviour so a future "silent fallback" refactor is flagged.
        with self.assertRaises(ValueError):
            theme.get_risk_level("not-a-number")

    def test_consistency_with_thresholds_dict(self):
        for level, upper in theme.RISK_THRESHOLDS.items():
            # Just below the upper bound should resolve to this level (except
            # sangat_tinggi whose upper IS 1.0 — test via 1.0 directly).
            JUST_BELOW = upper - 1e-6 if upper > 0 else 0.0
            if level == "sangat_tinggi":
                self.assertEqual(theme.get_risk_level(1.0), level)
            else:
                self.assertEqual(theme.get_risk_level(JUST_BELOW), level)


class TestRiskLabellingConsistency(unittest.TestCase):
    def test_get_risk_color_matches_risk_colors(self):
        for score in (0.1, 0.4, 0.6, 0.9):
            level = theme.get_risk_level(score)
            self.assertEqual(theme.get_risk_color(score), theme.RISK_COLORS[level])

    def test_get_risk_bg_color_matches_risk_bg_colors(self):
        for score in (0.1, 0.4, 0.6, 0.9):
            level = theme.get_risk_level(score)
            self.assertEqual(theme.get_risk_bg_color(score), theme.RISK_BG_COLORS[level])

    def test_get_risk_label_id_and_en(self):
        self.assertEqual(theme.get_risk_label(0.1, "id"), theme.RISK_LABELS["id"]["rendah"])
        self.assertEqual(theme.get_risk_label(0.9, "en"), theme.RISK_LABELS["en"]["sangat_tinggi"])

    def test_get_risk_icon_returns_emoji(self):
        for score in (0.1, 0.4, 0.6, 0.9):
            icon = theme.get_risk_icon(score)
            self.assertIsInstance(icon, str)
            self.assertTrue(icon)


class TestSerializeForJs(unittest.TestCase):
    def test_shape_has_expected_keys(self):
        payload = theme.serialize_for_js()
        for key in ("thresholds", "colors", "bg_colors", "labels"):
            self.assertIn(key, payload)

    def test_thresholds_are_floats(self):
        for v in theme.serialize_for_js()["thresholds"].values():
            self.assertIsInstance(v, float)

    def test_colors_cover_all_tiers(self):
        ser = theme.serialize_for_js()
        self.assertEqual(set(ser["colors"].keys()), set(theme.RISK_THRESHOLDS.keys()))

    def test_labels_have_both_locales(self):
        ser = theme.serialize_for_js()
        self.assertIn("id", ser["labels"])
        self.assertIn("en", ser["labels"])


class TestSerializeForJsDarkLight(unittest.TestCase):
    """Fase 4 dark/light payload for the React useTheme hook."""

    def test_dark_light_keys_present(self):
        payload = theme.serialize_for_js_dark_light()
        for key in ("dark", "light", "risk", "a11y"):
            self.assertIn(key, payload)

    def test_dark_and_light_palettes_differ(self):
        payload = theme.serialize_for_js_dark_light()
        # Light must override surface, text, border for the same key name.
        self.assertNotEqual(
            payload["light"]["surface"],
            payload["dark"]["surface"],
        )
        self.assertNotEqual(
            payload["light"]["text"],
            payload["dark"]["text"],
        )


class TestCssVariables(unittest.TestCase):
    def test_emits_dark_palette(self):
        css = theme.get_css_variables()
        self.assertIn('data-theme="dark"', css)

    def test_emits_light_palette(self):
        css = theme.get_css_variables()
        self.assertIn('data-theme="light"', css)

    def test_emits_focus_visible_ring(self):
        css = theme.get_css_variables()
        self.assertIn(":focus-visible", css)
        self.assertIn("--a11y-focus-ring", css)

    def test_emits_reduced_motion_block(self):
        css = theme.get_css_variables()
        self.assertIn("prefers-reduced-motion", css)

    def test_emits_risk_threshold_vars(self):
        css = theme.get_css_variables()
        self.assertIn("--risk-threshold-rendah", css)
        self.assertIn("--risk-threshold-sangat-tinggi", css)


class TestTokensJsonSingleSource(unittest.TestCase):
    """Guard that the on-disk tokens.json stays consistent with theme.py constants."""

    def test_tokens_file_exists(self):
        self.assertTrue(
            os.path.exists(theme._TOKENS_PATH),
            f"tokens.json missing at {theme._TOKENS_PATH}",
        )

    def test_thresholds_match_tokens(self):
        for level, expected in (
            ("rendah", 0.3),
            ("sedang", 0.5),
            ("tinggi", 0.7),
            ("sangat_tinggi", 1.0),
        ):
            self.assertAlmostEqual(
                theme.RISK_THRESHOLDS[level],
                expected,
                places=6,
                msg=f"Threshold drift on {level!r}",
            )

    def test_risk_colors_match_tokens(self):
        expected = {
            "rendah": "#22c55e",
            "sedang": "#fb923c",
            "tinggi": "#ef4444",
            "sangat_tinggi": "#7f1d1d",
        }
        for level, color in expected.items():
            self.assertEqual(theme.RISK_COLORS[level], color, f"Color drift on {level!r}")


if __name__ == "__main__":
    unittest.main()
