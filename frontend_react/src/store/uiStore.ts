/**
 * UI chrome store — mobile drawer state + command palette visibility.
 *
 * Separate from inferenceStore so panel-open state doesn't couple to model
 * data; a closed drawer never blocks a /predict mutation.
 *
 * ROADMAP §3-W3 adds a persona mode toggle ("Engineer / Analyst / Demo")
 * exposed via Header tabs. Persisted to localStorage so the operator's
 * persona survives a reload (and stays consistent across tabs of the same
 * browser session — one user, one mode).
 */
import { create } from 'zustand';

export type UiMode = 'engineer' | 'analyst' | 'demo';

interface UiStore {
  /** Mobile: left config drawer (layers / model / filters). Desktop: always open. */
  leftOpen: boolean;
  /** Mobile: right diagnostic drawer. Desktop: always open. */
  rightOpen: boolean;
  /** Ctrl+K command palette. */
  paletteOpen: boolean;
  /** Persona preset: Engineer (full chrome), Analyst (table focus), Demo (read-only). */
  mode: UiMode;
  setLeftOpen: (v: boolean) => void;
  setRightOpen: (v: boolean) => void;
  toggleLeft: () => void;
  toggleRight: () => void;
  setPaletteOpen: (v: boolean) => void;
  togglePalette: () => void;
  setMode: (m: UiMode) => void;
}

const MODE_KEY = 'firecast-ui-mode';

function readInitialMode(): UiMode {
  if (typeof window === 'undefined') return 'engineer';
  try {
    const stored = window.localStorage.getItem(MODE_KEY);
    if (stored === 'engineer' || stored === 'analyst' || stored === 'demo') return stored;
  } catch {
    /* sandbox without localStorage — keep default */
  }
  return 'engineer';
}

function persistMode(mode: UiMode): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(MODE_KEY, mode);
  } catch {
    /* noop */
  }
}

export const useUiStore = create<UiStore>((set) => ({
  // Drawers start closed on mobile; the desktop grid renders the columns
  // regardless (CSS media query), so these flags are only read by the
  // mobile drawer wrappers.
  leftOpen: false,
  rightOpen: false,
  paletteOpen: false,
  mode: readInitialMode(),
  setLeftOpen: (v) => set({ leftOpen: v }),
  setRightOpen: (v) => set({ rightOpen: v }),
  toggleLeft: () => set((s) => ({ leftOpen: !s.leftOpen, rightOpen: false })),
  toggleRight: () => set((s) => ({ rightOpen: !s.rightOpen, leftOpen: false })),
  setPaletteOpen: (v) => set({ paletteOpen: v }),
  togglePalette: () => set((s) => ({ paletteOpen: !s.paletteOpen })),
  setMode: (mode) => {
    persistMode(mode);
    set({ mode });
  },
}));
