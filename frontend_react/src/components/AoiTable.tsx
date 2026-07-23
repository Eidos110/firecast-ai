import { useMemo, useState } from 'react';
import { getRiskColor, getRiskLevel } from '../theme/tokens';
import { cn } from '../utils/cn';

export interface AoiRow {
  id: string;
  latitude: number;
  longitude: number;
  /** Risk probability 0..1. */
  risk: number;
  /** Optional place name or label. */
  name?: string;
  /** Optional secondary metric (e.g. confidence 0..1). */
  confidence?: number;
}

export interface AoiTableProps {
  rows: AoiRow[];
  /** Initial sort key. */
  initialSortKey?: keyof AoiRow;
  /** Initial sort direction. */
  initialSortDir?: 'asc' | 'desc';
  /** Caption shown to assistive tech when non-empty. */
  caption?: string;
  className?: string;
  /** Callback when a row is selected. */
  onRowSelect?: (row: AoiRow) => void;
}

type SortKey = keyof AoiRow;
type SortDir = 'asc' | 'desc';

const HEADER_LABELS: Record<SortKey, string> = {
  id: 'ID',
  latitude: 'Lat',
  longitude: 'Lon',
  risk: 'Risk',
  name: 'Name',
  confidence: 'Conf',
};

/**
 * AoiTable — sortable, accessible table for AOI batch results (Fase 4).
 * Keyboard: header buttons are real <button> elements; Enter/Space toggles sort.
 * Selection fires `onRowSelect`; the active row exposes `aria-current`.
 */
export function AoiTable({
  rows,
  initialSortKey = 'risk',
  initialSortDir = 'desc',
  caption,
  className,
  onRowSelect,
}: AoiTableProps): JSX.Element {
  const [sortKey, setSortKey] = useState<SortKey>(initialSortKey);
  const [sortDir, setSortDir] = useState<SortDir>(initialSortDir);
  const [selected, setSelected] = useState<string | null>(null);

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av;
      }
      const as = String(av ?? '');
      const bs = String(bv ?? '');
      return sortDir === 'asc' ? as.localeCompare(bs) : bs.localeCompare(as);
    });
    return copy;
  }, [rows, sortKey, sortDir]);

  const toggle = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const columns: SortKey[] = ['name', 'latitude', 'longitude', 'risk', 'confidence'];

  return (
    <table
      className={cn('aoi-table', className)}
      style={{ borderCollapse: 'collapse', width: '100%' }}
      aria-label={caption ?? 'AOI prediction results'}
    >
      {caption ? <caption style={{ textAlign: 'left', padding: '4px' }}>{caption}</caption> : null}
      <thead>
        <tr>
          {columns.map((col) => (
            <th
              key={col}
              scope="col"
              style={{
                textAlign: col === 'risk' || col === 'confidence' ? 'right' : 'left',
                padding: '8px',
                borderBottom: '1px solid var(--color-border, #334155)',
              }}
            >
              <button
                type="button"
                onClick={() => toggle(col)}
                aria-sort={
                  sortKey === col
                    ? sortDir === 'asc'
                      ? 'ascending'
                      : 'descending'
                    : 'none'
                }
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'inherit',
                  font: 'inherit',
                  cursor: 'pointer',
                  padding: 0,
                  minHeight: 44,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                {HEADER_LABELS[col]}
                {sortKey === col ? (sortDir === 'asc' ? ' \u2191' : ' \u2193') : ''}
              </button>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sorted.map((row) => {
          const riskLevel = getRiskLevel(row.risk);
          const riskColor = getRiskColor(row.risk);
          const isSel = selected === row.id;
          return (
            <tr
              key={row.id}
              aria-current={isSel ? 'true' : undefined}
              tabIndex={0}
              onClick={() => {
                setSelected(row.id);
                onRowSelect?.(row);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  setSelected(row.id);
                  onRowSelect?.(row);
                }
              }}
              style={{
                cursor: 'pointer',
                background: isSel
                  ? 'var(--color-surface-hover, #334155)'
                  : 'transparent',
                borderBottom: '1px solid var(--color-border, #334155)',
              }}
            >
              <td style={{ padding: '8px' }} aria-label={row.name ? undefined : row.id}>
                {row.name ?? row.id}
              </td>
              <td style={{ padding: '8px', fontVariantNumeric: 'tabular-nums' }}>
                {row.latitude.toFixed(4)}
              </td>
              <td style={{ padding: '8px', fontVariantNumeric: 'tabular-nums' }}>
                {row.longitude.toFixed(4)}
              </td>
              <td
                style={{
                  padding: '8px',
                  textAlign: 'right',
                  color: riskColor,
                  fontWeight: 600,
                }}
              >
                <span aria-hidden="true">{(row.risk * 100).toFixed(0)}%</span>
                <span className="sr-only" style={srOnly}>
                  {riskLevel}
                </span>
              </td>
              <td
                style={{
                  padding: '8px',
                  textAlign: 'right',
                  color: 'var(--color-text-muted, #94a3b8)',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {row.confidence != null ? `${(row.confidence * 100).toFixed(0)}%` : '\u2014'}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
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

export default AoiTable;
