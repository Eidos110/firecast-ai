# UI Revamp Reference Mockup

> Folder ini berisi mockup referensi (V1–V4) yang dipelajari saat menyusun PLAN.md.
> Sumber file asli: `E:\versi 1.txt` s.d. `E:\versi 4.txt`.

## Ringkasan Comparatif

| Versi | Sumber | Layout | Verdict |
|---|---|---|---|
| V1 | `E:\versi 1.txt` | 3-zone console (SVG map dummy) | Terlalu dense, map tidak real (SVG) |
| V2 | `E:\versi 2.txt` | Sidebar + 12-col grid + bottom chart | Responsif, tapi engineer-grade kurang |
| V3 | `E:\versi 3.txt` | 3-zone + bottom 3-col (ECharts) | Threshold konsisten (0.3/0.5/0.7), tapi terlalu ramping |
| **V4** | `E:\versi 4.txt` | 3-zone CSS grid + bottom timeline scrubber | **DIPILIH** — paling engineer-grade, hook `/predict` native |

## Pilihan: Versi 4

Lihat `PLAN.md` untuk breakdown task implementasi + adaptasi ke tokens FireCast.

## Keputusan Framework: Path A (Hybrid Streamlit)

Evaluasi 3 jalur:

| Path | Effort | Realtime | Status |
|---|---|---|---|
| A. Streamlit (count) | 26 jam | Polling | ✅ **DIPILIH** |
| B. + React tab Prediction | 65–75 jam | Possible | ❌ over-invest |
| C. Full React migrate | 80–100+ jam | Full | ❌ violates AGENTS.md |

Detail alasan + trade-off (apa yang tidak optimal di Path A) ada di `PLAN.md → section "Keputusan Framework"`.

**Sigms migrate ke B/C:** performance < Lighthouse 50, hotspot streaming < 1 menit latency, atau `st.session_state` race condition kambuh > 2 kali.

## Catatan Adaptasi

Hal-hal yang **tidak** diambil langsung dari V4 (perlu disesuaikan):

1. **Palet warna**: V4 pakai `--accent:#ff6b35`, `--danger:#dc3545`, `--ok:#28a745`.
   FireCast pakai `PALETTE["primary"]=#ef4444`, `RISK_COLORS['rendah']=#22c55e` (lihat `tokens.json`).
   → Saat implementasi, **wajib** pakai `frontend/utils/theme.py` jangan copy CSS V4.

2. **Threshold legend**: V4 legend `0.85/0.6/0.3`.
   FireCast `RISK_THRESHOLDS`: rendah=0.3, sedang=0.5, tinggi=0.7, sangat_tinggi=1.0.
   → Saat implementasi, **wajib** pakai `RISK_THRESHOLDS`.

3. **Endpoint hardcoded**: V4 `fetch('http://localhost:8000/predict')`.
   FireCast via `prediction_engine.run_prediction()`, bukan fetch langsung.
   → Tetap pakai `prediction_engine.py` existing.

## Yang Diambil dari V1/V2/V3 (perpaduan final)

- Dari **V1**: pertahankan **wind arrow overlay** dan **contour line** topografi DEM (untuk map statis)
- Dari **V2**: pertahankan **streaming hotspot table** kolom-kanan (sangat penting untuk ops live)
- Dari **V3**: pertahankan **raw API response JSON** dalam expander (debug engineer)

## Mockup Preview

> Catatan 2026-10-23: dokumen ini adalah rencana UI era Streamlit dan bersifat
> historis. Mockup PNG + generator matplotlib (`_preview_ui/`) sudah dihapus;
> UI aktif adalah React SPA di `frontend_react/`.
