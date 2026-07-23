import { useCallback, useEffect, useState } from 'react';
import type { DataTheme } from './tokens';

const STORAGE_KEY = 'firecast-theme';
const MEDIA_QUERY = '(prefers-color-scheme: light)';

type ThemeAttribute = DataTheme | 'auto';

function applyThemeAttr(theme: ThemeAttribute): DataTheme {
  let resolved: DataTheme;
  if (theme === 'auto') {
    const prefersLight =
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia(MEDIA_QUERY).matches;
    resolved = prefersLight ? 'light' : 'dark';
  } else {
    resolved = theme;
  }
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', resolved);
  }
  return resolved;
}

function readStoredTheme(): ThemeAttribute {
  if (typeof window === 'undefined') return 'dark';
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v === 'light' || v === 'dark' || v === 'auto') return v;
  } catch {
    // localStorage may be disabled (private mode); fall through.
  }
  return 'dark';
}

export interface UseThemeApi {
  /** The user's stored preference — may be 'auto' (follows the OS). */
  preference: ThemeAttribute;
  /** The resolved theme currently applied to <html data-theme>. */
  resolved: DataTheme;
  /** Choose 'dark' | 'light' | 'auto'. Persists to localStorage. */
  setTheme: (next: ThemeAttribute) => void;
  /** Convenience: cycle dark -> light -> auto -> dark. */
  cycleTheme: () => void;
}

export function useTheme(initial: ThemeAttribute = 'dark'): UseThemeApi {
  const [preference, setPreference] = useState<ThemeAttribute>(initial);
  const [resolved, setResolved] = useState<DataTheme>('dark');

  // First effect: read the persisted preference once on mount.
  useEffect(() => {
    const stored = readStoredTheme();
    setPreference(stored);
    const r = applyThemeAttr(stored);
    setResolved(r);
  }, []);

  // Follow OS preference changes when in auto mode.
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const mql = window.matchMedia(MEDIA_QUERY);
    const handler = () => {
      setResolved((currentResolved) => {
        // Only react when preference is auto — explicit choices are stable.
        if (readStoredThemePublic() !== 'auto') {
          return currentResolved;
        }
        return applyThemeAttr('auto');
      });
    };
    // addEventListener is the modern API (addListener deprecated); feature-check both.
    if (typeof mql.addEventListener === 'function') {
      mql.addEventListener('change', handler);
      return () => mql.removeEventListener('change', handler);
    }
    // Legacy Safari fallback.
    if (typeof (mql as MediaQueryList).addListener === 'function') {
      (mql as MediaQueryList).addListener(handler);
      return () => (mql as MediaQueryList).removeListener(handler);
    }
    return undefined;
  }, []);

  const setTheme = useCallback((next: ThemeAttribute) => {
    setPreference(next);
    try {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(STORAGE_KEY, next);
      }
    } catch {
      // storage may be unavailable; ignore — the in-memory state still flips.
    }
    const r = applyThemeAttr(next);
    setResolved(r);
  }, []);

  const cycleTheme = useCallback(() => {
    setPreference((p) => {
      const order: ThemeAttribute[] = ['dark', 'light', 'auto'];
      const idx = order.indexOf(p);
      const next = order[(idx + 1) % order.length] ?? 'dark';
      try {
        if (typeof window !== 'undefined') {
          window.localStorage.setItem(STORAGE_KEY, next);
        }
      } catch {
        /* noop */
      }
      const r = applyThemeAttr(next);
      setResolved(r);
      return next;
    });
  }, []);

  return { preference, resolved, setTheme, cycleTheme };
}

// Small helper so the matchMedia listener closure can re-read the live value
// without depending on stale state (kept private to this module).
function readStoredThemePublic(): ThemeAttribute {
  return readStoredTheme();
}
