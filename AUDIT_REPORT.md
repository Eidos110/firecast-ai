# Pemberitahuan & Planning — Audit & Redesign FireCast

> Tanggal: 2026-07-20  
> Lingkup: seluruh codebase (backend `src/`, frontend Streamlit `frontend/`, frontend React `frontend_react/`, infrastruktur/deploy).  
> Metode: audit read-only (compileall pass, pytest 28 passed/1 skipped). Tidak ada perubahan kode pada tahap ini.

---

## 1. PEMBERITAHUAN

### 1.1 Ringkasan temuan

| Kategori          | Jumlah | Kritis | Tinggi | Sedang | Rendah |
|-------------------|-------:|------:|------:|------:|------:|
| Bug aktif         |   22   |   0   |  16   |  22    |  34    |
| AntiPattern        |    8   |   —   |   —   |   —    |   —    |
| CodeSmell          |   28   |   —   |   —   |   —    |   —    |
| Security           |    5   |   1   |   1   |   3    |   —    |
| Inconsistency      |    9   |   —   |   —   |   —    |   —    |
| UI/UX & A11y       |   ~30  |   —   | berserak di semua file frontend | — | — |
| **TOTAL identifikasi** | **~100+** | **1** | **~20** | **~30** | **~50** |

> Catatan: bug historis AGENTS.md #1–7 sudah terkonfirmasi FIXED. Audit ini menemukan **issue baru yang belum terdokumentasi**.

### 1.2 Sumber data audit (paralel, 3 subagent)

1. **Backend `src/`** — 72 issue, 16 file diperiksa penuh.
2. **Frontend Streamlit + React** — ~95 issue, 20 file Python + 7 file TS/TSX/CSS.
3. **Infra/dependency/deploy** — ~20 issue, requirements, Docker, Railway, Makefile, tests, git-tracking.

---

## 2. ISSUE PALING KRITIS (wajib diperbaiki dulukan)

### 2.1 Backend — Top 5

1. **`src/models/causal_gru.py:12-13` & `bigru.py:11-12` memakai `import torch` top-level.**  
   AntiPattern High → di sandbox Railway/HF, `import` modul langsung gagal → **seluruh endpoint `/predict` (stacking) gagal 503** padahal torch tersedia.  
   Fix: pindah ke pola `_get_torch()` lazy seperti `cnn.py`.

2. **`.env`: `API_SECRET_KEY=your_secure_api_secret_key_here` (placeholder non-empty).**  
   Security High. `auth.get_api_key` hanya cek `is None`, sehingga placeholder literal menjadi API key **valid yang bisa ditebak**.  
   Fix: ganti secret 64-char acak ATAU tambah blacklist placeholder di `auth.py:26`.

3. **`src/models/cnn.py:load_state_dict._set_nested` (baris 110–129) index `OrderedDict[int]`** → `TypeError` saat load bobot legacy `.pth` key `conv_block1.0.*`.  
   Fix: pakai `list(cur._modules.values())[int(part)]` atau jadikan `TunedCNN1D` subclass `nn.Module` resmi.

4. **`src/models/cnn.py:eval()` (baris 173–175) noop** — tidak mempropagasi `.eval()` ke sub-layer BatchNorm. BatchNorm tetap train-mode → output inference bergeser tergantung batch. Untuk API fire-risk, ini bisa menggeser skor ±0.1–0.3.  
   Fix: subclass `nn.Module` (otomatis `.eval()` rekursif).

5. **`src/feature_engineering.py:205` `.columns.drop(['label'])` KeyError** bila DataFrame inference tidak punya kolom `label`.  
   Fix: `.drop(['label'], errors='ignore')`.

### 2.2 Frontend — Top 5 (UI/UX + bug)

1. **Threshold risiko tidak konsisten di 4 tempat** (Critical).  
   - `theme.get_risk_level`: `<0.3 rendah / <0.5 sedang / <0.7 tinggi`  
   - `interactive_map_simple.py` JS: `>=0.8 Extreme / >=0.6 High / >=0.3 Medium`  
   - `results_display.py _get_temporal_action_recommendation`: `0.6/0.8`  
   - `InteractiveMap.tsx getRiskLevel`: `0.8/0.6/0.3`  
   → skore 0.5 dilabel "Medium" di marker, "tinggi" di sidebar, saran "Waspada". User kebingungan.  
   Fix: **single-source** `theme.RISK_THRESHOLDS` di_FE + komponen serialize ke JS.

