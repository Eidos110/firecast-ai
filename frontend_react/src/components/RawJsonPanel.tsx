/**
 * RawJsonPanel — collapsible <pre> block showing the raw /predict JSON
 * response (V3 mockup pattern). Useful for engineers debugging model output.
 */
import { useTranslation } from 'react-i18next';

import { useInferenceStore } from '../store/inferenceStore';

export function RawJsonPanel(): JSX.Element {
  const { t } = useTranslation();
  const prediction = useInferenceStore((s) => s.prediction);
  return (
    <details style={{ marginTop: 12 }}>
      <summary
        style={{
          fontSize: 11,
          textTransform: 'uppercase',
          letterSpacing: 1,
          color: 'var(--color-text-muted)',
          cursor: 'pointer',
        }}
      >
        {t('spa.metrics.raw_api_response')}
      </summary>
      <pre
        style={{
          background: '#0a0e13',
          border: '1px solid var(--color-border)',
          borderRadius: 6,
          padding: 8,
          marginTop: 8,
          fontFamily: 'var(--font-family-mono)',
          fontSize: 10,
          color: 'var(--color-success)',
          overflowX: 'auto',
          maxHeight: 240,
        }}
      >
        {prediction ? JSON.stringify(prediction, null, 2) : '{}'}
      </pre>
    </details>
  );
}

export default RawJsonPanel;
