# AGENTS.md — FireCast Engineering Guide

> Panduan singkat untuk engineer (manusia & agen) yang bekerja di repo ini.
> Audit awal 2026-07-19. **Update TAHAP E 2026-07-30**: UI stack pindah ke React SPA (Streamlit pensiun).

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
| Backend test suite | `& "E:\C.TSUBASA\miniconda\envs\FIREvCPU\python.exe" -m pytest tests/ -q` |
| Cek sintaks Python | `& ... python.exe -m compileall -q src` |
| Jalan API + SPA (single-service) | `& ... python.exe start_api.py` **atau** `& ... python.exe launch_prototype.py --mode app` (port 7860; SPA served dari `frontend_react/build`) |
| API only (no SPA) | `& ... python.exe launch_prototype.py --mode api` (port 8000) |
| React dev (HMR) | `cd frontend_react && npm run dev` (port 3000, proxy API -> :8000 via vite.config.ts) |
| React build | `cd frontend_react && npm run build` |
| React typecheck / lint / test | `cd frontend_react && npm run typecheck \|\| npm run lint \|\| npm test` |
| Lighthouse CI | `cd frontend_react && npm run lhci` |
| Lint cepat (Python) | `& ... python.exe -m ruff check .` (bila ruff terpasang — **all checks passed 2026-08-03**) |

## 2. Arsitektur Singkat (post React-SPA migration, TAHAP E)

