import {
  RISK_THRESHOLDS,
  RISK_COLORS,
  RISK_TIER_LABELS,
  type RiskTierId,
} from '../theme/tokens';
import { cn } from '../utils/cn';

export interface BatchHeatmapLegendProps {
  /** Locale used for the tier captions ('id' or 'en'). */
  locale?: 'id' | 'en';
  /** Optional className. */
  className?: string;
}

const ID_LABELS: Record<RiskTierId, string> = {
  rendah: 'Rendah',
  sedang: 'Sedang',
  tinggi: 'Tinggi',
  sangat_tinggi: 'Sangat Tinggi',
};

const TIER_ORDER: RiskTierId[] = ['rendah', 'sedang', 'tinggi', 'sangat_tinggi'];

/**
 * BatchHeatmapLegend — single-source legend for the batch heatmap (Fase 4).
 * Reads thresholds + colors directly from `tokens.ts` so the map markers and
 * the legend cannot drift apart.
 */
export function BatchHeatmapLegend({
  locale = 'en',
  className,
}: BatchHeatmapLegendProps): JSX.Element {
  let prev = 0;
  return (
    <ul
      className={cn('batch-heatmap-legend', className)}
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '12px',
        listStyle: 'none',
        margin: 0,
        padding: 0,
      }}
      role="list"
      aria-label="Risk level legend"
    >
      {TIER_ORDER.map((tier) => {
        const upper = RISK_THRESHOLDS[tier];
        const label = locale === 'id' ? ID_LABELS[tier] : RISK_TIER_LABELS[tier];
        const range = `< ${prev.toFixed(2)} \u2013 ${upper.toFixed(2)}`;
        const swatch = RISK_COLORS[tier];
        prev = upper;
        return (
          <li
            key={tier}
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <span
              aria-hidden="true"
              style={{
                width: 12,
                height: 12,
                backgroundColor: swatch,
                borderRadius: 2,
                display: 'inline-block',
              }}
            />
            <span style={{ color: 'var(--color-text-secondary, #cbd5e1)' }}>
              <strong style={{ color: 'var(--color-text, #f1f5f9)' }}>{label}</strong>
              <span style={{ marginLeft: 6, fontVariantNumeric: 'tabular-nums' }}>
                {range}
              </span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export default BatchHeatmapLegend;
