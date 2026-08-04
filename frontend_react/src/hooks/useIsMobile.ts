/**
 * useIsMobile — reactive media-query hook.
 *
 * Returns true when the viewport is at or below `maxWidthPx`. Debounce-free:
 * matchMedia change events are already edge-triggered, so a simple listener
 * is enough. SSR-safe (defaults to false when window is undefined).
 */
import { useEffect, useState } from 'react';

export function useIsMobile(maxWidthPx = 900): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
    return window.matchMedia(`(max-width: ${maxWidthPx}px)`).matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined;
    const mql = window.matchMedia(`(max-width: ${maxWidthPx}px)`);
    const handler = () => setMatches(mql.matches);
    handler();
    if (typeof mql.addEventListener === 'function') {
      mql.addEventListener('change', handler);
      return () => mql.removeEventListener('change', handler);
    }
    if (typeof (mql as MediaQueryList).addListener === 'function') {
      (mql as MediaQueryList).addListener(handler);
      return () => (mql as MediaQueryList).removeListener(handler);
    }
    return undefined;
  }, [maxWidthPx]);

  return matches;
}

export default useIsMobile;
