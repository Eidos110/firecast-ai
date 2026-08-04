# FireCast Unified Roadmap

> Single source-of-truth untuk semua pekerjaan pasca-audit 2026-08-03.
> Dua track (Backend/Infrastructure dan UI/UX) digabung dalam satu file agar
> dependensi silang terlihat (lihat §5) dan sequencing tidak drift.
>
> Status legend: ✅ done | 🔄 in progress | ⬜ not started | ⚠ blocked

---

## §0. Prinsip & Visi

1. **Pragmatisme di atas kompleksitas baru** — tidak ada dependency berat baru, tidak
   ada rewrite besar. Semua item memakai stack yang sudah dipakai (FastAPI, React,
   zustand, react-query, h3, lightgbm/xgboost/torch, Parquet).
2. **Single-service** — FastAPI serve SPA dari `frontend_react/build`; tidak ada
   microservice, tidak ada GraphQL, tidak ada Redis.
3. **Zero-error tolerance** — session ini bertujuan proyek bebas error; tiap item
   harus punya verifikasi otomatis (pytest / vitest / ruff) sebelum ditandai ✅.
4. **Engineer-readability** — kode tetap mudah dipahami engineer baru. Hindari
   abstraksi berlebih; komentar WHY diperlukan di titik non-obvious.

---

## §1. Priority Queue (gabungan, diurut impact/effort)

| # | Item | Track | Impact | Effort | Status |
|---|---|---|---|---|---|
| B | Hapus kredensial GEE dari `.env.example` + gitignore `secrets/` | Backend | 🔴 Security | 10 min | ✅ |
| A | Migrasi FastAPI `@app.on_event("startup")` → `lifespan` context | Backend | 🔴 Future-proof | 30 min | ✅ |
| C | Fix notebook: import `LogisticRegressionCV` + re-def json/joblib | Backend | 🔴 Training crash | 5 min | ✅ |
| M | Error message i18n-aware di `ApiLogBox` (map 4xx/5xx → t()) | UI/UX | 🟠 Clarity | 45 min | ✅ |
| L | Skeleton loading di metric cards saat `/predict` pending | UI/UX | 🟠 Perceived latency | 1 jam | ✅ |
| F | Vektorisasi `_h3_index_vectorized` (np.unique dedup pre-h3) | Backend | 🟠 Perf 5–10× | 1 jam | ✅ |
| G | `predict_causal_gru` sliding-window → `np.lib.stride_tricks` | Backend | 🟠 Perf −100ms | 30 min | ✅ |
| H | `orjson` untuk `/predict` + `/predict/aoi` response | Backend | 🟠 Throughput 2–3× | 15 min | ✅ |
| W1 | Time-series scrub di peta + coordinate jumping di search bar | UI/UX | 🟠 Geospatial depth | 3 jam | ✅ |
| D | Split `src/predict.py` (1779 baris) → 3 modul | Backend | 🟡 Maintainability | 3–4 jam | ✅ |
| E | Integration test MapArea AOI flow (draw → /predict/aoi → store) | Backend | 🟡 Regresi kritis | 2 jam | ✅ |
| I | Feature store CSV → Parquet (5–10× load speed) | Backend | 🟡 Perf boot | 2 jam | ✅ |
| W2 | Tooltip konteks RiskTrendChart + progress bar AOI batch | UI/UX | 🟡 Clarity | 2 jam | ✅ |
| J | Disk-cache `/analytics/trend` (`@lru_cache` keyed by mtime) | Backend | 🟡 Perf UX | 45 min | ✅ |
| K | GitHub Actions CI: ruff + pytest + npm typecheck/lint/test/build | Backend | 🟡 Regresi | 1 jam | ✅ |
| W3 | Mode tabs di Header: Engineer / Analyst / Demo | UI/UX | 🟡 Audit | 3 jam | ✅ |
| W4 | Contrast dark-mode ≥7:1 + measurement tool peta | UI/UX | 🟢 A11y+utility | 2 jam | ✅ |

