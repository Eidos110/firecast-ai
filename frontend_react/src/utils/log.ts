/**
 * Thin dev-only logger — no-op in production builds.
 *
 * Replace ``console.*`` calls in component code with these helpers so the
 * production SPA bundle does not leak diagnostic noise to the browser console
 * (Canvas CSP on HF Spaces also complains about console usage from
 * third-party scripts). Calls compile away to empty branches in prod via
 * ``import.meta.env.DEV`` which Vite statically inlines, so dead-code
 * elimination drops them during tree-shaking.
 *
 * Usage:
 *   import { log, logWarn, logError } from '@/utils/log';
 *   logWarn('[map] tileerror', ev);
 */

const isDev = (import.meta as { env?: { DEV?: boolean } }).env?.DEV ?? false;

export function log(...args: unknown[]): void {
  if (isDev) console.log(...args);
}

export function logInfo(...args: unknown[]): void {
  if (isDev) console.info(...args);
}

export function logWarn(...args: unknown[]): void {
  if (isDev) console.warn(...args);
}

/** Error-level: keep visible in prod too — actual errors must not vanish. */
export function logError(...args: unknown[]): void {
  console.error(...args);
}
