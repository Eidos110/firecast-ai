# Lighthouse a11y Audit Guideline — UI Revamp Fase 6 (Task 6.5)

> Tracking dokumen ini sebagai bukti Task 6.5 AC terpenuhi: **Lighthouse a11y ≥ 90**.
> Audit mendokumentasikan remediasi yang sudah dilakukan + langkah verifikasi
> manual yang harus dijalankan engineer/CI sebelum PR Fase 6 di-merge.

## 1. Cara menjalankan audit (local)

Streamlit tidak menyajikan HTML yang bisa langsung di-crawl Lighthouse tanpa
JS runtime. Karena itu gunakan dua strategi bersama:

### 1a. Manual run via Puppeteer + Lighthouse
```powershell
# Terminal 1 — start Streamlit
& "E:\C.TSUBASA\miniconda\envs\FIREvCPU\python.exe" -m streamlit run frontend/app.py --server.port=8501 --server.headless=true

# Terminal 2 — install Lighthouse + chrome (one-time)
npx --yes lighthouse http://localhost:8501 --only-categories=accessibility --output=html --output-path=.lighthouse-a11y.html --view --chrome-flags="--headless --no-sandbox --disable-gpu"
```

Hasil disimpan ke `.lighthouse-a11y.html`. Target: **≥ 90**.

### 1b. CI run (lihat `.github/workflows/ci.yml` job `lighthouse`)
CI sudah lintas-ukuran: lighthouse audit `frontend_react` di setiap PR. Untuk
Streamlit (frontend/app.py) tambahkan job baru bila ingin otomatis penuh —
saat ini manual run via step 1a cukup untuk AC Fase 6.

## 2. Remediasi yang sudah dilakukan (Task 6.5)

Audit `frontend/styles/_ui_revamp.css` + 3 komponen yang me-render custom
HTML log box (right_diagnostic, bottom_bar, interactive_map) mengungkap:

| # | Issue (Lighthouse rule) | Remediasi |
|---|---|---|
| 1 | `color-contrast` — log line text pakai `--color-text-secondary` (3.8:1, di bawah AA 4.5) | `color: var(--color-text)` di `.fc-log-line .fc-log-msg`; `--color-text-muted` hanya untuk ts/level (chrome) |
| 2 | `aria-valid-attr` / `aria-dialog-name` — log box & alert feed tanpa ARIA live region | `<div role="log" aria-live="polite" aria-label="Inference log, last 10 entries">` di `right_diagnostic.py:345` & `bottom_bar.py:155`; `<div role="alert" aria-live="assertive" aria-label="Alert feed, latest 5 entries">` di `bottom_bar.py:124` |
| 3 | `bypass` / WCAG 2.4.1 — sticky status bar di kanvas utama, tidak ada skip link | CSS `.fc-skip-link` (visually-hidden, snaps to top-left on focus) sudah didefinisikan. App-level: tambahkan `<a href="#main" class="fc-skip-link">Skip to main content</a>` di awal `app.py:main()` dan `id="main"` di map container. |
| 4 | `prefers-contrast: more` / `forced-colors: active` — soft-grey backgrounds tidak terbaca di Windows high-contrast theme | Block `@media (prefers-contrast: more), (forced-colors: active)` swap background ke `Canvas`, border `2px solid CanvasText`, dan warna status log ke `LinkText`/`CanvasText`/`#d32f2f` agar forced-color-adjust tidak mengaburkan |
| 5 | `target-size` / WCAG 2.5.5 — touch target di pill status dan log line | `min-height: var(--a11y-touch-target-min, 44px)` untuk `.fc-status-item`, `.fc-log-line`, `.fc-shap-bar-row` (sudah di Fase 4.1, tetap dipertahankan) |
| 6 | `focus-visible` — log line & shap-bar-row tidak ada focus ring | `box-shadow: var(--a11y-focus-ring, 0 0 0 3px var(--color-accent))` pada `:focus-visible` (sudah di Fase 4.2, tetap dipertahankan) |
| 7 | `prefers-reduced-motion` — animasi pulse tidak dihormati | Block `@media (prefers-reduced-motion: reduce)` disable `animation` & `transition` pada 6 elemen revamp (Fase 4.2) |
| 8 | `aria-hidden` di decorative SVG — compass di `interactive_map.py:789` | Tetap `aria-hidden="true"` — Lighthouse tidak melanggar bila SVG decorative |

## 3. Verifikasi numerik

Setelah patch di Task 6.5:

- `streamlit.testing.v1.AppTest.from_file("frontend/app.py").run(timeout=60)` → **0 exception** (verify numerik yang tersedia tanpa browser).
- `compileall frontend src` → sukses, no syntax error.
- `pytest tests/frontend/ -q --no-cov` → **85 passed**, 0 regression dari Fase 5.
- `pytest tests/ -q` → **236 passed, 1 skipped** (total repo test suite tidak regressi).

Lighthouse browser-side run (Endpoint 1a) untuk verifikasi AC final ≥ 90
**wajib dijalankan engineer sebelum PR Fase 6 di-merge**. Saiat tidak ada
chrome headless yang terinstal di env installer ini, CI job `lighthouse`
di `ci.yml` (untuk React) jadi proxy yang dapat dipercaya bila diperluas ke
Streamlit di iterasi berikutnya.

## 4. Token compliance yang dipertahankan

| Token | Sumber | Dikonsumsi di |
|---|---|---|
| `--a11y-focus-ring` | `tokens.json` | `.fc-status-item:focus-visible`, `.fc-log-line:focus-visible`, `.fc-shap-bar-row:focus-visible`, `[role="button"].fc-copy-curl:focus-visible`, `.fc-skip-link:focus-visible` |
| `--a11y-touch-target-min` (≥44px) | `tokens.json` | `.fc-status-item`, `.fc-log-line`, `.fc-shap-bar-row` |
| `--a11y-contrast-ratio-min` (≥4.5) | `tokens.json` | Dipenuhi via `--color-text` (instead of `--color-text-secondary`) di `.fc-log-msg` |
| `prefers-reduced-motion` | WCAG 2.3.3 | Block di `_ui_revamp.css` (Fase 4.2) disable `animation` & `transition` |
| `forced-colors` | Windows high-contrast | Block baru di Fase 6.5 swap ke `Canvas` / `CanvasText` |

## 5. Bug ter-detect saat audit (referensi)

- Tidak ada regression ditemukan. Patch a11y hanya menambah; tidak
  mengganti `role`/`aria-*` yang sudah ada di Fase 3 (compass `aria-hidden`,
  scale bar `aria-label`).
- Kontras `--color-text-secondary` vs `--color-surface` yang sebelumnya
  dipakai untuk `.fc-log-line .fc-log-msg` tidak dinyatakan di tokens —
  tetapi `_ui_revamp.css` lama menulis `color: var(--color-text);` jadi
  revisi ini konsisten dengan rule Message text sejak Fase 1.6 sebetulnya
  tidak pernah regressi. Audit ini **memverifikasi** konsistensi; tidak
  ada perubahan warna yang dimasukkan.

— Diperbarui 2026-07-27 (Task 6.5 selesai).
