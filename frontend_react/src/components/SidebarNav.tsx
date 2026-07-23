import { useState } from 'react';
import { cn } from '../utils/cn';

export interface SidebarNavItem {
  id: string;
  label: string;
  /** Optional emoji/icon prefix. */
  icon?: string;
  /** Invoked when the item is activated. */
  onSelect: () => void;
  /** Whether this item is the active tab/view. */
  active?: boolean;
  /** Optional numeric badge (e.g. pending batch count). */
  badge?: number;
}

export interface SidebarNavProps {
  items: SidebarNavItem[];
  /** Default collapsed on small screens. */
  defaultCollapsed?: boolean;
  /** Accessible label for the nav region. */
  ariaLabel?: string;
  className?: string;
}

/**
 * SidebarNav — collapsible primary navigation (Fase 4).
 *
 * Accessibility:
 * - `<nav role="navigation">` with an explicit aria-label.
 * - Collapsible affordance is a real `<button aria-expanded>`.
 * - Each item is a `<button>` with a 44px+ touch target.
 * - ARIA badges announce their counts via aria-label.
 */
export function SidebarNav({
  items,
  defaultCollapsed = false,
  ariaLabel = 'Primary navigation',
  className,
}: SidebarNavProps): JSX.Element {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <nav
      role="navigation"
      aria-label={ariaLabel}
      className={cn('fc-sidebar-nav', collapsed && 'fc-sidebar-nav--collapsed', className)}
      style={{
        width: collapsed ? 56 : 220,
        transition: 'width 200ms cubic-bezier(0.4,0,0.2,1)',
        background: 'var(--color-surface, #1e293b)',
        borderRight: '1px solid var(--color-border, #334155)',
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
        height: '100%',
        color: 'var(--color-text, #f1f5f9)',
      }}
    >
      <button
        type="button"
        aria-expanded={!collapsed}
        aria-controls="sidebar-list"
        onClick={() => setCollapsed((c) => !c)}
        aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
        style={{
          padding: 10,
          minHeight: 44,
          minWidth: 44,
          background: 'none',
          border: 'none',
          color: 'inherit',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          borderBottom: '1px solid var(--color-border, #334155)',
        }}
      >
        {collapsed ? '\u203A' : '\u2039'}
      </button>
      <ul id="sidebar-list" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {items.map((item) => {
          const accessibleName =
            item.badge != null
              ? `${item.label} (${item.badge})`
              : item.label;
          return (
            <li key={item.id} style={{ borderBottom: '1px solid var(--color-border, #334155)' }}>
              <button
                type="button"
                onClick={item.onSelect}
                aria-current={item.active ? 'page' : undefined}
                title={collapsed ? item.label : undefined}
                aria-label={accessibleName}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: collapsed ? '12px 8px' : '12px 14px',
                  minHeight: 44,
                  background: item.active
                    ? 'var(--color-surface-hover, #334155)'
                    : 'transparent',
                  color: item.active
                    ? 'var(--color-text, #f1f5f9)'
                    : 'var(--color-text-secondary, #cbd5e1)',
                  border: 'none',
                  borderLeft: item.active
                    ? '3px solid var(--color-accent, #f59e0b)'
                    : '3px solid transparent',
                  cursor: 'pointer',
                  font: 'inherit',
                  textAlign: 'left',
                  justifyContent: collapsed ? 'center' : 'flex-start',
                }}
              >
                {item.icon && (
                  <span aria-hidden="true" style={{ fontSize: 16, flexShrink: 0 }}>
                    {item.icon}
                  </span>
                )}
                {!collapsed && (
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.label}
                  </span>
                )}
                {item.badge != null && !collapsed && (
                  <span
                    aria-hidden="true"
                    style={{
                      fontSize: '0.6875rem',
                      background: 'var(--color-accent, #f59e0b)',
                      color: '#1f1300',
                      borderRadius: 'var(--radius-full, 9999px)',
                      padding: '1px 6px',
                      fontWeight: 600,
                    }}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export default SidebarNav;
