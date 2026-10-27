# Audit Archive

Historical audit / bug-fix reports from the Streamlit era and earlier phases.
**These documents describe states of the codebase that no longer exists** —
kept for provenance only, do not use them as a source of current behavior.

For the live bug ledger, see the table in the repo-root `AGENTS.md` §4.
Latest comprehensive review: 2026-08-23 (bugs #14–#17 and follow-ups).

| File | Era |
|---|---|
| `AUDIT_REPORT.md` | Pre-Agent-Manager baseline (2026-07) |
| `BUG_REPORT.md`, `BUG_FIX_REPORT.md`, `COMPLETE_BUGFIX_SUMMARY.md` | Fase 1–5 backend/frontend bug sweeps |
| `RISK_FACTORS_BUGFIX_SUMMARY.md` | Risk-factor calculation fixes |
| `DEBUG_SUMMARY.md` | Ad-hoc debugging session notes |

### `ui-revamp-streamlit-era/`

Planning and progress logs for the **Streamlit engineer-console UI revamp**
(2026-07-26 → 2026-07-28, "Path A — Hybrid Streamlit"). Superseded in full by
**TAHAP E (2026-07-30)**: the React SPA in `frontend_react/` is the one and only
UI; all Streamlit code (`frontend/app.py`, `frontend/utils/*`, `frontend/components/*`)
was deleted. Kept for provenance of layout decisions (3-zone grid, tokens, i18n)
that the React SPA carried over.
