/**
 * RightDiagnostic — right column orchestrator (320px).
 *
 * Composes: P(fire) hero badge → MetricGrid → SHAP section → RiskTrendChart →
 * RawJsonPanel → ApiLogBox. Reads all data from the inference store.
 */
import { useInferenceStore } from '../store/inferenceStore';
import { getRiskColor, getRiskLevel, getRiskTierId } from '../theme/risk';
import { useTranslation } from 'react-i18next';

import { MetricGrid } from './MetricGrid';
import { ShapList } from './ShapList';
import { RiskTrendChart } from './RiskTrendChart';
import { RawJsonPanel } from './RawJsonPanel';
import { ApiLogBox } from './ApiLogBox';

export function RightDiagnostic(): JSX.Element {
  const { t } = useTranslation();
  const prediction = useInferenceStore((s) => s.prediction);
  const runId = useInferenceStore((s) => s.runId);
  const score = prediction?.risk_score ?? 0;
  const level = prediction ? getRiskLevel(prediction.risk_score) : 'Low';
  const tierId = prediction ? getRiskTierId(prediction.risk_score) : 'rendah';
  const color = getRiskColor(level);

  return (
    <aside
      aria-label={t('spa.metrics.diagnostic_panel_label')}
      style={{
        width: 320,
        background: 'var(--color-surface)',
        borderLeft: '1px solid var(--color-border)',
        overflowY: 'auto',
        padding: 12,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span className="fc-section-title" style={{ margin: 0 }}>
          {t('spa.metrics.p_fire')}
        </span>
        <span className="fc-mono" style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
          run: {runId}
        </span>
      </div>

      <div
        style={{
          background: `linear-gradient(to bottom right, ${color}1a, ${color}26)`,
          border: `1px solid ${color}66`,
          borderRadius: 8,
          padding: 12,
          marginBottom: 12,
        }}
      >
        <div style={{ fontSize: 10, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>
          {t('spa.metrics.p_fire_window')}
        </div>
        <div className="fc-mono" style={{ fontSize: 28, fontWeight: 700, color }}>
          {prediction ? score.toFixed(3) : '—'}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
          <span
            style={{
              background: `rgba(${hexToRgb(color)},0.18)`,
              color,
              border: `1px solid ${color}`,
              padding: '2px 8px',
              borderRadius: 10,
              fontSize: 10,
              fontWeight: 600,
              fontFamily: 'var(--font-family-mono)',
            }}
          >
            {t(`spa.legend.${tierId}`)}
          </span>
          {prediction?.confidence != null && (
            <span className="fc-mono" style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
              {t('spa.metrics.confidence')}: ±{prediction.confidence.toFixed(2)}
            </span>
          )}
        </div>
      </div>

      <SectionTitle>{t('spa.metrics.live_metrics')}</SectionTitle>
      <MetricGrid />

      <div style={{ marginTop: 12 }} aria-hidden />

      <SectionTitle>{t('spa.metrics.shap_explanation')}</SectionTitle>
      <ShapList />

      <SectionTitle>{t('spa.trend.chart_label')}</SectionTitle>
      <RiskTrendChart />

      <RawJsonPanel />

      <SectionTitle>{t('spa.metrics.api_log')}</SectionTitle>
      <ApiLogBox />
    </aside>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <h4
      className="fc-section-title"
      style={{ marginTop: 14, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}
    >
      {children}
    </h4>
  );
}

function hexToRgb(hex: string): string {
  const m = /^#?([a-f0-9]{2})([a-f0-9]{2})([a-f0-9]{2})$/i.exec(hex);
  if (!m) return '239,68,68';
  return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)].join(',');
}

export default RightDiagnostic;