```
start_api.py            → uvicorn launcher (HF Spaces + dev). Mount SPA, auto demo-mode bila
                          bundle legacy + new sama-sama hilang.
start_api.sh            → shell alt (Render / host biasa); hapus render.yaml (lihat §)
Dockerfile              → TAHAP E MULTI-STAGE: Node 20 builds React (stage `spa-build`)
                          -> Python 3.12 slim serve base (`base`). Target tunggal :7860.
Procfile                → `web: python start_api.py` (single-service; Render-free)
docker-compose.yml      → single service `firecast` (api+SPA). nginx profile untuk HTTPS.
scripts/deploy_hf_space.py → deploy HF Space BUILD-ONLY (allowlist staging): build SPA lokal,
                          stage src/+models/+data parquet+build/, upload via Hub API (Xet),
                          tunggu RUNNING, verifikasi /health. Target: Kaido1/firecast-private
                          (Space publik; nama lama dipertahankan karena recreate Docker Space
                          diblokir kebijakan PRO 2026). Butuh env HF_TOKEN.

backend (src/)
  config.py            → dataclass config + legacy module-level vars (jangan dihapus)
  geo_api.py           → FastAPI app: /predict, /weather, /api/models/*, /geo/*, /analytics/*,
                        /predict/aoi, /admin/*, /health
  geo/__init__.py      → TAHAP B pkt geo sandbox-free services (locations, geocode, trend, aoi)
  geo/services.py      → API-safe port dari frontend/utils/{analytics,aoi_analysis}.py
  geo_api_spa.py       → TAHAP E: StaticFiles mount + SPA history-mode fallback (no-op bila
                        frontend_react/build hilang sehingga dev tetap boot)
  api/models.py        → router manajemen versi model (TANPA prefix, mounted tanpa prefix)
  predict.py           → predict_fire_risk + predict_batch + predict_stacking
  feature_engineering.py → lag/roll/spectral/fire-indices (threshold mode train/inference)
  data_loader.py       → load_data_for_evaluation (legacy CNN+LGBM)
  database.py          → SQLModel (sqlite). Lazy: jangan import di top-level __init__
  auth.py              → get_api_key dependency
  models/
    cnn.py             → TunedCNN1D (lazy torch, custom state-dict loader)
    lgbm.py            → load_lgbm_model (Booster/LGBMClassifier heuristik)
    xgb.py             → load_xgb_model + predict_xgb (RAISE saat error, jgn fallback 0.5)
    causal_gru.py      → CausalGRUWithAttention (input 19 raw features, seq_len=7)
    ensemble.py        → evaluate_ensemble (legacy)
    registry.py        → CRUD ModelVersion + path-traversal protection

frontend_react/         → TAHAP C-D-E: React SPA (satu-satunya UI)
  src/App.tsx           → 3-area grid (topbar/sidebar/map+timeline/diagnostic)
  src/api/{client,hooks} → fetch wrapper + react-query v5 hooks (useHealth, useModels,
                            useLocations, useGeocode, useTrend, usePredict, usePredictAoi,
                            useActivateModel)
  src/store/inferenceStore.ts → zustand: selectedCell, layers[8], aoiOverlay, prediction,
                                  aoiLogs (ring buffer 50), latencyMs, isPlaying
  src/i18n/             → initI18n() bootstrap; single-source = frontend/locales/{en,id}.json
  src/theme/            → tokens.ts (risk threshold & colors), useTheme.ts (dark/light)
  src/components/       → Header, SidebarNav, LayerControlPanel, RiskLegend, FiltersPanel,
                          ModelSelectPanel, MapArea+InteractiveMap+MapOverlays, RightDiagnostic
                          (P(fire) hero+MetricGrid+ShapList+RiskTrendChart+RawJsonPanel+ApiLogBox),
                          TimelineScrubber; tests bersangkutan (*.test.tsx)
  vite.config.ts        → base './', manualChunks (vendor-leaflet/-charts/-react/-query/...)
  lighthouserc.cjs       → TAHAP E: SPA audit, perf>70 gate

frontend/                 → hanya design tokens + locales (single-source) + utils reference
  themes/tokens.json     → sumber kebenaran warna + risk_threshold (jangan hardcode)
  locales/{en,id}.json   → i18n bersama (namespace `spa.*` ditambah di TAHAP E untuk V4 SPA)
  utils/                 → referensi porting (weather_api, gee_data, analytics, aoi_analysis,
                          i18n, log_handler, data_handler, theme) — Streamlit-only kode sudah
                          dihapus di TAHAP A; tidak ada `app.py`/`prediction_engine.py` lagi.

add_new_model/         → model stacking baru (lgb/xgb/meta/causal_gru) + raw_features.json
models/                → model legacy (CNN+LGBM) + scaler + threshold
data/                  → CSV feature dataset + cache hex JSON + locations.json (378 kota ID)
notebooks/             → 3 notebook pelatihan (02/03/04; notebook-01 stub pensiun 2026-08-04 — lihat §5-F)
tests/                 → test_api_geo (TestClient), test_config, test_prediction, test_integration
docs/react-spa-migration/PLAN.md → log per-tahap migrasi (A..E)
nginx/conf.d/firecast.conf → TAHAP E: SPA history-mode reverse-proxy (HTTPS optional profile)
```

## 3. Konvensi & Aturan Wajib

### Arsitektur & dependensi
- **Lazy import torch/slowapi/sqlmodel/h3**. Tidak boleh ada import di top-level yang men-trigger torch. Pakai pola `_get_torch()` seperti `src/config.py` dan `src/models/cnn.py`.
- **`src/__init__.py` hanya import sub-modul "aman"** (config, utils, data_loader). `predict`, `database`, `models`, `geo_api`, `geo_api_spa` tetap lazy — komentarnya di `__init__.py` JANGAN di-uncomment.
- **Jangan taruh prefix di APIRouter** kalau router akan di-mount dengan `prefix=...` di `include_router`. Pilih satu tempat saja (mounter). Lihat coment di `src/api/models.py` baris 13.
- **SPA mount order**: `mount_spa()` di `start_api.py` HARUS dipanggil setelah semua `@app.get/post` di `src/geo_api.py` dideklarasikan, agar API routes match lebih dulu dari catch-all SPA fallback. `geo_api_spa.py:_spa_fallback` mencantumkan `include_in_schema=False` dan `/{path:path}` agar tidak muncul di OpenAPI.

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

