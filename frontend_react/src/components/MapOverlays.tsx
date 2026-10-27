/**
 * MapOverlays — floating HTML overlay widgets on top of the InteractiveMap
 * (V1/V4 mockup pattern). Pure presentation; receives the same coord + zoom
 * state MapArea tracks.
 *
 * PLAN §4 TAHAP D #7 calls out: "compass + coord readout + layer legend".
 * The layer legend lives in the left sidebar (see `RiskLegend` in
 * `LayerControlPanel.tsx`) so this file owns just the on-map pieces:
 *   - bottom-left: EPSG + lat / lon readout
 *   - top-right : a circular compass widget
 *   - top-left  : zoom + active-region pill
 *
 * Receives state via props so it can be unit-tested in isolation without a
 * store wrapper.
 *
 * ROADMAP §3-W2 adds a sticky indeterminate progress bar pinned to the top
 * of the map while a `/predict/aoi` batch is in flight. The bar is part of
 * the overlay layer (so it doesn't have to fight Leaflet's z-index) and is
 * driven by `useIsMutating` (any in-flight mutation across the SPA shows it;
 * matches the MetricGrid skeleton pattern in §3-L).
 */
import type { CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import { useIsMutating } from '@tanstack/react-query';

export interface MapOverlaysProps {
  /** Latest hovered/clicked coordinate or null until first interaction. */
  coordReadout: { lat: number; lon: number; zoom: number } | null;
  /** Human-readable region label (top-left pill). */
  regionLabel?: string;
  /** EPSG code for the bottom-left readout. Default 4326. */
  epsg?: number;
}

const pillStyle: CSSProperties = {
  background: 'rgba(15,20,25,0.7)',
  border: '1px solid var(--color-border)',
  borderRadius: 6,
  padding: '4px 8px',
  fontSize: 11,
  color: 'var(--color-text-muted)',
  fontFamily: 'var(--font-family-mono)',
  backdropFilter: 'blur(6px)',
};

export function MapOverlays({
  coordReadout,
  regionLabel = 'Kalimantan Tengah',
  epsg = 4326,
}: MapOverlaysProps): JSX.Element {
  const { t } = useTranslation();
  const lat = coordReadout?.lat ?? -1.8;
  const lon = coordReadout?.lon ?? 113.5;
  const zoom = coordReadout?.zoom ?? 7;

  // Indeterminate progress: any in-flight mutation flips the bar on. The
  // /predict/aoi flow can take >3 s on large polygons, so a non-toast
  // affordance is required (ROADMAP §3-W2). Toasts themselves are kept for
  // *finished* actions only.
  const mutatingCount = useIsMutating();
  const isBusy = mutatingCount > 0;

  return (
    <>
      {/* bottom-left: EPSG + lat / lon readout */}
      <div className="fc-map-overlay" style={{ position: 'absolute', bottom: 12, left: 12, ...pillStyle }}>
        {t('spa.map.coord_readout.epsg', { code: epsg })} &middot; LAT{' '}
        <span className="fc-mono" style={{ color: 'var(--color-text)' }}>
          {lat.toFixed(4)}
        </span>{' '}
        &middot; LON{' '}
        <span className="fc-mono" style={{ color: 'var(--color-text)' }}>
          {lon.toFixed(4)}
        </span>
      </div>

      {/* top-left: zoom pill + region */}
      <div className="fc-map-overlay" style={{ position: 'absolute', top: 12, left: 12, ...pillStyle }}>
        {t('spa.map.zoom.label')}: {zoom} &middot; {regionLabel}
      </div>

      {/* top-right: compass */}
      <div
        aria-label={t('spa.map.compass.label')}
        style={{
          position: 'absolute',
          top: 12,
          right: 12,
          width: 48,
          height: 48,
          borderRadius: '50%',
          background: 'rgba(15,20,25,0.85)',
          border: '1px solid var(--color-border)',
          display: 'grid',
          placeItems: 'center',
          color: 'var(--color-text-muted)',
          fontFamily: 'var(--font-family-mono)',
          fontSize: 10,
          backdropFilter: 'blur(6px)',
        }}
      >
        {t('spa.map.compass.north')}
        <span
          style={{
            position: 'absolute',
            width: 2,
            height: 16,
            background: 'var(--color-primary)',
            top: 4,
          }}
        />
      </div>

      {/* Sticky indeterminate progress bar (ROADMAP §3-W2).
          Pinned to the top edge of the map area; visible whenever any
          React-Query mutation is in-flight. Test hook: data-testid="aoi-progress". */}
      {isBusy && (
        <div
          data-testid="aoi-progress"
          role="progressbar"
          aria-busy="true"
          aria-label={t('spa.map.aoi.progress_label', { defaultValue: 'Predicting AOI batch…' })}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: 3,
            overflow: 'hidden',
            zIndex: 999,
          }}
        >
          <div
            style={{
              height: '100%',
              width: '35%',
              background: 'var(--color-primary)',
              animation: 'fc-progress-indeterminate 1.2s ease-in-out infinite',
            }}
          />
        </div>
      )}
    </>
  );
}

export default MapOverlays;
