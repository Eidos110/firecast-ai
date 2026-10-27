/**
 * CommandPalette — Ctrl+K quick-action launcher (engineer-console style).
 *
 * Actions: toggle each map layer, jump to layer sections, switch model tier,
 * run inference, cycle theme, switch language. Filter is plain substring on
 * the lower-cased title (fast, locale-aware enough for an 8-action list).
 * Arrow-Up/Down move selection, Enter executes, Escape closes. The palette
 * is listbox/buttons (not combobox) so focus stays on the input while mouse
 * + keys both work.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useUiStore } from '../store/uiStore';
import { useInferenceStore, type LayerId } from '../store/inferenceStore';
import { useTheme } from '../theme/useTheme';
import { setLang, getCurrentLang } from '../i18n/i18n';

interface Action {
  id: string;
  title: string;
  hint?: string;
  run: () => void;
}

export interface CommandPaletteProps {
  onRequestClose: () => void;
}

export function CommandPalette({ onRequestClose }: CommandPaletteProps): JSX.Element | null {
  const open = useUiStore((s) => s.paletteOpen);
  if (!open) return null;
  return <PaletteBody onRequestClose={onRequestClose} />;
}

function PaletteBody({ onRequestClose }: CommandPaletteProps): JSX.Element {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const layers = useInferenceStore((s) => s.layers);
  const toggleLayer = useInferenceStore((s) => s.toggleLayer);
  const { cycleTheme } = useTheme();

  const actions = useMemo<Action[]>(() => {
    const list: Action[] = [];
    for (const layer of layers) {
      list.push({
        id: `layer:${layer.id}`,
        title: `${layer.active ? '◉' : '○'} ${t('spa.palette.toggle_layer')} — ${layer.label}`,
        hint: layer.active ? 'on' : 'off',
        run: () => toggleLayer(layer.id as LayerId),
      });
    }
    list.push({
      id: 'theme:cycle',
      title: `◐ ${t('spa.palette.cycle_theme')}`,
      hint: 'dark→light→auto',
      run: () => cycleTheme(),
    });
    list.push({
      id: 'lang:switch',
      title: `⇄ ${t('spa.palette.switch_language')}`,
      hint: getCurrentLang()==='en' ? 'EN→ID' : 'ID→EN',
      run: () => setLang(getCurrentLang() === 'en' ? 'id' : 'en'),
    });
    return list;
  }, [layers, toggleLayer, cycleTheme, t]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return actions;
    return actions.filter((a) => a.title.toLowerCase().includes(q));
  }, [actions, query]);

  // Focus the input on mount.
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Reset selection when the filter changes.
  useEffect(() => {
    setActiveIdx(0);
  }, [query]);

  const execute = (idx: number) => {
    const action = filtered[idx];
    if (!action) return;
    action.run();
    onRequestClose();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onRequestClose();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      execute(activeIdx);
    }
  };

  return (
    <div className="fc-palette-backdrop" onClick={onRequestClose}>
      <div
        className="fc-palette"
        role="dialog"
        aria-modal="true"
        aria-label={t('spa.palette.label')}
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          className="fc-palette-input"
          type="text"
          placeholder={t('spa.palette.placeholder')}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          aria-label={t('spa.palette.label')}
        />
        <div className="fc-palette-list" role="listbox" aria-label={t('spa.palette.label')}>
          {filtered.length === 0 && (
            <div className="fc-palette-empty">{t('spa.palette.empty')}</div>
          )}
          {filtered.map((a, i) => (
            <button
              key={a.id}
              type="button"
              role="option"
              aria-selected={i === activeIdx}
              className="fc-palette-item"
              onMouseEnter={() => setActiveIdx(i)}
              onClick={() => execute(i)}
            >
              <span>{a.title}</span>
              {a.hint && <span className="fc-palette-hint">{a.hint}</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default CommandPalette;
