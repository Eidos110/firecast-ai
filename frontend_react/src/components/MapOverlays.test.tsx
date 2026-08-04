/**
 * MapOverlays — unit tests (TAHAP D).
 *
 * ROADMAP §3-W2 added ``useIsMutating`` for the sticky AOI progress bar —
 * the hook requires a QueryClientProvider ancestor. We wrap every render
 * with a fresh client per test so mutations started by other components
 * don't bleed between tests.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { MapOverlays } from './MapOverlays';

function wrap(ui: JSX.Element) {
  const client = new QueryClient();
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('<MapOverlays>', () => {
  it('renders the coordinate readout with provided lat / lon', () => {
    wrap(<MapOverlays coordReadout={{ lat: -1.2345, lon: 113.678, zoom: 7 }} />);
    expect(screen.getByText(/EPSG:4326/i)).toBeInTheDocument();
    expect(screen.getByText(/LAT/i)).toBeInTheDocument();
    expect(screen.getByText(/-1\.2345/)).toBeInTheDocument();
    expect(screen.getByText(/113\.6780/)).toBeInTheDocument();
  });

  it('falls back to numeric default when coordReadout is null', () => {
    wrap(<MapOverlays coordReadout={null} />);
    expect(screen.getByText(/-1\.8000/)).toBeInTheDocument();
    expect(screen.getByText(/113\.5000/)).toBeInTheDocument();
  });

  it('accepts a custom region label and shows it in the zoom pill', () => {
    wrap(<MapOverlays coordReadout={{ lat: -5, lon: 100, zoom: 5 }} regionLabel="Aceh" />);
    // The pill renders "Zoom level: 5 · Aceh" — check both fragments are present.
    expect(screen.getByText(/Zoom/i).parentElement ?? screen.getByText(/Zoom/i)).toBeInTheDocument();
    expect(screen.getByText(/Aceh/)).toBeInTheDocument();
  });

  it('uses a custom EPSG code in the readout string', () => {
    wrap(<MapOverlays coordReadout={null} epsg={3857} />);
    expect(screen.getByText(/EPSG:3857/i)).toBeInTheDocument();
    expect(screen.queryByText(/EPSG:4326/i)).not.toBeInTheDocument();
  });
});