## 4. Bug Historis Penting (sudah diperbaiki 2026-07-19, re-audit 2026-08-01)

> **Catatan re-audit 2026-08-01**: Bug #3, #4, dan #9 di bawah awalnya
> ditandai `FIXED` pada audit 2026-07-19, tetapi re-audit menyeluruh
> menemukan bug #3 dan #4 masih ada (regresi), dan bug #9 belum tercatat.
> Ketiganya diperbaiki penuh pada 2026-08-01. Status di tabel sudah
> dikoreksi agar engineer tidak salah baca log historis.

| # | Deskripsi | File | Status |
|---|---|---|---|
| 1 | Double-prefix router `/api/models/api/models/...` → endpoint 404 | `src/api/models.py` & `src/geo_api.py` | FIXED |
| 2 | Rainfall parsing TypeError saat `1h=0`, `3h=None` | `frontend/utils/weather_api.py` | FIXED |
| 3 | `predict_xgb` silent 0.5 fallback (menyesatkan "Medium"). Audit 2026-07-19 klaim FIXED; re-audit 2026-08-01 menemukan `except: return np.full(n, 0.5)` masih ada di `src/models/xgb.py:80`. Diperbaiki penuh 2026-08-01: ganti `return np.full(n, 0.5)` dengan `raise RuntimeError(...)` yang dipropagasi sebagai `PredictionError` → HTTP 500. | `src/models/xgb.py` | FIXED (re-verified 2026-08-01) |
| 4 | `causal_gru.py __main__` pakai `dummy_scaler=None` → `AttributeError` saat `scaler.transform(X_raw)` dipanggil. Audit 2026-07-19 klaim FIXED; re-audit 2026-08-01 menemukan baris `dummy_scaler = None` masih ada di line 297. Diperbaiki penuh 2026-08-01: ganti dengan identity `StandardScaler` (mean=0, scale=1, n_features_in_=input_dim) sehingga self-test `__main__` jalan tanpa crash. | `src/models/causal_gru.py` | FIXED (re-verified 2026-08-01) |
| 5 | Variabel CSS hilang `--color-warning`/`--color-error`/`--color-text-primary`/`--color-text-secondary` digunakan di `app.py` tapi tidak ada di `theme.py:PALETTE` → border notif & teks label tak ter-style | `frontend/utils/theme.py` | FIXED |
| 6 | Class CSS `.risk-summary-bar` dipakai di `app.py:1235,1259` tapi tidak didefinisikan → floating risk summary jatuh berantakan | `frontend/app.py` | FIXED |
| 7 | Legend risiko di `results_display.py` pakai rentang `0-30/30-60/60-80/>80` yang TIDAK konsisten dengan `theme.get_risk_level` (`<30/30-50/50-70/>70`) — menyesatkan pengguna | `frontend/components/results_display.py` & `frontend/utils/theme.py` (baru: `get_risk_range`, `RISK_THRESHOLDS`) | FIXED |
| 8 | `frontend/utils/prediction_engine.py` bootstrap me-replace `sys.modules["src"]`, `sys.modules["src.predict"]`, `sys.modules["src.database"]` dengan instance baru via `importlib.util.spec_from_file_location`. Saat dipanggil SETELAH test/import lain yang sudah set global `predict_xgb` lewat `predict._init_models` / `predict.load_stacking_models`, instance stale menyebabkan `NameError: name 'predict_xgb' is not defined` intermiten (muncul hanya saat pytest collection memuat modul theme sebelum predict). | `frontend/utils/prediction_engine.py` (re-use instance bila sudah ada di `sys.modules`) | FIXED |
| 9 | `_safe_lgbm_predict` (`src/predict.py`) silent 0.5 fallback di semua path gagal LGBM. Bug kembar #3 yang tidak tercatat di audit awal. Diperbaiki penuh 2026-08-01: hapus `return np.full(n_samples, 0.5, dtype=float)`, ganti dengan `raise RuntimeError(...)` + log `logger.error(...)`. Sekaligus hapus parameter `cnn_probs` (unused) dari signature. | `src/predict.py` | FIXED (2026-08-01) |
| 10 | `src/launch.py` hardcode path `/usr/local/lib/python3.9/site-packages/torch/lib/libtorch_cpu.so` (3x duplikat). Path basi untuk env Python 3.12 (FIREvCPU). Diperbaiki 2026-08-01: discovery dinamis via `torch.__file__` + `Path(torch.__file__).parent / "lib" / "libtorch_cpu.so"`; skip patch saat torch unavailable atau file tidak ada (Windows wheel pakai .dll). | `src/launch.py` | FIXED (2026-08-01) |
| 11 | `src/geo_api_spa.py` `API_PREFIXES` mencantumkan `/weather` padahal endpoint sudah pensiun di TAHAP E. Stale docstring menyesatkan engineer. Diperbaiki 2026-08-01: hapus `/weather` dari tuple dan docstring routing-strategy. | `src/geo_api_spa.py` | FIXED (2026-08-01) |
| 12 | **`src/config.py` type-drift**: `_init_legacy_vars()` cast semua legacy path ke `str(...)`, tapi `src/data_loader.py` panggil `.exists()` pada `config.DATA_PATH`/`SCALER_PATH`/`FEATURE_COLUMNS_PATH` → `AttributeError: 'str' object has no attribute 'exists'`. Tersembunyi lama karena `tests/test_integration.py::test_data_loading` menelan exception itu sebagai skipped. Audit 2026-08-03: konversi legacy **path** vars → `pathlib.Path` (drop-in untuk `open`/`pd.read_csv`/`joblib.load`/`Path()`), BASE_DIR dibiarkan `str`. Sekarang test_integration **pass** (bukan skip lagi) dan boot API `/health` = 200. | `src/config.py`, `src/data_loader.py` | FIXED (2026-08-03) |
| 13 | `launch_prototype.py` masih referensi Streamlit (`--mode frontend`/`both` jalankan `streamlit run frontend/app.py`) padahal SPA React sudah jadi satu-satunya UI sejak TAHAP E. `pyproject.toml` juga masih list `streamlit/folium/streamlit-folium/plotly` di deps, coverage source masih tunjuk `frontend/components` (sudah dihapus), dan pytest markers `frontend`/`slow` usang. Audit 2026-08-03: launcher di-rewrite ke mode `app` (SPA via `start_api.py`) / `api` / `test`; pyproject dibersihkan dari stack pensiun, coverage source → `src` + `frontend/utils`, marker dipangkas ke `integration` saja. | `launch_prototype.py`, `pyproject.toml` | FIXED (2026-08-03) |

