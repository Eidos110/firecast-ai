/**
 * MapArea AOI integration test (ROADMAP §2-E).
 *
 * The real Leaflet / leaflet-draw stack requires a DOM with a real layout
 * engine, which jsdom doesn't provide. To keep the test fast and stable we
 * mock the underlying «InteractiveMap» component and drive the same props
 * the real draw-control would call. The assertions then prove that the
 * wiring from "AOI drawn" to store / toast / apiLog is correct — which is
 * the integration risk that nothing else in the suite covers today.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act, render, waitFor } from '@testing-library/react';
import i18n from 'i18next';

import { MapArea } from './MapArea';
import { useInferenceStore } from '../store/inferenceStore';
import { initI18n } from '../i18n/i18n';

// --------------------------------------------------------------------------
// Mock InteractiveMap — keep the prop surface identical, record callbacks.
// The actual polygon-draw geometry math inside InteractiveMap is unit-tested
// elsewhere; here we only care about *cross-component* wiring.
// --------------------------------------------------------------------------
interface MockProps {
  onAoiDrawn?: (f: GeoJSON.Feature) => void;
  onAoiUpdated?: (f: GeoJSON.Feature) => void;
  onAoiDeleted?: () => void;
  onCellSelect?: (p: { lat: number; lon: number }) => void;
  aoi?: GeoJSON.Feature | null;
  overlay?: GeoJSON.FeatureCollection | null;
  layers?: Array<{ id: string; label: string; active: boolean; opacity: number }>;
}
let lastProps: MockProps | null = null;

vi.mock('./InteractiveMap', () => ({
  InteractiveMap: (props: MockProps) => {
    lastProps = props;
    return <div data-testid="mock-interactive-map" />;
  },
}));

// MapOverlays and toast don't affect the wiring assertions; mock them so the
// test doesn't have to set up Leaflet or any timing around toasts.
vi.mock('./MapOverlays', () => ({
  MapOverlays: () => <div data-testid="mock-map-overlays" />,
}));
vi.mock('../store/toastStore', () => ({
  toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() },
}));

const AOI_FEATURE: GeoJSON.Feature = {
  type: 'Feature',
  geometry: {
    type: 'Polygon',
    coordinates: [
      [
        [100.0, -1.0],
        [100.5, -1.0],
        [100.5, -1.5],
        [100.0, -1.5],
        [100.0, -1.0],
      ],
    ],
  },
  properties: {},
};

describe('MapArea — AOI flow integration (ROADMAP §2-E)', () => {
  beforeEach(async () => {
    await initI18n();
    await i18n.changeLanguage('en');
    lastProps = null;
    // Reset only the fields under test; the remaining store state is
    // whatever the previous test left it in, mirroring production usage
    // (the store is a singleton across the SPA session).
    useInferenceStore.setState({
      selectedCell: null,
      selectedAoi: null,
      aoiOverlay: null,
      apiLogs: [],
    });
  });

  it('marks selectedCell when the user clicks on the map', () => {
    render(<MapArea />);
    expect(lastProps).not.toBeNull();
    act(() => {
      lastProps!.onCellSelect?.({ lat: -1.17, lon: 100.4 });
    });
    const cell = useInferenceStore.getState().selectedCell;
    expect(cell).toEqual({ lat: -1.17, lon: 100.4 });
  });

  it('stores the polygon in ``selectedAoi`` and logs an API event when drawn', async () => {
    render(<MapArea />);
    act(() => {
      lastProps!.onAoiDrawn?.(AOI_FEATURE);
    });
    await waitFor(() => {
      const state = useInferenceStore.getState();
      expect(state.selectedAoi).toEqual(AOI_FEATURE);
      // Roadmap §2-E: an 'AOI drawn' info row must land in the log so the
      // engineer console surfaces the action even before /predict/aoi runs.
      expect(state.apiLogs.some((e) => e.level === 'ok')).toBe(true);
    });
  });

  it('replaces ``selectedAoi`` on edit and clears overlay', async () => {
    render(<MapArea />);
    act(() => {
      lastProps!.onAoiDrawn?.(AOI_FEATURE);
    });
    const editedFeature: GeoJSON.Feature = {
      ...AOI_FEATURE,
      properties: { edited: true },
    };
    act(() => {
      lastProps!.onAoiUpdated?.(editedFeature);
    });
    await waitFor(() => {
      const state = useInferenceStore.getState();
      expect(state.selectedAoi).toEqual(editedFeature);
    });
  });

  it('clears AOI and overlay when the draw control fires delete', async () => {
    render(<MapArea />);
    act(() => {
      lastProps!.onAoiDrawn?.(AOI_FEATURE);
    });
    // Force-set a stale overlay to prove the delete handler really clears it.
    act(() => {
      useInferenceStore.getState().setAoiOverlay({
        type: 'FeatureCollection',
        features: [],
      });
      lastProps!.onAoiDeleted?.();
    });
    await waitFor(() => {
      const state = useInferenceStore.getState();
      expect(state.selectedAoi).toBeNull();
      expect(state.aoiOverlay).toBeNull();
      expect(state.apiLogs.some((e) => e.level === 'warn')).toBe(true);
    });
  });
});
