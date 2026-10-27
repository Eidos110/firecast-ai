# FireCast

[![CI](https://github.com/Eidos110/firecast-ai/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/Eidos110/firecast-ai/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12-blue)](pyproject.toml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688)](requirements.txt)
[![React 18](https://img.shields.io/badge/React-18-61dafb)](frontend_react/package.json)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

FireCast is a fire-risk prediction platform for Indonesia. It pairs a FastAPI
backend with a React single-page application, both served by one process. The
active prediction model is a two-leg stacking ensemble (LightGBM and XGBoost
combined by a logistic-regression meta-learner) whose output is
isotonic-calibrated before the decision threshold is applied.

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [API reference](#api-reference)
- [Prediction model](#prediction-model)
- [Configuration](#configuration)
- [Development](#development)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Security](#security)
- [License](#license)

## Features

| Feature | Description |
|---|---|
| Point prediction | `POST /predict` returns a calibrated risk score, risk band, SHAP top features and model provenance |
| Area-of-interest batch | Draw a polygon in the browser; the server builds the grid and runs batch inference via `POST /predict/aoi` |
| Interactive map | Leaflet map with a risk heatmap, AOI editor and wind vectors |
| Risk trend analytics | Per-day p10/p50/p90 risk series derived from the processed feature dataset |
| Geocoding | Local registry of 378 Indonesian cities with a Nominatim fallback |
| Internationalization | English and Indonesian interfaces, persisted per browser |
| Model registry | Versioned model registry with activation control, backed by SQLModel |
| Single-process deployment | One uvicorn worker serves both the API and the built SPA on port 7860 |

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                       Browser (SPA)                         │
│        Leaflet map · AOI editor · diagnostics panel         │
└─────────────────────────────┬───────────────────────────────┘
                              │ JSON over HTTP
┌─────────────────────────────▼───────────────────────────────┐
│                 FastAPI (uvicorn, port 7860)                │
│   /predict · /predict/aoi · /geo/* · /analytics/* · /admin/*│
│        rate limiting · CORS allow-list · X-API-Key auth     │
└─────────────────────────────┬───────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│                      Serving stack                          │
│   feature builder → LGBM + XGBoost → LR meta → isotonic     │
│   SHAP explanation · model registry (SQLModel/SQLite)       │
└─────────────────────────────────────────────────────────────┘
```

### Repository layout

```text
frontend_react/          React 18 + Vite + TypeScript SPA
  src/App.tsx            Three-area layout: topbar, sidebar + map, diagnostics
  src/api/               Typed fetch client and react-query hooks
  src/store/             Zustand stores (inference, UI, toasts)
frontend/
  locales/               Shared en.json and id.json (single source)
  themes/tokens.json     Design tokens consumed by Tailwind and TypeScript
src/
  geo_api.py             FastAPI application: routing, rate limits, CORS
  geo_api_spa.py         SPA static mount and history-mode fallback
  api/models.py          Model-registry router (X-API-Key protected)
  predict.py             Serving orchestration and calibration
  features/              Single-sample feature builder and SHAP explanation
  models/                LightGBM, XGBoost, CNN (legacy) loaders and registry
  geo/services.py        Locations, geocoding, trends, AOI grid and batching
  database.py            SQLModel engine and model-registry tables
  config.py              Typed configuration with legacy aliases
add_new_model/           Active V4.2 serving bundle (~2.5 MB, tracked in git)
models/                  Legacy CNN + LightGBM bundle
data/                    Feature dataset (CSV/parquet) and locations.json
tests/                   Pytest suite: API, train/serve parity, security
```

## Quick start

Prerequisites: Python 3.12 and Node 20 or newer.

### Development (two terminals)

```bash
cp .env.example .env               # then set API_SECRET_KEY
pip install -r requirements.txt
```

```bash
# Terminal 1: API server on port 8000
python launch_prototype.py --mode api
```

```bash
# Terminal 2: Vite dev server on port 3000 (proxies API requests)
cd frontend_react && npm install && npm run dev
```

### Production-style (single process)

```bash
cd frontend_react && npm run build && cd ..
python start_api.py                # API and SPA on port 7860
```

### Docker

```bash
cp .env.example .env
docker compose up -d --build
```

## API reference

All mutating and administrative endpoints require the `X-API-Key` header,
whose value is set through the `API_SECRET_KEY` environment variable.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | — | Liveness probe |
| GET | `/geo/locations` | — | City registry |
| GET | `/geo/geocode?q=` | — | Local registry lookup, then Nominatim |
| GET | `/analytics/trend?lat&lon&days` | — | Per-day risk series |
| POST | `/predict` | `X-API-Key` | Single-point prediction |
| POST | `/predict/aoi` | `X-API-Key` | Polygon grid batch prediction |
| GET/POST | `/api/models/*` | `X-API-Key` | Model registry and activation |
| POST | `/admin/cache/invalidate` | `X-API-Key` | Clear the prediction cache |
| GET | `/admin/cache/stats` | `X-API-Key` | Cache snapshot |
| POST | `/admin/db/purge` | `X-API-Key` | Prediction-retention purge |
| GET | `/admin/db/stats` | `X-API-Key` | Table statistics |

Rate limits per client IP: 30 requests per minute for `/predict` and 10 for
`/predict/aoi`.

### Example

```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: $API_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "temperature": 32,
    "humidity": 45,
    "wind_speed": 5,
    "rainfall": 0,
    "latitude": -1.17,
    "longitude": 100.4,
    "reference_date": "2026-06-15"
  }'
```

`reference_date` is optional and accepts ISO dates (`YYYY-MM-DD`). When
provided, the seasonal `month`, `day` and `day-of-year` features are computed
against that date. Interactive OpenAPI documentation is served at `/docs`.

## Prediction model

The active serving bundle lives in `add_new_model/` and is identified as
**V4.2 (cross-section, 34 features)** in `VERSION.json`.

| Component | Detail |
|---|---|
| Base learners | LightGBM 4.6.0 and XGBoost 3.3.0 (serving versions must match training exactly) |
| Meta-learner | `LogisticRegressionCV` trained on 5-fold out-of-fold predictions of both base learners |
| Calibration | Isotonic regression fitted on the validation split |
| Decision threshold | 0.5316 on the calibrated scale (`threshold_config.json`; returned as `decision_threshold`) |
| Validation status | `validated`: test AUC 0.842, Brier score 0.164 |

The legacy prediction path (`model_type="legacy"` in the API) uses the CNN +
LightGBM mean ensemble in `models/`. It is retained for comparison only and
is not the default.

## Configuration

All variables are optional unless noted. See [.env.example](.env.example) for
the complete list.

| Variable | Default | Purpose |
|---|---|---|
| `API_SECRET_KEY` | **required** | Value accepted in the `X-API-Key` header. Empty or placeholder values are rejected at startup. |
| `HOST` / `PORT` | `0.0.0.0` / `7860` | Bind address for `start_api.py` |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | Bind address for `launch_prototype.py` |
| `ALLOWED_ORIGINS` | localhost development list | CORS allow-list, comma-separated origins |
| `FC_DISABLE_CALIBRATION` | unset | Set to `1` to bypass isotonic calibration (A/B comparison only) |
| `ML_DEVICE` | `auto` | Compute device: `auto`, `cpu` or `cuda` |
| `APP_ENV` | `development` | Environment label for observability |
| `SENTRY_DSN` | unset | Optional Sentry error reporting |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | Optional OpenTelemetry tracing endpoint |

## Development

```bash
make setup          # Install Python dev dependencies and npm ci
make api            # Run uvicorn with reload on port 8000
make dev            # Run Vite on port 3000
make test           # Run the pytest suite
make lint           # Run ruff
make check          # Lint + backend tests + frontend typecheck and tests
```

Continuous integration ([.github/workflows/ci.yml](.github/workflows/ci.yml))
enforces the following gates on every push and pull request:

- Ruff and Black formatting checks, plus `compileall` on `src/`
- Pytest with coverage (minimum 40%)
- Frontend typecheck, ESLint, unit tests and production build
- Lighthouse performance audit of the built SPA
- Docker image smoke build

## Deployment

### Hugging Face Spaces

`scripts/deploy_hf_space.py` builds the SPA locally, stages an explicit
allowlist of files (`src/`, model bundles, parquet data, `locations.json`,
and the SPA build), uploads them through the Hub API, waits for the Space to
reach `RUNNING`, and verifies `/health`. The API key is provided to the Space
as an encrypted secret, never as a repository file.

### Docker

The `Dockerfile` is a multi-stage build: Node 20 compiles the SPA, and
Python 3.12 serves the API and static assets on port 7860. Compose runs this
as a single service; the `production` profile adds an nginx reverse proxy for
TLS termination.

## Troubleshooting

| Symptom | Cause and resolution |
|---|---|
| `POST /predict` returns 500 with a model error | The serving bundle in `add_new_model/` is incomplete. Required files: `lgb_model.pkl`, `xgb_model.pkl`, `scaler_all.pkl`, `stacking_weights.pkl`, `calibration_isotonic.pkl`, `feature_cols.json`, `threshold_config.json` |
| `ModuleNotFoundError: No module named 'src'` | Run commands from the repository root, or set `PYTHONPATH` to it |
| The SPA route returns 404 | `frontend_react/build/` does not exist. Build it with `npm run build`, or use the Vite dev server |
| Protected endpoints return 401 or 500 | The `X-API-Key` header is missing or incorrect, or `API_SECRET_KEY` is unset or a placeholder |
| HTTP 429 responses | Per-IP rate limit reached (30/min for `/predict`, 10/min for `/predict/aoi`) |

## Security

`.env` and `secrets/` are gitignored and excluded from Docker builds.
`detect-secrets` runs in CI and rejects commits that contain
credential-like strings. Vulnerabilities should be reported privately; see
[SECURITY.md](SECURITY.md) for the reporting process and the current
rotation status of known secrets.

## License

This project is released under the [MIT License](LICENSE).