2. **Warna risiko tidak single-source (`RISK_COLORS` tidak teknis).**  
   `tinggi=#ef4444` di theme, `#f97316` di prediction_engine, `sangat_tinggi=#7f1d1d` di theme vs `#991b1b` di InteractiveMap.tsx/map_interface.py. Avatar/map berbeda warna untuk level yang sama.  
   Fix: satu token CSS `--risk-high / --risk-extreme`, dipakai semua komponen.

3. **`weather_display.py:138` baca key `hourly_forecast`** padahal `weather_api.py` return `forecast` → blok forecast 24 jam **tidak pernah tampil**.  
   Fix: rename key salah satu sisi.

4. **`results_display.py:874` `prediction_result.get("model_confidence", 0.85)`** — key yang benar `"confidence"` (lihat `_post_process_results:469`). User selalu melihat confidence **85% palsu**.

5. **`gee_data.py:209` `sort('CLOUDY_PIXEL_PERCENTAGE', False)`** — `False` di Earth Engine berarti `ascending=False` → mengambil image **paling berawan**. Selain itu `sidebar.py:714` tampilkan "✅ Data satelit (GEE)" padahal data synthetic fallback (GEE mati). Misleading High.

### 2.3 Infra — Top 5

1. **`Dockerfile` single-stage Streamlit**, tetapi `docker-compose.yml` & `Makefile` memanggil `docker build --target api/frontend/development/react-builder` yang **tidak ada**. Setiap `docker-compose build` langsung gagal. (Critical, Deploy)

2. **`lightgbm==3.3.5`** dipin di `requirements.txt:36`, tetapi runtime 4.6.0 & `pyproject.toml` tulis `lightgbm>=3.3.5`. `pyproject.dependencies` bahkan tidak cantum `xgboost/shap/streamlit/fastapi/h3/slowapi/sqlmodel` → `pip install .` tidak menghasilkan app fungsional. Sklearn 1.0.2 (latih) vs 1.9.0 (runtime) → `InconsistentVersion` warning = potensi silent-corrupt prediksi. (High, ML-integrity)

3. **`shap` broken di env FIREvCPU**: `import shap` → `TypeError: Converting np.inexact...` (shap×numpy 2.x). Bila ada codepath yang import shap non-lazy → crash. Workaround: `numpy<2` atau `shap>=0.45`. (High, Runtime)

4. **`requirements-dev.txt` tidak terpasang di env** (`ruff`, `black`, `httpx`, `yoyo-migrations` semua `ModuleNotFoundError`). Tidak ada `httpx` → `TestClient` FastAPI tidak bisa dipakai. **Zero coverage pada `/predict`, `/weather`, `/api/models/*`**. (High, Testing)

5. **`migrations/066_add_model_versioning.py` import `from yoyo import step`** — `yoyo` tidak ada di requirements mana pun → migrasi tak bisa jalan. (High, DB)

### 2.4 Keamanan tambahan

- `frontend/utils/gee_data.py:27-28` **hardcode service-account email** `popaye@firecast-001.iam.gserviceaccount.com` di file ter-track git. Key file aman (`.gitignore:154`), tapi identitas service-account ter-ekspos.
- `.kilo/agent-manager.json` **ter-track** padahal `.gitignore:77-78` menyatakan ignore. `git rm --cached -r .kilo/` perlu.
- `firecast-private/` & `tmp-space-deploy/` adalah **nested git repos** (duplikasi codebase + dependency outdated `python-jose`, `streamlit-aggrid`). Berisiko `git add -A` menarik ribuan file.

---

## 3. KEPUTUSAN STRATEGIS — Frontend Modernisasi

