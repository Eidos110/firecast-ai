/**
 * Header — Engineer Console sticky top bar (V4 layout + V1 system pills).
 *
 * Shows: brand, active model pill, run_id pill, EPSG pill, region select,
 * datetime-local, search, system-status LED, accuracy, avg inference, user.
 *
 * Reads from the global inference store (runId / activeModel); other values
 * are local (region select) or test-only static (accuracy, user avatar).
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '../utils/cn';
import { useInferenceStore } from '../store/inferenceStore';
import { useHealth } from '../api/hooks';
import { LanguageToggle } from './LanguageToggle';
import { ThemeToggle } from './ThemeToggle';
import { HeaderGeoControls } from './HeaderGeoControls';
import { ModeTabs } from './ModeTabs';
import { useUiStore } from '../store/uiStore';

export interface HeaderProps {
  className?: string;
  isMobile?: boolean;
}

export function Header({ className, isMobile = false }: HeaderProps): JSX.Element {
  const { t } = useTranslation();
  const runId = useInferenceStore((s) => s.runId);
  const activeModel = useInferenceStore((s) => s.activeModel);
  const latencyMs = useInferenceStore((s) => s.latencyMs);
  const [region, setRegion] = useState('Kalimantan Tengah');
  const healthQuery = useHealth(/* enabled= */ true);
  const online = !healthQuery.isError && latencyMs != null;
  const toggleLeft = useUiStore((s) => s.toggleLeft);
  const toggleRight = useUiStore((s) => s.toggleRight);
  const togglePalette = useUiStore((s) => s.togglePalette);

  return (
    <header
      role="banner"
      className={cn('fc-header', className)}
      style={{
        height: 48,
        background: 'var(--color-surface)',
        borderBottom: '1px solid var(--color-border)',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '0 16px',
        position: 'sticky',
        top: 0,
        zIndex: 200,
      }}
    >
      {isMobile && (
        <button
          type="button"
          className="fc-hamburger"
          aria-label={t('spa.nav.toggle_left')}
          onClick={toggleLeft}
        >
          ☰
        </button>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700 }}>
        <span
          aria-hidden
          style={{
            width: 10,
            height: 10,
            borderRadius: '50%',
            background: 'var(--color-primary)',
            boxShadow: '0 0 10px var(--color-primary)',
            display: 'inline-block',
          }}
        />
        <span style={{ fontSize: 15, color: 'var(--color-text)' }}>{t('spa.brand')}</span>
        <span
          style={{
            fontSize: 10,
            color: 'var(--color-text-muted)',
            fontFamily: 'var(--font-family-mono)',
            borderLeft: '1px solid var(--color-border)',
            paddingLeft: 10,
          }}
        >
          {t('spa.brand_version')}
        </span>
      </div>

      {/* ROADMAP §3-W3 — persona tab strip. Hidden on mobile (drawers own space). */}
      {!isMobile && <ModeTabs />}

      <Pill label={t('spa.pill.model')} value={activeModel?.version ?? 'loading...'} />
      <Pill label={t('spa.pill.run')} value={runId} />
      <Pill label={t('spa.pill.epsg')} value="4326" />

      {/* ROADMAP §3-W1: coordinate-jumping search box + date scrub. Hidden
          on mobile — the drawer layout already crowds the bar and engineers
          on phones reach for the AOI workflow instead of typing coords. */}
      {!isMobile && <HeaderGeoControls />}

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
        <label
          htmlFor="region-select"
          className="sr-only"
          style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}
        >
          {t('spa.region.label')}
        </label>
        <select
          id="region-select"
          value={region}
          aria-label={t('spa.region.select_label')}
          onChange={(e) => setRegion(e.target.value)}
          style={{
            background: 'var(--color-surface-hover)',
            border: '1px solid var(--color-border)',
            color: 'var(--color-text)',
            padding: '4px 8px',
            borderRadius: 4,
            fontFamily: 'var(--font-family-mono)',
            fontSize: 12,
          }}
        >
          <option>Kalimantan Tengah</option>
          <option>Kalimantan Timur</option>
          <option>Riau</option>
          <option>Sumatera Selatan</option>
          <option>Papua</option>
        </select>
      </div>

      <div style={{ flex: 1 }} />

      <SystemStatus latencyMs={latencyMs} online={online} healthBusy={healthQuery.isLoading && !healthQuery.data} />
      <Pill
        label={t('spa.pill.last_run')}
        value={latencyMs != null ? `${Math.round(latencyMs)}ms` : t('spa.pill.last_run_dash')}
        tone={latencyMs != null && latencyMs < 100 ? 'good' : 'warn'}
      />

      <button
        type="button"
        onClick={togglePalette}
        aria-label={t('spa.palette.open_label')}
        title="Ctrl+K"
        className="fc-hamburger"
        style={{ display: isMobile ? 'none' : 'inline-flex', gap: 4, fontSize: 11, fontFamily: 'var(--font-family-mono)' }}
      >
        ⌘K
      </button>
      <ThemeToggle />
      <LanguageToggle />

      {isMobile && (
        <button
          type="button"
          className="fc-hamburger"
          aria-label={t('spa.nav.toggle_right')}
          onClick={toggleRight}
        >
          📊
        </button>
      )}
      <div
        aria-hidden
        style={{
          width: 28,
          height: 28,
          borderRadius: '50%',
          background: 'linear-gradient(135deg, #3b82f6, #7c3aed)',
          display: 'grid',
          placeItems: 'center',
          color: '#fff',
          fontSize: 11,
          fontWeight: 700,
          cursor: 'pointer',
        }}
        title={t('spa.user.avatar_label')}
        onClick={() => {
          const next = window.prompt(t('spa.user.prompt_name'), readStoredName());
          if (next != null) writeStoredName(next);
          window.dispatchEvent(new Event('firecast-user-updated'));
        }}
      >
        {initialsFromName(readStoredName())}
      </div>
    </header>
  );
}