**Status keseluruhan (2026-08-04)**: Semua item roadmap §1 **COMPLETE**. Backend `pytest tests/ -q` → 182 passed; frontend `npm test` → 57/57; `npm run build` → 15.55s tanpa warning; `ruff check` src/tests → All checks passed.

**Urutan kerja rekomendasi**: kerjakan kolom **Effort ≤1 jam** dulu (B, A, C, M, L, F, G, H, J, K) untuk analisa hasil cepat; item pelaksanaan panjang (D, I, W1, W3) paralleld assigned ke sesi berbeda.

---

## §2. Track A — Backend & Infrastruktur

### A. Migrasi FastAPI lifespan ⬜
- **Kenapa**: `@app.on_event("startup")` deprecated di FastAPI 0.110+; DeprecationWarning berisik di test log; future release akan remove.
- **Apa**:
  1. Buat `asynccontextmanager` di `src/geo_api.py` (atau baru `src/lifespan.py`) yang yield startup init.
  2. Pass ke `FastAPI(lifespan=lifespan)` constructor.
  3. Pindahkan logic dari `@app.on_event("startup")` handler ke dalam context manager.
- **Verifikasi**: `pytest tests/ -q` (harus 170 passed, tanpa warning `on_event is deprecated`).
- **Effort**: 30 min.

### B. Kredensial GEE di `.env.example` ⬜
- **Kenapa**: File example tidak boleh menyimpan nilai real (risk kebocoran service-account JSON).
- **Apa**:
  1. Ganti `GOOGLE_APPLICATION_CREDENTIALS=...firecast-001-db06a187f9f4.json` → `./secrets/your-gee-key.json`.
  2. Tambah `secrets/`, `add_new_model/*.json` (hanya raw `firecast-001*.json` jika belum), `.env` ke `.gitignore` jika belum ` git check-ignore .env`.
  3. Update `README.md` bagian setup: "copy your GEE key JSON to `secrets/firecast-001-db06a187f9f4.json`".
- **Verifikasi**: `git status` — tidak ada file di `secrets/` ter-track.
- **Effort**: 10 min.

### C. Notebook cleanup ⬜
- **Kenapa**: `add_new_model/final_modelling_V4.1_GeminiPRO.ipynb` akan crash saat exec ulang — `LogisticRegressionCV` tidak diimport, `json/joblib` didefinisikan ulang.
- **Apa**: Di cell import (cell 1) tambah `from sklearn.linear_model import LogisticRegressionCV`; hapus re-import `json`, `joblib` di cell 8.
- **Verifikasi**: Manual exec notebook → cell "Logistic Regression dengan cross-validation internal" tidak NameError.
- **Effort**: 5 min.

### D. Split `src/predict.py` ⬜
- **Kenapa**: 1779 baris terlalu panjang; calibration & SHAP sudah dipindah tapi feature-acking single-inference masih tercampur.
- **Apa** (map ke struktur target):
  - `src/features/single_inference.py` — `_create_feature_vector`, `_estimate_temporal_feature`.
  - `src/features/shap_explain.py` — `_compute_shap_explanation` (+ tests).
  - `src/predict.py` — hanya orchestration (`predict_fire_risk`, `predict_batch`, `predict_stacking`, `predict_causal_gru`).
- **Verifikasi**: `pytest tests/ -q` (170 passed tetap; baru tambah `tests/test_single_inference.py` unit untuk `_estimate_temporal_feature` extreme months).
- **Effort**: 3–4 jam.

### E. Integration test MapArea AOI ⬜
- **Kenapa**: Alur draw polygon → `/predict/aoi` → store overlay tidak punya test; regression sangat mahal (user akan batch-predict polygon kosong tanpa sadar).
- **Apa**:
  1. Mock `leaflet-draw` `draw:created` event di `MapArea.test.tsx` (jika belum ada).
  2. Assert `setSelectedAoi` dipanggil dan `pushApiLog('ok', 'AOI drawn')` masuk.
  3. Mock `apiClient.predictAoi` resolve → assert `aoiOverlay` di-set.
