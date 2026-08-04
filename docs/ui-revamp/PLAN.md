# UI Revamp Plan — FireCast v3.0 (Engineer Console)

> **Status**: DRAFT — untuk approval sebelum implementasi
> **Dibuat**: 2026-07-26
> **Berdasarkan**: audit 4 mockup (V1–V4) + hasil iterasi preview PNG (SHAP waterfall, temporal band, risk gauge)
> **Layout acuan**: Versi 4 (Fire Risk Forecasting System) — disesuaikan dengan tokens.json + palette FireCast

---

## 1. Tujuan & Non-Tujuan

### Tujuan
1. Konsolidasi UI FireCast ke layout **3-zona engineer-grade** (sidebar config | map center | right diagnostic)
2. Fix inkonsistensi threshold (0.3/0.6/0.8 vs 0.3/0.5/0.7) yang masih ada di `results_display.py:1216-1223` dan `results_display.py:208-214`
3. Tampilkan **provenance ML** (model card, AUC, drift, latency) secara inline, bukan tersembunyi
4. Tambah **probabilistic band p10-p90** pada temporal forecast (standar ML forecasting)
5. Ganti list-text SHAP menjadi **SHAP waterfall plot**
6. Tambah **status bar permanen** + **API log warna-coded** + **timeline scrubber H-24→H+72**

### Keputusan Framework: Hybrid Streamlit (Path A)

Dipilih setelah evaluasi Streamlit vs React vs Hybrid:

| Path | Effort | Real-time | Custom Layout | Pilihan |
|---|---|---|---|---|
| A. Streamlit (PILIH) | 26 jam | Polling only (cukup) | Limited tapi acceptable | ✅ |
| B. Streamlit + React Tab Prediction | 65–75 jam | Possible via WS di React tab | Full V4 layout | ❌ (over-invest) |
| C. Full React migrate | 80–100+ jam | Full real-time | Bebas total | ❌ (rewrite besar-besaran, melanggar primer AGENTS.md) |

**Alasan pilih A:**
1. Pondasi Streamlit sudah 4 tab (`Prediction/Analysis/Batch/Settings`) dengan i18n, analytics, batch — rewrite ke React = 2x codebase yang harus maintain
2. Sebagian besar layout V4 (3-zona, gradient card, metric grid, expander model card, SHAP waterfall, temporal band) **achievable dengan** `st.columns` + `st.container` + `unsafe_allow_html` CSS injection
3. Real-time hotspot streaming (VIIRS push) saat ini belum menjadi kebutuhan FireCast — polling 5 menit sudah cukup. Bila nanti muncul, opsi B/C masih bisa diadopsi bertahap tanpa rewrite data layer
4. Sesuai primer AGENTS.md: "JANGAN rubah behavior graceful fallback" & "banyak fallback ada karena Railway/HF Spaces punya sandbox" — mempertahankan Streamlit menjaga garansi deployment yang sudah ada

**Yang TIDAK akan optimal di Path A (diterima sebagai trade-off):**
- Sticky status bar 100% se-true V4 tidak mungkin (Streamlit header tidak fixable native). Workaround: `position:sticky` dalam custom container HTML dengan keterbatasan z-index Streamlit navbar
- Timeline scrubber H-24→H+72 yang real-time update chart tanpa rerun: tidak bisa. Pakai `st.slider` yang trigger rerun (latensi ~1 detik)
- Live WebSocket log streaming: tidak mungkin tanpa hack. Pakai buffer polling + `st.rerun()` tiap 5 detik saat tab aktif (ATAU `st_autorefresh` bila dipasang)

**Sinyal kalau perlu migrate ke React (Path B/C):**
- Lighthouse performance score < 50 setelah revamp → pertimbangkan Path B untuk tab Prediction
- Hotspot streaming VIIRS jadi kebutuhan (< 1 menit latency) → wajib Path C
- Stuck `st.session_state` race condition muncul lagi > 2 kali → Path B

### Non-Tujuan (out-of-scope)
- **Tidak mengganti framework Streamlit → React** (Path A dipilih; Path B/C ditunda ke fase strategis)
- Tidak mengubah backend API contract (`/predict`, `/weather` response shape tetap)
- Tidak menambah model baru; pakai model yang sudah ada (stacking + legacy)
- Tidak mengubah `tokens.json` (single source of truth tetap)
- Tidak menambah dependency berat baru (React/Vite/WS/etc.) yang melanggar graceful-fallback primer

---

## 2. Layout Final (3-Zona + Bottom Timeline)