## 5. Rekomendasi Optimasi Berikutnya

> Tidak menggangu functioning, tapi akan mempermudah maintenance & performa.
> **TAHAP E 2026-07-30**: sebagian besar item di bawah ini SUDAH di-address
> (React SPA migration, single-service Docker, pytest coverage API, dll.). Yang
> tersisa dicatat ulang di bawah dengan prefix `[OPEN]` agar sudah tidak ambigu.

### A. Testing & CI (prioritas tinggi)
- **[OPEN]** Test API (`tests/test_api_geo.py`) sekarang sudah 53 test (46 TAHAP B + 7 TAHAP E `TestSpaMount`). Tambah unit test untuk `feature_engineering.compute_train_stats` & `_resolve_thresholds` (inference vs training mode), dan `predict_causal_gru` single-sample.
- **[OPEN]** Frontend Reac test sudah 24 (vitest). Tambah integration test untuk `MapArea.tsx` AOI flow (draw → /predict/aoi mutation → aoiLog.store).

### B. Type-safety & lint
- **[DONE]** `pyproject.toml` sudah diperbarui: `requires-python >=3.10`, classifiers 3.10/3.11/3.12, black target py310–py312, ruff target py312. Tidak ada lagi referensi 3.8/3.9.
- `lightgbm==3.3.5` di-lock, sementara xgboost pin `>=2.0.0`. Pastikan versi sama seperti saat pelatihan agar pickle tidak warning `InconsistentVersion` seperti log test sekarang.
- Pasang `ruff` dan jalankan pre-commit. Banyak sorted import, unused import, dan `noqa` usang di file besar (`predict.py` 1779 baris).

