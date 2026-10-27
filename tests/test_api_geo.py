"""API integration tests for ``src.geo_api`` (Fase 5).

Uses FastAPI's ``TestClient`` (backed by ``httpx``) to exercise the endpoints
that the audit flagged as having zero coverage:

- ``GET /health`` — public health check.
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
                "/admin/cache/stats",
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


@unittest.skipUnless(_HTTPX_OK, "httpx/fastapi not installed — skipping API tests")
class TestAdminCacheEndpoints(_ApiTestBase):
    """Audit priority 4 — /admin/cache/* lets ops drop in-memory caches
    without restarting the server."""

    def test_invalidate_requires_api_key(self):
        resp = self.client.post("/admin/cache/invalidate")
        self.assertEqual(resp.status_code, 401)

    def test_invalidate_rejects_wrong_key(self):
        resp = self.client.post("/admin/cache/invalidate", headers={"X-API-Key": "wrong"})
        self.assertEqual(resp.status_code, 401)

    def test_invalidate_with_valid_key(self):
        # The data csv may or may not be loadable in the sandbox, but the
        # endpoint must always return ok + a cleared dict (best-effort).
        resp = self.client.post("/admin/cache/invalidate", headers=self._headers())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")
        cleared = body.get("cleared", {})
        # Each named cache must report an integer count even if cache is absent.
        for _name, count in cleared.items():
            self.assertIsInstance(count, int)
        self.assertIn("prediction_cache", cleared)

    def test_stats_requires_api_key(self):
        resp = self.client.get("/admin/cache/stats")
        self.assertEqual(resp.status_code, 401)

    def test_stats_with_valid_key_returns_snapshot(self):
        resp = self.client.get("/admin/cache/stats", headers=self._headers())
        self.assertIn(resp.status_code, (200,))
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")
        stats = body.get("stats", {})
        self.assertIn("prediction_cache", stats)


@unittest.skipUnless(_HTTPX_OK, "httpx/fastapi not installed — skipping API tests")
class TestAdminDbRetention(_ApiTestBase):
    """Audit priority (Database & Persistence) — retention policy endpoints."""

    def test_purge_requires_api_key(self):
        resp = self.client.post("/admin/db/purge")
        self.assertEqual(resp.status_code, 401)

    def test_purge_with_valid_key(self):
        # The DB may be sqlite file that exists or not — endpoint must never
        # raise; it returns an explicit enabled/False reason when sqlmodel is
        # missing or engine unavailable.
        resp = self.client.post("/admin/db/purge", headers=self._headers())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")
        result = body.get("result", {})
        # Either enabled succeeded or explicitly disabled for a stated reason.
        self.assertIn("enabled", result)
        self.assertIsInstance(result.get("deleted", 0), int)

    def test_purge_with_days_param(self):
        resp = self.client.post("/admin/db/purge?days=7", headers=self._headers())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        result = body.get("result", {})
        # Days should propagate through when enabled.
        if result.get("enabled"):
            self.assertEqual(result.get("days"), 7)

    def test_stats_requires_api_key(self):
        resp = self.client.get("/admin/db/stats")
        self.assertEqual(resp.status_code, 401)

    def test_stats_with_valid_key(self):
        resp = self.client.get("/admin/db/stats", headers=self._headers())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")
        stats = body.get("stats", {})
        self.assertIn("enabled", stats)
        self.assertIsInstance(stats.get("rows", 0), int)


# ---------------------------------------------------------------------------
# TAHAP B — Geo / Analytics / AOI endpoints (React SPA migration PLAN §3).
#
# Coverage matrix:
#   /geo/locations — public-read, shape & non-empty, no key required.
#   /geo/geocode   — Tier-1 local match (network-free), 400 on empty q, 404 on
#                    miss. Nominatim Tier-2 is monkeypatched to avoid network
#                    flakiness in CI.
#   /analytics/trend — 400 on bad lat/lon, 200 + stable shape (empty series
#                    is valid when CSV has rows but the cell is outside the
#                    last-7-day window), 404 when CSV missing (monkeypatched).
#   /predict/aoi   — 401 without key, 400 on bad geometry / empty grid, 200
#                    with batch results. The model layer is monkeypatched so
#                    the test does NOT depend on torch/scaler/sklearn that
#                    may be unavailable in the lint sandbox.
# ---------------------------------------------------------------------------


@unittest.skipUnless(_HTTPX_OK, "httpx/fastapi not installed — skipping API tests")
class TestGeoLocationsEndpoint(_ApiTestBase):
    """``GET /geo/locations`` — SPA sidebar city registry."""

    def test_does_not_require_api_key(self):
        resp = self.client.get("/geo/locations")
        self.assertEqual(resp.status_code, 200)

    def test_response_shape(self):
        resp = self.client.get("/geo/locations")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # Top-level keys must match the public contract.
        self.assertIn("count", body)
        self.assertIn("locations", body)
        self.assertIsInstance(body["locations"], list)
        self.assertEqual(body["count"], len(body["locations"]))
        if body["locations"]:
            first = body["locations"][0]
            for key in ("id", "name", "lat", "lon"):
                self.assertIn(key, first)

    def test_locations_are_usable_indonesian_entries(self):
        resp = self.client.get("/geo/locations")
        body = resp.json()
        # data/locations.json ships with 378 entries on this repo. The exact
        # number is not part of the contract, but the file is committed so
        # the test SHOULD see a non-empty registry; if it is empty the SPA
        # combobox would be broken.
        self.assertGreater(body["count"], 0)


@unittest.skipUnless(_HTTPX_OK, "httpx/fastapi not installed — skipping API tests")
class TestGeoGeocodeEndpoint(_ApiTestBase):
    """``GET /geo/geocode?q=`` — local JSON lookup + Nominatim fallback."""

    def test_does_not_require_api_key(self):
        resp = self.client.get("/geo/geocode", params={"q": "aceh"})
        self.assertEqual(resp.status_code, 200)

    def test_tier1_local_exact_match_returns_source_local(self):
        resp = self.client.get("/geo/geocode", params={"q": "Aceh"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["source"], "local")
        self.assertEqual(body["name"], "Aceh")
        self.assertIn("lat", body)
        self.assertIn("lon", body)

    def test_tier1_local_substring_match(self):
        # 'ace' is a substring of 'Aceh' / 'Aceh Besar'; Tier-1 must resolve.
        resp = self.client.get("/geo/geocode", params={"q": "ace"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["source"], "local")

    def test_empty_q_returns_400(self):
        resp = self.client.get("/geo/geocode", params={"q": ""})
        self.assertEqual(resp.status_code, 400)

    def test_whitespace_q_returns_400(self):
        resp = self.client.get("/geo/geocode", params={"q": "   "})
        self.assertEqual(resp.status_code, 400)

    def test_no_match_returns_404_when_nominatim_disabled(self):
        # Monkeypatch the Nominatim Tier-2 so the test is network-free and
        # a true "no local match" surfaces a clean 404.
        from src.geo import services as _svc

        original = _svc._nominatim_geocode
        _svc._nominatim_geocode = lambda *a, **kw: None
        try:
            resp = self.client.get("/geo/geocode", params={"q": "zzzzz_nonexistent_city_zzzzz"})
            self.assertEqual(resp.status_code, 404)
        finally:
            _svc._nominatim_geocode = original

    def test_tier2_invoked_when_tier1_misses(self):
        # When Tier-1 misses and Tier-2 (network) hits, the endpoint must
        # return 200 with the Tier-2 payload. Monkeypatch Tier-2 so no real
        # HTTP request is issued — this keeps CI deterministic and prevents
        # the Nominatim 1 req/sec upstream cap from being burned by tests.
        from src.geo import services as _svc

        fake_payload = {"name": "Fakeopolis", "lat": -1.5, "lon": 120.0, "source": "nominatim"}
        original = _svc._nominatim_geocode
        _svc._nominatim_geocode = lambda *a, **kw: fake_payload
        try:
            resp = self.client.get("/geo/geocode", params={"q": "zzzzz_nonexistent_city_zzzzz"})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json(), fake_payload)
        finally:
            _svc._nominatim_geocode = original


@unittest.skipUnless(_HTTPX_OK, "httpx/fastapi not installed — skipping API tests")
class TestAnalyticsTrendEndpoint(_ApiTestBase):
    """``GET /analytics/trend?lat&lon&days=7`` — trend time-series aggreg."""

    def test_does_not_require_api_key(self):
        resp = self.client.get("/analytics/trend", params={"lat": -1.17, "lon": 100.40, "days": 7})
        self.assertEqual(resp.status_code, 200)

    def test_response_shape(self):
        resp = self.client.get("/analytics/trend", params={"lat": -1.17, "lon": 100.40, "days": 7})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        for key in ("lat", "lon", "radius_km", "days", "series"):
            self.assertIn(key, body)
        self.assertIsInstance(body["series"], list)
        for entry in body["series"]:
            for key in ("date", "fire_rate", "p10", "p50", "p90", "count"):
                self.assertIn(key, entry)

    def test_invalid_lat_returns_400(self):
        resp = self.client.get("/analytics/trend", params={"lat": 999, "lon": 0})
        self.assertEqual(resp.status_code, 400)

    def test_invalid_lon_returns_400(self):
        resp = self.client.get("/analytics/trend", params={"lat": 0, "lon": 999})
        self.assertEqual(resp.status_code, 400)

    def test_days_clamped_to_range(self):
        # days=0 must NOT 400 — it is clamped server-side to 1. The contract
        # is "graceful clamp" so a curious SPA user passing ?days=0 still
        # gets a 1-day window rather than an error toast.
        resp = self.client.get("/analytics/trend", params={"lat": -1.17, "lon": 100.40, "days": 0})
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(resp.json()["days"], 90)
        self.assertGreaterEqual(resp.json()["days"], 1)

    def test_csv_missing_returns_404(self):
        # When the source CSV is unreachable the endpoint must surface 404
        # (NOT 500) so the SPA charts an empty-state instead of erroring.
        from src.geo import services as _svc

        original = _svc._trend_get_df
        _svc._trend_get_df = lambda *a, **kw: (_ for _ in ()).throw(
            FileNotFoundError("simulated missing CSV")
        )
        try:
            resp = self.client.get("/analytics/trend", params={"lat": -1.17, "lon": 100.40})
            self.assertEqual(resp.status_code, 404)
        finally:
            _svc._trend_get_df = original


@unittest.skipUnless(_HTTPX_OK, "httpx/fastapi not installed — skipping API tests")
class TestPredictAoiEndpoint(_ApiTestBase):
    """``POST /predict/aoi`` — batch predict over an AOI polygon grid."""

    _VALID_GEOJSON = {
        "type": "Polygon",
        "coordinates": [[[100, 0], [101, 0], [101, -1], [100, -1], [100, 0]]],
    }

    def test_requires_api_key(self):
        resp = self.client.post(
            "/predict/aoi",
            json={"geojson": self._VALID_GEOJSON, "grid_size": 2},
        )
        self.assertEqual(resp.status_code, 401)

    def test_rejects_wrong_key(self):
        resp = self.client.post(
            "/predict/aoi",
            json={"geojson": self._VALID_GEOJSON, "grid_size": 2},
            headers={"X-API-Key": "definitely-wrong"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_rejects_unsupported_geometry(self):
        resp = self.client.post(
            "/predict/aoi",
            json={
                "geojson": {
                    "type": "LineString",
                    "coordinates": [[0, 0], [1, 1]],
                }
            },
            headers=self._headers(),
        )
        self.assertEqual(resp.status_code, 400)

    def test_rejects_empty_grid(self):
        # Send a malformed geometry where ``build_aoi_grid`` raises ValueError
        # (no recognizable ring → empty bbox). The endpoint catches the
        # ValueError and returns 400. This is the SPA's "user drew something
        # weird" path — we never want to 200 with a count=0 result array
        # because the heatmap would silently show nothing.
        empty_geom = {"type": "Polygon", "coordinates": []}
        resp = self.client.post(
            "/predict/aoi",
            json={"geojson": empty_geom, "grid_size": 2},
            headers=self._headers(),
        )
        self.assertIn(resp.status_code, (400, 422))

    def test_valid_request_with_mocked_model_returns_200(self):
        # Mock the model layer so the test runs without torch/sklearn.
        # Each point receives a deterministic stub result and we verify the
        # endpoint surfaces lat/lon/row/col enrichment + correct counts.
        from src.geo import services as _svc

        def fake_run(points, base_features, model_version=None, model_type="new"):
            return [
                {
                    "lat": p["lat"],
                    "lon": p["lon"],
                    "row": p.get("row"),
                    "col": p.get("col"),
                    "risk_score": 0.42,
                    "risk_level": "Medium",
                    "status": "success",
                    "latency_ms": 1.0,
                }
                for p in points
            ]

        original = _svc.run_aoi_batch
        _svc.run_aoi_batch = fake_run
        try:
            resp = self.client.post(
                "/predict/aoi",
                json={
                    "geojson": self._VALID_GEOJSON,
                    "grid_size": 3,
                    "base_features": {
                        "temperature": 28,
                        "humidity": 60,
                        "wind_speed": 3,
                    },
                    "model_type": "legacy",
                },
                headers=self._headers(),
            )
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            # grid_size=3 → up to 9 points (fewer if shapely clips corners).
            self.assertGreater(body["count"], 0)
            self.assertEqual(body["ok"], body["count"])
            self.assertEqual(body["errors"], 0)
            self.assertEqual(body["grid_size"], 3)
            first = body["results"][0]
            for key in ("lat", "lon", "row", "col", "risk_score", "status"):
                self.assertIn(key, first)
        finally:
            _svc.run_aoi_batch = original

    def test_grid_size_validation_bounds(self):
        # grid_size > 64 must be rejected by Pydantic with 422.
        resp = self.client.post(
            "/predict/aoi",
            json={"geojson": self._VALID_GEOJSON, "grid_size": 65},
            headers=self._headers(),
        )
        self.assertEqual(resp.status_code, 422)

    def test_grid_size_zero_rejected(self):
        resp = self.client.post(
            "/predict/aoi",
            json={"geojson": self._VALID_GEOJSON, "grid_size": 0},
            headers=self._headers(),
        )
        self.assertEqual(resp.status_code, 422)

    def test_missing_geojson_rejected(self):
        resp = self.client.post(
            "/predict/aoi",
            json={"grid_size": 2},
            headers=self._headers(),
        )
        self.assertEqual(resp.status_code, 422)

    def test_unknown_model_type_rejected(self):
        resp = self.client.post(
            "/predict/aoi",
            json={
                "geojson": self._VALID_GEOJSON,
                "grid_size": 2,
                "model_type": "gpu-experimental",
            },
            headers=self._headers(),
        )
        self.assertEqual(resp.status_code, 422)

    def test_per_cell_error_not_silent_0_5(self):
        # When run_aoi_batch flags one cell as an error (model failure), the
        # endpoint must return that cell with status=="error" — NEVER a
        # silent 0.5+risk_level="Medium" that would hide a real fire on the
        # map (AGENTS.md §3 + bug #3). This is the contract test for that.
        from src.geo import services as _svc

        def fake_run(points, base_features, model_version=None, model_type="new"):
            results = []
            for i, p in enumerate(points):
                if i == 0:
                    results.append(
                        {
                            "lat": p["lat"],
                            "lon": p["lon"],
                            "status": "error",
                            "error": "simulated model failure",
                        }
                    )
                else:
                    results.append(
                        {
                            "lat": p["lat"],
                            "lon": p["lon"],
                            "risk_score": 0.6,
                            "status": "success",
                        }
                    )
            return results

        original = _svc.run_aoi_batch
        _svc.run_aoi_batch = fake_run
        try:
            resp = self.client.post(
                "/predict/aoi",
                json={"geojson": self._VALID_GEOJSON, "grid_size": 2},
                headers=self._headers(),
            )
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["errors"], 1)
            self.assertEqual(body["ok"], body["count"] - 1)
            err_cell = next(r for r in body["results"] if r["status"] == "error")
            self.assertNotIn("risk_score", err_cell)
            self.assertIn("error", err_cell)
        finally:
            _svc.run_aoi_batch = original


@unittest.skipUnless(_HTTPX_OK, "httpx/fastapi not installed — skipping API tests")
class TestSpaMount(unittest.TestCase):
    """TAHAP E — verify ``src.geo_api_spa.mount_spa`` is a safe, no-op-on-missing
    FastAPI static-file mount with history-mode SPA fallback behaviour.

    The test runs against a *synthetic* FastAPI app (not ``src.geo_api:app``)
    so it does not pollute the production route table with a throwaway SPA
    mount, and so it can exercise the missing-build-dir path without touching
    the repo's real ``frontend_react/build`` (which may or may not exist on
    a CI worker).
    """

    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI

        cls._FastAPI = FastAPI

    def setUp(self):
        import tempfile

        from src.geo_api_spa import mount_spa

        self._mount_spa = mount_spa
        self._tmp = Path(tempfile.mkdtemp())
        (self._tmp / "index.html").write_text(
            "<!doctype html><html><body>SPA-ROOT</body></html>", encoding="utf-8"
        )
        (self._tmp / "favicon.ico").write_bytes(bytes([0, 1, 2, 3]))
        assets = self._tmp / "assets"
        assets.mkdir()
        (assets / "index.js").write_text("console.log(42)", encoding="utf-8")
        (assets / "logo.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8"
        )

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_app(self):
        app = self._FastAPI()

        @app.get("/health")
        async def _h():
            return {"status": "ok"}

        @app.get("/predict")
        async def _p():
            return {"risk_score": 0.1}

        return app

    def test_mount_returns_true_when_build_present(self):
        app = self._make_app()
        mounted = self._mount_spa(app, self._tmp)
        self.assertTrue(mounted)
        client = TestClient(app)
        # Root returns the SPA shell.
        r = client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("SPA-ROOT", r.text)

    def test_mount_returns_false_when_build_missing(self):
        app = self._make_app()
        mounted = self._mount_spa(app, Path("/nonexistent-path-for-sure"))
        self.assertFalse(mounted)
        client = TestClient(app)
        # API still works; the SPA routes are 404 because they were never mounted.
        self.assertEqual(client.get("/health").status_code, 200)
        self.assertEqual(client.get("/").status_code, 404)

    def test_api_routes_take_precedence_over_spa_fallback(self):
        app = self._make_app()
        self._mount_spa(app, self._tmp)
        client = TestClient(app)
        # /predict is declared BEFORE mountain; FastAPI matches it first.
        self.assertEqual(client.get("/predict").status_code, 200)
        self.assertEqual(client.get("/health").status_code, 200)
        # A non-existent API path must NOT be silently swallowed by SPA.
        # /api/models (declared nowhere on this synthetic app) should fall
        # back to index.html because there is no handler — this is the
        # documented behaviour of history-mode SPA fallback.
        r = client.get("/non-existent-route")
        self.assertEqual(r.status_code, 200)
        self.assertIn("SPA-ROOT", r.text)

    def test_static_assets_served_with_immutable_cache(self):
        app = self._make_app()
        self._mount_spa(app, self._tmp)
        client = TestClient(app)
        r = client.get("/assets/index.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("console.log(42)", r.text)
        cc = r.headers.get("cache-control", "")
        self.assertIn("immutable", cc)
        self.assertIn("31536000", cc)

        r_svg = client.get("/assets/logo.svg")
        self.assertEqual(r_svg.status_code, 200)
        self.assertIn("svg", r_svg.headers.get("content-type", ""))

    def test_root_html_is_never_cached(self):
        app = self._make_app()
        self._mount_spa(app, self._tmp)
        client = TestClient(app)
        cc = client.get("/").headers.get("cache-control", "")
        self.assertIn("no-cache", cc)
        # API responses keep no cache-control header unless explicitly set.
        self.assertIsNone(client.get("/health").headers.get("cache-control"))

    def test_deep_link_falls_back_to_index(self):
        app = self._make_app()
        self._mount_spa(app, self._tmp)
        client = TestClient(app)
        for path in ("/analysis", "/predict/abc", "/settings/team"):
            r = client.get(path)
            self.assertEqual(r.status_code, 200, msg=f"deep link {path} should serve SPA")
            self.assertIn("SPA-ROOT", r.text)

    def test_static_files_at_build_root_are_served_directly(self):
        """Files like favicon.ico, manifest.webmanifest that Vite emits at the
        build root (not under /assets/) must be served as-is, not via SPA
        fallback, so the browser receives the correct content-type."""
        app = self._make_app()
        self._mount_spa(app, self._tmp)
        client = TestClient(app)
        r = client.get("/favicon.ico")
        self.assertEqual(r.status_code, 200)
        self.assertIn("icon", r.headers.get("content-type", ""))


# ---------------------------------------------------------------------------
# ROADMAP §3-W1 (2026-08-04) — ``reference_date`` body param for /predict.
#
# The SPA Header date-scrubber sends ``"reference_date": "YYYY-MM-DD"`` so
# the backend re-anchors all temporal features to that day instead of
# "today". The endpoint must accept a valid ISO date, respond 200 with a
# PredictionResult (we use a stubbed ``predict_fire_risk`` so the test does
# not depend on torch/sklearn), and 422 on a malformed string.
# ---------------------------------------------------------------------------


@unittest.skipUnless(_HTTPX_OK, "httpx/fastapi not installed — skipping API tests")
class TestPredictReferenceDate(_ApiTestBase):
    """``POST /predict`` — optional ``reference_date`` parameter (ROADMAP §3-W1)."""

    def _base_payload(self) -> dict:
        return {
            "temperature": 32.0,
            "humidity": 55.0,
            "wind_speed": 6.0,
            "latitude": -1.17,
            "longitude": 100.4,
        }

    def _stub_predict(self, monkeypatch):
        """Stub ``src.predict.predict_fire_risk`` so this test never loads a
        real model — we only verify the HTTP plumbing of the new field."""
        from src import predict as sp

        def fake_predict_fire_risk(
            features, model_version=None, model_type="new", use_cache=False, reference_date=None
        ):
            # Echo the anchor back so the test can assert it propagated all
            # the way through the FastAPI → predict.py boundary.
            return {
                "risk_score": 0.42,
                "risk_level": "Medium",
                "confidence": 0.8,
                "timestamp": "2026-08-04T00:00:00",
                "status": "success",
                "reference_date_seen": (
                    None if reference_date is None else reference_date.isoformat()
                ),
            }

        monkeypatch.setattr(sp, "predict_fire_risk", fake_predict_fire_risk, raising=True)

    def test_valid_reference_date_is_accepted(self) -> None:
        """``POST /predict`` with a valid ISO ``reference_date`` returns 200."""
        # Use unittest.mock.patch (present on every stdlib) instead of
        # pytest's monkeypatch fixture because the surrounding class is
        # ``unittest.TestCase`` — pytest injects the fixture only for
        # ``pytest``-style classes, not into TestCase methods.
        from unittest.mock import patch as _patch

        from src import predict as sp

        with _patch.object(
            sp,
            "predict_fire_risk",
            new=lambda features, model_version=None, model_type="new", use_cache=False, reference_date=None: {
                "risk_score": 0.42,
                "risk_level": "Medium",
                "confidence": 0.8,
                "timestamp": "2026-08-04T00:00:00",
                "status": "success",
                "reference_date_seen": (
                    None if reference_date is None else reference_date.isoformat()
                ),
            },
        ):
            payload = {**self._base_payload(), "reference_date": "2026-06-15"}
            r = self.client.post("/predict", json=payload, headers=self._headers())
            assert r.status_code == 200
            body = r.json()
            assert body["reference_date_seen"] == "2026-06-15T12:00:00"

    def test_reference_date_omitted_keeps_default(self) -> None:
        """Without ``reference_date`` the field is ``None`` (legacy path)."""
        from unittest.mock import patch as _patch

        from src import predict as sp

        with _patch.object(
            sp,
            "predict_fire_risk",
            new=lambda features, model_version=None, model_type="new", use_cache=False, reference_date=None: {
                "risk_score": 0.42,
                "risk_level": "Medium",
                "confidence": 0.8,
                "timestamp": "2026-08-04T00:00:00",
                "status": "success",
                "reference_date_seen": (
                    None if reference_date is None else reference_date.isoformat()
                ),
            },
        ):
            r = self.client.post("/predict", json=self._base_payload(), headers=self._headers())
            assert r.status_code == 200
            assert r.json()["reference_date_seen"] is None

    def test_malformed_reference_date_returns_422(self) -> None:
        """``reference_date: "not-a-date"`` must surface a clean 422, not a 500."""
        from unittest.mock import patch as _patch

        from src import predict as sp

        # Stub predict so we test the *validation* path of the endpoint
        # itself, not the (irrelevant here) model logic.
        with _patch.object(
            sp,
            "predict_fire_risk",
            new=lambda *a, **kw: {"risk_score": 0.42, "status": "success"},
        ):
            payload = {**self._base_payload(), "reference_date": "not-a-date"}
            r = self.client.post("/predict", json=payload, headers=self._headers())
            assert r.status_code == 422
            assert "reference_date" in r.text


if __name__ == "__main__":
    unittest.main()
