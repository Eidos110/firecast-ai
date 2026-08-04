// Shared Vitest setup — jsdom + jest-dom matchers + cleanup + i18next init.
import { afterEach, beforeAll } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// Initialise i18next synchronously before any test imports its hooks. The
// locales live alongside in `frontend/locales/`; the test-resolver reads them
// via the same `tsconfig.include` expansion as the app bundle.
import { initI18n } from '../i18n/i18n';

beforeAll(async () => {
  await initI18n();
});

// jsdom does not implement ResizeObserver, but Recharts ResponsiveContainer
// (used by RiskTrendChart + ProbabilitySparkline + the batch legend) calls
// `new ResizeObserver(...)` on mount. Polyfill a no-op observer so tests
// pass in jsdom without leaking real DOM measurements.
class ResizeObserverStub {
  observe(): void {
    /* no-op */
  }
  unobserve(): void {
    /* no-op */
  }
  disconnect(): void {
    /* no-op */
  }
}
(globalThis as any).ResizeObserver = (globalThis as any).ResizeObserver ?? ResizeObserverStub;

afterEach(() => {
  cleanup();
});
