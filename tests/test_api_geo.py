"""API integration tests for ``src.geo_api`` (Fase 5).

Uses FastAPI's ``TestClient`` (backed by ``httpx``) to exercise the endpoints
that the audit flagged as having zero coverage:

- ``GET /health`` — public health check.
- ``GET /precompute_progress`` — gated by ``X-API-Key``.
- ``GET /api/models/``, ``GET /api/models/{name}``, ``.../active`` — gated.
- ``POST /api/models/register``, ``.../activate`` — gated + body validation.
- Auth edge cases:
    * missing ``X-API-Key`` -> 401,
    * wrong key -> 401,
    * server with placeholder secret -> 500 (per ``auth._PLACEHOLDER_API_KEYS``).

A temporary, random API key is injected via ``os.environ`` before importing
the app; the key is rolled afterwards so it never leaks into the working tree.
If ``httpx`` is missing the module is skipped (slim sandbox installs).
"""

from __future__ import annotations

import os
import secrets as _secrets
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import httpx  # noqa: F401
    from fastapi.testclient import TestClient

    _HTTPX_OK = True
except Exception:
    _HTTPX_OK = False


@unittest.skipUnless(_HTTPX_OK, "httpx/fastapi not installed — skipping API tests")
class _ApiTestBase(unittest.TestCase):
    """Shared setup: inject a random API key, import the app, build the client."""

    @classmethod
    def setUpClass(cls):
        cls._initial_env = {
            key: os.environ.get(key) for key in ("API_SECRET_KEY", "API_KEY", "ALLOWED_ORIGINS")
        }
        cls._test_key = _secrets.token_urlsafe(48)
        os.environ["API_SECRET_KEY"] = cls._test_key
        os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:8501")

        # Import the app AFTER the secret is in the environment so the security
        # dependency resolves correctly on every request.
        from src.geo_api import app  # local import — keeps env ordering deterministic

        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        # Restore the original environment; never leak the random key.
        for key, old in cls._initial_env.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        # Drop the cached config singleton too — it was built against the
        # random test key and the next test class will inject a NEW key. If we
        # leave the singleton intact, auth would compare the next class's key
        # against this class's key and return 401 (cross-class pollution).
        try:
            from src import config as _cfg

            _cfg._config_instance = None
        except Exception:
            pass

    def _headers(self, *, key: str | None = None, wrong: bool = False) -> dict:
        if wrong:
            return {"X-API-Key": "definitely-not-the-right-key"}
        return {"X-API-Key": key or self._test_key}


@unittest.skipUnless(_HTTPX_OK, "httpx/fastapi not installed — skipping API tests")
class TestHealthEndpoint(_ApiTestBase):
    def test_health_ok_without_auth(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("status", body)
        self.assertEqual(body["status"], "ok")

    def test_health_does_not_require_api_key(self):
        # Even with an invalid key, /health must succeed — it's the liveness probe.
        resp = self.client.get("/health", headers=self._headers(wrong=True))
        self.assertEqual(resp.status_code, 200)


@unittest.skipUnless(_HTTPX_OK, "httpx/fastapi not installed — skipping API tests")
class TestPrecomputeProgress(_ApiTestBase):
    def test_requires_api_key(self):
        resp = self.client.get("/precompute_progress")
        self.assertEqual(resp.status_code, 401)

    def test_wrong_key_rejected(self):
        resp = self.client.get("/precompute_progress", headers=self._headers(wrong=True))
        self.assertEqual(resp.status_code, 401)

    def test_valid_key_returns_payload(self):
        resp = self.client.get("/precompute_progress", headers=self._headers())
        self.assertIn(resp.status_code, (200, 503))  # DB may be unavailable in sandbox
        if resp.status_code == 200:
            body = resp.json()
            for k in ("status", "current", "total", "message"):
                self.assertIn(k, body)


@unittest.skipUnless(_HTTPX_OK, "httpx/fastapi not installed — skipping API tests")
class TestModelsRouter(_ApiTestBase):
    def test_list_requires_api_key(self):
        resp = self.client.get("/api/models/")
        self.assertEqual(resp.status_code, 401)

    def test_list_valid_key(self):
        resp = self.client.get("/api/models/", headers=self._headers())
        # 200 = DB available; 503 = DB unavailable (sandbox) — both are valid auth outcomes.
        self.assertIn(resp.status_code, (200, 503))

    def test_versions_for_unknown_model_404_or_200_empty(self):
        resp = self.client.get("/api/models/nonexistent_model", headers=self._headers())
        self.assertIn(resp.status_code, (200, 404, 503))

    def test_register_requires_body(self):
        # Missing JSON body -> fastapi validation error (422) — not 401.
        resp = self.client.post(
            "/api/models/register",
            headers=self._headers(),
        )
        # Auth still runs before body validation per dependency order:
        # dependencies=[Depends(limiter.limit(...))] + path-level get_api_key.
        self.assertIn(resp.status_code, (401, 422))

    def test_register_rejects_path_traversal(self):
        resp = self.client.post(
            "/api/models/register",
            headers=self._headers(),
            json={
                "model_name": "evil",
                "version": "v1",
                "file_path": "../../../etc/passwd",
            },
        )
        # Either auth blocked (shouldn't, key is valid) or registry rejects traversal.
        self.assertIn(resp.status_code, (400, 403, 404, 422, 500, 503))


@unittest.skipUnless(_HTTPX_OK, "httpx/fastapi not installed — skipping API tests")
class TestAuthPlaceholderGuard(_ApiTestBase):
    """Ensure the server fails closed when API_SECRET_KEY is a known placeholder."""

    def test_placeholder_secret_returns_500(self):
        # Temporarily swap in a placeholder, then hit a gated endpoint.
        # ``src.config.get_config`` caches a singleton, so we must also null the
        # cache before swapping env (otherwise auth would still see the old key).
        # We clear the cache afterwards so the next test class gets a fresh
        # singleton built from the restored environment (prevents cross-test
        # pollution from the placeholder key).
        from src import config

        original_secret = os.environ.get("API_SECRET_KEY")
        os.environ["API_SECRET_KEY"] = "your_secure_api_secret_key_here"
        config._config_instance = None  # force re-evaluation on next get_config()
        try:
            resp = self.client.get(
                "/precompute_progress",
                headers={"X-API-Key": "your_secure_api_secret_key_here"},
            )
            self.assertEqual(resp.status_code, 500)
        finally:
            # Restore env FIRST so the rebuilt singleton carries the legitimate key.
            if original_secret is None:
                os.environ.pop("API_SECRET_KEY", None)
            else:
                os.environ["API_SECRET_KEY"] = original_secret
            # Rebuild the cached singleton from the restored env (any
            # placeholder-polluted cache is replaced atomically here).
            config._config_instance = None
            config.get_config()


if __name__ == "__main__":
    unittest.main()
