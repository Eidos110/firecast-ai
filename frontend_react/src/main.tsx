/**
 * FireCast SPA boot — initialises i18n (async) and QueryClient, then mounts
 * the <App /> tree wrapped in the shared providers:
 *   - <QueryClientProvider>  (react-query retries / fetch caching)
 *   - <I18nextProvider>      (exposes t() via useTranslation in components)
 *
 * The theme provider is intentionally NOT a global context: `useTheme()` is
 * self-contained (reads localStorage + matchMedia, applies `data-theme`
 * directly on <html>) so the header can call it without a provider in the
 * tree above it. See theme/useTheme.ts for the rationale.
 *
 * Boot order: initI18n() → mount <App/>.  i18n is initialised before render
 * so the first paint already has `t()` hydrated — avoids a flash of empty
 * labels on the engineer console's header.
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import i18n from 'i18next';

import App from './App.tsx';
import './index.css';
import { ErrorBoundary } from './components/ErrorBoundary';
import { initI18n } from './i18n/i18n';
import { logError } from './utils/log';

// Single shared QueryClient. react-query v5 default retry (3x) + 1m stale time
// keeps the diagnostic panel from hammering /predict during rapid clicks.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1, // backend-side errors should surface fast in the ApiLogBox
      staleTime: 60 * 1000,
      refetchOnWindowFocus: false,
    },
  },
});

const root = document.getElementById('root');
if (!root) {
  throw new Error('FireCast SPA: #root element not found in index.html');
}

// Initialise i18n before first render so `t()` is hydrated synchronously.
// We swallow init errors so a malformed locale file never bricks the console:
// labels will fall back to key strings, which is the lesser evil.
initI18n()
  .catch((err) => {
    logError('[FireCast] i18n init failed; continuing with key fallback:', err);
  })
  .finally(() => {
    ReactDOM.createRoot(root).render(
      <React.StrictMode>
        <ErrorBoundary>
          <QueryClientProvider client={queryClient}>
            <I18nextProvider i18n={i18n}>
              <App />
            </I18nextProvider>
          </QueryClientProvider>
        </ErrorBoundary>
      </React.StrictMode>,
    );
  });
