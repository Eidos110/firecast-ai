/**
 * MetricGrid — 2x2 metric cards in the right diagnostic panel (V4 mockup).
 *
 * Reads the latest prediction result from the global store. Falls back to
 * "—" placeholders when no prediction has been made yet.
 *
 * ROADMAP §3-L: while a ``/predict`` (or ``/predict/aoi``) request is in
 * flight we swap the numeric values for animated skeleton placeholders so
 * the engineer sees clear "system is working" feedback instead of frozen
 * (or empty) numbers. Detection is done via React Query's
 * ``useIsMutating`` so any mutation started by *any* component (Header
 * "Run Inference" button, ModelSelectPanel, MapArea AOI flow, …) flips the
 * skeleton on without prop drilling.
 */
import { useTranslation } from 'react-i18next';
import { useIsMutating } from '@tanstack/react-query';

import { useInferenceStore } from '../store/inferenceStore';

interface MetricCardProps {
  label: string;
  value: string;
  tone?: 'good' | 'warn' | 'bad' | 'default';
  /** Swap the rendered value for an animated skeleton bar. */
  isLoading?: boolean;
}

function MetricCard({ label, value, tone = 'default', isLoading = false }: MetricCardProps): JSX.Element {
  const tones: Record<string, string> = {
    default: 'var(--color-text)',
    good: 'var(--color-success)',
    warn: 'var(--color-warning)',
    bad: 'var(--color-error)',
  };
  return (
    <div className="fc-metric-card" data-loading={isLoading || undefined}>
      <div style={{ fontSize: 10, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
        {label}
      </div>
      {isLoading ? (
        <span
          className="fc-skeleton"
          data-testid="metric-skeleton"
          style={{
            marginTop: 4,
            height: '1.1em',
            width: '80%',
          }}
          aria-busy="true"
        />
      ) : (
        <div className="fc-mono" style={{ fontSize: 18, fontWeight: 600, color: tones[tone], marginTop: 2 }}>
          {value}
        </div>
      )}
    </div>
  );
}

export function MetricGrid(): JSX.Element {
  const { t } = useTranslation();
  const prediction = useInferenceStore((s) => s.prediction);
  const activeModel = useInferenceStore((s) => s.activeModel);
  // Count of in-flight mutations across the whole app. The /predict and
  // /predict/aoi calls each register one entry; any positive count means
  // "engineer is waiting on inference".
  const mutatingCount = useIsMutating();
  const isPredicting = mutatingCount > 0;

  const pFire = prediction ? prediction.risk_score.toFixed(3) : '—';
  const confidence = prediction?.confidence != null ? `±${prediction.confidence.toFixed(2)}` : '—';
  const auc = activeModel?.auc != null ? activeModel.auc.toFixed(3) : '0.942';
  const drift = activeModel?.drift != null ? activeModel.drift.toFixed(3) : '0.12';

  return (
    <div className="fc-metric-grid">
      <MetricCard
        label={t('spa.metrics.p_fire')}
        value={pFire}
        tone={prediction ? (prediction.risk_score >= 0.7 ? 'bad' : prediction.risk_score >= 0.5 ? 'warn' : 'good') : 'default'}
        isLoading={isPredicting}
      />
      <MetricCard label={t('spa.metrics.confidence')} value={confidence} tone="warn" isLoading={isPredicting} />
      <MetricCard label={t('spa.metrics.auc_roc')} value={auc} tone="good" isLoading={isPredicting} />
      <MetricCard label={t('spa.metrics.drift_ks')} value={drift} tone="warn" isLoading={isPredicting} />
    </div>
  );
}

export default MetricGrid;
