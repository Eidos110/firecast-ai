/**
 * ShapList — top-feature SHAP bars (V4 mockup pattern, ported to TS+React).
 *
 * Renders one row per top_feature from the latest prediction result. Each
 * row shows feature name, normalized bar width, signed contribution value.
 *
 * Fallback: when no prediction available, shows a faint placeholder list of
 * common FireCast feature names so the panel doesn't look empty during boot.
 */
import { useTranslation } from 'react-i18next';

import { useInferenceStore } from '../store/inferenceStore';
import { getRiskColor } from '../theme/risk';

const FALLBACK_FEATURES = [
  { name: 'temperature_2m', value: 0.31 },
  { name: 'humidity_rel', value: 0.22 },
  { name: 'wind_speed', value: 0.14 },
  { name: 'NDVI', value: 0.11 },
  { name: 'fuel_moisture', value: 0.09 },
];

export function ShapList(): JSX.Element {
  const { t } = useTranslation();
  const prediction = useInferenceStore((s) => s.prediction);
  const features = prediction?.shap_explanation?.top_features ?? FALLBACK_FEATURES;
  const maxAbs = Math.max(0.001, ...features.map((f) => Math.abs(f.value)));

  return (
    <div
      role="list"
      aria-label={t('spa.metrics.shap_top_features_label')}
      style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
    >
      {features.slice(0, 8).map((f) => {
        const positive = f.value >= 0;
        const width = Math.min(100, (Math.abs(f.value) / maxAbs) * 100);
        const color = positive
          ? getRiskColor(0.5) // amber-ish — fires correlate with these vars
          : 'var(--color-info)';
        return (
          <div key={f.name} role="listitem" style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
            <span style={{ width: 110, color: 'var(--color-text-muted)', fontFamily: 'var(--font-family-mono)' }}>
              {f.name}
            </span>
            <div className="fc-shap-bar">
              <div style={{ width: `${width}%`, background: color }} />
            </div>
            <span
              className="fc-mono"
              style={{ minWidth: 48, textAlign: 'right', color: positive ? 'var(--color-warning)' : 'var(--color-info)' }}
            >
              {positive ? '+' : ''}
              {f.value.toFixed(2)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default ShapList;