```
┌───────────────────────────────────────────────────────────────┐
│  STATUS BAR (h=48px)  : 🔥FireCast | model | run_id | status  │  ← baru
├──────────┬───────────────────────────────────┬────────────────┤
│ SIDEBAR  │            MAP CENTER              │ RIGHT DIAGNOSTIC│
│ (280px)  │           (flex-1)                │   (320px)      │
│          │                                    │                │
│ • Layers │  • Leaflet map (existing)          │ • Risk hero    │
│ • Model  │  • AOI polygon overlay             │   + CI90       │
│   config │  • Risk heatmap (grid points)     │ • Metric grid  │
│ • Filters│  • Wind vectors (optional)        │   4 cards      │
│          │                                    │ • SHAP waterfall│
│          │                                    │ • Model card   │
│          │                                    │   (expander)   │
│          │                                    │ • Raw JSON     │
│          │                                    │   (expander)   │
│          │                                    │ • API log      │
│          │                                    │   (8-10 line)  │
├──────────┴───────────────────────────────────┴────────────────┤
│ BOTTOM BAR (h=160px)                                          │
│ ┌─────────────────┬─────────────────┬────────────────────┐    │
│ │ Temporal Band   │ Alert Feed      │ Inference Log      │    │
│ │ (p10-p90 chart) │ (5 latest row)  │ (POST /predict...)│    │
│ └─────────────────┴─────────────────┴────────────────────┘    │
│ Timeline scrubber: H-24 ←────────●─────────→ H+72            │
└───────────────────────────────────────────────────────────────┘
```

### Pemetaan ke Streamlit
| Zona | Implementasi | File baru |
|---|---|---|
| Status bar | `st.markdown(unsafe_allow_html)` sticky header + CSS injection | `frontend/components/status_bar.py` |
| Sidebar config | `st.sidebar` OR `st.columns([1,2.5,1.2])[0]` | refactor dari `frontend/components/sidebar.py` |
| Map center |Existing `render_interactive_map` dari `interactive_map.py` | tidak ada |
| Right diagnostic | `st.columns[2]` vertical stack | `frontend/components/right_diagnostic.py` (baru) |
| Bottom timeline | `st.container` below main row | `frontend/components/bottom_bar.py` (baru) |
| SHAP waterfall | helper baru | `frontend/components/shap_waterfall.py` (baru) |
| Temporal band | helper baru | `frontend/components/temporal_band.py` (baru) |
| API log | ring buffer di `st.session_state["log_buffer"]` + handler | `frontend/utils/log_handler.py` (baru) |

---

## 3. Token & Styling Compliance

### Wajib pakai source of truth
- **Warna**: `frontend/utils/theme.py:PALETTE` & `RISK_COLORS` → JANGAN copy CSS dari V4 (`--accent:#ff6b35` dst.)
- **Threshold**: `frontend/utils/theme.py:RISK_THRESHOLDS` (rendah=0.3, sedang=0.5, tinggi=0.7, sangat_tinggi=1.0) → JANGAN hardcode `0.6/0.85` seperti V4
- **Typography**: `TYPOGRAPHY` dict (`Inter` + `JetBrains Mono`)
- **Spacing/Radius/Shadow**: dari `SPACING`, `RADIUS`, `SHADOW` dict
- **A11y**: `A11Y["focus_ring"]`, `A11Y["touch_target_min"]`, `prefers-reduced-motion`

### Custom CSS tambahan (di `frontend/styles/app.css`)
- `.status-bar` (sticky top)
- `.metric-grid` (2x2 layout right panel)
- `.shap-bar` (per-bar SHAP styling)
- `.log-line.ok/.warn/.err` (warna-coded log)
- `.timeline-scrubber` (custom st.slider styling)

---

## 4. Breakdown Task (16 task, 5 fase)

> Setiap task punya acceptance criteria (AC) yang siap diverifikasi via pytest/manual.

### FASE 0 — Bug Fix Prasyarat (P0, sebelum revamp)

