"""Security regression tests for the SPA static mount (audit 2026-08-23, bug #14).

``src.geo_api_spa._spa_fallback`` used to join the request path onto
``static_dir`` with no containment check, so ``GET /%2e%2e/%2e%2e/secrets/x.json``
escaped the build directory and served ANY readable file on disk (verified:
.env, GEE service-account key, SQLite db) without authentication — and the
mount is active on every production launch, including the public HF Space.

These tests pin the patched behaviour: traversal attempts must fall back to
``index.html`` (SPA history-mode semantics), never leak file contents outside
``static_dir``, while legitimate static assets and SPA deep links keep working.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.geo_api_spa import mount_spa

SECRET_MARKER = "GEE-SERVICE-ACCOUNT-PRIVATE-KEY-DO-NOT-LEAK"


class TestSpaTraversalProtection(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())
        # A realistic build dir layout.
        build = self._tmp / "build"
        build.mkdir()
        (build / "index.html").write_text(
            "<!doctype html><html><body>SPA-ROOT</body></html>", encoding="utf-8"
        )
        (build / "favicon.ico").write_bytes(bytes([0, 1, 2, 3]))
        assets = build / "assets"
        assets.mkdir()
        (assets / "app.js").write_text("console.log(42)", encoding="utf-8")

        # Sensitive artefacts OUTSIDE the build dir — exactly what an attacker
        # would try to reach from a public Space.
        secrets_dir = self._tmp / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "gee-key.json").write_text(
            f'{{"private_key": "{SECRET_MARKER}"}}', encoding="utf-8"
        )
        (self._tmp / ".env").write_text("API_SECRET_KEY=super-secret", encoding="utf-8")

        app = FastAPI()
        mounted = mount_spa(app, build)
        self.assertTrue(mounted, "mount_spa must mount when build/index.html exists")
        self.client = TestClient(app)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _assert_no_leak(self, response):
        # Traversal must NOT serve the secret file. After the patch it falls
        # back to index.html (200, SPA shell) — the key property is that the
        # secret marker never appears in any response body.
        self.assertNotIn(SECRET_MARKER, response.text)
        self.assertNotIn("super-secret", response.text)

    def test_traversal_encoded_dots(self):
        """%2e%2e sequences (verified exploit vector) must not escape static_dir."""
        resp = self.client.get("/%2e%2e/%2e%2e/secrets/gee-key.json")
        self._assert_no_leak(resp)

    def test_traversal_plain_dots(self):
        resp = self.client.get("/../../secrets/gee-key.json")
        self._assert_no_leak(resp)

    def test_traversal_backslash_windows(self):
        """Windows separators are also normalized by Path.resolve()."""
        resp = self.client.get("/..%5c..%5csecrets/gee-key.json")
        self._assert_no_leak(resp)

    def test_traversal_env_file(self):
        resp = self.client.get("/%2e%2e/.env")
        self._assert_no_leak(resp)

    def test_legit_assets_still_served(self):
        """Regression guard: the containment fix must not break normal assets."""
        resp = self.client.get("/assets/app.js")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("console.log", resp.text)
        # NOTE: do NOT assert a specific JS media type — Windows' mimetypes
        # registry can map .js to text/plain; the bytes + 200 are the contract.
        resp = self.client.get("/favicon.ico")
        self.assertEqual(resp.status_code, 200)

    def test_spa_fallback_still_works(self):
        """Unknown routes fall back to index.html (history-mode deep links)."""
        resp = self.client.get("/analysis/some/deep/link")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("SPA-ROOT", resp.text)


if __name__ == "__main__":
    unittest.main()
