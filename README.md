# 🔥 FireCast

**Fire Risk Prediction System using Ensemble Machine Learning**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status: Prototype](https://img.shields.io/badge/Status-Prototype-orange.svg)]
[![Docker Ready](https://img.shields.io/badge/Docker-Ready-blue.svg)](docker-compose.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-teal.svg)](http://localhost:7860/docs)
[![React SPA](https://img.shields.io/badge/React-SPA_4.0-61dafb.svg)](frontend_react/)

FireCast is an advanced fire forecasting and risk prediction system. It combines an **ensemble of deep learning and gradient boosting** → to estimate fire risk using meteorological, spectral, and temporal features in near real time.

> **UI Stack v4.0** (Tahap E, 2026-07): the Streamlit shell has been retired and replaced by a single-page React app under `frontend_react/`. One uvicorn worker now serves **both** the FastAPI backend and the compiled SPA at `/`. See [`docs/react-spa-migration/PLAN.md`](docs/react-spa-migration/PLAN.md) for the per-stage changelog.

---

## 🗂 Table of Contents

- [Features](#-features)
- [Quick Start](#-quick-start)
- [Architecture](#-architecture)
- [Installation](#-installation)
- [Usage](#-usage)
- [API Reference](#-api-reference)
- [Model Architecture](#-model-architecture)
- [Project Structure](#-project-structure)
- [Deployment](#-deployment)
- [Development](#-development)
- [Troubleshooting](#-troubleshooting)
- [License](#-license)
- [Contact](#-contact)

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔥 Fire Risk Prediction | Real-time risk scores from an ensemble + stacking model |
| 🌍 Interactive Map (React+Leaflet) | Risk heatmap, AOI draw/edit, fire-point pulse, wind vectors |
| 🧪 Engineer Console (V4) | 3-column layout: layers + map + diagnostic with SHAP bars + API log |
| 🌐 i18n (id/en) | full `spa.*` translation namespace, persisted to `localStorage` |
| 🏅 Weather Integration | Live weather via OpenWeatherMap with graceful demo fallback |
| 🔎 Two-tier Geocoding | Local Indonesia DB (378 cities) → Nominatim/OSM fallback |
| 📊 Analytics Trends | Per-day p10 / p50 / p90 band from the features CSV |
| 🎯 AOI Batch Prediction | Draw a polygon → grid-sample → batch `/predict/aoi` |
| 🐳 Docker Ready | One-command `docker-compose up` (single service, multi-stage build) |
| 🔌 REST API | FastAPI + OpenAPI at `/docs` |
| 💻 CLI | `python main.py` for headless inference runs |
| 🔒 No-Keys Demo | Fully functional without a model or API keys (`ENABLE_DEMO_MODE=true`) |

---

## 🚀 Quick Start

Three ways to run, all from the repo root.

### Option A → Local dev (recommended for engineers)

```bash
# 1. Backend + SPA dev server (two terminals)
cp .env.example .env
python start_api.py                         # API + SPA at :7860 (after `npm run build`)
# Other terminal:
cd frontend_react && npm install && npm run dev   # Vite HMR :3000, proxies API to :8000
```

### Option B → Single-service (Hugging Face Spaces / Render / production-y)

```bash
cp .env.example .env
cd frontend_react && npm install && npm run build && cd ..
python start_api.py                         # serves / from frontend_react/build + API
```

### Option C → Docker (one command, multi-stage build)

```bash
cp .env.example .env
docker-compose up -d                         # builds React + Python, serves on :7860
docker-compose logs -f firecast
```

### Verify services

| Service | URL |
|---|---|
| SPA shell | http://localhost:7860/ |
| API Server | http://localhost:7860/predict (and all `/api/*`, `/geo/*`, `/analytics/*`, `/health`) |
| API Docs (Swagger UI) | http://localhost:7860/docs |
| Health Check | http://localhost:7860/health |
| Vite dev server (Option A only) | http://localhost:3000 |

---

## 🏗 Architecture

```
              +--------------------------------------+
              |            uvicorn :7860              |
              |  (start_api.py — single worker)       |
              +--------------------------------------+
              |  src/geo_api.py   -> FastAPI routes   |
              |    /predict /weather /geo /analytics  |
              |    /api /admin /health /docs          |
              |                                      |
              |  src/geo_api_spa.py -> StaticFiles+SPA|
              |    GET /          -> index.html (no cache)
              |    GET /assets/*   -> hashed assets, 1y immutable
              |    GET *           -> SPA fallback (history mode)
              +--------------------------------------+
                            ^
                            |
                  +---------+---------+
                  | frontend_react/   |
                  |  React + Vite SPA  |
                  |  zustand + react-query + Leaflet,
                  |  recharts, i18next (id/en)
                  +--------------------+
```

The backend never returns 0.5 silently on model error (legacy bug #3) → it raises `PredictionError` which the API translates to HTTP 500. The SPA falls back to deterministic `mockPredict()` demo data while piping a colour-coded `err` row to the API log panel.

---

## 📦 Installation

### Prerequisites

- **Python 3.12** (matches training env, avoids pickle `InconsistentVersion`)
- **Node 20** (for `frontend_react/` build; CI uses 20)
- **Docker** (optional)

### Python deps

```bash
# Use the pinned env to avoid libtorch/sklearn version drift:
"E:\C.TSUBASA\miniconda\envs\FIREvCPU\python.exe" -m pip install -r requirements.txt
```

### React deps

```bash
cd frontend_react
npm install
```

### Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `OPENWEATHER_API_KEY` | (none) | real weather data; demo fallback if missing |
| `API_SECRET_KEY` | (none, rejects placeholders) | gates `/api/models/*`, `/predict/aoi`, `/admin/*` |
| `PORT` | `7860` | uvicorn port (HF Spaces expects 7860) |
| `HOST` | `0.0.0.0` | bind address |
| `ENABLE_DEMO_MODE` | auto-set by `start_api.py` | `true` when model bundle missing |
| `ALLOWED_ORIGINS` | `http://localhost:8501,3000,8000` | CSV CORS allow-list |
| `ML_DEVICE` | `cpu` | torch device |

See `.env.example` for the full list.

---

## 🎮 Usage

### React SPA

Production build lives under `frontend_react/build/`. In dev use `npm run dev` for HMR; in production `start_api.py` serves the compiled bundle from `/`.

The 3-column V4 layout (Header / Layers+Map+Filters / Diagnostic + Timeline) is composed in `frontend_react/src/App.tsx`:

| Region | Component | Responsibility |
|---|---|---|
| Topbar | `Header.tsx` | brand + model/run/EPSG pills + status LED (polls `/health` 30s) |
| Left sidebar | `LayerControlPanel.tsx`, `FiltersPanel.tsx`, `ModelSelectPanel.tsx` | 8 layer toggles + opacity, region/risk/date filters, model + Run Inference |
| Map | `MapArea.tsx` + `InteractiveMap.tsx` + `MapOverlays.tsx` | Leaflet map, AOI draw, compass + coord readout |
| Right diagnostic | `RightDiagnostic.tsx` | P(fire) hero, MetricGrid, ShapList, RiskTrendChart (Recharts), RawJsonPanel, ApiLogBox |
| Bottom bar | `TimelineScrubber.tsx` | H-24 → H+72 scrubber, play/pause, export JSON |

### REST API

Available under **http://localhost:7860/docs** with full Swagger documentation.

### CLI

```bash
python main.py --predict
```

---

## 🧠 Model Architecture

FireCast uses an **ensemble / stacking** model family whose outputs are calibrated and passed through an optimised decision threshold (targeting ~80% recall for fire risk):

```
Input Features (40+ dimensions)
        |
   +----|------------------------+
   |    |                        |
  CNN   LightGBM       CausalGRU + XGBoost + Meta
   |     |                |  |       |
   +--|---+               +--+-------+
      +--> calibrated average / stacking prediction
```

### Risk thresholds (single source: `frontend/themes/tokens.json`)

| Tier | Score range | Color |
|---|---|---|
| rendah (Low) | `< 0.30` | `#22c55e` |
| sedang (Medium) | `0.30 – 0.50` | `#fb923c` |
| tinggi (High) | `0.50 – 0.70` | `#ef4444` |
| sangat_tinggi (Extreme) | `>= 0.70` | `#7f1d1d` |

### Feature Engineering

| Category | Examples |
|---|---|
| Temporal | Lag variables, rolling averages (3/7/14-day windows) |
| Fire Indices | VPD, fuel dryness, extreme-weather indices |
| Spectral | NDVI, NDWI, NBR, EVI |
| Cyclical | Month & day-of-year sinusoidal encoding |
| Trends | 3-day deltas, precipitation deficit |

---

## 🗂 Project Structure (post React-SPA migration)

```
firecast/
├── src/                         # Backend
│   ├── config.py                # dataclass config (single source of paths)
│   ├── geo_api.py               # FastAPI app + endpoints (TAHAP B added /geo/* /analytics/* /predict/aoi)
│   ├── geo_api_spa.py           # TAHAP E — StaticFiles mount + SPA history-mode fallback
│   ├── predict.py               # inference + calibration
│   ├── feature_engineering.py   # feature builder
│   ├── api/models.py            # /api/models/* CRUD + activate endpoint
│   ├── geo/services.py          # TAHAP B — Sandbox-safe port of frontend utils
│   └── models/                  # cnn.py, lgbm.py, xgb.py, bigru.py, causal_gru.py
│
├── frontend_react/              # TAHAP C-D-E: React SPA (single UI)
│   ├── src/
│   │   ├── App.tsx              # 3-area grid orchestrator
│   │   ├── api/                 # client.ts + hooks.ts (react-query v5)
│   │   ├── store/inferenceStore.ts # zustand store
│   │   ├── i18n/                # i18next wired to frontend/locales/(en,id).json
│   │   ├── theme/               # tokens.ts, risk.ts, useTheme.ts (dark/light)
│   │   └── components/          # Header, SidebarNav, MapArea, RightDiagnostic, TimelineScrubber…
│   ├── vite.config.ts          # base './', manualChunks (vendor-leaflet/-charts/...)
│   └── lighthouserc.cjs         # TAHAP E — SPA perf > 70 gate
│
├── frontend/                    # only design tokens + locales + Streamlit-reference utils kept
│   ├── themes/tokens.json       # single source of truth for colors + risk thresholds
│   └── locales/(en,id).json     # shared i18n (SPA imports these at build time)
│
├── tests/                       # pytest backend + TestClient API
├── notebooks/                   # training notebooks
├── models/                      # legacy CNN+LGBM weights
├── add_new_model/              # stacking model artifacts (lgb/xgb/meta/causal_gru)
├── docs/react-spa-migration/    # PLAN.md — stage-by-stage migration log
│
├── Dockerfile                   # TAHAP E — multi-stage: Node builds React → Python serves
├── docker-compose.yml           # TAHAP E — single-service `firecast` (api + SPA)
├── nginx/conf.d/firecast.conf   # TAHAP E — SPA fallback for HTTPS reverse-proxy
├── start_api.py                 # uvicorn launcher (HF Spaces + dev)
├── Procfile                     # `web: python start_api.py`
├── main.py                      # CLI entry point
├── pyproject.toml               # project metadata
├── requirements.txt             # Python deps (CPU torch, shap, lightgbm, xgboost, fastapi)
└── README.md                    # this file
```

---

## 🔌 API Reference

Full interactive docs at **http://localhost:7860/docs** (Swagger UI).

### Survey of endpoints

| Method | Path | Status | Purpose |
|---|---|---|---|
| GET | `/health` | public | liveness probe |
| POST | `/predict` | public (rate-limited) | single-cell fire risk prediction |
| POST | `/predict/aoi` | gated `X-API-Key` | batch over a GeoJSON polygon + grid size |
| GET | `/weather` | public | OpenWeatherMap proxy |
| GET | `/geo/locations` | public | 378 Indonesian cities from `data/locations.json` |
| GET | `/geo/geocode?q=` | public | Tier-1 local JSON, Tier-2 OSM Nominatim |
| GET | `/analytics/trend?lat&lon&days=7` | public | per-day p10/p50/p90 fire-risk band |
| GET | `/api/models/` | gated | list registered ModelVersion rows |
| POST | `/api/models/register` | gated | register new model version |
| POST | `/api/models/{name}/activate` | gated | activate a model version server-side |
| POST | `/admin/cache/invalidate` | gated | drop data cache without restart |
| GET | `/admin/db/stats` | gated | Prediction table size |

### Example: `/predict` body

```json
{
  "temperature": 30,
  "humidity": 55,
  "wind_speed": 6,
  "latitude": -6.2,
  "longitude": 106.8,
  "fuel_moisture": 20,
  "model_type": "new"
}
```

---

## 🐳 Deployment

### Hugging Face Spaces (default target)

1. Push the repo.
2. The platform reads `Dockerfile` (multi-stage: Node 20 builds React → Python 3.12 serves via `start_api.py` on port 7860).
3. Set secrets **OPENWEATHER_API_KEY** and **API_SECRET_KEY** in the Space settings.
4. `ENABLE_DEMO_MODE` auto-enables if model files are absent → the SPA still boots with mock predictions.

### Docker Compose (dev/staging)

```bash
docker-compose up -d              # build + run single service
docker-compose logs -f firecast
docker-compose down
```

### HTTPS reverse-proxy (optional)

`nginx/conf.d/firecast.conf` proxies everything to `firecast:7860`, serves immutable cache headers for `/assets/`, and falls back to `index.html` for SPA history-mode deep links. Use `docker-compose --profile production up -d`.

---

## 🛠️ Development

### Run tests

| Suite | Command |
|---|---|
| Python backend | `python -m pytest tests/ -q` (or skip Streamlit-only remaining tests with `--ignore=tests/frontend`) |
| React SPA (vitest) | `cd frontend_react && npm test` |
| React typescript strict | `cd frontend_react && npm run typecheck` |
| React lint (eslint) | `cd frontend_react && npm run lint` |
| React build | `cd frontend_react && npm run build` |
| Lighthouse audit | `cd frontend_react && npm run lhci` |

### Code quality

```bash
"E:\C.TSUBASA\miniconda\envs\FIREvCPU\python.exe" -m ruff check src tests      # lint
"E:\C.TSUBASA\miniconda\envs\FIREvCPU\python.exe" -m compileall -q src          # bytecode sanity
```

### Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit changes: `git commit -m 'feat: add feature X'`
4. Push to remote: `git push origin feature/my-feature`
5. Open a Pull Request

Please follow [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines.

---

## 🔧 Troubleshooting

### Models not loading → Demo Mode is active

`start_api.py` checks both `models/*.pth\.pkl` and `add_new_model/*.pkl`. If both are missing, `ENABLE_DEMO_MODE=true` is exported and the SPA returns deterministic `mockPredict()` data. Train models with the notebooks in `notebooks/` or ship prebuilt artifacts.

### `ModuleNotFoundError: No module named 'src'`

```powershell
$env:PYTHONPATH = (Get-Location).Path
python start_api.py
```

### Weather API returning errors

1. Confirm `OPENWEATHER_API_KEY` is set in `.env`.
2. Failure degrades to synthetic weather data (`demo_weather` key in i18n).
3. The ApiLogBox (bottom of the diagnostic column) shows the warn/err string colour-coded.

### SPA serve returns 404 at `/`

You likely ran `start_api.py` without building the SPA first (`frontend_react/build/index.html` missing). The launcher logs `SPA mount skipped … (dev mode)` and serves only the API. Either:

```bash
cd frontend_react && npm run build && cd ..   # build then re-launch
# or run the Vite dev server alongside (Option A in Quick Start)
```

### Port already in use

```powershell
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
python start_api.py        # PORT defaults to 7860; override via $env:PORT
```

---

## 📊 Performance Benchmarks (post SPA migration)

| Component | Metric |
|---|---|
| CNN Inference | ~50 ms / sample |
| LightGBM Inference | ~10 ms / sample |
| Stacking ensemble total | ~70 ms / sample |
| API End-to-End (`/predict`) | < 100 ms |
| SPA initial bundle (gzip) | index.js 37 KB + vendor-charts 151 KB + vendor-leaflet 43 KB |
| Lighthouse Performance (SPA root) | target > 70 (LHCI gate enforces, see `lighthouserc.cjs`) |

---

## 📄 License

This project is licensed under the **MIT License** → see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- [OpenWeatherMap](https://openweathermap.org/) → weather data
- BMKG (Indonesian Meteorological Agency) → supplementary weather data
- [LightGBM](https://lightgbm.readthedocs.io/) + [XGBoost](https://xgboost.readthedocs.io/) → gradient boosting
- [PyTorch](https://pytorch.org/) → deep learning framework
- [FastAPI](https://fastapi.tiangolo.com/) → API framework
- [React](https://react.dev/) + [Vite](https://vitejs.dev/) + [react-query](https://tanstack.com/query/latest) + [Leaflet](https://leafletjs.com/) → SPA stack

---

## 📧 Contact

Questions, bug reports, or feature requests? Open an issue on the GitHub repository.

---

> 🔥 **FireCast** → Protecting forests with AI.