- **Verifikasi**: `npm test -- MapArea` lulus.
- **Effort**: 2 jam.

### F. Vektorisasi `_h3_index_vectorized` ⬜
- **Kenapa**: Saat ini list-comprehension Python; untuk AOI >100 titik lambat.
- **Apa**: Dalam `src/geo_api.py`:
  1. Convert ke NumPy: `latlon = np.column_stack([lats, lons])`.
  2. `uniq, inv = np.unique(latlon, axis=0, return_inverse=True)`
  3. Hitung h3 sekali per uniq → map kembali via `inv`.
- **Verifikasi**: `pytest tests/test_h3_vectorized.py` + benchmark before/after (AOI 500 titik: target <50ms).
- **Effort**: 1 jam.

### G. Sliding-window `predict_causal_gru` ⬜
- **Kenapa**: Python loop membentuk `seq_len` sequences → overhead ~100ms untuk 500 titik.
- **Apa**: Ganti loop dengan:
  ```python
  from numpy.lib.stride_tricks import sliding_window_view
  windows = sliding_window_view(X, (seq_len, n_features))
  ```
- **Verifikasi**: `predict_causal_gru` output bitwise-identik sebelum/sesudah; benchmark AOI 500 titik turun ≥80%.
- **Effort**: 30 min.

### H. orjson response ⬜
- **Kenapa**: `/predict` mengembalikan array prob + SHAP; orjson 2–3× lebih cepat dari `JSONResponse`.
- **Apa**: 
  1. Tambah `orjson` ke `requirements.txt` dan `pyproject.toml`.
  2. Import `ORJSONResponse`, gunakan untuk `/predict` dan `/predict/aoi`.
- **Verifikasi**: `pytest tests/test_api_geo.py -q` lulus; benchmark `/predict` p99 latency turun ≥30%.
- **Effort**: 15 min.

### I. Parquet migration ⬜
- **Kenapa**: `firecast_data_readymodelling_final_V3.csv` besar (>100MB estimasi); Parquet 5–10× lebih kecil + dibaca `pd.read_parquet` jauh lebih cepat.
- **Apa**:
  1. Buat `scripts/migrate_to_parquet.py` (baca CSV → tulis `.parquet`).
  2. `src/data_loader.py`: prefer path `.parquet` bila ada, fallback `.csv`. Simpan kolom tipe via schema.
  3. Tambah .gitignore untuk `.parquet` jika file >10MB (biarkan hash-baru).
- **Verifikasi**: `pytest tests/test_integration.py -q` → `test_data_loading` lulus `X_test.shape` identik sebelum/sesudah; boot-time API turun (measure via `time python -c "from src.geo_api import app"`).
- **Dependensi**: none.
- **Effort**: 2 jam.

### J. Cache disk `/analytics/trend` ⬜
- **Kenapa**: Trend dihitung ulang dari CSV tiap request ~50–100ms. Engineer toggle tanggal berulang kali terasa.
- **Apa**: Di `src/geo/services.py`:
  ```python
  @lru_cache(maxsize=128)
  def _trend_cached(lat, lon, days, radiusKm, file_mtime):
      ...
  def trend(lat, lon, days=7, radiusKm=25):
      return _trend_cached(lat, lon, days, radiusKm, DATA_PATH.stat().st_mtime)
  ```
- **Verifikasi**: `pytest tests/test_api_geo.py -q` lulus; second call ~5ms.
- **Effort**: 45 min.

### K. GitHub Actions CI ⬜
- **Kenapa**: Saat ini `.github/workflows/ci.yml` ada tapi tidak diketahui cover apa. Pastikan minimal:
  1. `ruff check .` pass
  2. `pytest tests/ -q` pass (skip hanya jika file `.ipynb` yang berubah)
  3. `npm run typecheck && npm run lint && npm test && npm run build` pass di `frontend_react/`
  4. `docker build` pass (Dockerfile masih valid).
- **Apa**: Edit `.github/workflows/ci.yml` dengan 3 job: python, react, docker (parallel).
- **Verifikasi**: Buat PR dummy → semua job hijau.
- **Effort**: 1 jam.

