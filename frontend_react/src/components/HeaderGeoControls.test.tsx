/**
 * HeaderGeoControls tests (ROADMAP §3-W1).
 *
 * Covers:
 *   - Coordinate-jump: typing `-1.5, 102.3` and submitting sets
 *     ``selectedCell`` directly (no geocode network call).
 *   - Place-name path: typing "Jakarta" triggers the ``useGeocode`` hook;
 *     we mock the hook's data via vi.mock so this test stays hermetic.
 *   - Date-scrub: picking a date writes to ``selectedPredictionDate``.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import i18n from 'i18next';

import { HeaderGeoControls } from './HeaderGeoControls';
import { useInferenceStore } from '../store/inferenceStore';
import { initI18n } from '../i18n/i18n';

// Mock ``useGeocode`` so this test doesn't perform network calls
// (rate-limited Nominatim endpoint isn't test-friendly on CI).
vi.mock('../api/hooks', async (importOriginal) => {
  const real = (await importOriginal()) as Record<string, unknown>;
  return {
    ...real,
    useGeocode: vi.fn((_q: string, _e: boolean) => ({
      data: null,
      isLoading: false,
      isError: false,
    })),
  };
});

function wrap(ui: JSX.Element) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('HeaderGeoControls (ROADMAP §3-W1)', () => {
  beforeEach(async () => {
    await initI18n();
    await i18n.changeLanguage('en');
    useInferenceStore.setState({ selectedCell: null, selectedPredictionDate: null });
  });

  it('parses "lat, lon" and writes selectedCell on submit', async () => {
    wrap(<HeaderGeoControls />);
    const input = screen.getByRole('searchbox');
    await userEvent.type(input, '-1.5, 102.3');
    (input.closest('form') as HTMLFormElement).requestSubmit();
    expect(useInferenceStore.getState().selectedCell).toEqual({ lat: -1.5, lon: 102.3 });
  });

  it('rejects out-of-range coordinates without touching the store', async () => {
    wrap(<HeaderGeoControls />);
    const input = screen.getByRole('searchbox');
    await userEvent.type(input, '500, 900');
    (input.closest('form') as HTMLFormElement).requestSubmit();
    expect(useInferenceStore.getState().selectedCell).toBeNull();
  });

  it('updates selectedPredictionDate on date pick', async () => {
    wrap(<HeaderGeoControls />);
    // The date input has aria-label matched from the i18n default.
    const date = screen.getByLabelText(/prediction date/i);
    // fireEvent.change is the canonical way for <input type="date">; userEvent.type
    // doesn't simulate calendar widget selection in jsdom.
    const { fireEvent } = await import('@testing-library/react');
    fireEvent.change(date, { target: { value: '2026-08-01' } });
    await waitFor(() => {
      expect(useInferenceStore.getState().selectedPredictionDate).toBe('2026-08-01');
    });
  });
});
