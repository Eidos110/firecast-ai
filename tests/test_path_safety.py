"""Unit tests for ``src.utils.path_safety`` (Audit rekomendasi: whitelist).

Covers the centralised path-traversal helper used by both
``registry.get_model_path`` and ``api/models._validate_model_root`` so the
whitelist never drifts.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class TestPathSafety(unittest.TestCase):
    def setUp(self):
        # Force a deterministic config so allowed_model_roots() resolves to the
        # repo's own models/ and add_new_model/ directories.
        from src import config

        config._config_instance = None

    def tearDown(self):
        from src import config

        config._config_instance = None

    def test_safe_relative_to_true_for_subdir(self):
        from src.utils.path_safety import safe_relative_to

        parent = Path(_PROJECT_ROOT / "models").resolve()
        child = parent / "cnn_best.pth"
        self.assertTrue(safe_relative_to(child, parent))

    def test_safe_relative_to_false_for_outside(self):
        from src.utils.path_safety import safe_relative_to

        parent = Path(_PROJECT_ROOT / "models").resolve()
        outside = Path(_PROJECT_ROOT / "frontend").resolve()
        # If frontend happens to live under models/ (it shouldn't) the test
        # would be vacuous; assert the helper returns False for a clearly
        # unrelated path.
        if outside != parent:
            self.assertFalse(safe_relative_to(outside, parent))

    def test_allowed_model_roots_returns_two_dirs(self):
        from src.utils.path_safety import allowed_model_roots

        roots = allowed_model_roots()
        self.assertEqual(len(roots), 2)
        # Both should exist as directories in the repo.
        for root in roots:
            self.assertTrue(root.exists(), msg=f"{root} should exist in repo")

    def test_allowed_model_roots_contains_models_and_new_model(self):
        from src.utils.path_safety import allowed_model_roots

        roots = allowed_model_roots()
        root_names = {r.name for r in roots}
        self.assertIn("models", root_names)
        self.assertIn("add_new_model", root_names)

    def test_is_path_within_allowed_roots_accepts_real_file(self):
        # cnn_best.pth is one of the legacy model artifacts committed to models/.
        from src.utils.path_safety import allowed_model_roots, is_path_within_allowed_roots

        roots = allowed_model_roots()
        legacy_models = Path(_PROJECT_ROOT / "models" / "cnn_best.pth").resolve()
        if legacy_models.exists():
            self.assertTrue(is_path_within_allowed_roots(legacy_models, roots))

    def test_is_path_within_allowed_roots_rejects_traversal(self):
        from src.utils.path_safety import allowed_model_roots, is_path_within_allowed_roots

        roots = allowed_model_roots()
        evil_path = Path(_PROJECT_ROOT / ".." / "etc" / "passwd").resolve()
        # Resolve() collapses ".."; posix /etc/passwd is `/etc/passwd`. We
        # assert it is NOT within any of the model roots (the whole point of
        # the whitelist). On Windows /etc/passwd doesn't exist but the path
        # still resolves to an absolute path outside models/.
        self.assertFalse(is_path_within_allowed_roots(evil_path, roots))

    def test_register_rejects_path_outside_roots(self):
        # CLI callers reach registry.register_model_version directly; the
        # whitelist must be enforced there too, not only in the HTTP router.
        from src.models.registry import register_model_version

        self.assertFalse(register_model_version("lgb", "0.0.0", "../evil.pkl"))

    def test_registry_resolves_relative_paths_from_repo_root(self):
        from src.models.registry import _resolve_registry_path

        resolved = _resolve_registry_path("add_new_model/lgb_model.pkl")
        self.assertTrue(resolved.is_absolute())
        self.assertEqual(resolved.parent.name, "add_new_model")

    def test_is_path_within_allowed_roots_handles_unresolvable(self):
        # Non-existent path on a non-existent drive — resolve() raises OSError
        # on some platforms but is_path_within_allowed_roots should swallow it.
        from src.utils.path_safety import is_path_within_allowed_roots

        result = is_path_within_allowed_roots("Z:/nonexistent/foo.pkl", [])
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