#### Task 0.1 — Fix threshold legend di batch results
**File**: `frontend/components/results_display.py:208-214`
**Masalah**: legend masih pakai rentang `0-30/30-60/60-80/>80` (kambuh bug AGENTS.md #7)
**Perubahan**:
```python
# BEFORE
st.markdown(f"<span style='color:{RISK_COLORS['rendah']};font-weight:bold;'>● Rendah (0–30%)</span>")
# AFTER (pakai token)
from frontend.utils.theme import RISK_THRESHOLDS
st.markdown(f"<span style='color:{RISK_COLORS['rendah']}'>● Rendah (0—{RISK_THRESHOLDS['rendah']*100:.0f}%)</span>")
```
**AC**: 4 legend konsisten dengan `RISK_THRESHOLDS` (`0-30/30-50/50-70/70-100`)

#### Task 0.2 — Fix `_get_temporal_action_recommendation` threshold
**File**: `frontend/components/results_display.py:1216-1223`
**Masalah**: pakai `0.3/0.6/0.8` bukan `RISK_THRESHOLDS`
**Perubahan**:
```python
def _get_temporal_action_recommendation(risk_score: float) -> str:
    if risk_score < RISK_THRESHOLDS["rendah"]:
        return "Monitoring rutin"
    elif risk_score < RISK_THRESHOLDS["sedang"]:
        return "Waspada, siap tim"
    elif risk_score < RISK_THRESHOLDS["tinggi"]:
        return "Siaga, evakuasi preventif"
    return "DARURAT! Evakuasi segera"
```
**AC**: skor 0.55 → "Siaga" (bukan "Waspada" lagi); konsisten dengan `get_risk_level`

---

### FASE 1 — Komponen Baru (Foundation)

#### Task 1.1 — `frontend/utils/log_handler.py`
Buat handler Streamlit-compatible untuk log buffer sirkular (max 50 entry).
```python
class StreamlitLogHandler(logging.Handler):
    def emit(self, record):
        entry = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "msg": record.getMessage(),
            "color": "ok" if record.levelno < 30 else "warn" if record.levelno < 40 else "err",
        }
        st.session_state.setdefault("log_buffer", []).append(entry)
        if len(st.session_state["log_buffer"]) > 50:
            st.session_state["log_buffer"] = st.session_state["log_buffer"][-50:]
```
**AC**: `import StreamlitLogHandler; handler.emit(...)` → `st.session_state["log_buffer"]` bertambah 1 entry.

#### Task 1.2 — `frontend/components/status_bar.py`
Komponen bar sticky 48px. Baca data:
- `st.session_state["active_model_type"]` → "stacking v1.2"
- `st.session_state["api_status"]` → "API OK" / "API DOWN"
- `st.session_state["latency_ms"]` → dari `prediction_result`
- `st.session_state["model_auc"]` → dari `registry.ModelVersion` (lazy lookup)
- `st.session_state["rpm"]` → counter global
- UTC + WIB clock (JS auto-update via `streamlit.components.v1.html`)

**AC**: Status bar muncul sticky di top, update tiap rerun. 7 item: logo, status, model, AUC, latency, RPM, waktu.

#### Task 1.3 — `frontend/components/shap_waterfall.py`
Helper baru. Signature:
```python
def render_shap_waterfall(shap_explanation: dict, base_value: float = 0.5) -> None
```
Pakai Plotly `go.Waterfall` (orientation h), batasi 10 top features, warna `RISK_COLORS["tinggi"]` (menaik) / `RISK_COLORS["rendah"]` (menurunkan). Konsisten dengan preview PNG di `_preview_ui/preview_shap_waterfall.png`.

**AC**: input `{"top_features":[{"feature":"temp","shap_value":0.1},...]}` → render bar waterfall cumulatif dengan label `f(x) = X.XXX`.

#### Task 1.4 — `frontend/components/temporal_band.py`
Helper baru. Signature:
```python
def render_temporal_band(temporal_forecast: dict, current_risk: float) -> None
```
- Plotly chart dengan `mean` line, `p10-p90` fill (`fill="tonexty"`)
- Treshold horizontal pakai `RISK_THRESHOLDS` (BUKAN hardcoded 30/50/70)
- Marker puncak + annotation `Puncak: X% @ HH:00 WIB`
- Vertical line "SEKARANG" di `time_steps[0]`
- Fallback: kalau `p10`/`p90` tidak ada di dict, hitung default `mean ± 8%` (placeholder, bukan silent 0.5)

**AC**: input `{"time_steps":[...],"risk_scores":[...]}` → render chart dengan area band + 3 hline threshold dari token.

#### Task 1.5 — `frontend/components/right_diagnostic.py`
Container vertikal untuk panel kanan. Sub-komponen:
- `render_risk_hero(prob, secondary_prob, ci)` — gradient card dengan label + score + CI90
- `render_metric_grid_4()` — grid 2x2 (P(fire)/Confidence/AUC/Drift)
- `render_shap_waterfall()` — panggil Task 1.3
- `render_model_card_expander()` — expander dengan `st.json` provenance
- `render_raw_api_expander()` — expander dengan `st.json(prediction_result)`
- `render_api_log_box()` — render 10 entry terakhir dari `st.session_state["log_buffer"]`

**AC**: panggil `render_right_diagnostic(prediction_result)` → semua sub-komponen tampil terurut vertikal.

#### Task 1.6 — `frontend/components/bottom_bar.py`
Bottom bar 160px. Layout 3 kolom `[2, 1, 1.5]`:
- Kol 1: temporal band (kompak, height ~120px) — panggil Task 1.4
- Kol 2: alert feed (5 baris terakhir dari `prediction_result["alerts"]` atau log warning)
- Kol 3: inference log (10 entry terakhir dari `log_buffer` dengan styling `ok/warn/err`)

Di bawahnya: timeline scrubber `st.slider("Horizon", -24, 72, 0, step=1)` → update `st.session_state["temporal_offset_h"]` yang dipakai temporal band untuk highlight step yang di-hover.

**AC**: bottom bar muncul 3 kolom + slider di bawah. Slider menggerakkan highlight chart (via `st.session_state["temporal_offset_h"]`).

---

### FASE 2 — Integrasi & Refactor

#### Task 2.1 — Refactor `frontend/app.py:main()`
Pisahkan main() jadi 3 zona + bottom bar:
```python
def main():
    initialize_session_state()
    attach_log_handler()
    render_status_bar()       # Task 1.2
    st.markdown("---")
    
    col_left, col_center, col_right = st.columns([1, 2.6, 1.2], gap="small")
    with col_left:
        render_sidebar_config()      # refactor dari sidebar.py
    with col_center:
        render_map_center()
    with col_right:
        render_right_diagnostic(st.session_state.prediction_result)  # Task 1.5
    
    st.markdown("---")
    render_bottom_bar(st.session_state.prediction_result)  # Task 1.6
```

Existing 4 tab (Prediction/Analysis/Batch/Settings) tetap, tapi tab Prediction pakai layout baru. Tab lain biarkan dulu (revamp nanti).

**AC**: `streamlit run app.py` → 3-column layout + status bar + bottom bar muncul tanpa error.

#### Task 2.2 — Hook `prediction_engine.run_prediction` ke log_handler
Di `run_prediction` (atau wrapper), tambahkan emit log:
- `INFO` "POST /predict start, lat=X lon=Y"
- `INFO` "feature fetch complete" (weather+shap)
- `INFO` "model inference complete, p=X.XX, latency=Yms"
- `ERROR` "prediction failed: <msg>" jika raise

**AC**: jalankan predict → 3-4 entry muncul di bottom-bar inference log kolom 3.

#### Task 2.3 — Tambah `secondary_prob` & `ci` ke response
File: `src/predict.py:predict_fire_risk` (atau wrapper di `prediction_engine.py`)
- Tambah `secondary_prob` = probabilitas base learner (kalau stacking) atau model cadangan
- Tambah `ci` = `(mean - sigma, mean + sigma)` dari temperature-scaled probs
- Tambah `p10`/`p90` di `temporal_forecast` dict (kalau ada model MC-dropout, kalau tidak ada fallback `mean ± 8%`)

**AC**: `prediction_result["secondary_prob"]` dan `prediction_result["ci"]` ada (kalau tidak, diisi `None` dan `right_diagnostic` skip tampilan).

---

### FASE 3 — Map Enhancements (P2)

#### Task 3.1 — Wind vector overlay optional
Di `interactive_map.py`, kalau `st.session_state["layer_wind_vectors"]` True, kirim `windArrow` GeoJSON ke React map. Data dari `weather_data["wind_speed"]` & `wind_direction` di grid AOI.

**AC**: toggle wind vectors ON → panah biru muncul di map (1 per grid point, length ∝ wind_speed).

#### Task 3.2 — Risk heatmap IDW interpolation
Di `interactive_map.py`, kalau `risk_heatmap_mode="idw"`, hitung IDW weights dari grid points → kirim `heatmapRaster` GeoJSON ke React. Pakai `scipy.interpolate.griddata` lazy import (graceful fallback).

**AC**: select mode "IDW" → area kontinu warna, bukan titik diskret.

#### Task 3.3 — Compass + scale bar statis
Di overlay map (bisa via `streamlit.components.v1.html`), render compass rose kanan-atas + scale bar kiri-bawah. Pakal SVG inline.

**AC**: compass 64px & scale bar "10 km" muncul di 2 sudut map.

---

### FASE 4 — Polish & A11y

#### Task 4.1 — Status bar responsive (mobile/tablet)
Tambah `@media (max-width: 768px)` → status bar jadi 2 baris (logo+model atas, status+latency bawah). Sidebar collapse jadi `st.expander`.

**AC**: resize browser <768px → layout tetap西山 usable (no horizontal scroll).

#### Task 4.2 — Focus-visible & reduced-motion
Audit semua komponen pakai `:focus-visible` outline `A11Y["focus_ring"]`. Animasi `pulse` direspect `prefers-reduced-motion`.

**AC**: Lighthouse a11y score ≥ 90 pada komponen utama.

#### Task 4.3 — Engineer "copy as cURL" button
Di right diagnostic expander "Raw API Response", tambah button:
```
st.button("Copy as cURL", key="btn_copy_curl")
```
Yang meng-generate command cURL dengan endpoint `/predict`, payload terkini, dan `X-API-Key` placeholder. Output ke clipboard via `st.toast` + `st.session_state["curl_clipboard"]`.

**AC**: klik → clipboard berisi `curl -X POST http://localhost:8000/predict -H "X-API-Key: ..." -d '{"lat":...}'`.

---

### FASE 5 — Tests

#### Task 5.1 — Unit test komponen baru
```
tests/frontend/
  test_status_bar.py
  test_shap_waterfall.py
  test_temporal_band.py
  test_log_handler.py
```
Pakai `streamlit.testing` (v1.30+) atau mock `st.session_state`.

**AC**: `pytest tests/frontend/ -v` lulus dengan coverage ≥ 60% komponen baru.

#### Task 5.2 — Integration test smoke
File: `tests/test_ui_revamp_integration.py`
```python
def test_full_tab1_flow():
    client = TestClient(app)  # FastAPI
    # mock /predict response
    # verify status_bar renders, right_diagnostic renders, bottom_bar renders
```

**AC**: smoke test jalan tanpa error di CI lokal.

---

## 5. Order Implementasi & Dependencies

```
FASE 0 (bug fix) ───► FASE 1 (foundation) ───► FASE 2 (integrate) ──┬─► FASE 3 (map)
                                                                     └─► FASE 4 (polish)
                                                                                  │
                                                                                  ▼
                                                                          FASE 5 (tests)
```

### Urutan task (dependency graph)
```
0.1 ┐
0.2 ┘─┐
     ├──► 1.1 (log_handler) ──┐
     ├──► 1.2 (status_bar)    │
     ├──► 1.3 (shap_waterfall) │
     ├──► 1.4 (temporal_band)  │
     ├──► 1.5 (right_diagnostic) ──┐ (butuh 1.3, 1.4)
     └──► 1.6 (bottom_bar)         │ (butuh 1.4)
                                     ▼
                                     2.1 (refactor main)
                                     2.2 (hook log) ──► 2.3 (response shape)
                                                         │
                                                         ▼
                                              3.1, 3.2, 3.3 (map) — parallel
                                              4.1, 4.2, 4.3 (polish) — parallel
                                                         │
                                                         ▼
                                                     5.1, 5.2
```

---

## 6. Estimasi Effort

| Fase | Task | Effort (jam) | Σ Fase |
|---|---|---|---|
| 0 | 0.1, 0.2 | 0.5 | 0.5 |
| 1 | 1.1, 1.2, 1.3, 1.4, 1.5, 1.6 | 7.5 | 7.5 |
| 2 | 2.1, 2.2, 2.3 | 5 | 5 |
| 3 | 3.1, 3.2, 3.3 | 6 | 6 |
| 4 | 4.1, 4.2, 4.3 | 3 | 3 |
| 5 | 5.1, 5.2 | 4 | 4 |
| **Total** | 16 task | **26 jam** | 26 |

Assumsi: 1 engineer penuh-waktu, dependencies sequential. Bisa paralel antara FASE 3 dan FASE 4 (hemat ~3 jam).

---

## 7. Risiko & Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Plotly Waterfall chart tidak didukung versi lama | SHAP waterfall blank | Fallback ke `px.bar` orientation h dengan custom sum (acak yang sudah dipakai di preview PNG) |
| `streamlit.testing` tidak stabil | Test flaky | Pakai direct `pytest` + mock `st.session_state` dict manual |
| React map component tidak ter-build di HF Spaces | Wind vector & heatmap tidak muncul | Tetap pakai `render_interactive_map` existing; enhancement IDW/wind hanya jika build ada, otherwise `st.info` fallback |
| `predictions_result` belum punya `secondary_prob`/`ci`/`p10`/`p90` | UI blank card | `render_right_diagnostic` & `render_temporal_band` cek `None` → skip tampilan, tidak raise |
| `tokens.json` di-load lazy, race condition | Threshold `None` | `RISK_THRESHOLDS` sudah punya default di `theme.py:90-94`; tidak akan `None` |
| Status bar sticky konflik dengan Streamlit default header | Layout overlap | Gunakan `st.set_page_config(layout="wide")` + `position:relative` wrapper, jangan `position:fixed` |

---

## 8. Verifikasi Final (Definition of Done)

Setelah semua task selesai, verifikasi:

1. **Functional**
   - Run `streamlit run frontend/app.py --server.port=8501`
   - Klik map → predict → 3-zone layout terisi (sidebar config / map / right diagnostic)
   - Bottom bar tampil: temporal chart + alert feed + inference log
   - Timeline scrubber H-24→H+72 bisa digeser → highlight chart update

2. **Compliance**
   - Lihat legend: rentang pakai `RISK_THRESHOLDS` (0-30/30-50/50-70/70-100), BUKAN 0-30/30-60/60-80
   - Lihat temporal action: skor 0.55 → "Siaga" (bukan "Waspada")
   - Inspect CSS: tidak ada `--accent:#ff6b35` (V4 palette) — harusnya `--color-primary:#ef4444`

3. **Engineer UX**
   - "Copy as cURL" button menghasilkan command yang bisa di-paste ke terminal & jalan
   - "Raw API Response" expander menampilkan JSON lengkap (`p_fire`, `run_id`, `latency_ms`)
   - Model card expander menampilkan: model name, version, training date, AUC, F1, features, scaler

4. **A11y**
   - Lighthouse a11y ≥ 90
   - `prefers-reduced-motion: reduce` → animasi `pulse` berhenti
   - All button ≥ 44x44px touch target

5. **Test**
   - `pytest tests/frontend/ -v` lulus
   - `pytest tests/test_ui_revamp_integration.py -v` lulus

---

## 9. File yang Akan Berubah / Dibuat

### Dibuat (12 file baru)
```
frontend/components/
  status_bar.py             # Task 1.2
  right_diagnostic.py       # Task 1.5
  bottom_bar.py             # Task 1.6
  shap_waterfall.py         # Task 1.3
  temporal_band.py          # Task 1.4
frontend/utils/
  log_handler.py            # Task 1.1
frontend/styles/
  _ui_revamp.css            # CSS tambahan (status-bar, metric-grid, log-line)
tests/frontend/
  test_status_bar.py        # Task 5.1
  test_shap_waterfall.py    # Task 5.1
  test_temporal_band.py     # Task 5.1
  test_log_handler.py       # Task 5.1
tests/
  test_ui_revamp_integration.py  # Task 5.2
```

### Berubah (6 file existing)
```
frontend/components/results_display.py
  ├─ line 208-214  (Task 0.1: fix legend threshold)
  ├─ line 1216-1223 (Task 0.2: fix action recommendation threshold)
  └─ line 696-703  (Task 1.5: ganti list-text SHAP → panggil render_shap_waterfall)

frontend/app.py
  ├─ main() (Task 2.1: refactor 3-zone + bottom bar)
  └─ render_header() (Task 2.1: hapus local header, pakai status_bar baru)

frontend/utils/prediction_engine.py
  ├─ run_prediction() (Task 2.2: emit log via StreamlitLogHandler)
  └─ line ~480-500 (Task 2.3: tambah secondary_prob & ci di result)

frontend/components/sidebar.py
  └─ (Task 2.1: rename → render_sidebar_config(), tambah model config + filter risiko)

src/predict.py
  └─ predict_fire_risk() (Task 2.3: tambah secondary_prob & ci di response)

frontend/styles/app.css
  └─ (append _ui_revamp.css via @import atau merge langsung)
```

---

## 10. Glossary

- **p10/p90**: quantile bawah & atas dari distribusi probabilistik (untuk 90% confidence interval)
- **secondary_prob**: probabilitas dari base learner selain model utama (untuk indikator agreement)
- **MC-dropout**: teknik estimate uncertainty dengan menjalankan model N kali dengan dropout aktif
- **IDW**: Inverse Distance Weighting — interpolasi spasial untuk heatmap kontinu
- **Drift KS**: Kolmogorov-Smirnov statistic, mengukur pergeseran distribusi fitur dari baseline training
- **CI90**: 90% Confidence Interval (mean ± 1.645σ untuk distribusi normal)

---

## 11. Cara Memulai Implementasi

Setelah dokumen ini di-approve, langkah pertama:

```powershell
# Buat branch baru
cd "E:\Code\FireCast_Experimental\firecast_FINAL_version_C_Deepseek _version2_1-geminiPR_HFcpu-V1.1"
git checkout -b feat/ui-revamp-v3

# Mulai dari FASE 0 (bug fix, ~30 menit)
# Edit results_display.py baris 208-214 & 1216-1223

# Verifikasi cepat
& "E:\C.TSUBASA\miniconda\envs\FIREvCPU\python.exe" -m streamlit run frontend/app.py --server.port=8501
```

Progress tracking via `PROGRESS.md` (dibuat saat mulai implementasi).

---

**_Dokumen ini sebagai single source of truth untuk fase UI revamp. Setiap penyimpangan wajib update dokumen & commit dengan prefix `plan:`._**

---

# FASE 6 — Post-Revamp Hardening (Tambahan 2026-07-27)

> **Konteks**: FASE 0–5 selesai dengan **236 passed / 1 skipped** dan 0 exception di AppTest. Section ini men-dokumentasikan langkah-langkah lanjutan yang muncul selama audit `§5 Rekomendasi Berikutnya` (AGENTS.md) + `§7 Risiko & Mitigasi` (PLAN.md) + bug yang terungkap saat Fase 5 testing. Tujuan: meng-amankan apa yang sudah dibangun dan membuka jalan untuk iterasi ML/UI selanjutnya tanpa regression.

## 6.1 Tujuan Fase 6

1. **Amankan artefak** — version-control semua file baru lewat commit + PR ke `main` agar ada history reviewable.
2. **CI pipeline** — otomatisasi `pytest + ruff + compileall` di setiap PR sehingga regression tertangkap sebelum merge.
3. **Coverage gating** — pakai `pytest-cov` dengan threshold ≥ 60% untuk `frontend/components/` (memenuhi AC Task 5.1 secara numerik).
4. **Tutup gap backend** — endpoint `/predict` yang dirujuk oleh copy-as-cURL (Task 4.3) belum ada di `src/geo_api.py`. Either realize endpoint atau update cURL generator.
5. **A11y verifiable** — Lighthouse a11y score ≥ 90 (AC Task 4.2 masih self-asserted; perlu di-verify numerically).
6. **Refactor readability** — `src/predict.py` 1779 baris dan `frontend/app.py` 1300+ baris susah dibaca. Pisahkan modul-modul konsisten dengan AGENTS.md §5.C.

## 6.2 Non-Tujuan

- Tidak migrate Streamlit → React (keputusan `Path A` di §1 tetap;dibahas ulang hanya bila ada sinyal `Lighthouse < 50`).
- Tidak menambah model baru — pakai model existing.
- Tidak mengganti token system (`tokens.json` & `theme.py` tetap source of truth).
- Tidak menambah dependency berat yang melanggar graceful-fallback primer (AGENTS.md §6).

## 6.3 Breakdown Task (8 task, 3 prioritas)

| # | Task | Prioritas | Effort | File | Dependency |
|---|---|---|---|---|---|
| 6.1 | Commit + PR ke `main` | P0 | 0.5 jam | (git ops) | — |
| 6.2 | `requirements-dev.txt` final | P0 | 0.5 jam | `requirements-dev.txt` | — |
| 6.3 | GitHub Actions CI workflow | P0 | 2 jam | `.github/workflows/ci.yml` | 6.2 |
| 6.4 | `pytest-cov` + threshold gate | P1 | 1.5 jam | `pyproject.toml`, CI yaml | 6.3 |
| 6.5 | Lighthouse a11y audit + fix iteratif | P1 | 2 jam | `_ui_revamp.css`, `app.css` | 6.1 |
| 6.6 | Realize endpoint `/predict` atau redirect cURL | P1 | 3 jam | `src/geo_api.py`, `right_diagnostic.py` | — |
| 6.7 | Refactor `src/predict.py` → 3 modul | P2 | 4 jam | `src/calibration.py` (existing), `src/features/single_inference.py`, `src/features/shap_explain.py` | — |
| 6.8 | Refactor `frontend/app.py:main()` | P2 | 3 jam | `frontend/utils/aoi_controller.py` (existing), `frontend/app.py` | 6.7 |
| **Total** | 8 task | | **16.5 jam** | | |

### Detail Task

#### Task 6.1 — Commit + PR ke `main`
Stage 12 file baru + 6 file berubah:
```
frontend/utils/log_handler.py         frontend/components/status_bar.py
frontend/components/shap_waterfall.py frontend/components/temporal_band.py
frontend/components/right_diagnostic.py frontend/components/bottom_bar.py
frontend/styles/_ui_revamp.css        tests/test_ui_revamp.py
tests/frontend/__init__.py            tests/frontend/test_log_handler.py
tests/frontend/test_status_bar.py     tests/frontend/test_shap_waterfall.py
tests/frontend/test_temporal_band.py  tests/test_ui_revamp_integration.py
[b baru di Fase 3] frontend/components/interactive_map.py (helper tambahan)
[b baru di Fase 5 fix] frontend/components/temporal_band.py (bug fix)
```
File berubah:
```
frontend/styles/inject.py             frontend/app.py
frontend/utils/prediction_engine.py   frontend/components/results_display.py
frontend/components/sidebar.py        frontend/components/right_diagnostic.py
frontend/styles/_ui_revamp.css
```
Commit structure (3 logis commits):
- `feat(ui-revamp): Fase 1+2 — 3-zone engineer layout, log handler, status bar, shap/time/bottom panel`
- `feat(ui-revamp): Fase 3+4 — wind vector, IDW heatmap, compass, copy-as-cURL, a11y audit`
- `test(ui-revamp): Fase 5 — 93 unit + integration tests, fix temporal_band add_vline TypeError`

**AC**: diff reviewable di PR; PROGRESS & PLAN terlihat di PR description.

---

#### Task 6.2 — `requirements-dev.txt` final
Per AGENTS.md §5.A, dev dependencies yang saat ini TIDAK ada di env default: `pytest`, `pytest-cov`, `sqlmodel`, `slowapi`, `shap`, `h3`, `geopandas`, `shapely`, `ruff`, `black`, `httpx`, `plotly`, `scipy`, `orjson`.

**Perubahan**:
```diff
# requirements-dev.txt
+-r requirements.txt
+pytest>=7.4
+pytest-cov>=4.1
+httpx>=0.24
+plotly>=5.18
+scipy>=1.11
+h3>=4.0
+geopandas>=0.14
+shapely>=2.0
+ruff>=0.1
+black>=23.0
+slowapi>=0.1.9
+sqlmodel>=0.0.16
+shap>=0.44
+orjson>=3.9
```
**AC**: `pip install -r requirements-dev.txt` di env kosong → `pytest tests/ -q` lulus.

---

#### Task 6.3 — GitHub Actions CI workflow
```yaml
# .github/workflows/ci.yml
name: CI
on: [pull_request, push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements-dev.txt
      - run: python -m compileall -q frontend src tests
      - run: python -m ruff check .
      - run: python -m pytest tests/ -q --cov=frontend/components --cov-fail-under=60
```
**AC**: PR terbuka men-trigger CI; red build mem-block merge.

---

#### Task 6.4 — `pytest-cov` + threshold
Tambah konfigurasi di `pyproject.toml`:
```toml
[tool.pytest.ini_options]
addopts = "--cov=frontend/components --cov=tests/frontend --cov-report=term-missing"
```
Threshold 60% untuk `frontend/components/` (sesuai AC Task 5.1). Set bila coverage drop di bawah ambang, CI merah.

**AC**: `pytest --cov=frontend/components --cov-fail-under=60` exit 0 bila coverage ≥ 60%, nonzero sebaliknya.

---

#### Task 6.5 — Lighthouse a11y audit
Jalankan lokal:
```powershell
npx lighthouse http://localhost:8501 --only-categories=accessibility --output=html --output-path=lighthouse-report.html
```
Target: a11y ≥ 90. Iterasi fix di `_ui_revamp.css` & `app.css`:
- Validasi semua A11y tokens (`focus_ring`, `touch_target_min`) konsisten digunakan.
- Pastikan `aria-label` di komponen HTML custom (status_bar, log_box, shap-bar).
- Verifikasi `prefers-reduced-motion` benar-benar menonaktifkan animation pulse.
- Verifikasi kontras teks (≥ 4.5:1 per `A11Y["contrast_ratio_min"]`).

**AC**: Lighthouse a11y ≥ 90; screenshot attach ke PR.

---

#### Task 6.6 — Endpoint `/predict` atau update cURL generator
PLAN.md Task 4.3 meng-generate `curl -X POST http://localhost:8000/predict` tetapi endpoint belum ada (`src/geo_api.py` hanya punya `/health`, `/api/models/*`, `/admin/*`). Pilih satu:

**Opsi A (Realize endpoint)** — tambah:
```python
@app.post("/predict")
@limiter.limit("30/minute")
async def predict_endpoint(payload: PredictRequest, _: str = Depends(get_api_key)):
    result = predict_fire_risk(payload.dict())
    return result
```
Plus `PredictRequest` Pydantic model di `src/geo_api.py` atau `src/schemas.py`.

**Opsi B (Update cURL generator)** — di `right_diagnostic.py:render_raw_api_expander`, ganti URL ke endpoint existing atau dokumentasikan "internal-only".

Saran: **Opsi A** karena itu yang dirujuk PLAN §2 right_diagnostic "Raw API Response expander" — engineer UX mengharapkan cURL command yang benar-benar berjalan.

**AC**: klik "Copy as cURL" → paste ke terminal → 200 OK dengan body JSON prediksi.

---

#### Task 6.7 — Refactor `src/predict.py` (1779 baris)
Per AGENTS.md §5.C, pisahkan:
```
src/calibration.py            → sudah ada; lengkapi _calibrate_cnn_probs, _calibrate_lgbm_probs, temperature scaling
src/features/single_inference.py → _create_feature_vector, _estimate_temporal_feature
src/features/shap_explain.py   → _compute_shap_explanation
```
`src/predict.py` tetap public API (`predict_fire_risk`, `predict_batch`, `predict_stacking`) tapi import dari sub-modul — body function turun ke < 200 baris.

**AC**: `pytest tests/test_prediction.py -q` tetap lulus pasca-refactor; file baru lulus compileall; tidak ada import cyclic.

---

#### Task 6.8 — Refactor `frontend/app.py:main()`
Per AGENTS.md §5.C, ekstrak sisa AOI batch logic yang inline di `main()` ke `frontend/utils/aoi_controller.py`. Setelah refactor, `main()` hanya:
```python
def main():
    initialize_session_state()
    attach_log_handler()
    render_status_bar()
    render_tabs()
```
File `frontend/app.py` target turun dari 1147 baris ke < 400.

**AC**: `AppTest.from_file("frontend/app.py").run(timeout=60)` tetap 0 exception; 3-zone layout & tabs intact.

---

## 6.4 Order Implementasi

```
6.1 (commit+PR) ──► 6.2 (deps) ──► 6.3 (CI) ──► 6.4 (coverage)
                                       │
                                       └─► 6.5 (lighthouse) — paralel
                                       └─► 6.6 (predict endpoint) — paralel
                                           6.7 (predict.py refactor) — paralel dgn 6.5/6.6
                                           6.8 (app.py refactor) — butuh 6.7
```

## 6.5 Risiko & Mitigasi Fase 6

| Risiko | Mitigasi |
|---|---|
| Refactor `predict.py` ber破坏 pickle | Smoking test `test_full_prediction_workflow` di gate sebelum/sesudah |
| Lighthouse a11y < 90 di run pertama | Iteratif fix di CSS tokens; jangan `!important` kecuali last resort |
| Implementasi `/predict` membuka auth hole | Pakai `Depends(get_api_key)` seperti endpoint lain; rate-limit 30/min |
| Refactor `app.py` ada regression | `AppTest` di CI jadi safety net; refactor inkremental per bagian |
| CI di Ubuntu gagal karena Windows-specific path | Gunakan `pathlib.Path` (sudah); hindari hardcoded `\` separator |

## 6.6 Catatan Tambahan

- Implementasi 8 task boleh dikerjakan dalam sprint terpisah; tracking tetap via PROGRESS.md section "FASE 6".
- Bila ada task yang berkembang scope lebih besar dari estimasi, update PLAN.md dengan suffix `plan:` per primer dokumen ini.
- Bug yang ditemukan saat Fase 5 (temporal_band `add_vline`, config singleton pollution) menjadi pattern test reusable: setiap komponen yang punya module-level mutable state harus di-test dengan isolasi + reset di setUp/tearDown.