### 3.1 Status dua frontend
- **`frontend/` (Streamlit)**: aplikasi lengkap (4 tab), dipakai HF Spaces + dev, dark theme. UI fungsional tapi **1300+ baris `app.py`, 878 baris data lokasi hard-coded, inkonsistensi warna/threshold, A11y buruk di mobile, forecast 24 jam tidak tampil, i18n English penuh bug**.
- **`frontend_react/` (React)**: hanya komponen `InteractiveMap` yang di-embed ke Streamlit via `streamlit-component-lib`. **Bukan aplikasi React standalone**. App.tsx hanya mock. tsconfig error: `Cannot find global type Object/Boolean/CallableFunction` → `lib: ["DOM", "DOM.Iterable"]` hilang atau `skipLibCheck` off.

### 3.2 Rekomendasi pilihan

| Opsi | Usaha | Risiko | Hasil UI |
|------|------|--------|----------|
| **A. Polish Streamlit** (short-term) | Rendah | Rendah | Moderat, masih Streamlit-look |
| **B. Hybrid** (pertahankan Streamlit + perkuat React components) | Sedang | Sedang | Bagus, inkremental |
| **C. Migrasi penuh ke React** (Next/Vite + REST API) | Tinggi | Tinggi | Premium, kurangi ketergantungan Streamlit |

**Rekomendasi default: B (Hybrid)** — paling seimbang untuk repo existing, fokus pada:
- modernisasi component-kit React (`frontend_react/src/components/*`) agar menyerupai dashboard premium (Tailwind + headless UI),  
- Streamlit tetap jadi shell & form input (cepat dibangun),  
- REST API FastAPI (`src/geo_api`) sebagai sumber data tunggal,  
- token desain terpusat (design tokens JSON → dimakan React + CSS inject Streamlit).

Opsi C layak bila ada bandwidth 2–3 minggu: lebih bersih, mobile jauh lebih baik, dan A11y WCAG 2.1 AA lebih mudah dicapai React.

