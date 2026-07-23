import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Z_INDEX } from '../theme/tokens';
import { cn } from '../utils/cn';

export interface CommandItem {
  id: string;
  label: string;
  /** Optional hint shown on the right (e.g. keyboard shortcut). */
  hint?: string;
  /** Optional group/category for display grouping. */
  group?: string;
  /** Invoked when the command is selected. */
  onSelect: () => void;
  /** Optional substring match keywords for fuzzy search. */
  keywords?: string;
  /** Disable the item visually and keyboard-wise. */
  disabled?: boolean;
}

export interface CommandPaletteProps {
  commands: CommandItem[];
  /** Open state (controlled). */
  open: boolean;
  /** Callback to close the palette. */
  onClose: () => void;
  /** Placeholder text. */
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
}

/**
 * CommandPalette — keyboard-first command menu (Fase 4).
 *
 * Accessibility:
 * - Role `dialog` with `aria-modal`; focus moves to the search input on open.
 * - Mouse users can click items; keyboard users use Arrow Up/Down + Enter.
 * - Escape closes; Tab wraps within the list (focus trap is intentionally
 *   lightweight: Enter/Arrows are the documented interaction).
 */
export function CommandPalette({
  commands,
  open,
  onClose,
  placeholder = 'Type a command\u2026',
  ariaLabel = 'Command palette',
  className,
}: CommandPaletteProps): JSX.Element | null {
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const filtered = useMemo(() => {
    if (!query.trim()) return commands;
    const q = query.trim().toLowerCase();
    return commands.filter((c) => {
      const hay = `${c.label} ${c.keywords ?? ''} ${c.group ?? ''}`.toLowerCase();
      return hay.includes(q);
    });
  }, [query, commands]);

  useEffect(() => {
    if (open) {
      setQuery('');
      setActiveIndex(0);
      // Defer focus until after open animation.
      const t = setTimeout(() => inputRef.current?.focus(), 0);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [open]);

  useEffect(() => {
    if (activeIndex < 0 || activeIndex >= filtered.length) {
      setActiveIndex(Math.max(0, filtered.length - 1));
    }
  }, [filtered.length, activeIndex]);

  const choose = useCallback(
    (idx: number) => {
      const item = filtered[idx];
      if (!item || item.disabled) return;
      item.onSelect();
      onClose();
    },
    [filtered, onClose]
  );

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => Math.min(filtered.length - 1, i + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => Math.max(0, i - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      choose(activeIndex);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  if (!open) return null;

  return (
    <div
      className={cn('command-palette-overlay', className)}
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel}
      tabIndex={-1}
      onKeyDown={onKeyDown}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: Z_INDEX.commandPalette,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        padding: '12vh 16px 0',
      }}
    >
      <div
        role="complementary"
        style={{
          width: '100%',
          maxWidth: 560,
          background: 'var(--color-surface, #1e293b)',
          borderRadius: 'var(--radius-lg, 12px)',
          boxShadow: 'var(--shadow-lg)',
          overflow: 'hidden',
          color: 'var(--color-text, #f1f5f9)',
        }}
      >
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActiveIndex(0);
          }}
          placeholder={placeholder}
          aria-label={placeholder}
          style={{
            width: '100%',
            boxSizing: 'border-box',
            border: 'none',
            outline: 'none',
            padding: '14px 16px',
            fontSize: '0.9375rem',
            background: 'transparent',
            color: 'inherit',
            borderBottom: '1px solid var(--color-border, #334155)',
          }}
        />
        <ul ref={listRef} role="listbox" aria-activedescendant={filtered[activeIndex]?.id}>
          {filtered.length === 0 ? (
            <li style={{ padding: 16, color: 'var(--color-text-muted, #94a3b8)' }}>
              No matching commands.
            </li>
          ) : (
            filtered.map((item, idx) => {
              const isActive = idx === activeIndex;
              return (
                <li
                  key={item.id}
                  id={item.id}
                  role="option"
                  aria-selected={isActive}
                  tabIndex={-1}
                  onMouseMove={() => setActiveIndex(idx)}
                  onClick={() => choose(idx)}
                  style={{
                    padding: '9px 16px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    cursor: item.disabled ? 'not-allowed' : 'pointer',
                    opacity: item.disabled ? 0.5 : 1,
                    background: isActive ? 'var(--color-surface-hover, #334155)' : 'transparent',
                  }}
                >
                  <span style={{ flex: 1 }}>
                    {item.group && (
                      <span
                        style={{
                          fontSize: '0.6875rem',
                          color: 'var(--color-text-muted, #94a3b8)',
                          textTransform: 'uppercase',
                          letterSpacing: '0.04em',
                          marginRight: 6,
                        }}
                      >
                        {item.group}
                      </span>
                    )}
                    {item.label}
                  </span>
                  {item.hint && (
                    <kbd
                      style={{
                        fontSize: '0.6875rem',
                        color: 'var(--color-text-muted, #94a3b8)',
                        background: 'var(--color-background, #0f172a)',
                        border: '1px solid var(--color-border, #334155)',
                        borderRadius: 4,
                        padding: '1px 5px',
                      }}
                    >
                      {item.hint}
                    </kbd>
                  )}
                </li>
              );
            })
          )}
        </ul>
      </div>
    </div>
  );
}

export default CommandPalette;
