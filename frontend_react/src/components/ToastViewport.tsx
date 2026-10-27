/**
 * ToastViewport — fixed-position renderer for the toast store.
 *
 * Sits top-right at --z-toast (9000). Each toast auto-dismisses after its
 * ttlMs and is also manually closable. Colours come from the design tokens
 * so the toasts stay legible in both dark and light themes. ARIA: the whole
 * stack is a polite live region; errors upgrade to assertive.
 */
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useToastStore, type Toast } from '../store/toastStore';

const KIND_COLOR: Record<Toast['kind'], string> = {
  success: 'var(--color-success)',
  error: 'var(--color-error)',
  info: 'var(--color-info)',
};
const KIND_ICON: Record<Toast['kind'], string> = {
  success: '✓',
  error: '✕',
  info: 'ℹ',
};

function ToastItem({ toast }: { toast: Toast }): JSX.Element {
  const dismiss = useToastStore((s) => s.dismiss);
  useEffect(() => {
    if (!toast.ttlMs) return undefined;
    const id = window.setTimeout(() => dismiss(toast.id), toast.ttlMs);
    return () => window.clearTimeout(id);
  }, [toast.id, toast.ttlMs, dismiss]);

  return (
    <div
      role={toast.kind === 'error' ? 'alert' : 'status'}
      className="fc-toast"
      style={{
        borderLeft: `3px solid ${KIND_COLOR[toast.kind]}`,
      }}
    >
      <span aria-hidden className="fc-toast-icon" style={{ color: KIND_COLOR[toast.kind] }}>
        {KIND_ICON[toast.kind]}
      </span>
      <span className="fc-toast-message">{toast.message}</span>
      <button
        type="button"
        className="fc-toast-close"
        aria-label="Dismiss notification"
        onClick={() => dismiss(toast.id)}
      >
        ×
      </button>
    </div>
  );
}

export function ToastViewport(): JSX.Element {
  const toasts = useToastStore((s) => s.toasts);
  useTranslation(); // ensure re-render on locale switch (message strings are rendered at push time)
  return (
    <div className="fc-toast-viewport" aria-live="polite">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} />
      ))}
    </div>
  );
}

export default ToastViewport;
