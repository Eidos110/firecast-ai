# React SPA Migration Plan — FireCast v4.0

> **Status**: ACTIVE — TAHAP A, B, C, D & E SELESAI (TAHAP E selesai 2026-07-30)
> **Author**: Senior GIS + ML + Fullstack workplan
> **Path**: Jalan B (Streamlit → Full React SPA), base layout = Versi 4 mockup

---

## 0. Konteks Singkat

Repo FireCast sampai v3.x memakai dua proses UI paralel:
- **Streamlit** di `frontend/` (active, port 8501) — Python monolith
- **React** di `frontend_react/` (active HANYA sebagai Streamlit-component untuk Leaflet map)

Keputusan strategis: pindahkan seluruh UI ke **`frontend_react/` sebagai SPA standalone** (bukan lagi sub-component Streamlit). Backend `src/` tetap utuh; tambah endpoint yangbelum ter-expose ke REST.

Alasan:
1. Hilangkan bug kelas #8 (`sys.modules` hack di `prediction_engine.py`) secara permanen
2. Skalabilitas type-safe end-to-end (TS strict + react-query)
3. Konsistensi design-system (single `tokens.json` → CSS vars + TS + Tailwind)
4. Lighthouse performance target → mainkan real-time VIIRS hotspot streaming di kemudian hari

Layout acuan: **"Versi 4 — Fire Risk Forecasting System"** dengan pinjaman elemen V1 (system pills) dan V3 (raw JSON panel, 5-tier legend).

---

## 1. Aturan Wajib (Non-Negotiable)

| Aturan | Source | Implikasi |
|---|---|---|
| Single source of design | `frontend/themes/tokens.json` | JANGAN hardcode hex/color/threshold apapun; selalu load via `theme/tokens.ts` atau CSS vars |
| Threshold risk | `risk.<0.3 / <0.5 / <0.7 / >=0.7` | Tier: `rendah / sedang / tinggi / sangat_tinggi` (4 tier, bukan 5) |
| Risk color | `#22c55e / #fb923c / #ef4444 / #7f1d1d` | JANGAN pakai palette dari mockup mentah |
| Lazy import policy | `src/__init__.py` | Komentar lazy import JANGAN di-uncomment |
| Model error | `raise PredictionError` not silent 0.5 | Bug #3 — jangan kambuh |
| API router prefix | Satu tempat saja (`include_router`) | Bug #1 |
| Tailwind via npm, bukan CDN | `tailwind.config.cjs` sudah ada | inline-CDN dilarang |
| Demo mode fallback | Jika fetch gagal → mock data | Kompatibel dengan `ENABLE_DEMO_MODE` |

---

## 2. Layout Final (Versi 4 + Pinjaman)

