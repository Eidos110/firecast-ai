/**
 * FiltersPanel — left sidebar hazard filters (Region, Date Range, Risk Threshold).
 *
 * V4 mockup pattern. The Region select is now populated from `/geo/locations`
 * via the `useLocations` react-query hook so it reflects the backend's
 * Indonesia city registry rather than a hardcoded five-entry list. Dates
 * remain local-state for the moment — they don't affect the API yet, but
 * keeping them visible means a future PLAN §4 TAHAP E batch-export button
 * has a stable place to bind.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useLocations } from '../api/hooks';

const RISK_LEVEL_KEYS = ['all', 'ge_moderate', 'ge_high', 'extreme_only'] as const;
type RiskLevelKey = (typeof RISK_LEVEL_KEYS)[number];

export function FiltersPanel(): JSX.Element {
  const { t } = useTranslation();
  const [riskLevel, setRiskLevel] = useState<RiskLevelKey>('all');
  const [region, setRegion] = useState<string>('');
  const [dateStart, setDateStart] = useState('2026-07-15');
  const [dateEnd, setDateEnd] = useState('2026-07-29');

  // Default region label resolved via i18n once on first render so the
  // panel doesn't flash English/Bahasa before translations hydrate.
  const regionAllLabel = t('spa.filters.region_all');
  const effectiveRegion = region || regionAllLabel;

  // Populate the region dropdown from /geo/locations. Take the unique top-N
  // so the <select> keeps a usable height (V4 mockup shows ~5 lines).
  const locationsQuery = useLocations(/* enabled= */ true);
  const regionOptions = useMemo<string[]>(() => {
    const fallback = [
      regionAllLabel,
      'Sumatera',
      'Kalimantan',
      'Jawa',
      'Papua',
    ];
    const list = locationsQuery.data?.locations;
    if (!list || list.length === 0) return fallback;
    // Use the textual city names from the registry, trimmed + deduped.
    const seen = new Set<string>();
    const out: string[] = [];
    for (const entry of list) {
      const name = entry.name?.trim();
      if (name && !seen.has(name)) {
        seen.add(name);
        out.push(name);
      }
      if (out.length >= 50) break;
    }
    return [regionAllLabel, ...out];
  }, [locationsQuery.data, regionAllLabel]);

  return (
    <section aria-labelledby="filters-heading" className="fc-section">
      <h4 id="filters-heading" className="fc-section-title">
        {t('spa.filters.risk_level')}
      </h4>
      <label className="fc-field">
        <span className="fc-field-label">{t('spa.filters.risk_level')}</span>
        <select
          value={riskLevel}
          onChange={(e) => setRiskLevel(e.target.value as RiskLevelKey)}
          className="fc-input"
        >
          {RISK_LEVEL_KEYS.map((k) => (
            <option key={k} value={k}>
              {t(`spa.filters.risk_level_options.${k}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="fc-field">
        <span className="fc-field-label">{t('spa.filters.region')}</span>
        <select
          value={effectiveRegion}
          onChange={(e) => setRegion(e.target.value)}
          className="fc-input"
        >
          {regionOptions.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </label>
      <div className="fc-field">
        <span className="fc-field-label">{t('spa.filters.date_range')}</span>
        <div style={{ display: 'flex', gap: 6 }}>
          <input
            type="date"
            value={dateStart}
            onChange={(e) => setDateStart(e.target.value)}
            className="fc-input fc-mono"
            aria-label={t('spa.filters.start_date')}
          />
          <input
            type="date"
            value={dateEnd}
            onChange={(e) => setDateEnd(e.target.value)}
            className="fc-input fc-mono"
            aria-label={t('spa.filters.end_date')}
          />
        </div>
      </div>
      <div aria-live="polite" style={{ fontSize: 10, color: 'var(--color-text-muted)', marginTop: 4 }}>
        {locationsQuery.isLoading
          ? t('spa.filters.loading_locations')
          : locationsQuery.isError
            ? t('spa.filters.locations_unavailable')
            : t('spa.filters.region_count', { count: locationsQuery.data?.count ?? 0 })}
      </div>
    </section>
  );
}

export default FiltersPanel;