### C. Refactor code readability
- **`src/predict.py` terlalu panjang (1779 baris)**. Pisahkan:
  - `src/calibration.py` → `_calibrate_cnn_probs`, `_calibrate_lgbm_probs`, temperature scaling.
  - `src/features/single_inference.py` → `_create_feature_vector`, `_estimate_temporal_feature`.
  - `src/features/shap_explain.py` → `_compute_shap_explanation`.
- **[DONE TAHAP E]** `frontend/app.py` 1300+ baris udah dihapus total (Streamlit retired). Logika AOI-batch kini di-handle SPA via `/predict/aoi` + `MapArea.tsx`.
- **[DONE]** Alias `USE_BIGRU_AOI` di `src/predict.py` sudah dihapus — hanya `USE_CAUSAL_GRU_AOI` yang dibaca sekarang (komentar WHY tetap di modul agar engineer paham alasan penghentian dual-env-read).

### D. Performa
- **`_h3_index_vectorized` di `geo_api.py`** masih pakai Python comprehension; konversi ke `np.vectorize` bila h3 v4 mendukung, atau cache hasil per (lat,lon,res) set.
- **`predict_causal_gru`** punya Python loop membentuk sequence — gantakan dengan `np.lib.stride_tricks.sliding_window_view` untuk batch besar (AOI > 100 titik).
- **[DONE TAHAP E]** SPA asset manualChunks (`vendor-leaflet`, `vendor-charts`, `vendor-react`, `vendor-query`, …) — bundle split stable; gzip total ~250 KB.
- Gunakan `orjson` untuk `JSONResponse` (drop-in via `ORJSONResponse`): khusus endpoint `/predict` yang kirim prob+shap array, throughput bisa 2–3x.

### E. Keamanan & operasional
- **`.env` saat ini ter-track?** cek `git status` (terlihat modified `.gitignore`). Pastikan `.env` (berisi `OPENWEATHER_API_KEY`, `API_SECRET_KEY`, kunci GEE) selalu di-gitignore.
- **GEE key file** (`add_new_model/firecast-001-db06a187f9f4.json`) HARUS di-gitignore kalau belum — leak kunci service-account bisa disalahgunakan.
- **[DONE TAHAP E]** `start_api.py` sekarang cek **kedua** bundle: `models/*.{pth,pkl}` dan `add_new_model/{lgb,xgb}_model.pkl` sebelum enable DEMO_MODE.
- **[DONE TAHAP E]** Endpoint `/admin/cache/invalidate` plus `/admin/db/purge` sudah ada di `src/geo_api.py`.

### F. Notebooks
- **[DONE 2026-08-04]** Kernel metadata `notebooks/02_cnn1d_baseline.ipynb` diperbarui → `python3`, display "Python 3 (FIREvCPU)", language_info.version "3.12.0". JSON tetap valid.
- Bila notebook kosong (kurang dari 5 cell & hanya import), hapus atau isi; jangan biarkan stub membingungkan.

## 7. Catatan TAHAP E (2026-07-30)

> **Roadmap gabungan pasca-audit**: lihat `docs/ROADMAP.md` — menyatukan semua
> item strategis backend + gap UI/UX dalam satu priority queue + timeline
> mingguan + dependensi silang. Update setiap ada item yang dicentang.