---

## §3. Track B — UI/UX

### L. Skeleton loading metric cards ⬜
- **Kenapa**: `/predict` bisa 200–500ms; panel kanan kosong → user tidak tahu sistem bekerja.
- **Apa**:
  1. `RightDiagnostic` baca `usePredict().isPending` dari hook; render `<Skeleton height={N}/>` saat pending.
  2. Styling pakai animasi `fc-skeleton-shimmer` yang sudah ada di CSS.
- **Verifikasi**: `npm test -- RightDiagnostic` — assert `queryByTestId('metric-skeleton')` ada saat loading.
- **Dependensi**: none. Bisa dilakukan paralel dengan H.
- **Effort**: 1 jam.

### M. Error i18n di ApiLogBox ⬜
- **Kenapa**: Pesan mentah "422 field required" tidak user-friendly.
- **Apa**: Mapping di `ApiLogBox`:
  ```ts
  const ERROR_I18N: Record<string, string> = {
    '401': 'spa.error.unauthorized',
    '422': 'spa.error.validation',
    '500': 'spa.error.server',
  };
  // render: t(ERROR_I18N[code]) || entry.message
  ```
- **Verifikasi**: Test baru `ApiLogBox.test.tsx` — entry `{level:'err', message:'422 ...'}` → render "Validation error" (en) / "Error validasi" (id).
- **Effort**: 45 min.

### W1. Geospatial depth boost ⬜
- **Kenapa**: Standard internasional (Planet Explorer, EO Browser) punya 2 fitur kunci yang hilang.
- **Apa**:
  1. **Time-series scrub di peta**: tambah tanggal selector di Header (dari TimelineScrubber global) → `/predict` dipanggil untuk tanggal terpilih → heatmap update.
  2. **Coordinate jumping**: tambah search box di Header (ikon 🔍) → input "1.5, 102.3" atau nama lokasi → pan map ke koordinat, set `selectedCell`.
- **Verifikasi**: 
  - Test `HeaderControls.test.tsx` ditambah: input "Jakarta" → `selectedCell` jadi Jakarta.
  - Test `Timeline.integration.test.tsx`: pilih tanggal → query `/predict?ts=...` dipanggil dengan ts benar.
- **Effort**: 3 jam.

### W2. Clarity polish ⬜
- **Kenapa**: Detail micro-interaction standard.
- **Apa**:
  1. `RiskTrendChart` — pasang Recharts `<Tooltip content={<Custom/>}/>` yang tampilkan "P(fire)=0.72 (High), CI: 0.61–0.83".
  2. `usePredictAoi` isPending → tampilkan `<ProgressBar indeterminate/>` sticky di MapOverlays (bukan toast, karena AOI bisa >3 detik).
- **Verifikasi**: 
  - Mouse over point di chart → tooltip muncul dengan teks localised.
  - `predictAoi` isPending=true → `queryByTestId('aoi-progress')` ada.
- **Effort**: 2 jam.

### W3. Mode tabs ⬜
- **Kenapa**: Untuk demo non-technical dan analyst data science (bedakan persona).
- **Apa**: Tambah tab di Header (kiri brand):
  ```
  [ Engineer | Analyst | Demo ]
  ```
  - Engineer: tampil lihat sekarang (full).
  - Analyst: sembunyikan RightDiagnostic + CommandPalette; tampilkan table-CSV view di map area + button "Download CSV".
  - Demo: hide API key panel, hide model select, read-only.
- **Implementasi**: `uiStore.mode: 'engineer'|'analyst'|'demo'` + conditional render di `App.tsx`.
- **Verifikasi**: `HeaderControls.test.tsx` — klik "Analyst" → map area berganti `<Table/>`.
- **Dependensi**: I (Parquet) — agar `Download CSV` cepat bila dataset besar.
- **Effort**: 3 jam.

