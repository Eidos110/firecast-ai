/**
 * Toast store — transient user-facing notifications (success / error / info).
 *
 * Kept separate from `inferenceStore.apiLogs` on purpose:
 *   - apiLogs  = engineering audit trail (persistent in the session buffer,
 *                shown in ApiLogBox, coloured ok/warn/err).
 *   - toasts   = human-readable feedback about an *action* the user just
 *                took ("AOI drawn", "Model activated"), auto-dismissing.
 *
 * The <ToastViewport> component renders this store. `toast.success(...)` etc.
 * are exported as plain functions so non-React code (mutation callbacks) can
 * raise a toast without needing the hook.
 */
import { create } from 'zustand';

let nextId = 1;

export type ToastKind = 'success' | 'error' | 'info';

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
  /** Auto-dismiss after N ms; 0/undefined = sticky (manual close). */
  ttlMs?: number;
}

interface ToastStore {
  toasts: Toast[];
  push: (kind: ToastKind, message: string, ttlMs?: number) => number;
  dismiss: (id: number) => void;
  clear: () => void;
}

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  push: (kind, message, ttlMs = 4000) => {
    const id = nextId++;
    set((s) => {
      const next = [...s.toasts, { id, kind, message, ttlMs }];
      // Keep at most 5 visible — older ones drop to avoid screen flooding.
      while (next.length > 5) next.shift();
      return { toasts: next };
    });
    return id;
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  clear: () => set({ toasts: [] }),
}));

/** Imperative helpers — usable anywhere (no hook context needed). */
export const toast = {
  success: (message: string, ttlMs?: number) => useToastStore.getState().push('success', message, ttlMs),
  error: (message: string, ttlMs?: number) => useToastStore.getState().push('error', message, ttlMs ?? 6000),
  info: (message: string, ttlMs?: number) => useToastStore.getState().push('info', message, ttlMs),
};
