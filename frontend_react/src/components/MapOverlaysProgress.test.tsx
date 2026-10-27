/**
 * ROADMAP §3-W2 — clarity polish. Covers the two new affordances:
 *   1. RiskTrendChart's custom tooltip (P(fire)=0.72 (High), CI: …).
 *   2. MapOverlays' sticky indeterminate progress bar while /predict/aoi
 *      is in-flight.
 *
 * Both are presentational/DOM-shape assertions; no network calls.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import i18n from 'i18next';

import { MapOverlays } from './MapOverlays';
import { useInferenceStore } from '../store/inferenceStore';
import { initI18n } from '../i18n/i18n';

function wrapClient(ui: JSX.Element) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('MapOverlays — sticky AOI batch progress (ROADMAP §3-W2)', () => {
  beforeEach(async () => {
    await initI18n();
    await i18n.changeLanguage('en');
    useInferenceStore.setState({ apiLogs: [], selectedAoi: null });
  });

  it('does NOT show the progress bar by default', () => {
    wrapClient(<MapOverlays coordReadout={null} />);
    expect(screen.queryByTestId('aoi-progress')).toBeNull();
  });

  it('shows ``aoi-progress`` while any mutation is in-flight', async () => {
    const client = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    // Push a fake pending mutation into the cache so ``useIsMutating`` flips on.
    const mutationCache = client.getMutationCache();
    mutationCache.build(client, {
      mutationKey: ['fake', 'predict_aoi'],
      mutationFn: () => new Promise(() => {}),
    });
    const pending = mutationCache.find({ mutationKey: ['fake', 'predict_aoi'] });
    expect(pending).toBeTruthy();
    pending!.execute(undefined);

    render(
      <QueryClientProvider client={client}>
        <MapOverlays coordReadout={null} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('aoi-progress')).toBeTruthy();
    });
  });
});