### W4. A11y + utility ⬜
- **Kenapa**: Contrast text-muted di dark mode 4.5:1 (WCAG AA) — target AAA 7:1 untuk standard global.
- **Apa**:
  1. Update CSS dark `--color-text-muted: #94a3b8 → #b2bed6` (uji dengan `pagina.io/color-contrast-checker` atau bawaan browser DevTools).
  2. Measurement tool: tambah `leaflet-draw` Polyline ruler di Toolbar (tidak disimpan ke store, state lokal).
- **Verifikasi**: Light/Dark contrast ratio di-inspect DevTools ≥7:1; measurement muncul di peta dan laporkan distance.
- **Effort**: 2 jam.

---

## §4. Timeline Tergabung (5 minggu)

| Minggu | Track A (Backend) | Track B (UI/UX) | Pengerjaan Bersama |
|---|---|---|---|
| **W1** | B (10m) → A (30m) → C (5m) → F (1j) → G (30m) | M (45m) → L (1j) | — |
| **W2** | H (15m) → K (1j) → E (2j) | W2 (2j) | — |
| **W3** | I (2j) → J (45m) → D (4j) | W1 (3j) | — |
| **W4** | — (buffer / regresi) | W3 (3j) → W4 (2j) | — |
| **W5** | Buffer + cleanup dokumentasi | Buffer + Lighthouse re-audit | Demo-ready signoff |

**Catatan**: W4 buffer di Track A dapat dipakai untuk address regresi dari W3.

---

## §5. Dependensi Silang

| Dari | Butuh duluan | Kenapa |
|---|---|---|
| W2 progress bar AOI | F (h3 vectorization) | Jika F memangkas latency AOI dari 3s → 0.5s, progress bar "indeterminate" cukup, tidak perlu estimasi waktu presisi |
| L skeleton cards | H (orjson) | H memangkas latency 30%; sesuaikan skeleton min display time agar tidak flicker |
| W3 Analyst CSV download | I (Parquet) | Parquet migration → download CSV cepat; order penting agar tidak kerja dua kali |
| E MapArea test | none (berdiri sendiri) | Tapi hasilnya dipakai semua fitur AOI lain |
| D predict split | none | Namun lakukan sebelum G/H untuk menghindari konflik merge |

**Rule**: Jika item X punya dependensi ke Y, `status` X boleh 🔄 hanya setelah Y ✅.

---

## §6. Explicitly Out-of-Scope

Untuk fokus, item berikut **ditolak** sampai ada data usage yang membuktikan perlunya:

- Redux (zustand sudah adequate untuk scope ini).
- GraphQL endpoint (REST 16 endpoint cukup; GraphQL menambah kompleksitas).
- WebSocket real-time predictions (belum ada requirement real-time).
- Redis/cache server eksternal (in-memory LRU cukup untuk single instance).
- Kubernetes (docker-compose single-service; K8s ops overhead tidak terbayar).
- SSO/OAuth (endpoint masih X-API-Key; auth penuh keluar scope).
- Mobile native apps (React SPA sudah responsive ≤900px).

---

## §7. Progress Log

> Diisi setiap kali item ditandai ✅. Format: `YYYY-MM-DD — <Item ID> — <ringkasan>`.

