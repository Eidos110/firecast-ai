/**
 * MetricGrid tests — covers ROADMAP §3-L (skeleton while /predict pending).
 *
 * The component reads the global React Query client to know whether any
 * mutation is in-flight. We render it inside a real QueryClientProvider so
 * the behaviour under test matches production wiring exactly; we then start
 * a stale mutation manually via ``queryClient.getMutationCache()`` and
 * assert the placeholder skeletons are visible.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import i18n from 'i18next';

import { MetricGrid } from './MetricGrid';
import { useInferenceStore } from '../store/inferenceStore';
import { initI18n } from '../i18n/i18n';

function renderWithClient(ui: JSX.Element) {
  const client = new QueryClient({
    defaultOptions: {
      // Tests shouldn't retry — surfaces failures deterministically.
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('MetricGrid — skeleton state (ROADMAP §3-L)', () => {
  beforeEach(async () => {
    await initI18n();
    await i18n.changeLanguage('en');
    useInferenceStore.setState({
      prediction: null,
      activeModel: null,
    });
  });

  it('shows placeholder "—" rows when no prediction has been made', () => {
    renderWithClient(<MetricGrid />);
    // 4 cards each rendering "—" — confirms the idle, no-data path.
    const placeholders = screen.getAllByText('—');
    expect(placeholders.length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByTestId('metric-skeleton')).toBeNull();
  });

  it('renders skeletons while any mutation is in-flight', async () => {
    const { unmount } = renderWithClient(<MetricGrid />);
    // Manually mark a mutation as pending — this triggers useIsMutating
    // without needing the real /predict call to resolve.
    const skeletonNodes = screen.queryAllByTestId('metric-skeleton');
    // Initially there should be no skeletons.
    expect(skeletonNodes.length).toBe(0);

    // Render MetricGrid while a mutation is pending by pushing a fake
    // in-flight mutation directly through React Query's mutation cache.
    // The hook listens on the cache, so the next render flips the skeletons on.
    // We approximate that here by re-rendering with a fresh QueryClient that
    // *already* has a pending mutation; in a real app this happens when the
    // Header "Run Inference" button dispatches ``usePredict().mutate(...)``.
    unmount();

    const client = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    const mutationCache = client.getMutationCache();
    // Inject a fake pending mutation so useIsMutating returns 1.
    // The fake never resolves during the test — which is exactly what we
    // want, because we need the skeleton to stay visible.
    mutationCache.build(client, {
      mutationKey: ['fake', 'predict'],
      mutationFn: () => new Promise(() => {}),
    });
    // ``build`` alone doesn't start a mutation; we need to actually run it.
    const pendingMutation = mutationCache.find({ mutationKey: ['fake', 'predict'] });
    expect(pendingMutation).toBeTruthy();
    // Trigger mutation so its status becomes "pending".
    pendingMutation!.execute(undefined);

    render(
      <QueryClientProvider client={client}>
        <MetricGrid />
      </QueryClientProvider>,
    );
    await waitFor(() => {
      const skeletons = screen.queryAllByTestId('metric-skeleton');
      expect(skeletons.length).toBeGreaterThanOrEqual(4);
    });
  });
});
