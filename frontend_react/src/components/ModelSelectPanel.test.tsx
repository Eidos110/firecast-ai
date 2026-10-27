/**
 * ModelSelectPanel — integration test (TAHAP D).
 *
 * Verifies the "Run Inference" happy + error paths:
 *   1. With the happy path: clicking Run Inference POSTs to /predict via
 *      the usePredict mutation, the store is updated with the result
 *      (setPrediction), and the ApiLogBox / store gets an "OK" entry.
 *   2. With the error path: a rejected predict mutation triggers the
 *      mock fallback and an ERR ApiLogBox entry.
 *
 * We mock `../api/client` body for `mockPredict` (the demo fallback) and
 * the `/predict` fetch wrapper, then mount the panel through a fresh
 * QueryClientProvider so useMutation's internal cache doesn't bleed
 * between tests.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';

import { renderWithQueryClient } from '../__tests__/test-utils';

// Mock the api client. Only the methods the panel touches are needed;
// the rest stay as no-op Jest stubs so React Query never hits the real URL.
vi.mock('../api/client', () => ({
  mockPredict: vi.fn((lat: number, lon: number) => ({
    risk_score: 0.55,
    risk_level: 'High',
    confidence: 0.78,
    confidence_interval: { p10: 0.47, p90: 0.63 },
    cnn_probability: 0.53,
    lgbm_probability: 0.57,
    shap_explanation: { top_features: [] },
    factors: null,
    model_agreement: 0.9,
    run_id: `mock-${lat}-${lon}`,
    latency_ms: 0,
    timestamp: new Date().toISOString(),
    status: 'DEMO',
  })),
  apiClient: {
    predict: vi.fn(),
    activateModel: vi.fn(),
    listModels: vi.fn(),
  },
}));

// Mock the useModels hook to return empty (so the panel uses fallback options).
vi.mock('../api/hooks', () => ({
  useModels: vi.fn(() => ({
    data: { models: {}, count: 0 },
    isLoading: false,
    isError: false,
  })),
  usePredict: () => usePredictImpl(),
  useActivateModel: () => ({
    isPending: false,
    mutate: vi.fn(),
  }),
}));

// `usePredict` needs to be a live React Query hook (not a static vi.fn),
// otherwise mutateAsync never resolves. We re-export from the real module
// but only "usePredict" + "useActivateModel" come from another vi.mock below.
//
// To keep tests simple, we use a manual `usePredictImpl` that satisfies the
// panel's `mutation.isPending` / `mutateAsync` contract supervised by react-query.
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { mockPredict } from '../api/client';

function usePredictImpl() {
  return useMutation({
    mutationFn: (payload: unknown) => (apiClient.predict as unknown as (p: unknown) => Promise<unknown>)(payload),
  });
}

import { ModelSelectPanel } from './ModelSelectPanel';
import { useInferenceStore } from '../store/inferenceStore';

beforeEach(() => {
  vi.clearAllMocks();
  // Reset the store so the selectedCell + previous prediction logs don't bleed.
  useInferenceStore.setState({
    selectedCell: { lat: -0.5, lon: 100.4 },
    prediction: null,
    apiLogs: [],
    runId: 'test-run',
    activeModel: null,
    latencyMs: null,
  });
});

describe('<ModelSelectPanel>', () => {
  it('prevents running when no cell is selected', () => {
    useInferenceStore.setState({ selectedCell: null });
    renderWithQueryClient(<ModelSelectPanel />);
    const btn = screen.getByRole('button', { name: /Run Inference/i });
    expect(btn).toBeDisabled();
    expect(screen.getByText(/click.*select a cell/i)).toBeInTheDocument();
  });

  it('updates store + pushes an OK log on a successful predict', async () => {
    (apiClient.predict as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      risk_score: 0.42,
      risk_level: 'Medium',
      confidence: 0.78,
      cnn_probability: 0.4,
      lgbm_probability: 0.44,
      shap_explanation: { top_features: [] },
      factors: null,
      model_agreement: 0.9,
      run_id: 'fc-20260730',
      latency_ms: 42,
      timestamp: '2026-07-30T10:00:00Z',
      status: 'success',
    });

    renderWithQueryClient(<ModelSelectPanel />);
    const btn = screen.getByRole('button', { name: /Run Inference/i });
    expect(btn).not.toBeDisabled();

    btn.click();
    await waitFor(() => {
      const s = useInferenceStore.getState();
      expect(s.prediction?.risk_score).toBeCloseTo(0.42);
      const okLogs = s.apiLogs.filter((l) => l.level === 'ok' && l.message.includes('200'));
      expect(okLogs).toHaveLength(1);
    });
  });

  it('falls back to mockPredict and logs an ERR entry when predict rejects', async () => {
    (apiClient.predict as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('API 500: model crash'));
    renderWithQueryClient(<ModelSelectPanel />);
    screen.getByRole('button', { name: /Run Inference/i }).click();

    await waitFor(() => {
      const s = useInferenceStore.getState();
      // mock fallback places a prediction
      expect(s.prediction?.status).toBe('DEMO');
      // The error ApiLogBox entry contains the failure message.
      const errLogs = s.apiLogs.filter((l) => l.level === 'err' && l.message.includes('model crash'));
      expect(errLogs).toHaveLength(1);
      // mockPredict was called with our selected cell coords.
      expect(mockPredict).toHaveBeenCalledWith(expect.any(Number), expect.any(Number));
    });
  });
});
