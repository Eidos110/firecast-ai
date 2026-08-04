/**
 * LeftSidebar — width-280 column containing Layers + Model Cfg + Filters.
 * Composite, single component kept slim so App.tsx reads declaratively.
 */
import { LayerControlPanel, RiskLegend } from './LayerControlPanel';
import { ModelSelectPanel } from './ModelSelectPanel';
import { FiltersPanel } from './FiltersPanel';
import { ApiKeyPanel } from './ApiKeyPanel';

export function LeftSidebar(): JSX.Element {
  return (
    <aside
      aria-label="Configuration sidebar"
      style={{
        width: 280,
        height: '100%',
        background: 'var(--color-surface)',
        borderRight: '1px solid var(--color-border)',
        padding: 10,
        overflowY: 'auto',
        overflowX: 'hidden',
        scrollbarWidth: 'thin',
      }}
    >
      <ApiKeyPanel />
      <LayerControlPanel />
      <ModelSelectPanel />
      <FiltersPanel />
      <RiskLegend />
    </aside>
  );
}

export default LeftSidebar;
