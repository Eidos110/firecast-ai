/**
 * ModeTabs — persona toggle (ROADMAP §3-W3).
 *
 * Renders a small segmented control in the Header left-of-brand:
 *     [ Engineer | Analyst | Demo ]
 *
 * Selection flows into ``useUiStore.mode`` and persists across reloads via
 * localStorage (key: ``firecast-ui-mode``). Conditional-render logic lives
 * in App.tsx; this component is purely the Header-side control.
 *
 * Why a segmented control (rather than a dropdown)?
 *   - Standard console pattern (cf. Grafana, Honeycomb persona pickers).
 *     Radio-like visible options mean an occasional viewer instantly sees
 *     the three personas without having to discover a hidden menu.
 *   - Three options = under the 5-item "short-list" heuristics; beyond that
 *     we would switch to a dropdown.
 */
import { useTranslation } from 'react-i18next';

import { useUiStore, type UiMode } from '../store/uiStore';

const MODES: Array<{ id: UiMode; key: string }> = [
  { id: 'engineer', key: 'spa.mode.engineer' },
  { id: 'analyst', key: 'spa.mode.analyst' },
  { id: 'demo', key: 'spa.mode.demo' },
];

export function ModeTabs(): JSX.Element {
  const { t } = useTranslation();
  const mode = useUiStore((s) => s.mode);
  const setMode = useUiStore((s) => s.setMode);

  return (
    <div
      role="tablist"
      aria-label={t('spa.mode.label')}
      style={{
        display: 'inline-flex',
        border: '1px solid var(--color-border)',
        borderRadius: 4,
        overflow: 'hidden',
        background: 'var(--color-surface-hover)',
      }}
    >
      {MODES.map((m) => {
        const active = mode === m.id;
        return (
          <button
            key={m.id}
            type="button"
            role="tab"
            aria-selected={active}
            title={t(`spa.mode.${m.id}_hint`)}
            onClick={() => setMode(m.id)}
            style={{
              background: active ? 'var(--color-primary)' : 'transparent',
              color: active ? '#fff' : 'var(--color-text-muted)',
              border: 'none',
              padding: '4px 10px',
              fontSize: 11,
              fontFamily: 'var(--font-family-mono)',
              cursor: 'pointer',
              textTransform: 'uppercase',
              letterSpacing: 0.4,
            }}
          >
            {t(m.key)}
          </button>
        );
      })}
    </div>
  );
}

export default ModeTabs;
