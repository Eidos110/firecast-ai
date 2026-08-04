/**
 * RiskTrendChart — 7-day fire-risk trend sourced from `/analytics/trend`
 * via the `useTrend` react-query hook (PLAN §4 TAHAP D #6).
 *
 * V4 mockup pattern: a single median line (p50) drawn over a soft
 * p10 / p90 inter-quantile band (Recharts Area with `startOfYesterday/endOfToday`
 * style). The current cell's prediction risk_score is overlaid as a marker;
 * when the trend endpoint is unreachable we fall back to `mockTrend()` so
 * the panel never blanks under demo mode.
 *
 * Data shape contract: each row = `{day, fire_rate, p10, p50, p90, count}`.
 * `day` is a YYYY-MM-DD ISO string and renders as a short weekday label.
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Area,
  ComposedChart,
} from 'recharts';

import { useInferenceStore } from '../store/inferenceStore';
import { useTrend } from '../api/hooks';
import { mockTrend } from '../api/client';
import { RISK_THRESHOLDS, getRiskColor } from '../theme/tokens';

interface TrendPoint {
  day: string;
  weekday: string;
  fire_rate: number;
  p10: number;
  p50: number;
  p90: number;
  count: number;
}

function isoToWeekday(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' });
}

/**
 * Custom Recharts tooltip (ROADMAP §3-W2).
 *
 * Default Recharts formatter surfaces raw series names and a flat list of
 * numbers. For fire-triage users we surface the more actionable bundle:
 *   "P(fire)=0.72 (High), CI: 0.61–0.83"
 * so a single hover tells the analyst both the headline probability and the
 * 10th–90th quantile band (the same numbers RightDiagnostic shows, but
 * without quitting the chart). Falls through with ``null`` on non-payload
 * hovers so the tooltip hides instead of rendering an empty card.
 */
interface TrendTooltipPayload {
  payload?: TrendPoint;
}
interface TrendTooltipProps {
  /** i18next translator — pulled in via props so the component below stays
   *  a pure presentational function (no hooks inside a Recharts callback). */
  t: (k: string, o?: Record<string, unknown>) => string;
  active?: boolean;
  label?: string;
  /** Recharts supplies an array of cells; we read the first. */
  payload?: TrendTooltipPayload[];
}

function riskTierLabelFor(p50: number, t: TrendTooltipProps['t']): string {
  // Map probability → tier id used by the i18n keys `spa.legend.{rendah,sedang,tinggi,sangat_tinggi}`.
  if (p50 < RISK_THRESHOLDS.rendah) return t('spa.legend.rendah');
  if (p50 < RISK_THRESHOLDS.sedang) return t('spa.legend.sedang');
  if (p50 < RISK_THRESHOLDS.tinggi) return t('spa.legend.tinggi');
  return t('spa.legend.sangat_tinggi');
}

function TrendTooltip({ t, active, payload, label }: TrendTooltipProps): JSX.Element | null {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0]?.payload;
  if (!p) return null;
  const tier = riskTierLabelFor(p.p50, t);
  return (
    <div
      data-testid="trend-tooltip"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: 6,
        padding: '8px 10px',
        fontSize: 12,
        color: 'var(--color-text)',
        lineHeight: 1.5,
      }}
    >
      <div style={{ color: 'var(--color-text-muted)', marginBottom: 2 }}>
        {label ?? p.weekday} · {p.day} · n={p.count}
      </div>
      <div className="fc-mono" style={{ fontWeight: 600 }}>
        {t('spa.trend.tooltip_p_fire', {
          value: p.p50.toFixed(3),
          tier,
        })}
      </div>
      <div style={{ color: 'var(--color-text-muted)' }}>
        {t('spa.trend.tooltip_ci', {
          p10: p.p10.toFixed(3),
          p90: p.p90.toFixed(3),
        })}
      </div>
    </div>
  );
}

function convertTrend(
  series: { date: string; fire_rate: number; p10: number; p50: number; p90: number; count: number }[],
): TrendPoint[] {
  return series.map((p) => ({
    day: p.date,
    weekday: isoToWeekday(p.date),
    fire_rate: p.fire_rate,
    p10: p.p10,
    p50: p.p50,
    p90: p.p90,
    count: p.count,
  }));
}

export function RiskTrendChart(): JSX.Element {
  const { t } = useTranslation();
  const prediction = useInferenceStore((s) => s.prediction);
  const selectedCell = useInferenceStore((s) => s.selectedCell);

  const lat = selectedCell?.lat ?? null;
  const lon = selectedCell?.lon ?? null;
  const trend = useTrend(lat, lon, 7, 25, /* enabled= */ lat !== null && lon !== null);

  const data = useMemo<TrendPoint[]>(() => {
    // Live trend data takes precedence when available.
    if (trend.data?.series && trend.data.series.length > 0) {
      return convertTrend(trend.data.series);
    }
    // Demo fallback — synthesises a plausible series from the current risk
    // score so the chart is never empty during boot or when offline.
    const mock = mockTrend(lat ?? -1.8, lon ?? 113.5, prediction?.risk_score ?? null);
    return convertTrend(mock.series);
  }, [trend.data, lat, lon, prediction?.risk_score]);

  const lineColor = getRiskColor(prediction?.risk_score ?? 0.5);
  const isLoading = lat !== null && lon !== null && trend.isLoading && !trend.data;

  return (
    <div style={{ width: '100%', height: 130, position: 'relative' }}>
      {isLoading && (
        <div
          aria-live="polite"
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            fontSize: 10,
            color: 'var(--color-text-muted)',
          }}
        >
          {t('spa.trend.loading')}
        </div>
      )}
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 5, right: 8, bottom: 0, left: -22 }}>
          <XAxis dataKey="weekday" stroke="var(--color-text-muted)" fontSize={10} tickLine={false} />
          <YAxis domain={[0, 1]} stroke="var(--color-text-muted)" fontSize={10} tickLine={false} width={36} />
          <Tooltip
            contentStyle={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: 6,
              fontSize: 12,
              color: 'var(--color-text)',
            }}
            labelStyle={{ color: 'var(--color-text-muted)' }}
            content={<TrendTooltip t={t} />}
          />
          <ReferenceLine
            y={RISK_THRESHOLDS.tinggi}
            stroke="var(--color-text-muted)"
            strokeDasharray="4 4"
            label={{
              value: t('spa.trend.threshold_label'),
              fontSize: 9,
              fill: 'var(--color-text-muted)',
              position: 'insideTopRight',
            }}
          />
          {/* p10 .. p90 inter-quantile band. Rendered as a single Area over
              the p90 data with a faint fill; the p50 median line then draws
              on top, roughly centred inside the band. (Recharts doesn't
              support stacked range ribbons cleanly; this soft band is enough
              for the V4 engineer console's 130px-tall chart.) */}
          <Area
            type="monotone"
            dataKey="p90"
            stroke="none"
            fill={lineColor}
            fillOpacity={0.12}
            isAnimationActive={false}
            legendType="none"
          />
          <Area
            type="monotone"
            dataKey="p10"
            stroke="none"
            fill="var(--color-background)"
            fillOpacity={0.7}
            isAnimationActive={false}
            legendType="none"
          />
          {/* p50 median line — the headline series. */}
          <Line
            type="monotone"
            dataKey="p50"
            stroke={lineColor}
            strokeWidth={2}
            dot={{ r: 2, fill: lineColor }}
            activeDot={{ r: 4 }}
            name={t('spa.trend.axis_p50')}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export default RiskTrendChart;
