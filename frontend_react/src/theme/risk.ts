/**
 * FireCast risk-tier helpers (Fase 4).
 *
 * This module is now a thin compatibility shim over `./tokens`, which is the
 * single source of truth for the React component-kit (mirrors
 * `frontend/themes/tokens.json` and `frontend/utils/theme.py`).
 *
 * Previously this file hand-copied values and they drifted (e.g. `Medium` was
 * `#f59e0b` here while the Python theme used `#fb923c`). The drift caused the
 * map markers and the Streamlit sidebar to render different colours for the
 * same tier. Re-exporting from `tokens` keeps the two frontends aligned.
 *
 * Use `tokens.ts` directly for typed constants; this file is kept for
 * backward-compatible imports (`import { getRiskLevel } from '../theme/risk'`).
 */
import {
  RISK_THRESHOLDS as RISK_THRESHOLDS_TOKENS,
  RISK_COLORS as RISK_COLORS_TOKENS,
  RISK_BG_COLORS as RISK_BG_COLORS_TOKENS,
  RISK_TIER_LABELS,
  RISK_LABEL_TO_TIER,
  getRiskLevel as getRiskLevelToken,
  getRiskTier,
  type RiskTierLabel,
} from './tokens';

// Re-export the tier label type so consumers can import it from either
// `../theme/risk` or `../theme/tokens` (back-compat with the legacy
// Streamlit component bridge).
export type { RiskTierLabel };

export type RiskLevel = RiskTierLabel;

// Re-export the canonical thresholds typed as a plain object (still `as const`).
export const RISK_THRESHOLDS = RISK_THRESHOLDS_TOKENS;

// Map English label -> hex (uses canonical Indonesian-tier colour values).
export const RISK_COLORS: Record<RiskLevel, string> = {
  Low: RISK_COLORS_TOKENS[RISK_LABEL_TO_TIER.Low],
  Medium: RISK_COLORS_TOKENS[RISK_LABEL_TO_TIER.Medium],
  High: RISK_COLORS_TOKENS[RISK_LABEL_TO_TIER.High],
  Extreme: RISK_COLORS_TOKENS[RISK_LABEL_TO_TIER.Extreme],
};

export const RISK_BG_COLORS: Record<RiskLevel, string> = {
  Low: RISK_BG_COLORS_TOKENS[RISK_LABEL_TO_TIER.Low],
  Medium: RISK_BG_COLORS_TOKENS[RISK_LABEL_TO_TIER.Medium],
  High: RISK_BG_COLORS_TOKENS[RISK_LABEL_TO_TIER.High],
  Extreme: RISK_BG_COLORS_TOKENS[RISK_LABEL_TO_TIER.Extreme],
};

export const RISK_TIERS = RISK_TIER_LABELS;

/** Resolve a 0..1 score to the English risk-tier label. */
export function getRiskLevel(score: number): RiskLevel {
  return getRiskLevelToken(score);
}

/** Resolve a 0..1 score to the Indonesian risk-tier id (handy for server parity). */
export function getRiskTierId(score: number): (typeof RISK_LABEL_TO_TIER)[RiskLevel] {
  return getRiskTier(score);
}

/**
 * Map a risk-tier label (or a raw 0..1 score) to its hex color.
 * Accepts a label ("Low".."Extreme") or a numeric score (in which case
 * it first resolves the label via {@link getRiskLevel}).
 */
export function getRiskColor(levelOrScore: RiskLevel | number): string {
  if (typeof levelOrScore === 'number') {
    return RISK_COLORS[getRiskLevel(levelOrScore)];
  }
  return RISK_COLORS[levelOrScore];
}
