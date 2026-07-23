import { cn } from '../utils/cn';

export interface SkeletonProps {
  width?: number | string;
  height?: number | string;
  /** Border radius (defaults to var tokens --radius-sm). */
  radius?: number | string;
  /** Accessible label announced to screen readers. */
  ariaLabel?: string;
  /** Show shimmer animation (default true). */
  shimmer?: boolean;
  className?: string;
  /** Inner style overrides. */
  style?: React.CSSProperties;
}

/**
 * Skeleton — placeholder shimmer used while predictions/maps are loading.
 * Uses CSS custom properties so it adapts to dark/light themes automatically.
 * Honors prefers-reduced-motion (handled in theme CSS variables).
 */
export function Skeleton({
  width = '100%',
  height = 20,
  radius = 'var(--radius-sm, 4px)',
  ariaLabel = 'Loading',
  shimmer = true,
  className,
  style,
}: SkeletonProps): JSX.Element {
  return (
    <div
      className={cn('fc-skeleton', shimmer && 'fc-skeleton--shimmer', className)}
      role="status"
      aria-live="polite"
      aria-label={ariaLabel}
      style={{
        width,
        height,
        borderRadius: radius,
        background:
          'linear-gradient(90deg, var(--color-surface-hover, #334155) 25%, var(--color-surface, #1e293b) 50%, var(--color-surface-hover, #334155) 75%)',
        backgroundSize: '200% 100%',
        animation: shimmer ? 'fc-skeleton-shimmer 1.4s linear infinite' : undefined,
        ...style,
      }}
    >
      <span className="sr-only" style={srOnly}>
        {ariaLabel}
      </span>
    </div>
  );
}

const srOnly: React.CSSProperties = {
  position: 'absolute',
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: 'hidden',
  clip: 'rect(0,0,0,0)',
  whiteSpace: 'nowrap',
  border: 0,
};

export default Skeleton;
