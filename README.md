# 🔥 FireCast

Fire risk prediction for Indonesia: a FastAPI backend and a React SPA served by
one process. The active model is the **V4.2 two-leg stack** — LightGBM and
XGBoost probabilities combined by a `LogisticRegressionCV` meta-learner and
isotonic-calibrated.

## Features

| Feature | Description |
|---|---|
| Fire risk prediction | `/predict` returns calibrated `risk_score`, risk band, SHAP top features and provenance |
| Interactive map | Leaflet map with risk heatmap, AOI draw, wind vectors |
| AOI batch | Draw a polygon → server-side grid → `/predict/aoi` |
| Analytics trend | Per-day p10/p50/p90 series from the processed features dataset |
| Geocoding | Local 378-city registry → Nominatim fallback |
| i18n | English/Indonesian, persisted in `localStorage` |
| Model registry | SQLModel-backed version registry under `/api/models/*` |
| Single service | One uvicorn worker serves API + built SPA on `:7860` |

## Quick start

Requirements: Python 3.12 (pinned conda env in `AGENTS.md`), Node 20+, npm.

```bash
cp .env.example .env          # set API_SECRET_KEY
pip install -r requirements.txt

# Terminal 1 — API (port 8000)
python launch_prototype.py --mode api

# Terminal 2 — Vite dev server with HMR (port 3000, proxies /predict etc.)
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
  src/App.tsx            3-area layout (topbar / sidebar+map / diagnostic)
  src/api/               typed fetch client + react-query hooks
  src/store/             zustand stores (inference, UI, toasts)
frontend/
  locales/               shared en.json / id.json (single source)
  themes/tokens.json     design tokens (consumed by Tailwind + TS)
src/
  geo_api.py             FastAPI app, routing, rate limits, CORS
  geo_api_spa.py         SPA static mount + history fallback
  api/models.py          /api/models router (X-API-Key)
  predict.py             serving orchestration + calibration
  features/              single-sample feature builder + SHAP
  models/                lgbm, xgb, cnn (legacy), registry
  geo/services.py        locations, geocode, trend, AOI grid/batch
  database.py            SQLModel engine and model registry tables
  config.py              typed config + legacy module-level aliases
add_new_model/           active V4.2 bundle (gitignored binaries)
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
| GET | `/admin/db/stats` | `X-API-Key` | table stats |

Example:

```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: $API_SECRET_KEY" -H "Content-Type: application/json" \
  -d '{"temperature":32,"humidity":45,"wind_speed":5,
       "latitude":-1.17,"longitude":100.4,
       "rainfall":0,"reference_date":"2026-06-15"}'
```

`reference_date` (optional, ISO `YYYY-MM-DD`) re-anchors the seasonal
`month`/`day`/`doy` features.

OpenAPI: `/docs`.

## Model

Active bundle: `add_new_model/` (V4.2 cross-section, 34 features).

- Base learners: LightGBM `4.6.0`, XGBoost `3.3.0`.
- Meta: `LogisticRegressionCV`, 5-fold OOF over `[p_lgbm, p_xgb]`.
- Calibration: isotonic fitted on VAL (`calibration_isotonic.pkl`).
- Decision threshold: `0.5316` on the calibrated scale
  (`threshold_config.json`; surfaced as `decision_threshold` in responses).
- Validation: `VERSION.json` → `validation_status: "validated"` (test AUC
  0.842, Brier 0.164).

Kill switch for A/B testing the calibrated surface:
`FC_DISABLE_CALIBRATION=1`.

Legacy path: `model_type="legacy"` uses the CNN + LightGBM mean ensemble in
`models/`. It is kept for comparison, not the default.

The GRU leg was retired with V4.2; no GRU code or artifacts remain.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `API_SECRET_KEY` | — (required for protected routes) | `X-API-Key` value; placeholders rejected |
| `HOST` / `PORT` | `0.0.0.0` / `7860` | `start_api.py` bind |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | launcher defaults |
| `ALLOWED_ORIGINS` | localhost dev list | CORS allow-list (CSV) |
| `ML_DEVICE` | `auto` | `auto` / `cpu` / `cuda` |
| `APP_ENV` | `development` | observability environment |
| `SENTRY_DSN` | — | optional error reporting |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | optional tracing |

See `.env.example`.

## Development

```bash
make setup          # Python dev deps + npm ci
make api            # uvicorn --reload on :8000
make dev            # Vite on :3000
make test           # pytest
make lint           # ruff
make check          # lint + backend tests + frontend typecheck/tests
```

Quality gates used in CI:

```bash
python -m ruff check .
python -m black --check src tests main.py start_api.py launch_prototype.py
python -m compileall -q src
python -m pytest tests/ -q
cd frontend_react && npm run typecheck && npm run lint && npm test && npm run build
```

## Deployment

### Hugging Face Spaces

`scripts/deploy_hf_space.py` builds the SPA locally, stages an allowlist
(`src/`, `models/`, `add_new_model/`, parquet data, `locations.json`, the SPA
build), uploads via the Hub API, waits for `RUNNING` and verifies `/health`.
`API_SECRET_KEY` is a Space secret, never a repo file.

### Docker

`Dockerfile` is multi-stage: Node 20 builds the SPA, Python 3.12 serves both.
Target port is `7860`. `docker-compose.yml` runs the single service; the
`production` profile adds nginx for TLS.

## Troubleshooting

- **`/predict` returns 500 with a model error** — the bundle under
  `add_new_model/` is incomplete. Required: `lgb_model.pkl`, `xgb_model.pkl`,
  `scaler_all.pkl`, `stacking_weights.pkl`, `feature_cols.json`,
  `threshold_config.json`. All are gitignored.
- **`ModuleNotFoundError: No module named 'src'`** — run from the repo root or
  set `PYTHONPATH` to it.
- **`/` returns 404** — `frontend_react/build/` is missing. Run
  `npm run build`, or use the Vite dev server.
- **401/500 from protected routes** — `X-API-Key` missing/wrong, or
  `API_SECRET_KEY` unset/placeholder.
- **Rate limit exceeded** — `/predict` is capped at 30/min per IP; `/predict/aoi`
  at 10/min.

## Security

Never commit `.env` or service-account keys. `secrets/` is gitignored and
excluded from Docker builds. Report issues per `SECURITY.md`.

## License

MIT — see `LICENSE`.