- **render.yaml dihapus** (deployment target Hugging Face Spaces, bukan Render).
- **Deploy HF Space (2026-08-20)**: target `Kaido1/firecast-private` (dibuat publik;
  nama lama dipertahankan — recreate Docker Space diblokir kebijakan PRO 2026, 402).
  Alur: `scripts/deploy_hf_space.py` (allowlist staging, build-only — source React/
  tests/notebooks/docs TIDAK ikut; `API_SECRET_KEY` via Space secret terenkripsi).
  `git push` ke HF ditolak pre-receive (binary/Xet) → upload via Hub API `upload_folder`.
  Insiden historis: GEE key sempat bocor ke Space publik (commit lama) — key sudah
  dicabut (invalid_grant) & diganti; key baru hanya di `secrets/` (gitignored).
- **Dockerfile** sekarang multi-stage: `spa-build` (Node 20) → `base` (Python 3.12). Target tunggal :7860.
- **docker-compose.yml** single-service `firecast`; profile production menambah nginx (HTTPS).
- **nginx/conf.d/firecast.conf** di-rewrite untuk single upstream (history-mode SPA fallback via FastAPI, nginx hanya TLS + cache headers).
- **`src/geo_api_spa.py`** baru: `mount_spa(app, static_dir)` — mount `/assets` immutable 1y, root + catch-all returns `index.html` (no-cache), no-op bila `frontend_react/build` hilang (dev tetap boot).
- **i18n**: namespace `spa.*` ditambah ke `frontend/locales/{en,id}.json`; komponen inti (`Header`, `LayerControlPanel`, `RiskLegend`, `FiltersPanel`, `ModelSelectPanel`, `TimelineScrubber`, `RightDiagnostic`, `MapOverlays`) pakai `useTranslation()`.
- **Toggle Bahasa & Tema di Header (baru 2026-08-03)**: `LanguageToggle.tsx` (segmented EN/ID, `firecast-lang` localStorage) & `ThemeToggle.tsx` (cycle dark→light→auto via existing `useTheme.ts` hook, persist ke `firecast-theme`). Header juga fix brand string agar konsisten "Firecast" di id.json, dan hapus hardcode `next {24}h`/avatar "EN".
- **Avatar dinamis**: Avatar di Header kini inisial dari nama tampilan yang disimpan di `firecast-user-name` (localStorage). Klik avatar untuk update lewat prompt sederhana — tidak ada form pembawaan.
- **Toast system**: `store/toastStore.ts` (ring-buffer 5, auto-dismiss) + `components/ToastViewport.tsx` (pojok kanan atas, `z-toast: 9000`). Terhubung ke aksi AOI drawn/updated/deleted, `/predict` sukses/gagal, dan model-activate. Helper imperatif `toast.success/info/error` untuk callback di luar React.
- **Command palette (Ctrl+K)**: `components/CommandPalette.tsx` mendaftar toggle tiap layer + cycle theme + switch language, pencarian substring, arrow/enter navigation, Escape menutup. Store `paletteOpen` di `store/uiStore.ts`.
- **Mobile responsive (≤900px)**: `hooks/useIsMobile.ts` + drawer `.fc-drawer--left/right` + backdrop, trigger dari hamburger `☰` (kiri) & `📊` (kanan) di Header. Desktop layout tak berubah; drawer auto-tutup saat viewport meluas kembali.
- **Keyframes missing fix**: tambah `@keyframes fc-status-pulse` ke `index.css` — SystemStatus LED `animation` sebelumnya broken (tidak berdenyut) karena keyframes tidak ada.
- **Lighthouse**: `frontend_react/lighthouserc.cjs` meng-audit SPA root, perf gate `>0.7` sesuai PLAN §8.
- **Test count**: backend `pytest` **187 passed (0 skip)** — termasuk `tests/test_single_inference.py` (14 tests; estimator + create_feature_vector + reference_date anchor ROADMAP §3-W1) dan `tests/test_api_geo.py::TestPredictReferenceDate` (3 tests; date-ISO valid / default None / malformed → 422). Frontend `npm test` **57/57**.
- **FastAPI lifespan (2026-08-04, ROADMAP §2-A)**: `@app.on_event("startup")` deprecated di FastAPI 0.110+; startup logic dipindah ke `asynccontextmanager _lifespan(app)` di `src/geo_api.py` (`_init_observability_sync()` tetap sandbox-safe). Tidak ada lagi DeprecationWarning di logs test.
- **ROADMAP §2-F/G/H/J (2026-08-04)**: `_h3_index_vectorized` dedup via `np.unique(return_inverse=True)` (500-pt AOI 0.65 ms); `predict_causal_gru` pakai `np.lib.stride_tricks.sliding_window_view`; `orjson` jadi default FastAPI response class (ORJSONResponse fallback ke JSONResponse); `get_trend_series` tambah `lru_cache` keyed oleh `(lat, lon, days, radius_km, mtime)`.
- **ROADMAP §2-D (2026-08-04)**: `predict.py` sudah ter-split. `_create_feature_vector`, `_estimate_temporal_feature`, `_compute_shap_explanation` semuanya thin re-export yang delegasi ke `src/features/single_inference.py` & `src/features/shap_explain.py`. `predict.py` 1374 baris (1779 → 1374).
- **ROADMAP §2-I Parquet (2026-08-04)**: `data/firecast_data_readymodelling_final_V3.parquet` (3 MB, was 12 MB) + `data/processed_firecast_features_v3.parquet` (16 MB, was 55 MB). `src/data_loader.py:_resolve_tabular` prefer twin `.parquet`; `scripts/migrate_to_parquet.py` untuk regen; `pyarrow>=14.0.0` di requirements.txt; `.gitignore` blokir `data/*.parquet`.
- **ROADMAP §3-W1..W4 (2026-08-04)**: `HeaderGeoControls.tsx` (coord-jumping + date scrub) — koordinat form parse `-1.5, 102.3`, fallback geocode city via `useGeocode`. Custom Recharts tooltip di `RiskTrendChart` menampilkan "P(fire)=x (Tier) / CI: p10–p90". Sticky indeterminate progress bar di `MapOverlays` saat `useIsMutating()>0` (fc-progress-indeterminate). `ModeTabs.tsx` segmented persona (Engineer/Analyst/Demo) — simpan `useUiStore.mode` ke localStorage, App.tsx conditional render: analyst mode hide RightDiag+palette, demo also hide LeftSidebar. Dark `--color-text-muted` `#94a3b8 → #b2bed6` (WCAG AAA ~8.4:1) di `index.css` **dan** `frontend/themes/tokens.json` (sinkron). Leaflet-draw polyline ruler di InteractiveMap dengan FeatureGroup terpisah (measureItems) agar tidak trigger AOI flow.
- **ROADMAP §3-W1 closure (2026-08-04 PM)**: `ModelSelectPanel.runInference` kini pakai `selectedPredictionDate` diset dari HeaderGeoControls. Backend: `PredictRequest.reference_date: str | None` (YYYY-MM-DD ISO) diparse ke `datetime(..., 12:00)` lalu disalurkan ke `predict_fire_risk(reference_date=...)` → seasonal features `month/day/doy` bergeser sesuai tanggal pilihan user. Malformed date → 422, tidak 500. End-to-end flow: Header date-input → store → PredictPayload → POST /predict → seasonal features recomputed.
- Lihat `docs/react-spa-migration/PLAN.md` section "Progress Log" untuk log per-tahap A-E.

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

 Ditulis untuk FireCast repo — Diperbarui 2026-07-19. TAHAP E migration update 2026-07-30.
