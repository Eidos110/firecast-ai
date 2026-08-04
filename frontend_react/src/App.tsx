/**
 * FireCast Engineer Console SPA — root component (V4 layout, decoupled from
 * Streamlit).
 *
 * Layout:
 *   ┌─────────────────────────────────┐
 *   │  TOPBAR (48)                    │
 *   ├─────────┬──────────┬─────────────┤
 *   │ SIDEBAR │   MAP    │ RIGHT DIAGN │
 *   │ 280px   │  flex-1  │   320px     │
 *   ├─────────┴──────────┴─────────────┤
 *   │  BOTTOM (56) Timeline scrubber   │
 *   └───────────────────────────────────┘
 *
 * Responsive behaviour: at ≤900px the fixed side columns collapse into
 * drawers (uiStore.leftOpen / rightOpen) toggled from the Header hamburger
 * buttons; the map pane takes the full row. The desktop grid is untouched —
 * drawers are only mounted on small screens.
 *
 * Boot order at main.tsx: initI18n() → mount <App />. QueryClientProvider
 * powers /predict, /api/models, /geo/* request retries. Global overlays:
 * ToastViewport (top-right) + CommandPalette (Ctrl+K) live here so every
 * pane can raise them through the shared stores.
 */
import { useEffect } from 'react';
import { useTheme } from './theme/useTheme';
import { Header } from './components/Header';
import { LeftSidebar } from './components/LeftSidebar';
import { MapArea } from './components/MapArea';
import { RightDiagnostic } from './components/RightDiagnostic';
import { TimelineScrubber } from './components/TimelineScrubber';
import { ToastViewport } from './components/ToastViewport';
import { CommandPalette } from './components/CommandPalette';
import { useIsMobile } from './hooks/useIsMobile';
import { useUiStore } from './store/uiStore';

export function App(): JSX.Element {
  const { resolved } = useTheme('dark');
  void resolved; // applied via documentElement attribute inside useTheme
  const isMobile = useIsMobile(900);
  const leftOpen = useUiStore((s) => s.leftOpen);
  const rightOpen = useUiStore((s) => s.rightOpen);
  const setLeftOpen = useUiStore((s) => s.setLeftOpen);
  const setRightOpen = useUiStore((s) => s.setRightOpen);
  const togglePalette = useUiStore((s) => s.togglePalette);
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen);
  const mode = useUiStore((s) => s.mode);

  // Ctrl+K / Cmd+K opens the command palette; Escape closes it.
  // Skipped entirely in Analyst mode (ROADMAP §3-W3): the persona should not
  // surface developer-centric shortcuts to non-engineers.
  useEffect(() => {
    if (mode === 'demo' || mode === 'analyst') return undefined;
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        togglePalette();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [togglePalette, mode]);

  // Close drawers when crossing back to desktop.
  useEffect(() => {
    if (!isMobile) {
      setLeftOpen(false);
      setRightOpen(false);
    }
  }, [isMobile, setLeftOpen, setRightOpen]);

  // Per-mode shape switches (ROADMAP §3-W3):
  //   engineer — full chrome (left sidebar + map + right diagnostic + palette).
  //   analyst  — hide RightDiagnostic and CommandPalette; map area is free
  //              to switch to a table/CSV view in follow-up work. The grid
  //              still has 2 columns so the layout doesn't collapse mid-resize.
  //   demo     — read-only demo: hide RightDiagnostic AND the API-key/model
  //              panels (the former is mounted in LeftSidebar so we hide the
  //              whole sidebar too — Demo persona is meant for projection).
  const showLeftSidebar = mode !== 'demo';
  const showRightDiagnostic = mode === 'engineer';

  return (
    <div
      className="fc-app"
      data-mode={mode}
      style={{
        display: 'grid',
        height: '100vh',
        gridTemplateRows: '48px 1fr 56px',
        gridTemplateColumns: isMobile
          ? '1fr'
          : showLeftSidebar && showRightDiagnostic
            ? '280px 1fr 320px'
            : showLeftSidebar
              ? '280px 1fr'
              : showRightDiagnostic
                ? '1fr 320px'
                : '1fr',
        gridTemplateAreas: isMobile
          ? '"top" "main" "bottom"'
          : showLeftSidebar && showRightDiagnostic
            ? '"top top top" "left main right" "bottom bottom bottom"'
            : showLeftSidebar
              ? '"top top" "left main" "bottom bottom"'
              : showRightDiagnostic
                ? '"top top" "main right" "bottom bottom"'
                : '"top" "main" "bottom"',
      }}
    >
      <div style={{ gridArea: 'top' }}>
        <Header isMobile={isMobile} />
      </div>
      {!isMobile && showLeftSidebar && (
        <div style={{ gridArea: 'left' }}>
          <LeftSidebar />
        </div>
      )}
      <div style={{ gridArea: 'main', display: 'flex', overflow: 'hidden' }}>
        <MapArea />
      </div>
      {!isMobile && showRightDiagnostic && (
        <div style={{ gridArea: 'right' }}>
          <RightDiagnostic />
        </div>
      )}
      <div style={{ gridArea: 'bottom' }}>
        <TimelineScrubber />
      </div>

      {/* Mobile drawers — respects persona modes (both hidden in demo). */}
      {isMobile && (
        <>
          {(leftOpen || rightOpen) && (
            <div
              className="fc-drawer-backdrop"
              aria-hidden
              onClick={() => {
                setLeftOpen(false);
                setRightOpen(false);
              }}
            />
          )}
          {showLeftSidebar && (
            <div
              className={`fc-drawer fc-drawer--left${leftOpen ? ' fc-drawer--open' : ''}`}
              role="dialog"
              aria-modal="true"
              aria-label="Configuration drawer"
            >
              <LeftSidebar />
            </div>
          )}
          {showRightDiagnostic && (
            <div
              className={`fc-drawer fc-drawer--right${rightOpen ? ' fc-drawer--open' : ''}`}
              role="dialog"
              aria-modal="true"
              aria-label="Diagnostic drawer"
            >
              <RightDiagnostic />
            </div>
          )}
        </>
      )}

      {/* Global overlays — palette only in Engineer mode (analyst & demo get
          toasts; the dev tool picker would just confuse them). */}
      <ToastViewport />
      {mode === 'engineer' && <CommandPalette onRequestClose={() => setPaletteOpen(false)} />}
    </div>
  );
}

export default App;
