import { cn } from '../utils/cn';

export interface HeaderProps {
  title: string;
  subtitle?: string;
  /** Small badge shown on the right (e.g. model status / version). */
  badge?: string;
  /** Click handler for the brand block (usually opens command palette). */
  onBrandClick?: () => void;
  /** Right-side action nodes (theme toggle, settings, etc.). */
  actions?: React.ReactNode;
  className?: string;
}

/**
 * Header — sticky top bar for the dashboard shell (Fase 4).
 *
 * Accessibility:
 * - Uses a real `<header role="banner">`.
 * - The brand is a `<button>` so keyboard users can trigger `onBrandClick`.
 * - Touch targets respect the 44px minimum (var(--a11y-touch-target-min))
 *   via inline min-height.
 */
export function Header({
  title,
  subtitle,
  badge,
  onBrandClick,
  actions,
  className,
}: HeaderProps): JSX.Element {
  return (
    <header
      role="banner"
      className={cn('fc-header', className)}
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 200,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 16,
        padding: '10px 16px',
        minHeight: 'var(--a11y-touch-target-min, 44px)',
        background: 'var(--color-surface, #1e293b)',
        borderBottom: '1px solid var(--color-border, #334155)',
        color: 'var(--color-text, #f1f5f9)',
      }}
    >
      <button
        type="button"
        onClick={onBrandClick}
        aria-label={`${title}${subtitle ? `: ${subtitle}` : ''}`}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          padding: 0,
          margin: 0,
          textAlign: 'left',
          color: 'inherit',
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
          minHeight: 'var(--a11y-touch-target-min, 44px)',
          justifyContent: 'center',
        }}
      >
        <span style={{ fontSize: '1.0625rem', fontWeight: 700, lineHeight: 1 }}>
          {title}
        </span>
        {subtitle && (
          <span
            style={{
              fontSize: '0.75rem',
              color: 'var(--color-text-muted, #94a3b8)',
            }}
          >
            {subtitle}
          </span>
        )}
      </button>

      {badge && (
        <span
          aria-hidden="true"
          style={{
            background: 'var(--color-surface-hover, #334155)',
            color: 'var(--color-text-secondary, #cbd5e1)',
            fontSize: '0.6875rem',
            fontWeight: 600,
            padding: '3px 8px',
            borderRadius: 'var(--radius-full, 9999px)',
            whiteSpace: 'nowrap',
          }}
        >
          {badge}
        </span>
      )}

      {actions ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>{actions}</div>
      ) : null}
    </header>
  );
}

export default Header;
