# AGENTS.md — FireCast Engineering Guide

> Panduan singkat untuk engineer (manusia & agen) yang bekerja di repo ini.
> Ditulis dari hasil audit menyeluruh pada 2026-07-19.

## 1. Environment & Perintah Inti

- **Python (wajib)**: `E:\C.TSUBASA\miniconda\envs\FIREvCPU\python.exe` (3.12, torch CPU).
- Jangan gunakan `python`/`python3` global — bisa beda versi dan menyebabkan error `libtorch_cpu.so`/sklearn pickle mismatch.
- Set `PYTHONPATH` ke root repo sebelum menjalankan apapun:
  ```powershell
  $env:PYTHONPATH = (Get-Location).Path
  ```
- hindari 40 rpm(request per minute) pada penggunaan agent karena kita menggunakan API NVIDIA(Free tier). pada free time, kita mendapatkan 40 rpm. jika kita menggunakan lebih dari 40 rpm, kita akan mendapatkan error `429`. 

- Hindari burst request > 40 RPM (batas free-tier OpenWeatherMap). Internal limiter sudah 30/min per-IP + global token-bucket 30/min (`_owm_rate_ok` di `src/geo_api.py`).

### Perintah yang sering dipakai
| Tujuan | Perintah |
|---|---|
| Test suite | `& "E:\C.TSUBASA\miniconda\envs\FIREvCPU\python.exe" -m pytest tests/ -q` |
| Cek sintaks | `& ... python.exe -m compileall -q src frontend` |
| Jalan API | `& ... python.exe start_api.py` (port 8000) |
| Jalan Streamlit | `streamlit run frontend/app.py --server.port=8501` |
| Lint cepat | `& ... python.exe -m ruff check .` (bila ruff terpasang) |

## 2. Arsitektur Singkat

```
main.py                → bridge FastAPI `src.geo_api:app` (Railpack)
start_api.py           → uvicorn launcher untuk Render (auto demo-mode bila model hilang)
start_api.sh            → shell alt untuk Render
Dockerfile             → HF Spaces: Streamlit di port 7860, DEMO_MODE=true
Procfile               → Render: `python3 start_api.py`

src/
  config.py            → dataclass config + legacy module-level vars (jangan dihapus)
  geo_api.py           → FastAPI app: /predict, /weather, /api/models/*
  api/models.py        → router manajemen versi model (TANPA prefix)
  predict.py           → predict_fire_risk + predict_batch + predict_stacking
  feature_engineering.py → lag/roll/spectral/fire-indices (threshold mode train/inference)
  data_loader.py       → load_data_for_evaluation (legacy CNN+LGBM)
  database.py          → SQLModel (sqlite). Lazy: jangan import di top-level __init__
  auth.py              → get_api_key dependency
  models/
    cnn.py             → TunedCNN1D (lazy torch, custom state-dict loader)
    lgbm.py            → load_lgbm_model (Booster/LGBMClassifier heuristik)
    xgb.py             → load_xgb_model + predict_xgb (RAISE saat error, jgn fallback 0.5)
    bigru.py           → BiGRU legacy (jarang dipakai; see USE_BIGRU_AOI)
    causal_gru.py      → CausalGRUWithAttention (input 19 raw features, seq_len=7)
    ensemble.py        → evaluate_ensemble (legacy)
    registry.py        → CRUD ModelVersion + path-traversal protection

frontend/
  app.py               → Streamlit entry; tab prediction/analysis/batch/settings
  components/          → sidebar, interactive_map, results_display, weather_display
  utils/              → prediction_engine, weather_api, gee_data, analytics,
                        aoi_analysis, data_handler, i18n, theme, model_management
add_new_model/         → model stacking baru (lgb/xgb/meta/causal_gru) + raw_features.json
models/                → model legacy (CNN+LGBM) + scaler + threshold
data/                  → CSV feature dataset + cache hex JSON
notebooks/             → 4 notebook pelatihan
tests/                 → test_config / test_prediction / test_integration
```

## 3. Konvensi & Aturan Wajib

### Arsitektur & dependensi
- **Lazy import torch/slowapi/sqlmodel/h3**. Tidak boleh ada import di top-level yang men-trigger torch. Pakai pola `_get_torch()` seperti `src/config.py` dan `src/models/cnn.py`.
- **`src/__init__.py` hanya import sub-modul "aman"** (config, utils, data_loader). `predict`, `database`, `models`, `geo_api` tetap lazy — komentarnya di `__init__.py` JANGAN di-uncomment.
- **Jangan taruh prefix di APIRouter** kalau router akan di-mount dengan `prefix=...` di `include_router`. Pilih satu tempat saja (mounter). Lihat coment di `src/api/models.py` baris 13.

