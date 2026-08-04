/**
 * TimelineScrubber — bottom bar (h=56px) time-scrubber H-24 → H+72 (V4 mockup).
 *
 * Reads the global `horizonHours` from the store and updates it via range
 * input. Play/Pause toggles a setInterval that increments the horizon by 1h.
 * The "Now" stamp uses the latest prediction timestamp when available.
 */
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useInferenceStore } from '../store/inferenceStore';
import { getCurrentLang } from '../i18n/i18n';

const HORIZON_MIN = -24;
const HORIZON_MAX = 72;
const HORIZON_STEP = 1;

export function TimelineScrubber(): JSX.Element {
  const { t } = useTranslation();
  const horizonHours = useInferenceStore((s) => s.horizonHours);
  const setHorizonHours = useInferenceStore((s) => s.setHorizonHours);
  const isPlaying = useInferenceStore((s) => s.isPlaying);
  const setIsPlaying = useInferenceStore((s) => s.setIsPlaying);
  const setRunId = useInferenceStore((s) => s.setRunId);
  const runId = useInferenceStore((s) => s.runId);
  const apiLogs = useInferenceStore((s) => s.apiLogs);
  const lastLog = apiLogs.at(-1);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (isPlaying) {
      timerRef.current = setInterval(() => {
        setHorizonHours(Math.min(HORIZON_MAX, horizonHours + HORIZON_STEP));
      }, 1000);
      return () => {
        if (timerRef.current) clearInterval(timerRef.current);
        timerRef.current = null;
      };
    }
    return undefined;
  }, [isPlaying, horizonHours, setHorizonHours]);

  function togglePlay(): void {
    if (horizonHours >= HORIZON_MAX) setHorizonHours(HORIZON_MIN);
    setIsPlaying(!isPlaying);
  }

  const stamp = lastLog?.ts ?? new Date().toISOString();
  const lang = i18nLangForClock();
  return (
    <footer
      role="contentinfo"
      style={{
        height: 56,
        background: 'var(--color-surface)',
        borderTop: '1px solid var(--color-border)',
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        padding: '0 16px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1 }}>
        <span className="fc-mono" style={{ fontSize: 11, color: 'var(--color-text-muted)', minWidth: 60 }}>
          H{formatHorizon(horizonHours)}
        </span>
        <input
          type="range"
          min={HORIZON_MIN}
          max={HORIZON_MAX}
          step={HORIZON_STEP}
          value={horizonHours}
          onChange={(e) => setHorizonHours(Number(e.target.value))}
          aria-label={t('spa.timeline.label')}
          className="fc-range"
          style={{ flex: 1 }}
        />
        <span className="fc-mono" style={{ fontSize: 11, color: 'var(--color-primary)', minWidth: 50 }}>
          H{formatHorizon(horizonHours)}
        </span>
      </div>

      <span className="fc-mono" style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
        {t('spa.timeline.now')}: {new Date(stamp).toLocaleTimeString(lang, { hour12: false })} UTC
      </span>
      <button
        type="button"
        onClick={togglePlay}
        className="fc-btn-secondary"
        aria-label={isPlaying ? t('spa.timeline.pause') : t('spa.timeline.play')}
      >
        {isPlaying ? t('spa.timeline.pause') : t('spa.timeline.play')}
      </button>
      <button
        type="button"
        onClick={() => setRunId(`fc-${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')}`)}
        className="fc-btn-secondary"
        aria-label={t('spa.timeline.new_run')}
      >
        {t('spa.timeline.new_run')}
      </button>
      <button
        type="button"
        onClick={() => {
          void runId;
          const blob = new Blob([JSON.stringify({ runId, horizonHours }, null, 2)], {
            type: 'application/json',
          });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `firecast-${runId}.json`;
          a.click();
          URL.revokeObjectURL(url);
        }}
        className="fc-btn-secondary"
        aria-label={t('spa.timeline.export_json')}
      >
        {t('spa.timeline.export_json')}
      </button>
    </footer>
  );
}

/**
 * Resolve the BCP-47 tag for clock formatting from the active i18next language.
 * Reading the live language at render time keeps the clock aligned with the
 * user's last language toggle without subscribing to i18next events.
 */
function i18nLangForClock(): string {
  try {
    return getCurrentLang() === 'id' ? 'id-ID' : 'en-GB';
  } catch {
    return 'en-GB';
  }
}

function formatHorizon(h: number): string {
  if (h === 0) return '+0h';
  const sign = h > 0 ? '+' : '';
  return `${sign}${h}h`;
}

export default TimelineScrubber;