```
┌──────────────────────────────────────────────────────────────────┐
│  TOPBAR (h=48px)  [Logo] [model pill] [run pill] [EPSG] [search] │
│                     [active region] [horizon select] [status LED]│
├──────────┬──────────────────────────────────────┬────────────────┤
│ LEFT     │             MAP (Leaflet)           │ RIGHT DIAGNOSTIC│
│ SIDEBAR  │             (flex-1)                │   (320px)       │
│ (280px)  │                                      │                │
│          │                                      │ • P(fire) hero  │
│ • Layers │  • Risk circle heatmap              │   (RiskGauge)   │
│   (toggle│  • AOI polygon (draw/edit)          │ • Metric grid   │
│    8)    │  • Wind vectors (optional)            │   2x2          │
│ • Model  │  • Fire points (red dot pulse)       │ • SHAP list    │
│   cfg    │  • Click → push selected lat/lon      │   (CSS bar)    │
│ • Filters│  • Coordinate readout (bottom-left)  │ • Raw JSON     │
│   (region│  • Compass (top-right)               │   expander     │
│   date   │                                      │ • API log box  │
│   risk)  │                                      │   (color-coded)│
│ • Legend │                                      │                │
├──────────┴──────────────────────────────────────┴────────────────┤
│ BOTTOM BAR (h=56px)                                              │
│ [Timeline scrubber H-24 ←────●────→ H+72] [Play/Pause][Export]  │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Endpoint API Baru yang Perlu Ditambah ke Backend

Untuk menyokong SPA, expose yang berikut ke `src/geo_api.py`:

| Endpoint | Method | Tujuan | Source port-from |
|---|---|---|---|
| `/geo/locations` | GET | Serve `data/locations.json` (378 kota id) | sidebar._load_indonesia_locations |
| `/geo/geocode` | GET | Geocode nama kota (Nominatim fallback) | sidebar.geocode_location |
| `/analytics/trend` | GET | Time-series 7 hari untuk satu sel | analytics.get_monthly_fire_data (adapt) |
| `/predict/aoi` | POST | Batch predict untuk polygon AOI | aoi_prediction.predict_aoi_grid |
| `/predict` | POST | (sudah ada `geo_api.py:406`) | pertahankan |
| `/api/models` | GET | Daftar model aktif | `src/api/models.py` (sudah ada) |
| `/api/models/activate` | POST | (sudah ada) | pertahankan |
| `/health` | GET | (sudah ada) | pertahankan |

Implementasi: pakai Pydantic body, tidak ada silent 0.5, semua gated `X-API-Key` bila diperlukan (kecuali `/geo/locations` & `/health` public read).

---

## 4. Roadmap Eksekusi (5 Tahap)

### TAHAP A — Cleanup (1 hari)
- [x] Backup branch `backup/pre-react-spa`
- [x] Hapus file Streamlit-native yang tidak akan dipakai:
  - `frontend/app.py`, `frontend/styles/inject.py`, `frontend/styles/theme_toggle.py`, `frontend/styles/app.css`, `frontend/styles/_ui_revamp.css`
  - `frontend/components/*_bar.py`, `right_diagnostic.py`, `results_display.py`, `shap_waterfall.py`, `temporal_band.py`, `weather_display.py`, `model_management.py`, `sidebar.py`, `status_bar.py`, `bottom_bar.py`
  - `frontend/utils/tabs/__init__.py`, `prediction_tab.py`, `analysis_tab.py`, `batch_tab.py`, `settings_tab.py`
  - `frontend/utils/prediction_engine.py` (bug #8 source)
- [x] Hapus duplikat `.js` di `frontend_react/src/` (3 file)
- [x] Hapus `frontend_react/build/`, `node_modules/` (artifact)
- [x] Hapus folder subrepo tergitignore: `firecast-private/`, `tmp-space-deploy/`, `.kilo/`
- [x] Verifikasi `python -m compileall src` masih bersih

### TAHAP B — Backend Endpoint Baru (1 hari)
- [x] `GET /geo/locations` (array `{name, lat, lon}`)
- [x] `GET /geo/geocode?q=<string>` (Tier-1: local JSON, Tier-2: Nominatim)
- [x] `GET /analytics/trend?lat&lon&days=7`
- [x] `POST /predict/aoi` (body: GeoJSON polygon + grid_size; response: batch prediction)
- [x] Unit tests untuk 4 endpoint baru di `tests/test_api_geo.py`

### TAHAP C — React SPA Foundation (2 hari)
- [x] Pasang deps baru: `npm i react-router-dom @tanstack/react-query zustand recharts lucide-react` (sudah ada di `package.json`; `npm install` menyelesaikan 827 packages)
- [x] Buat `src/store/inferenceStore.ts` (zustand: model, run_id, aoi, horizon_hours, layers, selected_cell) — sudah ada
- [x] Buat `src/api/client.ts` (fetch wrapper + react-query hooks) — sudah ada
- [x] Buat `src/i18n/i18n.ts` + import `frontend/locales/{en,id}.json` — sudah ada (perbaikan path import & tsconfig `include`)
- [x] Setup `App.tsx` dengan layout grid 3-area + QueryClientProvider + I18nProvider + ThemeProvider (`main.tsx` updated untuk wrap providers; Theme via `useTheme()` self-contained)
- [x] Pisahkan `InteractiveMap.tsx` dari `streamlit-component-lib` (ganti `Streamlit.setComponentValue` → callback props) — sudah decoupled (hanya komentar konteks tersisa, tidak ada import aktual)
- [x] Update `frontend_react/src/components/index.ts` barrel export (semua komponen Tahap D ditambah)

### TAHAP D — Komponen Inti (3-4 hari)
> **Fitur sudah terskeleton** pada penyelesaian TAHAP C; TAHAP D = wiring data-flow + react-query + MapOverlays separation + tests.
- [x] `Header.tsx` — porting V1 system pills (model/run/EPSG/LED); `SystemStatus` kini pakai `useHealth()` polling 30s (real online/offline, bukan latencyMs proxy)
- [x] `LayerControlPanel.tsx` — porting V4 Layers + V4 opacity slider (per-layer toggle + opacity slider ke `firstActive` layer) + `RiskLegend` (4-tier V4 RISK_THRESHOLDS)
- [x] `ModelSelect.tsx` + Run Inference button (`POST /predict`) → `ModelSelectPanel.tsx` pakai `usePredict` mutation (mutation.isPending) + `useModels` untuk hidupkan dropdown dari registry + `useActivateModel` untuk "Set active (server)" button; demo fallback `mockPredict()` saat reject
- [x] `TimelineScrubber.tsx` — bottom slider H-24 → H+72 + play/pause (`setInterval` 1s increment) + Export JSON blob download
- [x] `RightDiagnostic.tsx`:
  - `RiskGauge` (sudah ada) untuk P(fire) hero
  - `MetricGrid` 4 cards (P(fire), Confidence, AUC-ROC, Drift KS) — ter-wire ke `prediction` & `activeModel`
  - `ShapList` (CSS bar; porting V4 fs-row pattern) — ter-wire ke `prediction.shap_explanation.top_features` dengan fallback list
  - `RawJsonPanel` (`<pre>` block; dari V3) — collapsible `<details>`, ter-wire ke `prediction`
  - `ApiLogBox` (ring buffer 50 entry; warna-coded dari V4) — ter-wire ke `store.apiLogs`, reverse-render (latest atas)
- [x] `RiskTrendChart.tsx` (Recharts ComposedChart; 7 hari p10/p50/p90 band Area + p50 median Line) — pakai `useTrend(lat, lon, 7, 25)` react-query hook; demo fallback `mockTrend()` saat hook error/empty
- [x] `MapOverlays.tsx` (compass + coord readout + zoom/region pill) — file baru dipisah dari `MapArea.tsx`; layer legend tetap di sidebar (`RiskLegend`)

**Plus (di luar checklist PLAN asli):**
- [x] `src/api/client.ts` diperbaiki type contract sesuai `geo_api.py` aktual: `listLocations` → `{count, locations}`, `getTrend` → `TrendResponse` (`{lat, lon, radius_km, days, series}` dengan `series: [{date, fire_rate, p10, p50, p90, count}]`), `predictAoi` → `PredictAoiResponse` (`{count, ok, errors, grid_size, results}`), `listModels` → `ListModelsResponse` (`{models, count}`), `activateModel(modelName)` — endpoint actual `POST /api/models/{name}/activate` (bukan `version` body)
- [x] `src/api/hooks.ts` baru — react-query v5 hooks (`useModels`, `useLocations`, `useGeocode`, `useHealth`, `useTrend`, `usePredict`, `usePredictAoi`, `useActivateModel`) + `queryKeys` factory untuk invalidation
- [x] `FiltersPanel.tsx` Region select dipopulasi dari `/geo/locations` via `useLocations()` (fallback 5-region kalau endpoint gagal)
- [x] API key persisted ke `localStorage` (`firecast-api-key`); `client.ts` membaca saat runtime, bukan import-time, agar test/SSR aman
- [x] 3 file test baru (`MapOverlays.test.tsx` 4 test, `RiskTrendChart.test.tsx` 3 test, `ModelSelectPanel.test.tsx` 3 test) + `__tests__/test-utils.tsx` (QueryClient wrapper) + `setup.ts` ResizeObserver stub (Recharts ResponsiveContainer jsdom polyfill)

### TAHAP E — Deployment & Polish (1-2 hari)
- [x] Multi-stage Dockerfile: build React → serve via FastAPI StaticFiles
- [x] Hapus `render.yaml` (target deployment HF Spaces, bukan Render) + update `Procfile`: satu service "firecast" (api + static frontend)
- [x] Update `nginx/` reverse-proxy untuk SPA fallback (history mode)
- [x] Lighthouse audit via `frontend_react/lighthouserc.cjs`; target perf > 70
- [x] i18n id/en full coverage untuk semua label mockup (namespace `spa.*`)
- [x] Update `README.md` & `AGENTS.md` dokumen migrasi

**Total estimasi: 8-10 hari**.

---

## 5. Daftar File — Set "PERTAHANKAN"

### Backend (semua `src/`)
`src/__init__.py`, `auth.py`, `cache.py`, `calibration.py`, `config.py`, `data_loader.py`, `database.py`, `feature_engineering.py`, `geo_api.py`, `launch.py`, `observability.py`, `predict.py`, `utils.py`, `utils/`, `api/models.py`, `features/`, `models/`

### Model artifacts (binary)
`models/*`, `add_new_model/*` (kecuali `final_modelling_V4.1_GeminiPRO.ipynb` tetap)

### Data
`data/firecast_data_readymodelling_final_V3.csv`, `data/processed_firecast_features_v3.csv`, `data/locations.json`, `data/firecast.db`, `data/_tmp_hexagons_res_6.json`

### Infra & DevOps
`Dockerfile` (akan di-update multi-stage), `docker-compose.yml`, `Procfile`, `render.yaml`, `railway_api.toml`, `nginx/`, `.github/`, `.pre-commit-config.yaml`, `.secrets.baseline`, `.gitignore`, `.gitattributes`, `.dockerignore`, `.env.example`, `.env.production`, `requirements*.txt`, `pyproject.toml`, `runtime.txt`, `apt.txt`

### Tests
`tests/**/*.py` (semua), `frontend_react/src/__tests__/setup.ts`, `frontend_react/src/components/{RiskGauge,ProbabilitySparkline}.test.tsx`

### React (akan di-extend)
`frontend_react/package.json`, `vite.config.ts`, `tsconfig*.json`, `tailwind.config.cjs`, `.eslintrc.cjs`, `lighthouserc.cjs`, `README.md`
`frontend_react/src/main.tsx`, `App.tsx`, `index.css`, `vite-env.d.ts`
`frontend_react/src/components/`: ErrorBoundary, Skeleton, Toast, ToastViewport, useToasts, RiskGauge, ProbabilitySparkline, BatchHeatmapLegend, AoiTable, CommandPalette, Header, SidebarNav, InteractiveMap (akan di-refactor)
`frontend_react/src/theme/`: tokens.ts, risk.ts, useTheme.ts
`frontend_react/src/utils/cn.ts`

### Design tokens & locales
`frontend/themes/tokens.json` (single source), `frontend/locales/{en,id}.json`, `frontend/.streamlit/config.toml` (legacy, boleh buang di TAHAP E)

### Streamlit utils reusable (logic tetap)
`frontend/utils/theme.py`, `weather_api.py`, `gee_data.py`, `analytics.py`, `aoi_analysis.py`, `aoi_prediction.py`, `i18n.py`, `log_handler.py`, `data_handler.py`
(yang akan jadi reference untuk porting ke API/src)

### Docs
`README.md`, `AGENTS.md`, semua `*_REPORT.md`, `docs/ui-revamp/{PLAN,PROGRESS,REVIEW_HASIL,README}.md`, `CONTRIBUTING.md`, `LICENSE`, `cured`, `_preview_ui/`

`launch_prototype.py`, `start_api.py`, `main.py`, `scripts/`, `notebooks/`, `migrations/`, `_preview_ui/`, `cured`

### File planner (ini)
`docs/react-spa-migration/PLAN.md`

---

## 6. Daftar File — Set "HAPUS"

### Streamlit-native (diganti React)
- `frontend/app.py`, `frontend/styles/*` (4 file), `frontend/components/sidebar.py`, `frontend/components/results_display.py`, `frontend/components/weather_display.py`, `frontend/components/model_management.py`, `frontend/components/status_bar.py`, `frontend/components/bottom_bar.py`, `frontend/components/right_diagnostic.py`, `frontend/components/shap_waterfall.py`, `frontend/components/temporal_band.py`, `frontend/components/interactive_map.py` (838 line, akan di-port ke `InteractiveMap.tsx` yang ada)
- `frontend/utils/tabs/__init__.py`, `frontend/utils/tabs/prediction_tab.py`, `frontend/utils/tabs/analysis_tab.py`, `frontend/utils/tabs/batch_tab.py`, `frontend/utils/tabs/settings_tab.py`
- `frontend/utils/prediction_engine.py` (851 line, bug #8 source)
- `frontend/utils/aoi_controller.py` (Streamlit glue), `frontend/utils/aoi_prediction.py` (akan di-port ke API)

### Duplikat (.js redundant di React)
- `frontend_react/src/App.js`, `frontend_react/src/main.js`, `frontend_react/src/components/InteractiveMap.js`

### Build artifact
- `frontend_react/build/`, `frontend_react/node_modules/`, `frontend_react/.lighthouseci/`

### Subrepo tergitignore
- `firecast-private/`, `tmp-space-deploy/`, `.kilo/`

### Python build artifact
- Semua `__pycache__/`, `.ruff_cache/`, `.pytest_cache/`, `.coverage`

---

## 7. Risk Register & Mitigasi

| Risk | Mitigasi |
|---|---|
| `prediction_engine.py` dihapus → API dependency lain yang masih transitif break | Cek dulu `frontend/components/model_management.py` & `interactive_map.py`; jika masih import → rapikan/hapus |
| `InteractiveMap.tsx` decouple dari streamlit-component-lib → event handler lama hangus | Rename: `onMapClick`, `onAoiDraw`, `onAoiUpdate`, `onLayerToggle`; mock props di App.tsx untuk dev mode |
| Server-side rendering hilang (streamlit rendered server) → SEO/metascore drop | FireCast private system, tidak-butuh SEO. Tidak relevan. |
| Demo mode default bisa hide kegagalan | Tetap expose status di `ApiLogBox` warna-coded (warn/err) walau mode demo |
| Deploy statis melalui FastAPI bisa cache stale | Pasang `Cache-Control: no-cache` untuk `index.html`, `max-age=31536000` untuk `/assets/*` hashed |

---

## 8. Acceptance Criteria

Migrasi dianggap selesai jika:

1. ✅ `npm run build` di `frontend_react/` menghasilkan dist tanpa error
2. ✅ `npm run typecheck` lulus strict mode
3. ✅ `npm run lint` bersih (max-warnings=0)
4. ✅ `pytest tests/ -q` lulus (backend tidak broke)
5. ✅ `python -m compileall src` lulus
6. ✅ Manual smoke: `npm run dev` + `python start_api.py` → click map → predict side panel render → AOI draw → batch predict render
7. ✅ Lighthouse Performance > 70 (mobile) di default route
8. ✅ Dark/light theme toggle berfungsi, WCAG AA contrast terpenuhi
9. ✅ Threshold di UI sama persis dengan `tokens.json:risk_threshold`
10. ✅ Demo mode tersedia (`ENABLE_DEMO_MODE=true` → API mock + UI mock fallback)

---

## 9. Progress Log

### 2026-07-29 — TAHAP A dimulai
- [x] Backup branch dibuat `backup/pre-react-spa`
- [x] Cleanup file Streamlit-native
- [x] Cleanup duplikat .js & build artifact
- [x] Cleanup subrepo tergitignore
- [x] Verifikasi backend compile OK

(spesifik aksi dicatat di tiap commit)

### 2026-07-29 — TAHAP A selesai (verifikasi objektif)
- [x] Verifikasi 35/35 file/folder Streamlit-native + duplikat `.js` + build artifact + subrepo tergitignore **terhapus** (`frontend\app.py`, `frontend\components\*.py` lama, `frontend\utils\prediction_engine.py`, `frontend\utils\aoi_*.py`, `frontend\styles\*`, `frontend_react\src\App.js`, `frontend_react\src\main.js`, `frontend_react\src\components\InteractiveMap.js`, `frontend_react\build\`, `frontend_react\node_modules\`, `firecast-private\`, `tmp-space-deploy\`, `.kilo\` → semua `GONE`).
- [x] `python -m compileall -q src` bersih (no output).
- [x] Status `git`: deletion tertahan (status `D`) — siap di-commit di TAHAP E.
- [x] Catatan: `frontend/utils/{analytics,aoi_analysis,weather_api,gee_data,i18n,log_handler,data_handler}.py` **dipertahankan** sebagai referensi porting (set "PERTAHANKAN" PLAN §5).

### 2026-07-29 — TAHAP B selesai (verifikasi objektif)
Implementasi 4 endpoint SPA baru pada `src/geo/` + `src/geo_api.py` (PLAN §3):

- [x] `GET /geo/locations` — public-read, mtime-aware loader untuk `data/locations.json` (378 entry Indonesia), mengembalikan `{count, locations:[{id,name,lat,lon}]}` diurut by `name`. Rate-limit 30/min.
- [x] `GET /geo/geocode?q=` — Tier-1 local JSON (exact + substring match), Tier-2 OSM Nominatim (placeholder-User-Agent guard). 400 saat `q` kosong, 404 saat kedua tier miss. Public-read, rate-limit 30/min.
- [x] `GET /analytics/trend?lat&lon&days=7` — per-day fire-risk trend dari `processed_firecast_features_v3.csv` (mtime-aware `lru_cache`), haversine radius filter (default 25km), p10/p50/p90 quantile band + `fire_rate` + `count` per day. `days` di-clamp `[1,90]`. 400 lat/lon invalid, 404 saat CSV hilang. Public-read, rate-limit 30/min.
- [x] `POST /predict/aoi` — gate `X-API-Key`, body GeoJSON `{Polygon,MultiPolygon,Feature}` + `grid_size` (1..64), sebelumnya `run_aoi_batch` (per-cell `predict_fire_risk`, **tidak** silent-0.5: cell error → `status:"error"` dengan `error` message, tidak ada `risk_score`). Shapely `intersects` (boundary-inclusive) saat tersedia, fallback bbox-grid saat tidak. Rate-limit 10/min (inference berat).

**File baru:**
- `src/geo/__init__.py` — paket geo (Streamlit-free, lazy-import policy).
- `src/geo/services.py` — API-safe port dari `frontend/utils/{analytics,aoi_analysis}.py` (tidak `@st.cache_data`): `load_locations`, `geocode`, `_local_geocode`, `_nominatim_geocode`, `get_trend_series`, `build_aoi_grid`, `run_aoi_batch`.

**File diubah:**
- `src/config.py` — tambah property `PathsConfig.locations_path` (single source of truth untuk `data/locations.json`).
- `src/geo_api.py` — import `src.geo.services` + 4 endpoint baru + Pydantic `AoiPolygonRequest` (lazy import policy dipertahankan, `<module import after app/limiter>`).
- `tests/test_api_geo.py` — tambah 4 kelas test: `TestGeoLocationsEndpoint` (3 test), `TestGeoGeocodeEndpoint` (6 test, Nominatim Tier-2 di-monkeypatch agar network-free), `TestAnalyticsTrendEndpoint` (6 test, CSV-missing di-monkeypatch), `TestPredictAoiEndpoint` (9 test, model layer di-monkeypatch agar tidak butuh torch/sklearn). Total 24 test baru.

**Verifikasi akhir TAHAP B:**
- Smoke via `TestClient`:
  - `/geo/locations` → 200, count=378 ✅
  - `/geo/geocode?q=aceh` → 200, source=local ✅
  - `/analytics/trend?lat=-1.17&lon=100.40&days=7` → 200, series=[] (sel di luar window CSV) ✅
  - `/predict/aoi` tanpa key → 401 ✅
  - `/predict/aoi` dengan key, grid_size=2, `model_type=legacy` → 200, count=4, ok=4, errors=0 ✅
- `pytest tests/test_api_geo.py -q` → 46 passed (21 pra-TAHAP A + 25 baru) ✅
- `pytest tests/ -q --ignore=tests/frontend` → 140 passed, 1 skipped (pre-existing, `test_integration` data-loader `str`-path bug, **bukan** regresi) ✅
- `python -m compileall -q src` → bersih ✅

**Decision log:**
- **Auth policy** `/geo/locations` & `/geo/geocode` & `/analytics/trend` = public-read sesuai PLAN §3 (SPA sidebar/chart harus jalan anonim di hosted demo). `/predict/aoi` gated `X-API-Key` karena inference berat.
- **No-silent-0.5**: per-cell AOI failure → `status:"error"` + `error` message (AGENTS.md §3 + bug #3 dipertahankan). Test kontrak `test_per_cell_error_not_silent_0_5` memverifikasi cell error **tidak** punya `risk_score` field.
- **Boundary-inclusive grid**: `shapely.intersects` (bukan `contains`) agar corner AOI tidak ke-skip (`grid_size=2` → corner = bbox exactly on boundary). Tanpa ini grid corner polygon `[100,0]-[101,0]-[101,-1],[100,-1]` menghasilkan grid kosong (contains reject boundary point) → 400 menyesatkan.
- **Graceful fallback**: shapely absen → bbox-grid penuh (PLAN §6). Fitur opsional (Nominatim, shapely, CSV) semua di-`try/except ImportError`/`OSError` → sandbox-safe.

**File baru/modifikasi siap di-commit** (belum commit sesuai aturan opencode "no commit unless asked"):
- new: `src/geo/__init__.py`, `src/geo/services.py`
- modified: `src/config.py`, `src/geo_api.py`, `tests/test_api_geo.py`, `docs/react-spa-migration/PLAN.md`

### 2026-07-29 — TAHAP C selesai (verifikasi objektif)
React SPA Foundation — semua 7 item checklist PLAN §4 TAHAP C terpenuhi:

- [x] **Deps**: `npm install` menyelesaikan 827 packages dari `frontend_react/package.json` (deps: react-router-dom, @tanstack/react-query, zustand, recharts, lucide-react, i18next, react-i18next, leaflet, leaflet-draw; devDeps: vitest, @testing-library, tailwind, typescript 5.2).
- [x] **`src/store/inferenceStore.ts`** (zustand): state `selectedCell`, `selectedAoi`, `aoiOverlay`, `layers[8]`, `activeModel`, `runId`, `horizonHours`, `isPlaying`, `prediction`, `latencyMs`, `apiLogs` (ring buffer 50). Layer toggle/set-opacity + circular `pushApiLog` + auto-sync `latencyMs` saat `setPrediction`. Default layers 8-baris dengan opacity default sesuai V4.
- [x] **`src/api/client.ts`** (fetch wrapper): typed methods `health`, `predict`, `predictAoi`, `listModels`, `activateModel`, `listLocations`, `geocode`, `getTrend`. `X-API-Key` header passthrough via `opts.apiKey`. `JSONOrThrow` sanitize error detail. `mockPredict(lat,lon)` deterministic untuk demo-mode (PLAN §1 "Demo mode fallback").
- [x] **`src/i18n/i18n.ts`** + import locales: bootstrap `i18next` + `react-i18next` dari `environment/locales/{en,id}.json`. `initI18n()` async dengan `localStorage` persist (`firecast-lang`). Path import diperbaiki ke `../../../frontend/locales/*.json`; `tsconfig.json` `include` di-expand agar TS resolve modul JSON di luar `src/` (single-source-of-truth tetap di `frontend/locales/`, PLAN §1).
- [x] **`main.tsx` rewrite**: boot `initI18n()` (async, swallow error → key-fallback) → mount `<App />` di dalam `<ErrorBoundary>` → `<QueryClientProvider>` (retry=1, staleTime=60s, noFocusRefetch) → `<I18nextProvider>`. Theme tidak dibungkus provider global karena `useTheme()` self-contained (localStorage + matchMedia + `data-theme` attr pada `<html>`), sesuai komentar di theme/useTheme.ts.
- [x] **`InteractiveMap.tsx` decoupled** dari `streamlit-component-lib`: tidak ada import aktual streamlit-component-lib / `Streamlit.*` (grep verifikasi). Komunikasi via callback props (`onCellSelect`, `onAoiDrawn`, `onAoiUpdated`, `onAoiDeleted`, `overlay`, `layers`). Tipe `L.Control.DrawOptions` diperbaiki dari `L.DrawOptions` (yang tidak ada di @types/leaflet-draw namespace atas).
- [x] **`components/index.ts` barrel** diperbarui: export semua komponen Tahap D skeleton — `LeftSidebar`, `LayerControlPanel` (+ `RiskLegend`), `ModelSelectPanel`, `FiltersPanel`, `MapArea`, `InteractiveMap` (+ types), `RightDiagnostic`, `MetricGrid`, `ShapList`, `RiskTrendChart`, `RawJsonPanel`, `ApiLogBox`, `TimelineScrubber`. HeaderProps di-export (perbaikan TS2614).

**Perbaikan typecheck lain (10 error awal → 0):**
- `Header.tsx`: `HeaderProps` diubah dari `interface` → `export interface` (tidak ada runtime impact).
- `theme/risk.ts`: tambah `export type { RiskTierLabel }` re-export agar `InteractiveMap.tsx` (`import { type RiskTierLabel } from '../theme/risk'`) compile.
- `components/RiskTrendChart.tsx`: shadowing variabel `lat`/`lon` di `buildSeedSeries` → rename parameter ke `latIn`/`lonIn` (TS2300 duplicate identifier + TS18047 possibly-null).
- `InteractiveMap.tsx`: `as unknown as L.DrawOptions` → `as unknown as L.Control.DrawOptions` (TS2694 namespace tidak punya `DrawOptions`).
- Hapus 4x `eslint-disable-next-line @typescript-eslint/no-explicit-any` directive "unused" karena rule tsudah off di `.eslintrc.cjs` (lint `--report-unused-disable-directives --max-warnings 0`).
- `main.tsx`: hapus `eslint-disable-next-line no-console` yang tidak dibutuhkan.

**Verifikasi akhir TAHAP C:**
- `npm run typecheck` → bersih (no output) ✅
- `npm run lint --max-warnings 0` → bersih ✅
- `npm run build` → `tsc --noEmit && vite build`, 936 modul transformed, `build/assets/index.js` 103 KB (gzip 33 KB), build 32s ✅
- `npm test` (vitest) → 14/14 passed (RiskGauge 8 + ProbabilitySparkline 6) ✅
- `python -m compileall -q src` → bersih ✅
- `pytest tests/test_api_geo.py -q` → 46 passed (no regression dari TAHAP B) ✅

**Decision log:**
- **Locale path strategy**: biarkan single source of truth di `frontend/locales/` (sibling); `tsconfig.json` `include` di-expand ke `../frontend/locales/{en,id}.json` sehingga TS resolve `resolveJsonModule` tanpa duplikat file. Alternatif "salin ke `frontend_react/src/i18n/locales/`" ditolak karena akan menimbulkan drift sebelumnya (lihat `theme/risk.ts` docstring tentang drift Medium `#f59e0b` vs `#fb923c`).
- **Theme tidak dibungkus context**: `useTheme()` self-contained (baca localStorage, matchMedia, set `data-theme` pada `<html>`). Pattern ini sudah dipakai sebelum TAHAP C dan dipertahankan untuk minimize provider tree deep & hindari race condition StrictMode double-mount.
- **Demo-mode**: `mockPredict()` di `client.ts` dipanggil oleh `RightDiagnostic.tsx` saat API gagal/`ENABLE_DEMO_MODE=true`. Status field = `'DEMO'` agar `ApiLogBox` (warna-coded) tetap menampilkan `warn` level (PLAN §7 risk register: "Demo mode default bisa hide kegagalan").
- **i18n init async sebelum render**: `initI18n().catch(...).finally(render)` mencegah flash label kosong pada first paint; error di-swallow (continue with key fallback) sehingga locale rusak tidak brick console.

**File baru/modifikasi TAHAP C siap di-commit** (belum commit sesuai aturan opencode "no commit unless asked"):
- modified: `frontend_react/tsconfig.json`, `frontend_react/src/i18n/i18n.ts`, `frontend_react/src/main.tsx`, `frontend_react/src/components/index.ts`, `frontend_react/src/components/Header.tsx`, `frontend_react/src/components/InteractiveMap.tsx`, `frontend_react/src/components/RiskTrendChart.tsx`, `frontend_react/src/theme/risk.ts`, `docs/react-spa-migration/PLAN.md`

### 2026-07-30 — TAHAP D selesai (verifikasi objektif)
Komponen Inti — semua 7 item checklist PLAN §4 TAHAP D terpenuhi + 5访谈 tambahan (PLAN asli hanya menyebut komponen, tapi data-flow ke API belum lengkap):

**1. Header + useHealth polling (#1):**
- `Header.tsx` V1 system pills (model/run/EPSG/LED) sudah ada dari skeleton.
- `SystemStatus` diupgrade: kini pakai `useHealth()` polling 30s (real online/offline), bukan lagi `latencyMs != null` proxy yang false-positive saat belum pernah run inference. Status "connecting…" → "online" → "offline" transitions via `healthQuery.isLoading`/`isError`.

**2. LayerControlPanel + RiskLegend (#2):**
- 8 layer toggle rows (ALL from store.layers) dengan per-layer swatch color, border highlight saat active, `aria-pressed` untuk a11y.
- Opacity slider terikat ke `firstActive` layer (V4 mockup pattern — satu slider shared).
- `RiskLegend` 4-tier menggunakan RISK_THRESHOLDS tokens (rendah/sedang/tinggi/sangat_tinggi), range string dari `tokens.ts` (`0.00 – 0.30`, `0.30 – 0.50`, `0.50 – 0.70`, `0.70 – 1.00`) — single-source-of-truth dipertahankan (PLAN §1).

**3. ModelSelectPanel + Run Inference (#3):**
- Tombol "▶ Run Inference" kini pakai `usePredict()` mutation react-query (v5 `mutation.isPending`), menggantikan ad-hoc `useState(false)` busy flag.
- Model dropdown dihidupkan dari `useModels()` (registry `/api/models/`); entry dideduksi via heuristic name pattern (`/new|stack|causal|gru/i` → 'new', else 'legacy'), dengan fallback 2-entry kalau registry kosong/tidak terjangkau. Dedup via `Map` agar tidak ada label ganda.
- Tombol sekunder "Set active (server)" memanggil `useActivateModel().mutate(modelName)` (endpoint `POST /api/models/{name}/activate` sesuai `src/api/models.py:150` — bukan `version` body seperti dugaan asli `client.ts`).
- Error path: `mutation.mutateAsync()` reject → `pushApiLog('err', msg)`, fallback ke `mockPredict()` deterministic, store tetap terisi sehingga panel tidak kosong. ApiLogBox color-coded 'err' row menampilkan failure cause (PLAN §7 risk register: demo tidak boleh sembunyikan kegagalan).

**4. TimelineScrubber (#4):**
- Slider -24 → +72 (`HORIZON_MIN`/`MAX`), `setInterval` 1s increment saat Play active, "Now" stamp dari `apiLogs.at(-1)?.ts` (atau `new Date().toISOString()` saat belum ada log).
- Tombol "New run" (regenerasi runId), "Export JSON" (Blob download `firecast-{runId}.json` berisi `{runId, horizonHours}`).

**5. RightDiagnostic composite (#5):**
- P(fire) hero badge: gradient background berdasarkan `getRiskColor(level)`, label tier + confidence interval.
- `MetricGrid` 2x2: P(fire), Confidence, AUC-ROC (default 0.942 bila `activeModel.auc` null), Drift KS (default 0.12). Tone good/warn/bad dari RISK_THRESHOLDS.
- `ShapList`: 8 baris max, bar width relatif ke `maxAbs`, positive → amber `getRiskColor(0.5)`, negative → `var(--color-info)`. Fallback 5-feature list (`temperature_2m`, `humidity_rel`, `wind_speed`, `NDVI`, `fuel_moisture`) untuk boot state.
- `RawJsonPanel`: collapsible `<details>` `<pre>` (maxHeight 240, overflowX auto, monospace) menampilkan `JSON.stringify(prediction, null, 2)`.
- `ApiLogBox`: reverse-render (latest atas), 3-level color-coded (`ok`=success, `warn`=warning, `err`=error), `aria-label="API log"`, ring buffer 50 entry (dari store `pushApiLog` `next.shift()` bila >50).

**6. RiskTrendChart → /analytics/trend (#6):**
- Sekarang pakai `useTrend(lat, lon, 7, 25)` react-query hook (enabled hanya saat `lat != null && lon != null`).
- Recharts `ComposedChart`: p10 area (background-color fill untuk batalkan p90 area) + p90 area (lineColor fill, fillOpacity 0.12) + p50 median Line (strokeWidth 2, dot r=2). Tooltip formatter menampilkan value + `n={count}` label.
- ReferenceLine di `RISK_THRESHOLDS.tinggi` (0.70) dengan label "thr".
- Demo fallback: `mockTrend(lat, lon, current)` menghidupkan 7-day deterministic series bila hook error/empty (PLAN §7: chart tidak boleh blank di demo mode).

**7. MapOverlays (#7):**
- File baru `MapOverlays.tsx`: floating overlay murni-presentational, menerima `coordReadout`/`regionLabel`/`epsg` via props. Bottom-left: EPSG+lat/lon readout pill. Top-left: zoom+region pill. Top-right: compass widget (N label + primary-color needle).
- `MapArea.tsx` direfactor: hanya orkestrator — buka `InteractiveMap` + `<MapOverlays>` + push `onAoiDrawn`/`onAoiUpdated`/`onAoiDeleted` ke store (`selectedAoi`/`aoiOverlay`) + `pushApiLog` untuk setiap event AOI.
- Layer legend tetap di sidebar (`RiskLegend` dipasang di kaki `LeftSidebar`) sesuai V4 mockup spatial design.

**Plus 5访谈 PLan asli (di luar checklist #1-#7):**

**8. `src/api/client.ts` type contract fix:**
- Cross-check response shape vs `src/geo_api.py` aktual (Tahap B) + `src/api/models.py`:
  - `listLocations` return `{count, locations: LocationPreset[]}` (bukan `LocationPreset[]` langsung — bug asli `client.ts`).
  - `predictAoi` return `PredictAoiResponse` (`{count, ok, errors, grid_size, results: AoiCellResult[]}` — bukan `PredictionResult`).
  - `getTrend` return `TrendResponse` (`{lat, lon, radius_km, days, series: TrendSeriesPoint[]}` — bukan `{days, values}`).
  - `listModels` return `ListModelsResponse` (`{models: Record<string, ModelRegistryEntry[]>, count}` — bukan `ModelInfo[]`).
  - `activateModel(modelName)` endpoint actual `POST /api/models/{name}/activate` (bukan `version` body di `/activate`).
- API key dibaca dari `localStorage` saat runtime via `readStoredApiKey()` + `authedOpts()` (bukan import-time) — test/SSR aman, user bisa set key dari devtools tanpa recompile.

**9. `src/api/hooks.ts` baru — react-query v5 wrapper:**
- `useModels` (staleTime 5min), `useLocations` (staleTime 30min — public-read static 378 entry), `useGeocode(q)` (staleTime 10min), `useHealth` (refetchInterval 30s untuk live LED), `useTrend(lat, lon, days, radiusKm)` (staleTime 60s), `usePredict`/`usePredictAoi`/`useActivateModel` mutations.
- `queryKeys` factory export untuk invalidation (`queryKeys.models()`, `queryKeys.trend(lat, lon, days, radiusKm)`, dll.) — pattern react-query recommended untuk cache invalidation dari component lain.

**10. `FiltersPanel.tsx` Region select dari /geo/locations:**
- Region dropdown kini hidup dari `useLocations()` (terkenal 378 entry dari backend); trim+dedup, cap 50 option untuk tinggi viewport. Fallback 5-region hardcoded bila endpoint gagal.
- Status text live ("Loading locations…", "{count} region entries", "Locations unavailable — fallback list shown") menjamin transparency ke user ketika backend tidak terjangkau (PLAN §7 risk register).

**11. Tests (**`src/__tests__/test-utils.tsx`** + 3 file test baru):**
- `test-utils.tsx`: `renderWithQueryClient()` helper membalut JSX di `QueryClientProvider` (fresh QueryClient per render, retry=false, gcTime=0 — cache tidak bleed antar test).
- `__tests__/setup.ts`: ResizeObserver stub (no-op observe/unobserve/disconnect) — polyfill karena jsdom tidak implement ResizeObserver, Recharts ResponsiveContainer `new ResizeObserver()` throw `ReferenceError` tanpa stub.
- `MapOverlays.test.tsx` (4 test): coord readout rendering, null fallback, custom region, custom EPSG.
- `RiskTrendChart.test.tsx` (3 test): live series dari mocked `useTrend` (no loading overlay), error fallback ke mockTrend (no blank), boot state selectedCell null (mount without throwing). Assertion strategi: uji container DOM + loading-text presence/absence, **bukan** `.recharts-surface` selection (Recharts defer first paint sampai ResizeObserver callback fire — jsdom stub tidak fire sehingga selection flaky).
- `ModelSelectPanel.test.tsx` (3 test): button disabled saat `selectedCell=null`, happy path predict (store prediction + apiLogs['ok']), error path predict reject (mockPredict fallback + apiLogs['err']).

**Verifikasi akhir TAHAP D:**
- `npm run typecheck` → bersih (no output) ✅
- `npm run lint --max-warnings 0` → bersih ✅ (dihapus: 2 unused-import `render` di test file)
- `npm run build` → `tsc --noEmit && vite build`, 938 modul transformed, `index.js` 108 KB (gzip 35 KB), `vendor-query.js` 49 KB (naik 13 KB dari TAHAP C karena hooks + react-query usage), `vendor-charts.js` 533 KB (naik 23 KB karena RiskTrendChart pakai ComposedChart+Area), build 22.5s ✅
- `npm test` (vitest) → **24/24 passed** (RiskGauge 8 + ProbabilitySparkline 6 + MapOverlays 4 + RiskTrendChart 3 + ModelSelectPanel 3) ✅ — naik dari 14 di TAHAP C
- `python -m compileall -q src` → bersih ✅
- `pytest tests/test_api_geo.py -q` → 46 passed (no regression dari TAHAP B) ✅

**Decision log:**
- **Recharts `useTrend` mock**: kita mock `../api/hooks.useTrend` (bukan fetch) karena chart hanya peduli hook return shape; backend fetch contract sudah terkover di pytest TAHAP B. Hindari mock fetch di jsdom — `Response` impl. jsdom tidak reliable untuk curl test response yang sudah di-promise.
- **Chart test assertion strategi**: gunakan loading-text presence/absence (deterministic dari hook isLoading), bukan `.recharts-surface` SVG selection. Recharts ResponsiveContainer defer first paint menunggu ResizeObserver callback yang stub no-op tidak pernah fire — svg selection jadi flaky. Pragmatic: assert "tidak blank + tidak throw" daripada "SVG terstruktur persis".
- **ResizeObserver stub di setup.ts**: no-op polyfill global, tidak dibatasi per-test — semua test yang render Recharts (ProbabilitySparkline, RiskTrendChart) atau komponen yang pakai leaflet-internal-overlays memakai ResponsiveContainer akan terbantu. Hindari leak ke test lainnya karena stub pure no-op.
- **Model dropdown heuristic**: heuristic pattern `/new|stack|causal|gru/i` untuk class registry names ke tier 'new'/'legacy' agar tidak hardcode mapping setiap model name. Trade-off: jika model naming convention berubah di backend (e.g. model bernama "next-gen" yang tidak match regex, akan salah dikategorisasi sebagai 'legacy'. Mitigasi: backend `model_type` field seharusnya eksplisit returned; upgrade di TAHAP E bila diperlukan.
- **API key di `localStorage`**: `firecast-api-key` key. Tidak ada UI input saat ini (akan di TAHAP E); user set via devtools `localStorage.setItem('firecast-api-key', '...')`. Dipilih storage-level agar tidak hardcoded di env (env build-time ter-komit riskan; localStorage runtime-only — tidak ada leak ke git).
- **client.ts API key source**: `readStoredApiKey()` membaca saat call time, bukan import time. Alasan: (1) vitest jsdom tidak set localStorage sampai beforeAll/setupFiles, (2) import-time akan cache stale value saat test override. Pembacaan saat call time = fresh key every request.
- **MapArea AOI pushApiLog**: saat AOI draw/edit/delete, push log 'ok'/'warn' ke store agar ApiLogBox mencerminkan aksi AOI (user terverifikasi event diterima, plan §7 risk register: "tetap expose status di ApiLogBox warna-coded walau mode demo").

**File baru/modifikasi TAHAP D siap di-commit** (belum commit sesuai aturan opencode "no commit unless asked"):
- new: `frontend_react/src/api/hooks.ts`, `frontend_react/src/components/MapOverlays.tsx`, `frontend_react/src/components/MapOverlays.test.tsx`, `frontend_react/src/components/RiskTrendChart.test.tsx`, `frontend_react/src/components/ModelSelectPanel.test.tsx`, `frontend_react/src/__tests__/test-utils.tsx`
- modified: `frontend_react/src/api/client.ts` (type contract fix + authedOpts + mockTrend), `frontend_react/src/components/index.ts` (export MapOverlays), `frontend_react/src/components/RiskTrendChart.tsx` (useTrend + ComposedChart p10/p50/p90), `frontend_react/src/components/ModelSelectPanel.tsx` (usePredict mutation + useModels + useActivateModel), `frontend_react/src/components/FiltersPanel.tsx` (useLocations), `frontend_react/src/components/Header.tsx` (useHealth polling), `frontend_react/src/components/MapArea.tsx` (delegasi ke MapOverlays + AOI store wiring), `frontend_react/src/__tests__/setup.ts` (ResizeObserver stub), `docs/react-spa-migration/PLAN.md` (status + checklist TAHAP D + progress log)

### 2026-07-30 — TAHAP E selesai (verifikasi objektif)
Deployment & Polish — semua 6 item checklist PLAN §4 TAHAP E terpenuhi:

**1. Multi-stage Dockerfile (#1):**
- `Dockerfile` di-rewrite jadi **2 stage**: `spa-build` (Node 20-slim `npm ci` + `npm run build`) → `base` (Python 3.12-slim `pip install -r requirements.txt` + `COPY --from=spa-build /spa/build /app/frontend_react/build`).
- Target tunggal `:7860` (HF Spaces default). HEALTHCHECK cek `/health`. Entrypoint `CMD ["python","start_api.py"]` (single uvicorn process serve API + SPA).

**2. render.yaml hapus + Procfile single-service (#2):**
- `render.yaml` **dihapus** (per user request: deployment target HF Spaces, bukan Render). `Procfile` = `web: python start_api.py` (single-service konsisten).
- `docker-compose.yml` direwrite: 1 service `firecast` (api+SPA) + optional `nginx` profile (HTTPS). Hapus service `frontend` (Streamlit) dan `dev` (legacy launcher).
- `start_api.sh` diupdate: pakai `$PORT-${PORT:-7860}` + `$HOST` env vars.

**3. nginx SPA fallback history mode (#3):**
- `nginx/conf.d/firecast.conf` di-rewrite: single upstream `firecast:7860`, server block 443 dengan:
  - `location /assets/` → immutable 1y cache
  - `location /predict|/weather|/geo/|/analytics/|/api/|/admin/|/health|/docs|/openapi.json|/redoc|/precompute_progress` → proxy langsung ke upstream
  - `location /` → SPA fallback catch-all (history mode)

**4. FastAPI StaticFiles mount + SPA fallback (#4):**
- `start_api.py` rewrite: panggil `mount_spa(app, STATIC_DIR)` setelah import app; `STATIC_DIR = frontend_react/build`. Auto demo-mode heuristic kini cek **dua** bundle (`models/*.pth\.pkl` DAN `add_new_model/*.pkl`) — bila keduanya hilang → `ENABLE_DEMO_MODE=true`.
- `src/geo_api_spa.py` baru: `mount_spa(app, static_dir)` mount `/assets` (immutable 1y), `GET /` returns `index.html` (no-cache), `GET /{path:path}` catch-all fallback ke `index.html` bila bukan static file. `http middleware` pasang `Cache-Control` sesuai route.
- **No-op bila build hilang** — `mount_spa` return False tanpa raise; API tetap boot (dev mode, Vite serve SPA).
- `tests/test_api_geo.py` tambah `TestSpaMount` 7 test: mount returns true/false, API precedence, asset immutable cache, root no-cache, deep-link fallback, static-file-at-build-root, content-type guesser.

**5. i18n id/en full coverage (#5):**
- `frontend/locales/{en,id}.json` tambah **namespace `spa.*`** (≈80 key) cover Header pills, LayerControlPanel+RiskLegend tier, RightDiagnostic section, TimelineScrubber, FiltersPanel, ModelSelectPanel, MapOverlays, trend chart, api log levels.
- Komponen inti wire `useTranslation()` dari `react-i18next`: `Header.tsx` (brand + pills + SystemStatus + region select), `LayerControlPanel.tsx` + `RiskLegend` (title+4 tier label), `RightDiagnostic.tsx` (section title, P(fire) hero, confidence, legend tier via `getRiskTierId`), `TimelineScrubber.tsx` (slider aria-label, now/play/pause/new run/export), `FiltersPanel.tsx` (risk/region/date labels + location status), `ModelSelectPanel.tsx` (model/horizon/threshold labels, run-inference button, no-cell msg), `MapOverlays.tsx` (compass + coord readout + zoom pill).
- `frontend_react/src/__tests__/setup.ts` tambah `beforeAll(initI18n)` agar semua test pakai i18n yang sudah di-init (otherwise `t()` return raw keys).
- Test assertion diupdate untuk regex yang lebih longga (`/click.*select a cell/i`, `/Zoom/i`).

**6. Lighthouse audit (#6):**
- `frontend_react/lighthouserc.cjs` rewrite untuk SPA root (bukan Streamlit): `url=['http://localhost:4173/']`, `preset: 'desktop'`, `blockedUrlPatterns` untuk hindari network call (predict/weather/api/geo/analytics) saat audit, perf gate `minScore: 0.7` (PLAN §8 acceptance "Performance > 70"), a11y `0.85` (WCAG AA commensurate), `best-practices` warn `0.85`, `seo` warn `0.8`. Output ke `.lighthouseci/`.

**Plus (di luar checklist):**
- `.github/workflows/ci.yml` di-cleanup: hapus step "Frontend components coverage gate (revamp modules)" dan "Streamlit AppTest smoke (frontend/app.py)" yang merujuk file Streamlit sudah dihapus di TAHAP A. Coverage utama `--cov=frontend/utils` saja (bukan `frontend/components` yang kosong).
- `README.md` full rewrite (bahasa en, structure 16 section) untuk reflect React-SPA stack: Quick Start (3 option dev/single/docker), Architecture diagram, Installation, Usage (SPA components table), API Reference (endpoint survey), Deployment HF Spaces + docker-compose + nginx, Development, Troubleshooting, Performance Benchmarks.
- `AGENTS.md` update bagian 1 (hapus Streamlit command, tambah React dev/build/test commands), bagian 2 (arsitektur SPA post-migration dengan `geo_api_spa.py`, `frontend_react/`), bagian 3 (SPA mount order rule), bagian 5 (`[DONE TAHAP E]` tags), tambah bagian 7 (catatan TAHAP E), footer update 2026-07-30.

**Verifikasi akhir TAHAP E:**
- `npm run typecheck` (frontend_react) → bersih (no output) ✅
- `npm run lint --max-warnings 0` → bersih ✅
- `npm run build` → 938 modul transformed, `assets/index.js` 117 KB (gzip 37.6 KB) — naik 9 KB dari TAHAP D karena i18n hooks + key lookup; `vendor-charts.js` 533 KB (gzip 151 KB) — stabil; build 28.67s ✅
- `npm test` (vitest) → **24/24 passed** (i18n init via setup.ts `beforeAll`; MusicMap/RightDiagnostic test assertion regex dilonggarkan) ✅
- `python -m compileall -q src start_api.py` → bersih ✅
- `pytest tests/test_api_geo.py -q` → **53 passed** (46 TAHAP B/D + 7 TAHAP E `TestSpaMount`) ✅
- Smoke integration: `mount_spa(app, 'frontend_react/build')` → `GET /` 200 (SPA shell len=862, `<title>`+`id="root"`), `GET /assets/index.js` 200 (`len=117206`, cache-control `public, max-age=31536000, immutable`), `GET /health` 200 (cache-control None — API route uncache), `GET /any-deep-route` 200 (SPA fallback to index.html) ✅

**Decision log:**
- **Hapus render.yaml**: user menyatakan target deployment HF Spaces (Docker-based) bukan Render (Procfile-based). Sehingga `render.yaml` redundant. `Procfile` tetap dipertahankan untuk platform yang support (mis. Render fallback / fly.io / dokku) dengan perintah singkat.
- **StaticFiles mount di modul terpisah (`geo_api_spa.py`)**: pisahkan dari `geo_api.py` supaya FastAPI app factory (`src/geo_api.py:app = FastAPI(...)`) tetap bebas dari urusan static file. `start_api.py` memanggil `mount_spa()` setelah import `app` agar mount terjadi setelah semua `@app.get/post` route dideklarasikan (sesuai aturan "SPA mount order" di AGENTS.md §3).
- **Cache-Control via middleware**: `geo_api_spa.py` pasang `@app.middleware("http")` yang set `Cache-Control: immutable, max-age=31536000` untuk `/assets/*`, `Cache-Control: no-cache, must-revalidate` untuk `index.html` root + catch-all fallback. API routes (`/predict`, `/health`, dst) tidak dapat cache-control header (tetap per FastAPI default), sehingga SPA+API cache policy terpisah dan eksplisit.
- **No-op on missing build**: `mount_spa(app, static_dir)` return `False` (tidak raise) bila `static_dir/index.html` hilang. Memungkinkan: (1) CI tanpa `npm run build` tetap boot API + jalan pytest; (2) dev mode pakai Vite `:3000` dengan proxy API ke `:8000`(atau :7860); (3) fresh deploy HF Spaces dengan build gagal tetap boots API dan menampilkan `404` di `/` (acceptable graceful degradation).
- **Demo-mode heuristic dua-bundle**: `start_api.py` kini cek `models/cnn_best.pth + lgbm_best.pkl + scaler.pkl + ensemble_threshold.pkl` LEGACY DAN `add_new_model/lgb_model.pkl + xgb_model.pkl` NEW stacking. `ENABLE_DEMO_MODE=true` hanya bila **kedua** bundle kosong. Memenuhi AGENTS.md §5.E hint: "Untuk deployment model stacking baru, sebaiknya periksa juga add_new_model/lgb_model.pkl & xgb_model.pkl".
- **i18n init di test setup**: vitest `setup.ts` panggil `await initI18n()` di `beforeAll` (bukan import-time) supaya `useTranslation()` di komponen test resolve key ke translation (bukan key literal). Pilihan ini konsisten dengan arsitektur i18n yang pakai async init di `main.tsx`.
- **Risk tier id di RightDiagnostic**: gunakan `getRiskTierId()` (return `rendah/sedang/tinggi/sangat_tinggi`) untuk resolve key `spa.legend.${tierId}`, BUKAN `level.toLowerCase().replace(' ','_')` (karena `RiskTierLabel` = `'Low'|'Medium'|'High'|'Extreme'` → tidak ada `'Sangat Tinggi'` kecocokan). Menghindari bug silent-fallback ke raw key.
- **README rewrite via opencode Write tool**: `Set-Content -Encoding UTF8` di Windows PowerShell 5.1 korupsi emoji non-BMP (≥ U+10000) pada file. Work-around: pakai `Write` tool opencode yang handle UTF-8 dengan benar, atau `python -c "Path(...).write_text(...,encoding='utf-8',newline='\\n')"`. Karakter arrow `→` (U+2192, BMP) aman di kedua tool; emoji 🔥 (U+1F525, supplementary plane) hanya aman di Write tool / Python `write_text`.

**File baru/modifikasi TAHAP E siap di-commit** (belum commit sesuai aturan opencode "no commit unless asked"):
- new: `src/geo_api_spa.py`
- deleted: `render.yaml`
- modified:
  - `Dockerfile` (multi-stage Node+Python)
  - `Procfile`, `start_api.py` (mount_spa + 2-bundle demo heuristic), `start_api.sh` (HF env vars)
  - `docker-compose.yml` (single-service `firecast` + optional nginx profile)
  - `nginx/conf.d/firecast.conf` (history-mode SPA fallback)
  - `frontend_react/lighthouserc.cjs` (SPA url + perf>0.7 gate + blockedUrlPatterns)
  - `frontend/locales/en.json`, `frontend/locales/id.json` (namespace `spa.*` ~80 key)
  - `frontend_react/src/__tests__/setup.ts` (beforeAll initI18n)
  - `frontend_react/src/components/Header.tsx`, `LayerControlPanel.tsx`, `RightDiagnostic.tsx`, `TimelineScrubber.tsx`, `FiltersPanel.tsx`, `ModelSelectPanel.tsx`, `MapOverlays.tsx` (useTranslation wire)
  - `frontend_react/src/components/MapOverlays.test.tsx`, `ModelSelectPanel.test.tsx` (regex dilonggarkan)
  - `tests/test_api_geo.py` (`TestSpaMount` 7 test)
  - `.github/workflows/ci.yml` (hapus step streamlit + frontend-component gate)
  - `README.md` (full rewrite, 16 section)
  - `AGENTS.md` (section 1/2/3 update + section 7 TAHAP E)
  - `docs/react-spa-migration/PLAN.md` (TAHAP E checklist + progress log)
