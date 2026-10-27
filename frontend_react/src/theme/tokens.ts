/**
 * FireCast Design Tokens — typed TypeScript mirror of `frontend/themes/tokens.json`.
 *
 * This file is the single source of truth for the React component kit (Fase 4).
 * It is intentionally hand-aligned with tokens.json (no build step required) so
 * that the SPA stays importable without a codegen pipeline.
 *
 * When you edit `frontend/themes/tokens.json`, update the matching values here
 * and run `npm run typecheck` to keep the two in sync.
 *
 * Risk thresholds mirror `frontend/utils/theme.py:RISK_THRESHOLDS`.
 * Risk colors mirror `frontend/utils/theme.py:RISK_COLORS`.
 *
 * Boundary semantics (mirrors Python `get_risk_level`):
 *   score < 0.3  -> rendah (Low)
 *   score < 0.5  -> sedang (Medium)
 *   score < 0.7  -> tinggi (High)
 *   score >= 0.7 -> sangat_tinggi (Extreme)
 */
export type DataTheme = 'dark' | 'light';

export type RiskTierId = 'rendah' | 'sedang' | 'tinggi' | 'sangat_tinggi';

/** English label used by the React component kit (mirrors `frontend_react/src/theme/risk.ts`). */
export type RiskTierLabel = 'Low' | 'Medium' | 'High' | 'Extreme';

export interface RiskThresholds {
  readonly rendah: 0.3;
  readonly sedang: 0.5;
  readonly tinggi: 0.7;
  readonly sangat_tinggi: 1.0;
}

export interface RiskColors {
  readonly rendah: '#22c55e';
  readonly sedang: '#fb923c';
  readonly tinggi: '#ef4444';
  readonly sangat_tinggi: '#7f1d1d';
}

export interface RiskBgColors {
  readonly rendah: 'rgba(34, 197, 94, 0.1)';
  readonly sedang: 'rgba(251, 146, 60, 0.1)';
  readonly tinggi: 'rgba(239, 68, 68, 0.1)';
  readonly sangat_tinggi: 'rgba(127, 29, 29, 0.15)';
}

export const RISK_THRESHOLDS: RiskThresholds = {
  rendah: 0.3,
  sedang: 0.5,
  tinggi: 0.7,
  sangat_tinggi: 1.0,
} as const;

export const RISK_TIER_LABELS: Record<RiskTierId, RiskTierLabel> = {
  rendah: 'Low',
  sedang: 'Medium',
  tinggi: 'High',
  sangat_tinggi: 'Extreme',
} as const;

export const RISK_LABEL_TO_TIER: Record<RiskTierLabel, RiskTierId> = {
  Low: 'rendah',
  Medium: 'sedang',
  High: 'tinggi',
  Extreme: 'sangat_tinggi',
} as const;

export const RISK_COLORS: RiskColors = {
  rendah: '#22c55e',
  sedang: '#fb923c',
  tinggi: '#ef4444',
  sangat_tinggi: '#7f1d1d',
} as const;

export const RISK_BG_COLORS: RiskBgColors = {
  rendah: 'rgba(34, 197, 94, 0.1)',
  sedang: 'rgba(251, 146, 60, 0.1)',
  tinggi: 'rgba(239, 68, 68, 0.1)',
  sangat_tinggi: 'rgba(127, 29, 29, 0.15)',
} as const;

/** Resolve a 0..1 score to the Indonesian-tier id (mirrors `theme.py:get_risk_level`). */
export function getRiskTier(score: number): RiskTierId {
  const s = typeof score === 'number' && Number.isFinite(score) ? score : 0;
  if (s < RISK_THRESHOLDS.rendah) return 'rendah';
  if (s < RISK_THRESHOLDS.sedang) return 'sedang';
  if (s < RISK_THRESHOLDS.tinggi) return 'tinggi';
  return 'sangat_tinggi';
}

/** Resolve a 0..1 score to the English label used by the React component kit. */
export function getRiskLevel(score: number): RiskTierLabel {
  return RISK_TIER_LABELS[getRiskTier(score)];
}

/** Returns the hex risk color for either a numeric score or a tier label. */
export function getRiskColor(scoreOrLevel: number | RiskTierLabel): string {
  if (typeof scoreOrLevel === 'number') {
    return RISK_COLORS[getRiskTier(scoreOrLevel)];
  }
  const tier = RISK_LABEL_TO_TIER[scoreOrLevel];
  return RISK_COLORS[tier] ?? '#fb923c';
}

// ── Heavy theme palettes / motion tokens intentionally omitted. ─────────────
// The React component-kit reads CSS custom properties (--color-* from
// tokens.json inside index.css) for theming; the dark/light palettes and
// motion/a11y constants below were never imported by any component. They
// are kept out of the bundle to avoid drift with the CSS source of truth.
// If you re-introduce a consumer, restore the block from git history and
// re-check the `frontend/themes/tokens.json` contract.