### 3.3 Sistem desain yang diusulkan
- **Palet**: slate-900 base (dark default) + light mode toggle, aksen `--risk-*` (rendah #22c55e, sedang #eab308, tinggi #ef4444, sangat_tinggi #7f1d1d) — ambang **0.3 / 0.5 / 0.7** disepakati tunggal.
- **Typography**: Inter (display) + JetBrains Mono (data); pakai CSS variables `--fs-xs…--fs-3xl`, `font-display: swap`.
- **Layout**: dashboard shell — header sticky + command palette, sidebar collapsible, main grid 12-col, map full-bleed.
- **Komponen**: card risiko dengan gauge radial, sparkline probabilitas 12-jam, batch heatmap legend, tabel AOI sortable, skeleton loader + toast error, dialog aksesibilitas (fokus-trap).
- **A11y**: kontras WCAG AA, label aria untuk tombol emoji, focus visible, dukungan keyboard untuk Leaflet draw.
- **i18n**: ekstrak semua string hardcoded ID → pakai `t()`; perbaiki `en.json` (banyak value masih Bahasa Indonesia, duplikasi 20+ key).

---

## 4. PLANNING (urutan eksekusi)

> Filosofi: "fix criticality → fungsional → modernisasi". Setiap fase commit terpisah & dapat di-rollback. Hindari request > 40 RPM (rate-limiter 30/min sudah ada di `/predict` & `/weather`).

### Fase 0 — Stabilkan & Hygiene (½ – 1 hari)
- [ ] `git rm --cached -r .kilo/` (leak `.kilo`).
- [ ] Hapus `bug_analysis_report.md` (placeholder tidak terproses), `requirements_1.txt` (orphan), `docker_stash/`.
- [ ] Tentukan nasib `firecast-private/` & `tmp-space-deploy/` (hapus atau jadikan submodule resmi `.gitmodules`).
- [ ] Konsolidasi `requirements`:
  - `requirements.txt`: pin `lightgbm==4.6.0`, `xgboost==3.3.0`, `scikit-learn==1.9.0`, `numpy<2` (workaround shap), `shap>=0.45`.
  - `requirements-dev.txt`: tambah `httpx`, `ruff`, `yoyo-migrations`, `pre-commit`; hapus `flake8`, `pylint`, `sphinx*`, `line-profiler`.
  - `pyproject.toml`: lengkapi `[project.dependencies]` (xgboost, shap, streamlit, fastapi, uvicorn, h3, slowapi, sqlmodel, geopandas, shapely), tambah `src.api` di `[tool.setuptools] packages`, tambah `[tool.ruff]`, update classifiers/urls.
- [ ] Sinkronisasi versi Python: `runtime.txt=python-3.12`, `Dockerfile FROM python:3.12-slim`, `README.md` → "Python 3.10+".
- [ ] `.env.example` & `auth.py`: tambah blacklist placeholder default; rotasi `API_SECRET_KEY` & `OPENWEATHER_API_KEY` (yang leak di `.env` working tree).

### Fase 1 — Bug Backend Kritis (1 – 2 hari)
- [ ] `causal_gru.py` & `bigru.py`: hapus `import torch`/`import torch.nn` top-level, pindah ke `_get_torch()` (merge versi `config.py` agar tidak triplicate).
- [ ] `bigru.predict_bigru`: hapus `np.random.randn` noise injection saat inference (non-deterministik) atau pasang `np.random.seed` tetap per-request.
- [ ] `cnn.py`: jadikan `TunedCNN1D(nn.Module)` (otomatis `.eval()` rekursif & `load_state_dict` native); hapus implementasi `_set_nested` custom.
- [ ] `feature_engineering.engineer_features:205`: `errors='ignore'` untuk `drop(['label'])`.
- [ ] `geo_api.py:96` `DATA_PATH` → gunakan `config.paths.data_path` (single source).
- [ ] `database.get_engine`: deteksi dialect sqlite → jangan kirim `pool_size/max_overflow`.
- [ ] `registry.get_model_path`: tambah `add_new_model/` ke whitelist (asimetri dengan `register_model_version`).
- [ ] `api/models.py`: refaktor `register_model` & `activate_version` ke body Pydantic, gunakan `HTTPException` (bukan `status:"error"` di HTTP 200).
- [ ] `predict.py`: hapus alias legacy `USE_BIGRU_AOI`; hapus env dead `INFERENCE_TEMPERATURE`; pastikan `_safe_lgbm_predict` dipakai di semua path (termasuk `predict_batch:621` & `predict_fire_risk` stacking fallback).
- [ ] Tambah `weights_only=True` eksplisit di `torch.load` (`causal_gru.py:157`).

### Fase 2 — Bug Frontend Kritis (1 – 2 hari)
- [ ] Definisikan `RISK_THRESHOLDS` & `RISK_COLORS` sebagai **satu-satunya** source, ekspos via template/dataset→JS; perbaiki `interactive_map_simple.py`, `results_display._get_temporal_action_recommendation`, `InteractiveMap.tsx getRiskLevel`.
- [ ] `weather_display.py:138` ganti `hourly_forecast` → `forecast` (sesuai `weather_api.py`).
- [ ] `results_display.py:874` `model_confidence` → `confidence` (key mismatch).
- [ ] `gee_data.py:209` balik `sort('CLOUDY_PIXEL_PERCENTAGE', True)` (ascending=True = paling sedikit berawan) & beri warning jujur saat GEE mati (bukan st.success).
- [ ] `handle_map_events`: guard `event_id is None`.
- [ ] `app.py:1090` `event.get("risk", 0)` → `event.get("risk") or 0`.
- [ ] `results_display.py:687,695` guard `None` sebelum format `:.0f`/`:.1f`.
- [ ] `aoi_analysis._generate_recommendations`: hapus prefix typo "Alert/Radio/Chart/Check/Search" pada teks rekomendasi.
- [ ] `i18n.en.json`: translate ulang rec_* ke English; dedup 20+ key.

### Fase 3 — CodeSmell & Refactor (2 – 3 hari)
- [ ] `predict.py` (1779 baris) split: `src/calibration.py`, `src/features/single_inference.py`, `src/features/shap_explain.py` (sesuai AGENTS §5C).
- [ ] `app.py` (1706 baris) ekstrak logika AOI-batch ke `frontend/utils/aoi_controller.py`.
- [ ] `sidebar.py`: keluarkan `INDONESIA_LOCATIONS` (450 baris) ke `data/locations.json` + dedup ("probolinggo", "nabire", dst).
- [ ] Hapus file mati/legacy: `interactive_map_simple.py`, `map_interface.py` (folium), `aoi_prediction.py`, `USE_BIGRU_AOI`, `_init_models`, scheduler mati di `geo_api.py`, `_load_precomputed_hex` dead code.
- [ ] Konsolidasi `_get_torch()` menjadi satu helper di `src/utils/lazy.py`.
- [ ] Hapus duplikasi `_get_api_key` antara `src/auth.py` & `src/geo_api.py`; `secrets.compare_digest`.
- [ ] `pyproject.toml`: tambah `[tool.ruff]` line-length 100, target py311.

### Fase 4 — Modernisasi UI/UX (3 – 5 hari, Fase utama tugas)
- [ ] **Design tokens** `frontend/themes/tokens.json` → generator CSS vars + TS typed export (`frontend_react/src/theme/tokens.ts`). Token: spacing, radius, shadow, color, risk-threshold, typography.
- [ ] **Streamlit shell**: refactor `app.py` agar `main()` hanya orkestrasi tab; pindahkan CSS ke `frontend/styles/*` terpisah, lazy-inject sekali per session (bukan per rerun).
- [ ] **React component-kit** baru di `frontend_react/src/components/`:
  - `RiskGauge.tsx` (radial SVG), `ProbabilitySparkline.tsx`, `BatchHeatmapLegend.tsx`, `AoiTable.tsx`, `Skeleton.tsx`, `Toast.tsx`, `CommandPalette.tsx`, `Header.tsx`, `SidebarNav.tsx`.
  - Tailwind config yang baca design tokens; setup `tsconfig` benar (`"lib": ["DOM","DOM.Iterable","ES2022"]`, `"skipLibCheck": true`) agar `tsc_errors.txt` hilang.
- [ ] **Dark/Light toggle**: `theme.py` ekspos `data-theme="light|dark"`, React baca `matchMedia` + `localStorage`.
- [ ] **Mobile**: meta viewport inject, sidebar collapsible, map touch-friendly, button 44×44 px.
- [ ] **A11y**: audit kontras (WCAG AA), `aria-label` untuk tombol emoji, `focus-visible`, keyboard navigation Leaflet draw.
- [ ] **Loading & error state**: skeleton + toast + banner (bukan `st.success("System Ready")` selalu) + diagram fallback saat data kosong.
- [ ] **i18n**: translate ulang `en.json`, hapus duplikasi key, tambah `t()` pada semua string hardcoded.

### Fase 5 — Quality Gate (1 – 2 hari)
- [ ] Tambah `tests/test_api_geo.py` (TestClient FastAPI) untuk `/predict`, `/weather`, `/api/models/*`, `/health`.
- [ ] Tambah unit test untuk `feature_engineering.compute_train_stats` & `_resolve_thresholds`, `predict_causal_gru` single-sample, `theme.get_risk_level` boundary 0.3/0.5/0.7.
- [ ] Tambah component test React (Vitest + Testing Library) untuk `RiskGauge`, `ProbabilitySparkline`.
- [ ] CI: `.github/workflows/ci.yml` matrix Python 3.11/3.12, install CPU torch, lint ruff, mypy, pytest + coverage, docker smoke build.
- [ ] Pre-commit ruff + black + nbstripout.

### Estimasi total: **8 – 13 hari kerja** (tunggal), dapat dipercepat dengan Agent Manager fan-out pada Fase 3 & 4 (modul independen).

---

## 5. CATATAN PENTING

- Tidak ada file kode diubah pada audit ini (read-only).
- AGENTS.md bug #1–7 terkonfirmasi FIXED; temuan ini semua **baru**.
- `.env` (working tree) berisi `OPENWEATHER_API_KEY` plaintext — rotate di OpenWeatherMap dashboard lalu set via Railway/Render secret manager (jangan commit).
- Rate limit 40 RPM ditaati: audit hanya baca file lokal, tidak mengenai API eksternal. Saat implementasi uji `/predict`/`/weather`, pakai 30 req/min lokal + backoff.
- Untuk eksekusi paralel aman, gunakan Agent Manager worktree per-fase (Fase 3 & 4 modulnya independen).
