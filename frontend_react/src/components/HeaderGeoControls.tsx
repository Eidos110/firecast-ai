/**
 * HeaderGeoControls — coordinate search & date-scrub input (ROADMAP §3-W1).
 *
 * Adds two engineer-console affordances to the Header:
 *   1. **Coordinate jumping**: a small search input that accepts either
 *      ``"-1.5, 102.3"`` or a city/region name. On submit we set
 *      ``inferenceStore.selectedCell`` so the InteractiveMap pans (it
 *      already reacts to ``selectedCell`` via its marker effect).
 *   2. **Prediction date scrub**: a ``<input type="date">`` that writes
 *      to ``inferenceStore.selectedPredictionDate`` so `/predict` calls
 *      can anchor to a historical or forecasted date instead of hard-coding
 *      "today" (which previously was the only option — a real gap when
 *      reviewing last-week fire behaviour).
 *
 * City lookup is delegated to ``useGeocode``; coordinate parsing is a thin
 * regex; both surface the same ``selectedCell`` consumer so the map, the
 * RightDiagnostic panel and the Risk trend all update consistently.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useGeocode } from '../api/hooks';
import { useInferenceStore } from '../store/inferenceStore';

const COORD_RE = /^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/;

/** Parse ``"-1.5, 102.3"`` → ``{lat: -1.5, lon: 102.3}``, otherwise null. */
function parseCoords(query: string): { lat: number; lon: number } | null {
  const m = COORD_RE.exec(query);
  if (!m) return null;
  const lat = Number(m[1]);
  const lon = Number(m[2]);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
  return { lat, lon };
}

export function HeaderGeoControls(): JSX.Element {
  const { t } = useTranslation();
  const setSelectedCell = useInferenceStore((s) => s.setSelectedCell);
  const selectedPredictionDate = useInferenceStore((s) => s.selectedPredictionDate);
  const setSelectedPredictionDate = useInferenceStore((s) => s.setSelectedPredictionDate);

  // Search box
  const [query, setQuery] = useState('');
  // Debounced (300ms) — geocode endpoint hits a remote provider; we don't
  // want to spam it on every keystroke.
  const [debouncedQuery, setDebouncedQuery] = useState('');
  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedQuery(query), 300);
    return () => window.clearTimeout(id);
  }, [query]);
  const coords = parseCoords(query);
  // Only issue a network geocode call when the input is *not* a lat/lon
  // pair — a coord parse hit has everything we need locally.
  const geocodeQuery = useGeocode(coords === null ? debouncedQuery : '', /* enabled= */ coords === null);

  function handleSubmit(e: React.FormEvent): void {
    e.preventDefault();
    if (coords) {
      setSelectedCell(coords);
      setQuery('');
      return;
    }
    // /geo/geocode returns either a single `GeocodeResult` or `null` (when
    // the lookup misses). We take the top (only) hit — there is no ranked
    // list to traverse, so the "select a different match" UX would need to
    // be added separately if the roadmap ever requires it.
    const result = geocodeQuery.data;
    if (!result) return;
    if (typeof result.lat === 'number' && typeof result.lon === 'number') {
      setSelectedCell({ lat: result.lat, lon: result.lon });
      setQuery('');
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      style={{ display: 'flex', alignItems: 'center', gap: 6 }}
      aria-label={t('spa.map.geo_controls_label', { defaultValue: 'Geospatial controls' })}
    >
      <input
        type="search"
        role="searchbox"
        aria-label={t('spa.map.jump_label', { defaultValue: 'Jump to coordinates or place' })}
        placeholder={t('spa.map.jump_placeholder', { defaultValue: 'Jakarta or -1.5, 102.3' })}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        style={{
          background: 'var(--color-surface-hover)',
          border: '1px solid var(--color-border)',
          color: 'var(--color-text)',
          padding: '4px 8px',
          borderRadius: 4,
          fontFamily: 'var(--font-family-mono)',
          fontSize: 12,
          width: 200,
        }}
      />
      <input
        type="date"
        aria-label={t('spa.map.prediction_date_label', { defaultValue: 'Prediction date' })}
        title={t('spa.map.prediction_date_hint', {
          defaultValue: 'Pick a date to anchor /predict away from "today".',
        })}
        value={selectedPredictionDate ?? ''}
        onChange={(e) => setSelectedPredictionDate(e.target.value || null)}
        style={{
          background: 'var(--color-surface-hover)',
          border: '1px solid var(--color-border)',
          color: 'var(--color-text)',
          padding: '3px 6px',
          borderRadius: 4,
          fontFamily: 'var(--font-family-mono)',
          fontSize: 11,
        }}
      />
    </form>
  );
}

export default HeaderGeoControls;
