/**
 * ThemeToggle — dark / light / auto cycle button for the Header.
 *
 * Single button that walks the `useTheme().cycleTheme()` order
 * (dark → light → auto). Icon shows the *resolved* value so the engineer can
 * predict which state they'll land in next. Title is localised via the shared
 * i18n store; aria-label mirrors it for screen-reader coverage.
 */
import { useTranslation } from 'react-i18next';
import { useTheme } from '../theme/useTheme';

export function ThemeToggle(): JSX.Element {
  const { t } = useTranslation();
  const { resolved, cycleTheme } = useTheme();

  // Sun = currently light, Moon = currently dark; clicking swaps the state, so
  // we render the icon of the mode you will leave.
  const icon = resolved === 'dark' ? '☀' : '🌙';
  const label = t('spa.theme_toggle.label');

  return (
    <button
      type="button"
      onClick={cycleTheme}
      aria-label={label}
      title={label}
      style={{
        minHeight: 32,
        minWidth: 32,
        padding: '0 6px',
        display: 'grid',
        placeItems: 'center',
        background: 'var(--color-surface-hover)',
        border: '1px solid var(--color-border)',
        borderRadius: 6,
        cursor: 'pointer',
        fontSize: 14,
        color: 'var(--color-text)',
        transition: 'background 120ms ease, filter 120ms ease',
      }}
    >
      <span aria-hidden>{icon}</span>
    </button>
  );
}

export default ThemeToggle;
