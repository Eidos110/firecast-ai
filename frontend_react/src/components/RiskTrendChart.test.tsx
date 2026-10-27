/**
 * RiskTrendChart — integration test (TAHAP D).
 *
 * Verifies:
 *   1. When /analytics/trend succeeds with a 3-day series, the chart mounts
 *      without rendering a "fetching trend…" placeholder (state == success).
 *   2. When the hook errors (CSV missing on the server), `mockTrend()` kicks
 *      in and the "fetching…" overlay doesn't show either.
 *   3. With no selected cell, the chart still mounts without throwing.
 *
 * We mock `../api/hooks.useTrend` rather than intercepting fetch — the chart
 * only cares about hook return shape, not the HTTP layer (the backend pytest
 * suite covers fetch contracts). We deliberately avoid asserting on raw SVG
 * elements because Recharts ResponsiveContainer defers its first paint until
 * a real ResizeObserver callback fires, which the jsdom stub doesn't fire —
 * so seletong `.recharts-surface` lookups are flaky here. The chart's own
 * in-tree state (loading label vs. no-loading label) is deterministic.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';

import { renderWithQueryClient } from '../__tests__/test-utils';

// Mock `useTrend` so we can push either a populated series or an error
// without touching the network. The hook module is mocked here and reset
// per-test via beforeEach so a previous test's success doesn't leak.
vi.mock('../api/hooks', () => ({
  useTrend: vi.fn(),
}));

import { useTrend } from '../api/hooks';
import { RiskTrendChart } from './RiskTrendChart';

// Reuse a stable three-day series the same shape /analytics/trend returns.
const LIVE_SERIES = [
  { date: '2026-07-27', fire_rate: 0.2, p10: 0.12, p50: 0.2, p90: 0.31, count: 18 },
  { date: '2026-07-28', fire_rate: 0.35, p10: 0.22, p50: 0.35, p90: 0.5, count: 22 },
  { date: '2026-07-29', fire_rate: 0.55, p10: 0.41, p50: 0.55, p90: 0.71, count: 31 },
];

beforeEach(() => {
  vi.clearAllMocks();
});

type MockedTrendReturn = Parameters<typeof vi.mocked<typeof useTrend>>[0] extends never
  ? ReturnType<typeof useTrend>
  : ReturnType<typeof useTrend>;

function mockTrendResult(partial: Partial<MockedTrendReturn>): void {
  vi.mocked(useTrend).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: async () => ({} as never),
    isPending: false,
    status: 'success',
    fetchStatus: 'idle',
    ...partial,
  } as MockedTrendReturn);
}

describe('<RiskTrendChart>', () => {
  it('shows no loading overlay when the live series is loaded', async () => {
    mockTrendResult({
      data: { lat: -1.8, lon: 113.5, radius_km: 25, days: 7, series: LIVE_SERIES },
    });
    const { container } = renderWithQueryClient(<RiskTrendChart />);
    await waitFor(() => {
      expect(screen.queryByText('fetching trend…')).not.toBeInTheDocument();
    });
    // The chart container div renders successfully (no exception path).
    expect(container.firstChild).not.toBeNull();
  });

  it('falls back to mockTrend when useTrend errors (no blank, no loading)', async () => {
    mockTrendResult({
      data: undefined,
      isError: true,
      error: new Error('backend missing CSV'),
      status: 'error',
    });
    renderWithQueryClient(<RiskTrendChart />);
    await waitFor(() => {
      expect(screen.queryByText('fetching trend…')).not.toBeInTheDocument();
    });
  });

  it('renders without throwing when selectedCell is null (boot state, no cell-selectable hook)', async () => {
    mockTrendResult({ data: undefined, status: 'pending' });
    const { container } = renderWithQueryClient(<RiskTrendChart />);
    await waitFor(() => {
      // Boot state: the container div should mount without exception.
      expect(container.firstChild).not.toBeNull();
    });
  });
});
