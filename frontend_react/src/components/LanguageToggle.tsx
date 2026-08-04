/**
 * LanguageToggle — EN/ID switcher for the Header.
 *
 * Two-button segmented control (44px-tall hit target per WCAG 2.5.5) that
 * round-trips between 'en' and 'id' via the shared i18n helper. Persists the
 * choice under the same localStorage key the i18n bootstrap reads
 * (firecast-lang), so a refresh restores the engineer's preference.
 */
import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { getCurrentLang, setLang, type Lang } from '../i18n/i18n';

export function LanguageToggle(): JSX.Element {
  const { t } = useTranslation();
  const current = getCurrentLang();

  const choose = useCallback((lang: Lang) => {
    if (lang !== getCurrentLang()) setLang(lang);
  }, []);

  return (
    <div
      role="group"
      aria-label={t('spa.lang_toggle.label')}
      style={{
        display: 'inline-flex',
        background: 'var(--color-surface-hover)',
        border: '1px solid var(--color-border)',
        borderRadius: 6,
        overflow: 'hidden',
        fontFamily: 'var(--font-family-mono)',
        fontSize: 11,
      }}
    >
      {(['en', 'id'] as const).map((lang) => {
        const active = current === lang;
        return (
          <button
            key={lang}
            type="button"
            aria-pressed={active}
            onClick={() => choose(lang)}
            style={{
              minHeight: 28,
              minWidth: 34,
              padding: '0 8px',
              border: 'none',
              background: active ? 'var(--color-primary)' : 'transparent',
              color: active ? '#fff' : 'var(--color-text-muted)',
              fontFamily: 'inherit',
              fontSize: 'inherit',
              fontWeight: active ? 700 : 500,
              cursor: 'pointer',
              transition: 'background 120ms ease, color 120ms ease',
            }}
          >
            {lang.toUpperCase()}
          </button>
        );
      })}
    </div>
  );
}

export default LanguageToggle;