function Pill({
  label,
  value,
  tone = 'default',
}: {
  label: string;
  value: string;
  tone?: 'default' | 'good' | 'warn' | 'bad';
}): JSX.Element {
  const tones: Record<string, string> = {
    default: 'var(--color-text)',
    good: 'var(--color-success)',
    warn: 'var(--color-warning)',
    bad: 'var(--color-error)',
  };
  return (
    <span
      style={{
        background: 'var(--color-surface-hover)',
        border: '1px solid var(--color-border)',
        color: 'var(--color-text-muted)',
        padding: '3px 10px',
        borderRadius: 12,
        fontFamily: 'var(--font-family-mono)',
        fontSize: 11,
      }}
    >
      {label}: <span style={{ color: tones[tone] }}>{value}</span>
    </span>
  );
}

function SystemStatus({ latencyMs, online, healthBusy }: { latencyMs: number | null; online: boolean; healthBusy: boolean }): JSX.Element {
  const { t } = useTranslation();
  const isOnline = online && latencyMs != null;
  const statusKey = healthBusy ? 'connecting' : isOnline ? 'online' : 'offline';
  const status = t(`spa.status.${statusKey}`);
  return (
    <span
      style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--color-text-muted)' }}
      aria-live="polite"
    >
      <span
        aria-hidden
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: isOnline ? 'var(--color-success)' : 'var(--color-text-muted)',
          boxShadow: isOnline ? '0 0 8px var(--color-success)' : 'none',
          animation: 'fc-status-pulse 2s infinite',
          display: 'inline-block',
        }}
      />
      {t('spa.status.label')}: {status}
    </span>
  );
}

function readStoredName(): string {
  try {
    return window.localStorage.getItem('firecast-user-name') || 'FireCast Engineer';
  } catch {
    return 'FireCast Engineer';
  }
}
function writeStoredName(name: string): void {
  try {
    window.localStorage.setItem('firecast-user-name', name.trim() || 'FireCast Engineer');
  } catch {
    /* noop */
  }
}
export function initialsFromName(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'FC';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default Header;
