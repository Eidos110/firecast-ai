/**
 * FireCast i18n bootstrap — react-i18next wired to the legacy
 * `frontend/locales/{en,id}.json` files. Single-source-of-truth stays with
 * those JSONs; SPA modules call `t('key')` directly, mirroring the Streamlit
 * `get_text()` convention.
 *
 * Loaded at app boot from `main.tsx` (see `initI18n()` export).
 */
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

// Locale JSON files live OUTSIDE frontend_react (single source of truth,
// see `frontend/locales/`). They're shared with the legacy Streamlit frontend
// path; tsconfig.json `include` expands to resolve them at compile time.
import enLocale from '../../../frontend/locales/en.json';
import idLocale from '../../../frontend/locales/id.json';

export const SUPPORTED_LANGS = ['en', 'id'] as const;
export type Lang = (typeof SUPPORTED_LANGS)[number];

const STORAGE_KEY = 'firecast-lang';

function detectInitialLang(): Lang {
  if (typeof window === 'undefined') return 'en';
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === 'en' || stored === 'id') return stored;
  } catch {
    /* localStorage unavailable — fall through */
  }
  // Default to English on this engineer console (AGENTS.md note: backend
  // logs & risk_level keys are lowercase ID terms; UI labels use the
  // translation per the user's preference).
  return 'en';
}

export async function initI18n(): Promise<void> {
  if (i18n.isInitialized) return;
  await i18n.use(initReactI18next).init({
    resources: {
      en: { translation: enLocale },
      id: { translation: idLocale },
    },
    lng: detectInitialLang(),
    fallbackLng: 'en',
    interpolation: { escapeValue: false },
    returnNull: false,
  });
}

export function setLang(lang: Lang): void {
  i18n.changeLanguage(lang);
  try {
    if (typeof window !== 'undefined') window.localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    /* noop */
  }
}

export function getCurrentLang(): Lang {
  return (i18n.language as Lang) || 'en';
}
