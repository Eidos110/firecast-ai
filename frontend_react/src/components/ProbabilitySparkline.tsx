import { useMemo } from 'react';
import { getRiskColor } from '../theme/tokens';
import { cn } from '../utils/cn';

export interface ProbabilitySparklineProps {
  /** Sequence of 0..1 probabilities (e.g. next 12 hours of forecast). */
  data: number[];
  /** Pixel width (defaults to 240). */
  width?: number;
  /** Pixel height (defaults to 48). */
  height?: number;
  /** Show a small dot at the latest point. */
  showLastDot?: boolean;
  ariaLabel?: string;
  className?: string;
}

/**
 * ProbabilitySparkline — lightweight inline SVG sparkline (no d3 or recharts).
 * The path fills with a translucent gradient keyed by the *last* point's risk tier.
 * Falls back gracefully to a flat line when data is empty or all-zero.
 */
export function ProbabilitySparkline({
  data,
  width = 240,
  height = 48,
  showLastDot = true,
  ariaLabel,
  className,
}: ProbabilitySparklineProps): JSX.Element {
  const safe = useMemo(() => {
    const cleaned = Array.isArray(data)
      ? data.map((v) => (Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : 0))
      : [];
    if (cleaned.length === 0) return new Array(2).fill(0);
    return cleaned;
  }, [data]);

  const last = safe[safe.length - 1] ?? 0;
  const color = getRiskColor(last);

  const { linePath, areaPath, points } = useMemo(() => {
    const n = safe.length;
    const stepX = width / Math.max(1, n - 1);
    const padY = height * 0.12;
    const usableH = height - padY * 2;
    let cumulative = '';
    let area = `M 0 ${height}`;
    const dots: [number, number][] = [];
    for (let i = 0; i < n; i++) {
      const x = i * stepX;
      const y = padY + (1 - safe[i]) * usableH;
      cumulative += `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)} `;
      area += ` L ${x.toFixed(2)} ${y.toFixed(2)}`;
      dots.push([x, y]);
    }
    area += ` L ${width.toFixed(2)} ${height} Z`;
    return { linePath: cumulative.trim(), areaPath: area, points: dots };
  }, [safe, width, height]);

  const label =
    ariaLabel ??
    `Probability trend over ${safe.length} points, current value ${(last * 100).toFixed(0)} percent`;

  const gradientId = useMemo(
    () => `spark-${Math.random().toString(36).slice(2, 8)}`,
    []
  );

  return (
    <div
      className={cn('probability-sparkline', className)}
      style={{ width, height, display: 'inline-block' }}
    >
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={label}
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.4" />
            <stop offset="100%" stopColor={color} stopOpacity="0.05" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill={`url(#${gradientId})`} stroke="none" />
        <path
          d={linePath}
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {showLastDot && points.length > 0 && (
          <circle
            cx={points[points.length - 1][0]}
            cy={points[points.length - 1][1]}
            r="2.5"
            fill={color}
          >
            <title>{label}</title>
          </circle>
        )}
      </svg>
    </div>
  );
}

export default ProbabilitySparkline;
