/**
 * ApiLogBox — color-coded ring-buffer log below the right diagnostic panel (V4).
 *
 * Reads the global `apiLogs` array from the inference store; each entry
 * carries an ISO ts, a "level" of ok/warn/err, and a message. Renders a
 * compact mono-spaced list; color is keyed to level per the V4 mockup.
 */
import { useTranslation } from 'react-i18next';

import { useInferenceStore } from '../store/inferenceStore';

const LEVEL_COLORS = {
  ok: 'var(--color-success)',
  warn: 'var(--color-warning)',
  err: 'var(--color-error)',
} as const;

const LEVEL_KEYS = {
  ok: 'spa.api_log.level_ok',
  warn: 'spa.api_log.level_warn',
  err: 'spa.api_log.level_err',
} as const;

/**
 * Map HTTP error codes embedded in entry messages to i18n keys (ROADMAP §3-M).
 *
 * Many callers push raw exception text like ``422 body did not match schema``;
 * users reading the log then see cryptic phrasing. This translation table
 * surfaces a friendly i18n string for the *most actionable* codes while
 * keeping the raw message visible in ``title`` for power-users digging
 * deeper. Codes not listed fall back through to the raw message unchanged.
 */
const ERROR_I18N_BY_CODE: Record<string, string> = {
  '401': 'spa.error.unauthorized',
  '403': 'spa.error.unauthorized',
  '404': 'spa.error.not_found',
  '422': 'spa.error.validation',
  '429': 'spa.error.rate_limited',
  '500': 'spa.error.server',
  '502': 'spa.error.server',
  '503': 'spa.error.server',
};

/** Extract the first 3-digit ``4xx``/``5xx`` token from ``message``. */
function extractHttpCode(message: string): string | null {
  if (typeof message !== 'string') return null;
  const m = /\b([45]\d{2})\b/.exec(message);
  return m ? m[1] : null;
}

/** i18n-aware display text for a log entry's ``message``. Pure (no hooks). */
function resolveLocalizedMessage(
  entry: { level: 'ok' | 'warn' | 'err'; message: string },
  t: (k: string) => string,
): string {
  // Only re-localise *error* entries — info/warn messages are usually
  // already well-worded and may be backend-generated.
  if (entry.level !== 'err') return entry.message;
  const code = extractHttpCode(entry.message);
  if (!code) return entry.message;
  const key = ERROR_I18N_BY_CODE[code];
  if (!key) return entry.message;
  const localised = t(key);
  // i18next returns the key itself when a translation is missing — fall
  // back to the raw message in that edge case so we never show ``spa.error.x``
  // to the user.
  return localised && localised !== key ? localised : entry.message;
}

export function ApiLogBox(): JSX.Element {
  const { t } = useTranslation();
  const apiLogs = useInferenceStore((s) => s.apiLogs);
  return (
    <div
      aria-label={t('spa.api_log.aria_label')}
      style={{
        background: '#0a0e13',
        border: '1px solid var(--color-border)',
        borderRadius: 6,
        padding: 8,
        fontFamily: 'var(--font-family-mono)',
        fontSize: 10,
        maxHeight: 160,
        minHeight: 120,
        overflowY: 'auto',
      }}
    >
      {apiLogs.length === 0 ? (
        <div style={{ color: 'var(--color-text-muted)' }}>{t('spa.api_log.no_inference_run')}</div>
      ) : (
        apiLogs
          .slice()
          .reverse()
          .map((entry, idx) => {
            const display = resolveLocalizedMessage(entry, t);
            return (
              <div key={idx} style={{ display: 'flex', gap: 8, lineHeight: 1.6 }}>
                <span style={{ color: 'var(--color-text-muted)' }}>{fmtTime(entry.ts)}</span>
                <span style={{ color: LEVEL_COLORS[entry.level] }}>{t(LEVEL_KEYS[entry.level])}</span>
                {/* ``title`` keeps the original raw message reachable for
                    engineers — the visible span shows the translated text. */}
                <span
                  title={display !== entry.message ? entry.message : undefined}
                  style={{ color: 'var(--color-text)', flex: 1 }}
                >
                  {display}
                </span>
              </div>
            );
          })
      )}
    </div>
  );
}

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '--:--:--';
  }
}

export default ApiLogBox;
