# 🔥 FireCast

**Fire Risk Prediction System using Ensemble Machine Learning**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status: Prototype](https://img.shields.io/badge/Status-Prototype-orange.svg)]
[![Docker Ready](https://img.shields.io/badge/Docker-Ready-blue.svg)](docker-compose.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-teal.svg)](http://localhost:8000/docs)
[![Streamlit](https://img.shields.io/badge/Streamlit-UI-red.svg)](http://localhost:8501)

FireCast is an advanced fire forecasting and risk prediction system. It combines a **Convolutional Neural Network (CNN)** with **LightGBM** — an ensemble of deep learning and gradient boosting — to estimate fire risk using meteorological, spectral, and temporal features in real time.

---

## 🗂 Table of Contents

- [Features](#-features)
- [Quick Start](#-quick-start)
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
| 🔥 Fire Risk Prediction | Real-time risk scores from an ensemble and stacking model |
| 🗺️ Interactive Map | Risk visualisation with Folium/Streamlit layers and marker sync |
| 🌤️ Weather Integration | Live weather via OpenWeatherMap, BMKG, or demo fallback |
| 🔎 Location Search | Two-tier geocoding: local Indonesian DB + Nominatim/OSM fallback |
| 📊 History Analytics | Historical fire pattern analysis and trend breakdowns |
| ⚙️ What-If Scenarios | Override sensors and parameters to model hypothetical conditions |
| 🐳 Docker Ready | One-command start with `docker-compose up` |
| 🔌 REST API | FastAPI backend with OpenAPI documentation at `/docs` |
| 💻 CLI | `python main.py` for headless inference runs |
| 🔏 No-Keys Demo | Fully functional without a model or API keys |
| 🗺️ AOI Analysis | Draw a polygon on the map to run batch risk predictions across the entire area |

---

## 🚀 Quick Start

FireCast runs in a single command via the unified launcher.

```bash
# 1. Set up the environment
cp .env.example .env

# 2. Launch the prototype
python launch_prototype.py
```

Then open **http://localhost:8501** in your browser.

### Launcher Flags

```bash
python launch_prototype.py --mode frontend   # UI only
python launch_prototype.py --mode api        # API only
python launch_prototype.py --mode both        # UI + API
python launch_prototype.py --mode test        # Run test suite
python launch_prototype.py --demo             # Force demo mode
python launch_prototype.py --port 8502        # Custom UI port
```

### Verify Installation

| Service | URL |
|---|---|
| Frontend (Streamlit) | http://localhost:8501 |
| API Server | http://localhost:8000 |
| API Docs (Swagger UI) | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |

---

## 📦 Installation

### Prerequisites

- **Python** 3.8 or higher
- **pip** or **conda**
- **Docker** (optional, for containerised deployment)

### Option 1 — Using Docker (Recommended)

```bash
cp .env.example .env
docker-compose up -d          # starts frontend + API services
docker-compose logs -f         # view live logs
docker-compose down            # stop all services
```

### Option 2 — Manual Setup

```bash
# Install core + optional extras
pip install -r requirements.txt
pip install -r requirements-frontend.txt    # UI dependencies
pip install -r requirements-api.txt         # API dependencies
pip install -r requirements-dev.txt         # dev & testing tools

# Configure environment variables
cp .env.example .env

# Run the system
streamlit run frontend/app.py              # UI
```

### Environment Variables

| Variable | Purpose |
|---|---|
| `OPENWEATHER_API_KEY` | Weather data from OpenWeatherMap |
| `BMKG_ENABLED` | Enable BMKG (Indonesian weather) provider |
| `APP_ENV` | `development` or `production` |
| `STREAMLIT_PORT` | Frontend port (default: `8501`) |
| `API_PORT` | API port (default: `8000`) |
| `ENABLE_DEMO_MODE` | Allow running without models or API keys |
| `API_SECRET_KEY` | Secret for securing API endpoints |

---

## 🎮 Usage

### Frontend (Streamlit UI)

```bash
streamlit run frontend/app.py
```

Three main tabs:

| Tab | Purpose |
|---|---|
| 🗺️ Prediksi Risiko | Map, weather, vegetation selection, prediction |
| 📊 Analisis Historis | Historical fire statistics & time-series patterns |
| ⚙️ Pengaturan | Model selection, risk tolerance, API keys |

### REST API

```bash
uvicorn src.geo_api:app --reload
```

Available under **http://localhost:8000/docs** with full Swagger documentation.

### CLI

```bash
python main.py --predict
```

### Location Search

FireCast includes a two-tier geocoding engine:

1. **Tier 1 — Local DB**: Instant lookup for Indonesian cities (Riau, Jakarta, Bandung, Medan, …) — no internet required.
2. **Tier 2 — Nominatim**: OpenStreetMap free API as a worldwide fallback.

Search from the map tab → sidebar → *Lokasi* to auto-center the map on any location.

---

## 🧠 Model Architecture

FireCast uses an **ensemble** of two complementary models whose outputs are averaged and passed through an optimised decision threshold (targeting ~80% recall for fire risk).

```
Input Features (40+ dimensions)
        │
   ┌────┴────┐
   │         │
  CNN      LightGBM
(1D Conv +   (Gradient
 BatchNorm)   Boosting)
   │         │
   └────┬────┘
        │   ──► Weighted Average ──► Risk Score + Threshold
```

### Model Components

| Component | Details |
|---|---|
| **CNN (1D)** | Temporal feature extraction via 1D convolutions, batch norm, dropout, and adaptive pooling |
| **LightGBM** | Fast inference, built-in feature importance, handles mixed feature types |
| **Ensemble** | Weighted average → calibrated threshold → probability → risk class |

### Feature Engineering

| Category | Examples |
|---|---|
| Temporal | Lag variables, rolling averages (3/7/14-day windows) |
| Fire Indices | VPD, fuel dryness, extreme-weather indices |
| Spectral | NDVI, NDWI, NBR, EVI |
| Cyclical | Month & day-of-year sinusoidal encoding |
| Trends | 3-day deltas, precipitation deficit |

---

## 📁 Project Structure

```
firecast/
├── 📂 frontend/                   # Streamlit UI
│   ├── app.py                     # Main application entry point
│   ├── components/
│   │   ├── map_interface.py       # Interactive map (Folium)
│   │   ├── results_display.py     # Prediction result panel
│   │   ├── sidebar.py             # Sidebar controls
│   │   └── weather_display.py     # Weather card widget
│   └── utils/
│       ├── data_handler.py        # CSV / data loading
│       ├── prediction_engine.py   # Feature builder + inference
│       └── weather_api.py         # OpenWeatherMap / BMKG / demo clients
│
├── 📂 src/                        # Backend source
│   ├── config.py                  # Settings & environment manager
│   ├── predict.py                 # Prediction pipeline
│   ├── geo_api.py                 # FastAPI routes
│   ├── feature_engineering.py     # Feature builder
│   ├── data_loader.py             # Dataset utilities
│   ├── utils.py                   # Shared helpers
│   └── models/
│       ├── cnn.py                 # CNN model definition
│       ├── lgbm.py                # LightGBM wrapper
│       └── ensemble.py            # Ensemble logic + threshold
│
├── 📂 notebooks/                  # Jupyter notebooks
│   ├── 01_feature_engineering.ipynb
│   ├── 02_cnn1d_baseline.ipynb
│   ├── 03_ensemble_cnn+lgbm.ipynb
│   └── 04_hyperparameter_tuning.ipynb
│
├── 📂 scripts/                    # Training & inference scripts
│   ├── train.py
│   └── inference.py
│
├── 📂 models/                     # Trained weights (output)
│   ├── cnn_best.pth
│   ├── lgbm_best.pkl
│   ├── scaler.pkl
│   ├── ensemble_threshold.pkl
│   └── feature_columns.json
│
├── 📂 tests/                      # Unit + integration tests
│   ├── test_config.py
│   ├── test_prediction.py
│   └── test_integration.py
│
├── 📂 .vscode/                    # VS Code workspace settings
├── 📄 launch_prototype.py         # Unified launcher entry point
├── 📄 main.py                     # CLI entry point
├── 📄 pyproject.toml              # Project metadata & build config
├── 📄 requirements.txt            # Core dependencies
├── 📄 requirements-*.txt          # Environment-specific extras
├── 📄 docker-compose.yml          # Docker orchestration
├── 📄 Dockerfile                  # Container build
├── 📄 .env.example                # Environment variable template
├── 📄 CONTRIBUTING.md
├── 📄 LICENSE
└── 📄 README.md                   # This file
```

---

## 🔌 API Reference

Full interactive documentation at **http://localhost:8000/docs** (Swagger UI by [FastAPI](https://fastapi.tiangolo.com/)).

### Health Check

```bash
GET /health
```

**Response:**

```json
{ "status": "ok" }
```

### Get Weather Data

```bash
GET /weather?lat=-6.2&lon=106.8
```

### Run Prediction

```bash
POST /predict
Content-Type: application/json

{
  "temperature": 35,
  "humidity": 40,
  "wind_speed": 8,
  "latitude": -6.2,
  "longitude": 106.8
}
```

| Field | Type | Required |
|---|---|---|
| `temperature` | `float` | ✓ |
| `humidity` | `float` | ✓ |
| `wind_speed` | `float` | ✓ |
| `latitude` | `float` | ✓ |
| `longitude` | `float` | ✓ |

---

## 🐳 Deployment

### Docker Compose

```bash
docker-compose up -d              # start everything
docker-compose up -d frontend     # UI only
docker-compose up -d api          # API only
docker-compose logs -f            # live logs
docker-compose down               # stop & clean up
```

### Deployment Comparison

| Option | Use Case |
|---|---|
| `streamlit run frontend/app.py` | Local development |
| `python launch_prototype.py` | Quick local start |
| `docker-compose up -d` | Production / staging |
| Streamlit Cloud | Zero-config cloud hosting |

---

## 🛠️ Development

### Running Tests

```bash
pytest tests/                       # all tests
pytest --cov=src --cov-report=html  # with coverage report
pytest tests/test_prediction.py     # single file
```

### Code Quality

```bash
black  src/ frontend/ tests/        # format code
isort  src/ frontend/ tests/        # sort imports
flake8 src/ frontend/ tests/        # lint
mypy   src/                         # type checking
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

### Models not loading — Demo Mode is active

This is expected if no trained model files exist in `models/`. FireCast will simulate predictions automatically. To train models, run the [training notebooks](notebooks/) or use `python launch_prototype.py --demo` to re-enable demo mode explicitly.

### `ModuleNotFoundError: No module named 'src'`

```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
# or use the launcher, which handles this automatically:
python launch_prototype.py
```

### Weather API returning errors

1. Confirm `OPENWEATHER_API_KEY` is set in `.env`.
2. FireCast falls back to synthetic weather data if the provider is unreachable.
3. To skip weather calls entirely, test in demo mode: `python launch_prototype.py --demo`.

### Port already in use

```bash
# Linux / macOS
lsof -ti:8501 | xargs kill -9
# Windows PowerShell
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
# or use a different port
python launch_prototype.py --port 8502
```

### Map not refreshing after location change

```bash
streamlit cache clear
```

---

## 📊 Performance Benchmarks

| Component | Metric |
|---|---|
| CNN Inference | ~50 ms / sample |
| LightGBM Inference | ~10 ms / sample |
| Ensemble Total | ~70 ms / sample |
| API End-to-End | < 100 ms |
| Frontend Load Time | < 3 s |

---

## 📄 License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- [OpenWeatherMap](https://openweathermap.org/) — weather data
- BMKG (Indonesian Meteorological Agency) — supplementary weather data
- [LightGBM](https://lightgbm.readthedocs.io/) — gradient boosting framework
- [PyTorch](https://pytorch.org/) — deep learning framework
- [FastAPI](https://fastapi.tiangolo.com/) — API framework
- [Streamlit](https://streamlit.io/) — web framework

---

## 📧 Contact

Questions, bug reports, or feature requests? Open an issue on the GitHub repository.

---

> 🔥 **FireCast** — Protecting forests with AI.
