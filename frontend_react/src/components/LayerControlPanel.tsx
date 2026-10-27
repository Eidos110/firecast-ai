/**
 * LayerControlPanel — left sidebar Layer section (V4 mockup).
 *
 * Maps 8 layers from the global inference store into toggleable rows with a
 * shared opacity slider. Renders the risk legend below the layers per tokens.
 */
import { useInferenceStore, type LayerId } from '../store/inferenceStore';
import { RISK_COLORS, RISK_THRESHOLDS } from '../theme/tokens';
import { cn } from '../utils/cn';
import { useTranslation } from 'react-i18next';

function layerSwatchColor(id: LayerId): string {
  const map: Record<LayerId, string> = {
    risk_heatmap: 'var(--color-primary)',
    active_fire: '#ef4444',
    predicted_spread: '#fb923c',
    wind_vectors: 'var(--color-info)',
    fuel_moisture: 'var(--color-success)',
    topography: 'var(--color-text-muted)',
    satellite_viirs: 'var(--color-warning)',
    roads: '#a78bfa',
  };
  return map[id] ?? 'var(--color-text-muted)';
}

export function LayerControlPanel(): JSX.Element {
  const { t } = useTranslation();
  const layers = useInferenceStore((s) => s.layers);
  const toggleLayer = useInferenceStore((s) => s.toggleLayer);
  const setLayerOpacity = useInferenceStore((s) => s.setLayerOpacity);
  const activeCount = layers.filter((l) => l.active).length;
  const firstActive = layers.find((l) => l.active);

  return (
    <section aria-labelledby="layers-heading" className="fc-section">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <h4 id="layers-heading" className="fc-section-title">
          {t('spa.layers.title')}
        </h4>
        <span style={{ fontSize: 10, color: 'var(--color-text-muted)', fontFamily: 'var(--font-family-mono)' }}>
          {t('spa.layers.active_count', { active: activeCount, total: layers.length })}
        </span>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 2,
        }}
      >
        {layers.map((l) => (
          <button
            key={l.id}
            type="button"
            data-compact="true"
            onClick={() => toggleLayer(l.id)}
            style={{
              all: 'unset',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '4px 6px',
              borderRadius: 4,
              fontSize: 11,
              borderLeft: l.active ? '2px solid var(--color-primary)' : '2px solid transparent',
              background: l.active ? 'rgba(239,68,68,0.08)' : 'transparent',
            }}
            aria-pressed={l.active}
            title={l.label}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, overflow: 'hidden' }}>
              <span
                aria-hidden
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: 3,
                  background: layerSwatchColor(l.id),
                  border: '1px solid rgba(255,255,255,0.15)',
                  display: 'inline-block',
                  flex: '0 0 auto',
                }}
              />
              <span
                style={{
                  color: l.active ? 'var(--color-text)' : 'var(--color-text-muted)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {l.label}
              </span>
            </span>
            <Toggle aria-label={t('spa.layers.toggle', { label: l.label })} on={l.active} />
          </button>
        ))}
      </div>

      <div style={{ marginTop: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>{t('spa.layers.opacity')}</span>
          <span
            style={{
              fontSize: 10,
              color: 'var(--color-text-muted)',
              fontFamily: 'var(--font-family-mono)',
            }}
          >
            {Math.round((firstActive?.opacity ?? 0.7) * 100)}%
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={100}
          value={Math.round((firstActive?.opacity ?? 0.7) * 100)}
          onChange={(e) => {
            const v = Number(e.target.value) / 100;
            if (firstActive) setLayerOpacity(firstActive.id, v);
          }}
          aria-label={t('spa.layers.layer_opacity')}
          style={{ '--accent-color': 'var(--color-primary)' } as React.CSSProperties}
          className="fc-range"
        />
      </div>
    </section>
  );
}

function Toggle({ on, ...a11y }: { on: boolean } & React.InputHTMLAttributes<HTMLInputElement>): JSX.Element {
  void a11y; // toggle is button-only; ARIA handled by the parent button
  return (
    <span
      aria-hidden
      className={cn('fc-toggle', on && 'on')}
      style={{
        background: on ? 'var(--color-primary)' : 'var(--color-border)',
        transition: 'background 0.2s ease',
      }}
    >
      <span
        style={{
          position: 'absolute',
          top: 1,
          left: on ? 14 : 1,
          width: 12,
          height: 12,
          borderRadius: '50%',
          background: '#fff',
          transition: 'left 0.2s ease',
          display: 'inline-block',
        }}
      />
    </span>
  );
}

export function RiskLegend(): JSX.Element {
  const { t } = useTranslation();
  const tiers: Array<[keyof typeof legendTiers, string]> = [
    ['rendah', `${RISK_THRESHOLDS.rendah.toFixed(2)} – 1.0`],
    ['sedang', `${RISK_THRESHOLDS.rendah.toFixed(2)} – ${RISK_THRESHOLDS.sedang.toFixed(2)}`],
    ['tinggi', `${RISK_THRESHOLDS.sedang.toFixed(2)} – ${RISK_THRESHOLDS.tinggi.toFixed(2)}`],
    ['sangat_tinggi', `${RISK_THRESHOLDS.tinggi.toFixed(2)} – 1.0`],
  ];
  return (
    <section aria-labelledby="legend-heading" className="fc-section">
      <h4 id="legend-heading" className="fc-section-title">
        {t('spa.legend.title')}
      </h4>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11 }}>
        {tiers.map(([id, range]) => (
          <div key={id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span
              aria-hidden
              style={{ width: 12, height: 12, borderRadius: 3, background: RISK_COLORS[id] }}
            />
            <span style={{ color: 'var(--color-text)' }}>{t(`spa.legend.${id}`)}</span>
            <span
              style={{
                marginLeft: 'auto',
                color: 'var(--color-text-muted)',
                fontFamily: 'var(--font-family-mono)',
                fontSize: 10,
              }}
            >
              {range}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

const legendTiers = {
  rendah: 1,
  sedang: 1,
  tinggi: 1,
  sangat_tinggi: 1,
};

export default LayerControlPanel;