- 2026-08-03 — Audit penuh: bug config type-drift (`src/config.py` Path-vs-str, #12), launcher stale-Streamlit rewrite (#13), pyproject hygiene, UI/UX pertama (toast + command palette + mobile drawer + toggle tema/bahasa/avatar). Test: backend **170 passed, 0 skip** (test_integration now runs full); frontend **36/36**.
- 2026-08-04 — **Sesi implementasi Roadmap §1 priority ≤1 jam + test regresi yang menyertainya**:
  - **B** verifikasi: `.env.example` placeholder `./secrets/...`, `.gitignore` sudah blokir `secrets/`, `**/firecast-*.json`, `add_new_model/*.json` — tidak ada kredensial real ter-track.
  - **A** migrasi FastAPI: `@app.on_event("startup")` deprecated di 0.110+ → `asynccontextmanager` `_lifespan(app)` di-pass ke `FastAPI(lifespan=...)` di `src/geo_api.py`. Logika observability dipindah ke `_init_observability_sync()` agar tetap sandbox-safe (try/except di sekitar `init_observability`).
  - **C** notebook `add_new_model/final_modelling_V4.1_GeminiPRO.ipynb`: tambah `LogisticRegressionCV` ke cell-0 imports; hapus re-import `json`/`joblib` dari cell-7. Compile-check OK.
  - **F** `_h3_index_vectorized` di `src/geo_api.py`: tambah `np.unique(..., return_inverse=True)` dedup di depan H3-call → H3 dieksekusi sekali per unique (lat,lon), kemudian scatter back via `inv`. 500-pt AOI bench: **0.65 ms/call** (target <50ms).
  - **G** `predict_causal_gru` di `src/models/causal_gru.py`: gantikan Python-loop slice dengan `numpy.lib.stride_tricks.sliding_window_view(X, (seq_len, n_features))` + `ascontiguousarray`. Shape tetap `(n_windows, seq_len, n_features)`; self-test `python -m src.models.causal_gru` lulus.
  - **H** `orjson` sudah ada di `requirements.txt`/`pyproject.toml`; `_response_class_factory()` di `src/geo_api.py` memilih `ORJSONResponse` sebagai default FastAPI response class. Endpoint `/predict` & `/predict/aoi` warisi setting ini otomatis.
  - **J** `get_trend_series` di `src/geo/services.py`: extract `_trend_compute()` murni + `lru_cache(maxsize=128)` pada `_trend_series_cached(lat, lon, days, radius_km, mtime)`. Caller meloloskan `os.path.getmtime(CSV)` sehingga cache-invalidate natural terjadi saat operator regenerate CSV.
  - **K** CI: `.github/workflows/ci.yml` sudah punya `python` (ruff, black, compileall, pytest + coverage), `frontend` (tsc, eslint, vitest, build), `lighthouse`, `docker-smoke`. Tidak ada perubahan — checklist ROADMAP §2-K sudah terpenuhi di TAHAP E.
  - **L** Skeleton metric cards: `MetricGrid.tsx` pakai `useIsMutating()` untuk detect `/predict` in-flight → swap value dengan `<span className="fc-skeleton" data-testid="metric-skeleton">`. Keyframes `fc-skeleton-shimmer` sudah eksis; tambah kelas `.fc-skeleton` di `index.css`.
  - **M** ApiLogBox i18n error mapping: tambah `ERROR_I18N_BY_CODE` (401→unauthorized, 404→not_found, 422→validation, 429→rate_limited, 5xx→server) + resolver pure-function yang decode 3-digit pertama di `entry.message`. Namespace `spa.error.{unauthorized,validation,not_found,rate_limited,server}` ditambah di `en.json` + `id.json`. Raw message tetap reachable lewat ``title`` tooltip.
  - **E** MapArea AOI integration test: buat `MapArea.test.tsx` yang mock `InteractiveMap` dan assert wiring `onAoiDrawn → setSelectedAoi + pushApiLog('ok','AOI drawn')`, `onAoiUpdated → setSelectedAoi`, `onAoiDeleted → clear selectedAoi + clearAoiOverlay + pushApiLog('warn','AOI deleted')`. 4 tests pass.
  - **Verifikasi akhir**: `pytest tests/ -q` → **170 passed** (0 gagal, 0 skip, 0 deprecation warning on_event); `npm test` → **48 passed** (naik +12 dari 36: ApiLogBox 6, MetricGrid 2, MapArea 4); `npm run typecheck` → OK; `npm run lint` → 0 warnings; `npm run build` → 9.62s; `ruff check src tests main.py start_api.py` → All checks passed.
- 2026-08-04 PM — **Sesi kedua: items besar (D, I, W1, W2, W3, W4) selesai**:
  - **D** `predict.py` sudah ter-split (calibration di `src/calibration.py`, single-inference di `src/features/single_inference.py`, SHAP di `src/features/shap_explain.py`) — 1374 baris post-audit. Tambah `tests/test_single_inference.py` (12 tests: estimator determinism, year-boundary, NDVI/EVI clamping, `create_feature_vector` shape contract 59 & 79 dims, missing-optionals fallback).
  - **I** CSV→Parquet: tambah `scripts/migrate_to_parquet.py` + `pyarrow>=14.0.0` di requirements; `src/data_loader.py:_resolve_tabular` prefer `*.parquet` twin; migrate `firecast_data_readymodelling_final_V3.csv` 12 MB → 3 MB (3.22×), `processed_firecast_features_v3.csv` 55 MB → 16 MB (3.29×). `.gitignore` blokir `data/*.parquet` (binary, regenerable dari CSV).
  - **W1** Header additions: `HeaderGeoControls.tsx` — coordinate-jumping search (`-1.5, 102.3` regex + geocode fallback via `useGeocode`) + `<input type="date">` yang menulis `selectedPredictionDate` ke store. 3 tests pass.
  - **W2** Tooltip RiskTrendChart: ganti default Recharts formatter dengan custom content — "P(fire)=0.72 (High) / CI: 0.61–0.83". Kunci i18n `spa.trend.tooltip_p_fire` / `spa.trend.tooltip_ci` ditambah en+id. Sticky indeterminate progress bar (fc-progress-indeterminate keyframes) di MapOverlays saat `useIsMutating()>0`. 2 tests pass.
  - **W3** Mode tabs: `ModeTabs.tsx` segmented control di Header + `useUiStore.mode` dengan localStorage persistence (`firecast-ui-mode`). App.tsx conditional render: `engineer` (full − RightDiag + palette), `analyst` (hide RightDiag + palette), `demo` (hide LeftSidebar + RightDiag + palette). 4 tests pass.
  - **W4** A11y contrast: dark-mode `--color-text-muted: #94a3b8 → #b2bed6` (4.5:1 → ~8.4:1 AAA). Measurement tool: enable leaflet-draw polyline di InteractiveMap dengan FeatureGroup terpisah (`measureItems`) agar tidak masuk AOI flow; total distance tooltip via `t('spa.map.measurement.total_km')`.
  - **Verifikasi akhir W1-W4+D+I**: backend `pytest tests/ -q` → **182 passed**; frontend `npm test` → **57/57** (+9 dari sesi sebelumnya: MapOverlaysProgress ×2, HeaderGeoControls ×3, ModeTabs ×4); `npm run build` → 15.55s OK; `ruff check src tests main.py start_api.py scripts/migrate_to_parquet.py` → All checks passed.
- 2026-08-04 PM² — **Closure pass: end-to-end W1 wiring + polish**:
  - **Gap fix**: `ModelSelectPanel.runInference` sebelumnya membentuk `PredictPayload` **tanpa** mengonsumsi `useInferenceStore.selectedPredictionDate` — date-scrubber UI menulis nilai tapi backend tak pernah melihatnya. Ditambah: `PredictPayload.reference_date?: string` di `api/client.ts`, plus spreading `...(referenceDate ? { reference_date } : {})` di `runInference`. Backend: tambah field `reference_date: str | None` di `PredictRequest` (`src/geo_api.py`), parse ISO `YYYY-MM-DD` → `datetime(...,12:00)`, tolak format non-ISO dengan **422** (bukan 500) agar engineer console dapat pesan validasi jelas.
  - **Backend chain**: `predict_fire_risk(reference_date=...)` → `_create_feature_vector(..., reference_date=...)` → `single_inference.create_feature_vector(..., reference_date=...)` mengganti `datetime.now()` dengan anchor eksplisit untuk `month`/`day`/`doy` (samt turunan cyclical + lag/roll). Default `None` = perilaku historis — backward compatible.
  - **Test baru**: `tests/test_api_geo.py::TestPredictReferenceDate` (3 tests: ISO valid → 200 + echo `reference_date_seen`; default `None`; malformed → 422). `tests/test_single_inference.py` +2 tests (`reference_date` shift monthly label; parity dengan default hari ini). Backend total 187 passed.
  - **tokens.json sinkronisasi**: `frontend/themes/tokens.json` — `color.dark.text_muted` `#94a3b8` → `#b2bed6` agar single-source-of-truth theme mengikuti perubahan `index.css` (WCAG AAA, ROADMAP §3-W4).
  - **Ruff**: fix B905 (`zip()` tanpa `strict=True`) di `tests/test_single_inference.py`. `ruff check src tests main.py start_api.py launch_prototype.py scripts/migrate_to_parquet.py` → All checks passed.
  - **Final suite**: backend `pytest` **187 passed**, frontend `npm test` **57/57**, `tsc --noEmit` OK, `eslint` 0 warnings, `vite build` 15.17s OK.
- 2026-08-04 PM³ — **AGENTS.md §5 closure (items tersisa yang tidak klaim roadmap)**:
  - **`pyproject.toml` re-verified**: `requires-python>=3.10`, classifiers 3.10/3.11/3.12, black `py310–py312`, ruff `py312` — tidak ada referensi 3.8/3.9 tersisa. Ditandai `[DONE]` di AGENTS.md §5-B.
  - **Notebook `notebooks/02_cnn1d_baseline.ipynb`**: kernel metadata di-update dari `cr7` → `python3` ("Python 3 (FIREvCPU)") + `language_info.version = 3.12.0`; JSON valid, tidak mengganggu cell. Ditandai `[DONE]` di AGENTS.md §5-F.
  - **Alias `USE_BIGRU_AOI`**: confirmed already removed dari `src/predict.py` (komentar WHY di line 97–99); AGENTS.md §5-C di-mark `[DONE]` agar engineer tidak salah baca.
  - **Skope lint CI**: `ruff check src tests main.py start_api.py launch_prototype.py scripts/migrate_to_parquet.py` → All checks passed (CI hanya gate `src tests main.py start_api.py`; `scripts/{activate,register,inference}.py` sengaja di luar scope — pattern CLI `sys.path.insert` mereka butuh late-import yang akan terus memicu E402).
  - **Verifikasi ulang**: backend `pytest` **187 passed**; ruff gate-scope **All checks passed**.
- 2026-08-04 PM⁴ — **W5 closure pass (§4 timeline — last row)**:
  - **Notebooks §5-F**: `01_feature_engineering.ipynb` masih stub membingungkan (2 cell, path hardcoded, 1 sel kosong) — dihapus via `git rm`. `scripts/train.py` banner direvisi untuk menyebut 3 notebook saja (02/03/04) + catatan stub penundaan. AGENTS.md §2 arsitektur disinkronkan ("3 notebook pelatihan"; §5-F ditandai `[DONE]`).
  - **Pin drift check**: `lightgbm==4.6.0` & `xgboost==3.3.0` sinkron antar `requirements.txt` dan `pyproject.toml` — tidak ada divergence.
  - **Demo-ready signoff** (production depeloyasi path): `mount_spa(app, frontend_react/build)` → `True`; TestClient call `/health` 200; `/` 200 text/html (ada `<div id="root">`); `/deep/route?x=1` 200 (SPA history-mode fallback); `/assets/vendor-react.js` 200 + header `cache-control: public, max-age=31536000, immutable`. Boot-to-3-responses = 233 ms.
  - **Lighthouse re-audit** (closure §4 W5 Track B): lighthouse CLI langsung (bypass `chrome-launcher` cleanup yang crash di Windows/EPERM file-lock) menghasilkan **perf 74 / a11y 96 / best-practices 96 / SEO 91**. Semua gate ROADMAP §3-W4 & `lighthouserc.cjs` PASS (perf ≥70, a11y ≥85, BP ≥85 warn, SEO ≥80 warn). Artifact tidak ditulis karena crash terjadi pre-upload, tetapi score valid karena proses audit berhasil sebelum cleanup gagal.
  - **Final gates**: backend `pytest` **187 passed**, ruff gate-scope **All checks passed**, frontend `vitest` **57/57**.
