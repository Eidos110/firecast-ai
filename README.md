# FireCast

[![CI](https://github.com/Eidos110/firecast-ai/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/Eidos110/firecast-ai/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12-blue)](pyproject.toml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688)](requirements.txt)
[![React 18](https://img.shields.io/badge/React-18-61dafb)](frontend_react/package.json)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

**FireCast** is a fire-risk prediction platform for Indonesia. A FastAPI backend
and a React SPA are served by a single process; the active model is the **V4.2
two-leg stack** — LightGBM and XGBoost probabilities combined by a
`LogisticRegressionCV` meta-learner and isotonic-calibrated before the decision
threshold is applied.

## Features

| Feature | Description |
|---|---|
| Fire risk prediction | `/predict` returns a calibrated `risk_score`, risk band, SHAP top features and model provenance |
| Interactive map | Leaflet map with risk heatmap, AOI drawing and wind vectors |
| AOI batch | Draw a polygon → server-side grid → `/predict/aoi` batch inference |
| Analytics trend | Per-day p10/p50/p90 risk series from the processed features dataset |
| Geocoding | Local 378-city registry with Nominatim fallback |
| i18n | English and Indonesian, persisted in `localStorage` |
| Model registry | SQLModel-backed version registry with activation under `/api/models/*` |
| Single-service deploy | One uvicorn worker serves the API and the built SPA on `:7860` |

## Quick start

Requirements: **Python 3.12** and **Node 20+**.

```bash
cp .env.example .env          # set API_SECRET_KEY
pip install -r requirements.txt

# Terminal 1 — API only (port 8000)
python launch_prototype.py --mode api

# Terminal 2 — Vite dev server with HMR (port 3000, proxies the API)
cd frontend_react && npm install && npm run dev
```

Production-style single service:

```bash
cd frontend_react && npm run build && cd ..
python start_api.py           # API + SPA on :7860
```

Or with Docker:

```bash
cp .env.example .env
docker compose up -d --build
```

## Architecture

```
frontend_react/          React 18 + Vite + TypeScript SPA
  src/App.tsx            3-area layout (topbar / sidebar + map / diagnostic)
  src/api/               typed fetch client + react-query hooks
  src/store/             zustand stores (inference, UI, toasts)
frontend/
  locales/               shared en.json / id.json (single source)
  themes/tokens.json     design tokens (consumed by Tailwind and TypeScript)
src/
  geo_api.py             FastAPI app: routing, rate limits, CORS
  geo_api_spa.py         SPA static mount + history-mode fallback
  api/models.py          /api/models router (X-API-Key protected)
  predict.py             serving orchestration + calibration
  features/              single-sample feature builder + SHAP explanation
  models/                lgbm, xgb, cnn (legacy), registry
  geo/services.py        locations, geocode, trend, AOI grid/batch
  database.py            SQLModel engine and model-registry tables
  config.py              typed config + legacy module-level aliases
add_new_model/           active V4.2 bundle (tracked binaries, ~2.5 MB)
models/                  legacy CNN + LightGBM bundle
data/                    feature CSV/parquet, locations.json
tests/                   pytest suite (API, parity, security, inference)
```

## API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | — | liveness probe |
| GET | `/geo/locations` | — | city registry |
| GET | `/geo/geocode?q=` | — | local → Nominatim lookup |
| GET | `/analytics/trend?lat&lon&days` | — | per-day risk series |
| POST | `/predict` | `X-API-Key` | single-point prediction |
| POST | `/predict/aoi` | `X-API-Key` | polygon grid batch |
| GET/POST | `/api/models/*` | `X-API-Key` | registry + activation |
| POST | `/admin/cache/invalidate` | `X-API-Key` | clear prediction cache |
| GET | `/admin/cache/stats` | `X-API-Key` | cache snapshot |
| POST | `/admin/db/purge` | `X-API-Key` | prediction-retention purge |
| GET | `/admin/db/stats` | `X-API-Key` | table statistics |

Example:

```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: $API_SECRET_KEY" -H "Content-Type: application/json" \
  -d '{"temperature":32,"humidity":45,"wind_speed":5,
       "latitude":-1.17,"longitude":100.4,
       "rainfall":0,"reference_date":"2026-06-15"}'
```

`reference_date` (optional, ISO `YYYY-MM-DD`) re-anchors the seasonal
`month`/`day`/`doy` features. Interactive docs: `/docs` (OpenAPI).

Rate limits: `/predict` 30 req/min and `/predict/aoi` 10 req/min per IP.

## Model

Active bundle: `add_new_model/` — **V4.2 cross-section, 34 features**.

| Component | Detail |
|---|---|
| Base learners | LightGBM `4.6.0`, XGBoost `3.3.0` (versions must match training exactly) |
| Meta-learner | `LogisticRegressionCV`, 5-fold OOF over `[p_lgbm, p_xgb]` |
| Calibration | Isotonic fitted on the validation split (`calibration_isotonic.pkl`) |
| Decision threshold | `0.5316` on the calibrated scale (`threshold_config.json`; surfaced as `decision_threshold` in responses) |
| Validation | `VERSION.json` → `validation_status: "validated"` (test AUC 0.842, Brier 0.164) |

Set `FC_DISABLE_CALIBRATION=1` to A/B test the uncalibrated surface.

The legacy path (`model_type="legacy"`) uses the CNN + LightGBM mean ensemble
in `models/` and is kept for comparison only — it is not the default. The GRU
leg was retired with V4.2; no GRU code or artifacts remain.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `API_SECRET_KEY` | — (required) | `X-API-Key` value; empty or placeholder values are rejected at startup |
| `HOST` / `PORT` | `0.0.0.0` / `7860` | `start_api.py` bind address |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | launcher defaults |
| `ALLOWED_ORIGINS` | localhost dev list | CORS allow-list (comma-separated) |
| `ML_DEVICE` | `auto` | `auto` / `cpu` / `cuda` |
| `APP_ENV` | `development` | observability environment |
| `SENTRY_DSN` | — | optional error reporting |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | optional distributed tracing |

See [.env.example](.env.example) for the full list.

## Development

```bash
make setup          # Python dev deps + npm ci
make api            # uvicorn --reload on :8000
make dev            # Vite on :3000
make test           # pytest
make lint           # ruff
make check          # lint + backend tests + frontend typecheck/tests
```

Quality gates enforced in CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)):
ruff, black, `compileall`, pytest with coverage (gate 40%), frontend
typecheck/lint/tests, Lighthouse performance audit and a Docker smoke build.

## Deployment

### Hugging Face Spaces

`scripts/deploy_hf_space.py` builds the SPA locally, stages an allowlist
(`src/`, `models/`, `add_new_model/`, parquet data, `locations.json`, the SPA
build), uploads via the Hub API, waits for `RUNNING` and verifies `/health`.
`API_SECRET_KEY` is configured as an encrypted Space secret — never a repo
file.

### Docker

`Dockerfile` is multi-stage: Node 20 builds the SPA, Python 3.12 serves both.
The target port is `7860`. `docker-compose.yml` runs the single service; the
`production` profile adds nginx for TLS termination.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `/predict` returns 500 with a model error | The bundle under `add_new_model/` is incomplete. Required files: `lgb_model.pkl`, `xgb_model.pkl`, `scaler_all.pkl`, `stacking_weights.pkl`, `calibration_isotonic.pkl`, `feature_cols.json`, `threshold_config.json` |
| `ModuleNotFoundError: No module named 'src'` | Run from the repo root, or set `PYTHONPATH` to it |
| `/` returns 404 | `frontend_react/build/` is missing — run `npm run build`, or use the Vite dev server |
| 401/500 from protected routes | `X-API-Key` missing or wrong, or `API_SECRET_KEY` unset/placeholder |
| HTTP 429 | Per-IP rate limit exceeded (`/predict` 30/min, `/predict/aoi` 10/min) |

## Security

Never commit `.env` or service-account keys. `secrets/` is gitignored and
excluded from Docker builds. Secret scanning (`detect-secrets`) runs in CI and
rejects commits containing credential-like strings. See
[SECURITY.md](SECURITY.md) for the full policy and rotation status.

## License

Released under the [MIT License](LICENSE).
