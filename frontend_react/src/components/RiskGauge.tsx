import { useMemo } from 'react';
import { getRiskLevel, getRiskColor } from '../theme/tokens';
import { cn } from '../utils/cn';

export interface RiskGaugeProps {
  /** Risk probability 0..1. */
  score: number;
  /** Optional accessible label (defaults to a generated phrase). */
  ariaLabel?: string;
  /** Pixel diameter for the gauge (defaults to 120). */
  size?: number;
  /** Stroke thickness in px (defaults to 10). */
  stroke?: number;
  /** Toggle the center percentage readout. */
  showLabel?: boolean;
  className?: string;
}

/** RiskGauge — radial SVG gauge that colours by risk tier (Fase 4). */
export function RiskGauge({
  score,
  ariaLabel,
  size = 120,
  stroke = 10,
  showLabel = true,
  className,
}: RiskGaugeProps): JSX.Element {
  const s = Math.max(0, Math.min(1, Number.isFinite(score) ? score : 0));
  const level = useMemo(() => getRiskLevel(s), [s]);
  const color = useMemo(() => getRiskColor(s), [s]);

  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * r;
  // Semi-arc from 135deg to 405deg (270° sweep).
  const sweepFraction = 0.75;
  const arcLength = circumference * sweepFraction;
  const dash = arcLength * s;
  const gap = circumference - dash;
  // Rotate so the arc starts at 135° (bottom-left).
  const rotation = 135;

  const label = ariaLabel ?? `Risk ${level}: ${(s * 100).toFixed(0)} percent`;

  return (
    <div
      className={cn('risk-gauge', className)}
      role="img"
      aria-label={label}
      style={{ width: size, height: size, position: 'relative' }}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        aria-hidden="true"
        focusable="false"
      >
        <g transform={`rotate(${rotation} ${cx} ${cy})`}>
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke="var(--color-surface-hover, #334155)"
            strokeWidth={stroke}
            strokeDasharray={`${arcLength} ${circumference - arcLength}`}
            strokeLinecap="round"
          />
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeDasharray={`${dash} ${gap}`}
            strokeLinecap="round"
            style={{ transition: 'stroke-dasharray 350ms cubic-bezier(0.4,0,0.2,1)' }}
          />
        </g>
      </svg>
      {showLabel && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            pointerEvents: 'none',
            color: 'var(--color-text, #f1f5f9)',
          }}
        >
          <span style={{ fontSize: size * 0.22, fontWeight: 700, lineHeight: 1 }}>
            {(s * 100).toFixed(0)}%
          </span>
          <span
            style={{
              fontSize: size * 0.12,
              color,
              fontWeight: 600,
              marginTop: size * 0.02,
            }}
          >
            {level}
          </span>
        </div>
      )}
    </div>
  );
}

export default RiskGauge;