### Penanganan model ML
- **JANGAN pernah kembalikan 0.5 diam-diam** saat model error. Itu bisa menyembunyikan bahaya kebakaran nyata di label "Medium". Selalu `raise` → `predict_fire_risk` akan bungkus jadi `PredictionError`. Lihat: `src/predict.py:_safe_lgbm_predict` & `src/models/xgb.py:predict_xgb`.
- **Pisahkan fitur raw vs engineered** untuk Causal GRU (`raw_feature_indices` mutlak diperlukan). Default 19 raw features dari `add_new_model/raw_features.json`.
- **Cache model** dalam `_MODEL_CACHE` (`predict.py`); panggil `clear_model_cache()` sesudah `register_model_version()` — sudah otomatis di `registry.py`.

### Panduan API
- `/predict` dan `/weather`: rate-limit 30/min per-IP (slowapi bila ada) + global 30/min OWM token bucket.
- `/api/models/*`: gated `X-API-Key`. Jangan tambahkan `Depends(limiter.limit(...))` di router level — slowapi tidak mendukung itu dan akan menghasilkan 422 "Field required: func" (lihat comment `src/geo_api.py:_router_dependencies`).
- CORS: `ALLOWED_ORIGINS` (env) csv, default localhost:8501/3000/8000.

### Keamanan
- `register_model_version` memvalidasi path di dalam `models/` atau `add_new_model/` (anti path-traversal). Jangan di-bypass.
- `API_SECRET_KEY` wajib set; bila kosong, semua endpoint yang pakai `get_api_key` menolak 500.

## 4. Bug Historis Penting (sudah diperbaiki 2026-07-19)

| # | Deskripsi | File | Status |
|---|---|---|---|
| 1 | Double-prefix router `/api/models/api/models/...` → endpoint 404 | `src/api/models.py` & `src/geo_api.py` | FIXED |
| 2 | Rainfall parsing TypeError saat `1h=0`, `3h=None` | `frontend/utils/weather_api.py` | FIXED |
| 3 | `predict_xgb` silent 0.5 fallback (menyesatkan "Medium") | `src/models/xgb.py` | FIXED |
| 4 | `causal_gru.py __main__` pakai `dummy_scaler=None` → AttributeError | `src/models/causal_gru.py` | FIXED |
| 5 | Variabel CSS hilang `--color-warning`/`--color-error`/`--color-text-primary`/`--color-text-secondary` digunakan di `app.py` tapi tidak ada di `theme.py:PALETTE` → border notif & teks label tak ter-style | `frontend/utils/theme.py` | FIXED |
| 6 | Class CSS `.risk-summary-bar` dipakai di `app.py:1235,1259` tapi tidak didefinisikan → floating risk summary jatuh berantakan | `frontend/app.py` | FIXED |
| 7 | Legend risiko di `results_display.py` pakai rentang `0-30/30-60/60-80/>80` yang TIDAK konsisten dengan `theme.get_risk_level` (`<30/30-50/50-70/>70`) — menyesatkan pengguna | `frontend/components/results_display.py` & `frontend/utils/theme.py` (baru: `get_risk_range`, `RISK_THRESHOLDS`) | FIXED |
| 8 | `frontend/utils/prediction_engine.py` bootstrap me-replace `sys.modules["src"]`, `sys.modules["src.predict"]`, `sys.modules["src.database"]` dengan instance baru via `importlib.util.spec_from_file_location`. Saat dipanggil SETELAH test/import lain yang sudah set global `predict_xgb` lewat `predict._init_models` / `predict.load_stacking_models`, instance stale menyebabkan `NameError: name 'predict_xgb' is not defined` intermiten (muncul hanya saat pytest collection memuat modul theme sebelum predict). | `frontend/utils/prediction_engine.py` (re-use instance bila sudah ada di `sys.modules`) | FIXED |

## 5. Rekomendasi Optimasi Berikutnya

> Tidak menggangu functioning, tapi akan mempermudah maintenance & performa.

### A. Testing & CI (prioritas tinggi)
- **Tambah pytest ke requirements-dev.txt** dan jalankan otomatis di CI. Saat ini `pytest`, `sqlmodel`, `slowapi`, `shap`, `h3`, `geopandas`, `shapely`, `ruff`, `black` TIDAK terinstall di env default sesuai `pyproject.toml` dependencies. Lengkapi `requirements-dev.txt`.
- **Tambah test untuk API** (`tests/test_api_geo.py`) dengan `TestClient` untuk `/predict`, `/weather`, `/api/models/*` — saat ini 0 coverage API meskipun paling kritis.
- **Tambah test unit** untuk `feature_engineering.compute_train_stats` & `_resolve_thresholds` (inference vs training mode), dan `predict_causal_gru` single-sample.

