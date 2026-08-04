/**
 * FireCast react-query hooks — thin wrappers over `apiClient` so the
 * SPA can call endpoints with proper caching, retries and error binding.
 *
 * Design notes (TAHAP D):
 *   - All query keys are namespaced under `['firecast', <resource>]`. A small
 *     `queryKeys` factory is exported for invalidation by callers.
 *   - Mutations (`usePredict`, `usePredictAoi`, `useActivateModel`) deliberately
 *     DON'T auto-invalidate a list query — the caller decides whether to
 *     `qc.invalidateQueries({ queryKey: queryKeys.models })` to avoid
 *     accidental refetch storms when /predict runs every time the horizon
 *     scrubber ticks.
 *   - Error surfaces to caller via `mutation.error` — wrapped components
 *     pipe `mutation.error` into the inference store's `pushApiLog` so the
 *     V4 ApiLogBox shows colour-coded WARN/ERR rows (PLAN §7 risk register:
 *     demo mode default can hide failure).
 *   - `useTrend` returns a derived series already shaped for Recharts
 *     (`{day, fire_rate, p10, p50, p90}`) so the chart component stays dumb.
 */
import { useMutation, useQuery } from '@tanstack/react-query';

import { apiClient, type PredictAoiPayload, type PredictPayload } from './client';
import type { PredictionResult } from '../store/inferenceStore';

export const queryKeys = {
  models: () => ['firecast', 'models'] as const,
  locations: () => ['firecast', 'geo', 'locations'] as const,
  geocode: (q: string) => ['firecast', 'geo', 'geocode', q] as const,
  trend: (lat: number, lon: number, days: number, radiusKm: number) =>
    ['firecast', 'analytics', 'trend', lat, lon, days, radiusKm] as const,
  health: () => ['firecast', 'health'] as const,
};

/** Cached read of `/api/models/` (X-API-Key gated server-side). */
export function useModels(enabled = true) {
  return useQuery({
    queryKey: queryKeys.models(),
    queryFn: () => apiClient.listModels(),
    enabled,
    // 5 min freshness avoids hammering the gated endpoint when the user
    // repeatedly opens the model dropdown.
    staleTime: 5 * 60 * 1000,
  });
}

/** Cached read of `/geo/locations` (public-read; fully cacheable). */
export function useLocations(enabled = true) {
  return useQuery({
    queryKey: queryKeys.locations(),
    queryFn: () => apiClient.listLocations(),
    enabled,
    // Public-read + static 378-entry file, cache aggressively for the session.
    staleTime: 30 * 60 * 1000,
  });
}

/** Geocode — keyed by query string; client-side debounce handled by caller. */
export function useGeocode(query: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.geocode(query),
    queryFn: () => apiClient.geocode(query),
    enabled: enabled && query.trim().length > 0,
    staleTime: 10 * 60 * 1000,
  });
}

/** Health-check ping (used by Header status LED). */
export function useHealth(enabled = true) {
  return useQuery({
    queryKey: queryKeys.health(),
    queryFn: () => apiClient.health(),
    enabled,
    // Poll health every 30s so the LED fades to red within ~30s of API loss.
    refetchInterval: 30 * 1000,
    staleTime: 25 * 1000,
  });
}

/** `/analytics/trend` — 7-day p10/p50/p90 series for the right diagnostic. */
export function useTrend(
  lat: number | null,
  lon: number | null,
  days = 7,
  radiusKm = 25,
  enabled = true,
) {
  return useQuery({
    queryKey:
      lat != null && lon != null
        ? queryKeys.trend(lat, lon, days, radiusKm)
        : ['firecast', 'analytics', 'trend', 'idle'] as const,
    queryFn: () => apiClient.getTrend(lat as number, lon as number, days, radiusKm),
    enabled: enabled && lat != null && lon != null,
    staleTime: 60 * 1000, // 1 min — fresh enough for user-driven cell changes.
  });
}

/**
 * Single-shot `/predict` mutation. Returns react-query v5 mutation handle;
 * the caller pushes both the success result and any error into the store
 * (see `ModelSelectPanel.runInference` for the wiring).
 */
export function usePredict() {
  return useMutation<PredictionResult, Error, PredictPayload>({
    mutationFn: (payload: PredictPayload) => apiClient.predict(payload),
  });
}

/** Single-shot `/predict/aoi` batch mutation. */
export function usePredictAoi() {
  return useMutation({
    mutationFn: (payload: PredictAoiPayload) => apiClient.predictAoi(payload),
  });
}

/**
 * Activate a model version (`POST /api/models/{name}/activate`).
 *
 * Variables: carries both the logical model name (registry key, e.g.
 * ``"stacking"``) AND the version string required by the Pydantic
 * ``ActivateVersionBody`` in ``src/api/models.py``. Omitting the version
 * body caused the user-visible 422 "Field required: body".
 */
export interface ActivateModelVars {
  modelName: string;
  version: string;
}

export function useActivateModel() {
  return useMutation<unknown, Error, ActivateModelVars>({
    mutationFn: ({ modelName, version }) => apiClient.activateModel(modelName, version),
  });
}
