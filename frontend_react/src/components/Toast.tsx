import { useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '../utils/cn';
import { Z_INDEX } from '../theme/tokens';

export type ToastVariant = 'info' | 'success' | 'warning' | 'error';

export interface ToastItem {
  id: string;
  title: string;
  description?: string;
  variant: ToastVariant;
  /** Auto-dismiss after N ms (0 disables). */
  duration?: number;
}

export interface ToastProps extends Omit<ToastItem, 'id'> {
  id?: string;
  onClose?: (id: string) => void;
}

const VARIANT_COLOR: Record<ToastVariant, string> = {
  info: 'var(--color-info, #3b82f6)',
  success: 'var(--color-success, #22c55e)',
  warning: 'var(--color-warning, #eab308)',
  error: 'var(--color-error, #dc2626)',
};

const VARIANT_ICON: Record<ToastVariant, string> = {
  info: '\u2139\uFE0F',
  success: '\u2705',
  warning: '\u26A0\uFE0F',
  error: '\u26D4\uFE0F',
};

function randomId(): string {
  return `t-${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * Single Toast card. Auto-dismisses after `duration` (default 4s, 0 keeps it open).
 */
export function Toast({ id, title, description, variant, duration = 4000, onClose }: ToastProps): JSX.Element {
  const internalId = useRef<string>(id ?? randomId());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const close = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    onClose?.(internalId.current);
  }, [onClose]);

  useEffect(() => {
    if (duration > 0) {
      timer.current = setTimeout(close, duration);
    }
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [duration, close]);

  return (
    <div
      role="alert"
      aria-live={variant === 'error' ? 'assertive' : 'polite'}
      className={cn('fc-toast', `fc-toast--${variant}`)}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '8px',
        padding: '12px 16px',
        marginBottom: 8,
        borderRadius: 'var(--radius-md, 8px)',
        background: 'var(--color-surface, #1e293b)',
        color: 'var(--color-text, #f1f5f9)',
        boxShadow: 'var(--shadow-lg, 0 10px 15px rgba(0,0,0,0.1))',
        borderLeft: `4px solid ${VARIANT_COLOR[variant]}`,
        zIndex: Z_INDEX.toast,
        maxWidth: 420,
      }}
    >
      <span aria-hidden="true" style={{ fontSize: 16 }}>
        {VARIANT_ICON[variant]}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{title}</div>
        {description && (
          <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted, #94a3b8)', marginTop: 2 }}>
            {description}
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={close}
        aria-label="Dismiss notification"
        style={{
          background: 'none',
          border: 'none',
          color: 'var(--color-text-muted, #94a3b8)',
          cursor: 'pointer',
          fontSize: 16,
          padding: 0,
          minHeight: 44,
          minWidth: 44,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <span aria-hidden="true">{'\u00D7'}</span>
      </button>
    </div>
  );
}

export interface ToastViewportProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}

/** ToastViewport — fixed container, typically in the top-right corner. */
export function ToastViewport({ toasts, onDismiss }: ToastViewportProps): JSX.Element {
  return (
    <div
      aria-live="polite"
      style={{
        position: 'fixed',
        top: 16,
        right: 16,
        zIndex: Z_INDEX.toast,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {toasts.map((t) => (
        <Toast key={t.id} {...t} onClose={onDismiss} />
      ))}
    </div>
  );
}

/** useToasts — small hook-driven store. Returns add + remove + items. */
export function useToasts() {
  const [items, setItems] = useState<ToastItem[]>([]);
  const add = (t: Omit<ToastItem, 'id'>): string => {
    const id = randomId();
    setItems((prev) => [...prev, { ...t, id }]);
    return id;
  };
  const remove = useCallback((id: string) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);
  return { items, add, remove };
}

export default Toast;