### B. Type-safety & lint
- `pyproject.toml` menyatakan Python 3.8–3.11, padahal env pakai 3.12. Update classifiers & `requires-python` bila sudah tidak support 3.8 (ruff black target-version sudah py311 max). Konsistenkan dengan `runtime.txt` (cek isinya).
- `lightgbm==3.3.5` di-lock, sementara xgboost pin `>=2.0.0`. Pastikan versi sama seperti saat pelatihan agar pickle tidak warning `InconsistentVersion` seperti log test sekarang.
- Pasang `ruff` dan jalankan pre-commit. Banyak sorted import, unused import, dan `noqa` usang di file besar (`predict.py` 1779 baris).

### C. Refactor code readability
- **`src/predict.py` terlalu panjang (1779 baris)**. Pisahkan:
  - `src/calibration.py` → `_calibrate_cnn_probs`, `_calibrate_lgbm_probs`, temperature scaling.
  - `src/features/single_inference.py` → `_create_feature_vector`, `_estimate_temporal_feature`.
  - `src/features/shap_explain.py` → `_compute_shap_explanation`.
- **`frontend/app.py` 1300+ baris**: ekstrak logika AOI-batch ke `frontend/utils/aoi_controller.py` sehingga `main()` hanya menyusun tabs.
- Hapus alias `USE_BIGRU_AOI` di predict.py (legacy) bila tidak dipakai — dia membaca env ganda `USE_BIGRU_AOI` OR `USE_CAUSAL_GRU_AOI` yang membingungkan.

### D. Performa
- **`_h3_index_vectorized` di `geo_api.py`** masih pakai Python comprehension; konversi ke `np.vectorize` bila h3 v4 mendukung, atau cache hasil per (lat,lon,res) set.
- **`predict_causal_gru`** punya Python loop membentuk sequence — gantikan dengan `np.lib.stride_tricks.sliding_window_view` untuk batch besar (AOI > 100 titik).
- **Streamlit caching** sudah dipakai di `weather_api`, `prediction_engine`. Tambah `@st.cache_data` di `analyse_aoi_results` bila belum, agar AOI rerun tidak recompute.
- Gunakan `orjson` untuk `JSONResponse` (drop-in via `ORJSONResponse`): khusus endpoint `/predict` yang kirim prob+shap array, throughput bisa 2–3x.

### E. Keamanan & operasional
- **`.env` saat ini ter-track?** cek `git status` (terlihat modified `.gitignore`). Pastikan `.env` (berisi `OPENWEATHER_API_KEY`, `API_SECRET_KEY`, kunci GEE) selalu di-gitignore.
- **GEE key file** (`add_new_model/firecast-001-db06a187f9f4.json`) HARUS di-gitignore kalau belum — leak kunci service-account bisa disalahgunakan.
- **`start_api.py` set `ENABLE_DEMO_MODE`** hanya berdasar model legacy. Untuk deployment model stacking baru, sebaiknya periksa juga `add_new_model/lgb_model.pkl` & `xgb_model.pkl`.
- Tambahkan endpoint admin `/admin/cache/invalidate` untuk `_data_cache.invalidate()` & `_invalidate_hex_cache()` tanpa restart (berguna pas data CSV diperbarui).

### F. Notebooks
- Kernel metadata `02_cnn1d_baseline.ipynb` = Python 3.9.25, sementara runtime = 3.12. Update kernel metadata (`jupyter nbconvert --to notebook --inplace`).
- Bila notebook kosong (kurang dari 5 cell & hanya import), hapus atau isi; jangan biarkan stub membingungkan.

## 6. Catatan penting tentang dependency opsional

Beberapa modul punya **graceful fallback** bila package opsional hilang:
- `h3` → `/clusters` endpoint disable.
- `slowapi` → rate-limiting disable (klien harus turun ke 30/min sendiri).
- `sqlmodel` → registry DB disable; predict log skip.
- `geopandas`/`shapely` → AOI polygon containment error.
- `ee` (Earth Engine) → GEE fallback ke synthetic band values.
- `shap` → SHAP explanation return `{}`.

JANGANG rubah behavior itu — banyak fallback ada karena Railway/HF Spaces punya sandbox yang melarang beberapa wheel. Selalu tambahkan `try/except ImportError` di sekitar import opsional baru.

---

 Ditulis untuk FireCast repo — Diperbarui 2026-07-19.
