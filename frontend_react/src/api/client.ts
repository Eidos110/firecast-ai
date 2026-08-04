/**
 * FireCast API client — typed fetch wrappers around the FastAPI backend
 * (`src/geo_api.py`). All methods return typed Promises; failures bubble
 * up to React Query error handlers via the hooks in `./hooks`.
 *
 * Vite dev proxy forwards `/predict`, `/api`, `/geo`, `/analytics`, `/health`
 * to `http://localhost:8000` (see vite.config.ts). In production the same
 * paths are served behind the same host (nginx reverse-proxy).
 *
 * Demo mode: when ENABLE_DEMO_MODE is set server-side or the network is
 * unreachable, callers can fall back to `mockPredict()` so the SPA keeps
 * working. `mockPredict()` mirrors the V4 mock pattern.
 *
 * Response contract cross-checked against `src/geo_api.py` + `src/api/models.py`
 * (TAHAP B & D) so the TS types line up with what the backend truly returns.
 */
import type { PredictionResult } from '../store/inferenceStore';
import { getRiskLevel } from '../theme/tokens';

const API_KEY_HEADER = 'X-API-Key';
const API_KEY_STORAGE = 'firecast-api-key';

export interface PredictPayload {
  temperature: number;
  humidity: number;
  wind_speed: number;
  latitude: number;
  longitude: number;
  wind_direction?: number;
  rainfall?: number;
  ndvi?: number;
  vegetation_type?: string;
  fuel_moisture?: number;
  model_version?: string;
  model_type?: 'new' | 'legacy';
  /**
   * ISO date (``YYYY-MM-DD``) for the temporal anchor. ROADMAP §3-W1 —
   * ``HeaderGeoControls`` writes to ``useInferenceStore.selectedPredictionDate``
   * and ``ModelSelectPanel.runInference`` forwards it here. Backend parses
   * this into a Python ``datetime`` and rotates month/day/doy features
   * accordingly. Omitting → server falls back to "today".
   */
  reference_date?: string;
}

export interface PredictAoiPayload {
  /** GeoJSON Polygon / MultiPolygon / Feature as a plain object (not a string). */
  geojson: Record<string, unknown>;
  grid_size: number; // grid side count (1..64)
  base_features?: Record<string, number | string>;
  model_version?: string;
  model_type?: 'new' | 'legacy';
}

/** Per-cell result from /predict/aoi — see `services.run_aoi_batch`. */
export interface AoiCellResult {
  latitude: number;
  longitude: number;
  row: number;
  col: number;
  risk_score?: number;
  risk_level?: string;
  confidence?: number;
  status: string; // 'success' | 'error'
  error?: string;
  [k: string]: unknown;
}

export interface PredictAoiResponse {
  count: number;
  ok: number;
  errors: number;
  grid_size: number;
  results: AoiCellResult[];
}

/** ``GET /api/models/`` — see ``src/api/models.py:list_models``. */
export interface ModelRegistryEntry {
  model_name: string;
  version: string;
  is_active: boolean;
  created_at?: string;
  performance_metrics?: Record<string, number> | null;
}

export interface ListModelsResponse {
  models: Record<string, ModelRegistryEntry[]>;
  count: number;
}

export interface HealthStatus {
  status: string;
  [k: string]: unknown;
}

export interface LocationPreset {
  id?: string;
  name: string;
  lat: number;
  lon: number;
  zoom?: number;
}

/** ``GET /geo/geocode?q=`` — see ``geo_api.py:geo_geocode``. */
export interface GeocodeResult {
  name: string;
  lat: number;
  lon: number;
  source: 'local' | 'nominatim';
}

/** Per-day row of the analytics trend series (see `services.get_trend_series`). */
export interface TrendSeriesPoint {
  date: string; // YYYY-MM-DD
  fire_rate: number;
  p10: number;
  p50: number;
  p90: number;
  count: number;
}

export interface TrendResponse {
  lat: number;
  lon: number;
  radius_km: number;
  days: number;
  series: TrendSeriesPoint[];
}

export interface ApiClientOptions {
  apiKey?: string;
}

function buildHeaders(opts?: ApiClientOptions): HeadersInit {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (opts?.apiKey) headers[API_KEY_HEADER] = opts.apiKey;
  return headers;
}

async function JSONOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: string;
    try {
      const j = await res.json();
      detail = j?.detail ?? j?.message ?? res.statusText;
    } catch {
      detail = res.statusText;
    }
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

/**
 * Read a single API key from window/localStorage at call time (not import
 * time) so that test mocks & SSR never pick a stale value. Returns undefined
 * when no key is set — backend endpoints gated by X-API-Key will 401, and
 * the react-query error handler in `usePredict` surfaces the message to the
 * ApiLogBox per PLAN §7 risk register.
 */
function readStoredApiKey(): string | undefined {
  if (typeof window === 'undefined') return undefined;
  try {
    return window.localStorage.getItem(API_KEY_STORAGE) ?? undefined;
  } catch {
    return undefined;
  }
}

/**
 * Persist an API key to localStorage so subsequent `authedOpts()` calls and
 * react-query refetches send the `X-API-Key` header. Callable directly from
 * the `ApiKeyPanel` sidebar component. No-op when `window` is undefined
 * (SSR / vitest jsdom without `window`). Returns the stored value (without
 * leading/trailing whitespace) for caller convenience.
 */
export function storeApiKey(key: string): string {
  const trimmed = key.trim();
  if (typeof window === 'undefined') return trimmed;
  try {
    if (trimmed) window.localStorage.setItem(API_KEY_STORAGE, trimmed);
    else window.localStorage.removeItem(API_KEY_STORAGE);
  } catch {
    /* localStorage unavailable (private mode) — caller still gets value */
  }
  return trimmed;
}

/** Remove the persisted API key. Idempotent. No-op outside the browser. */
export function clearApiKey(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(API_KEY_STORAGE);
  } catch {
    /* ignore */
  }
}

/** True when a non-empty API key is currently stored. Friendly for guards. */
export function hasApiKey(): boolean {
  return !!readStoredApiKey();
}

function authedOpts(explicit?: ApiClientOptions): ApiClientOptions {
  const stored = readStoredApiKey();
  if (stored && !explicit?.apiKey) return { apiKey: stored };
  return explicit ?? {};
}

export const apiClient = {
  async health(opts?: ApiClientOptions): Promise<HealthStatus> {
    const res = await fetch('/health', { headers: buildHeaders(opts) });
    if (!res.ok) throw new Error(`Health ${res.status}`);
    return res.json() as Promise<HealthStatus>;
  },

  async predict(payload: PredictPayload, opts?: ApiClientOptions): Promise<PredictionResult> {
    const res = await fetch('/predict', {
      method: 'POST',
      headers: buildHeaders(authedOpts(opts)),
      body: JSON.stringify(payload),
    });
    return JSONOrThrow<PredictionResult>(res);
  },

  async predictAoi(payload: PredictAoiPayload, opts?: ApiClientOptions): Promise<PredictAoiResponse> {
    const res = await fetch('/predict/aoi', {
      method: 'POST',
      headers: buildHeaders(authedOpts(opts)),
      body: JSON.stringify(payload),
    });
    return JSONOrThrow<PredictAoiResponse>(res);
  },

  async listModels(opts?: ApiClientOptions): Promise<ListModelsResponse> {
    const res = await fetch('/api/models/', { headers: buildHeaders(authedOpts(opts)) });
    return JSONOrThrow<ListModelsResponse>(res);
  },

  /**
   * Activate a model version. The Pydantic body
   * ``ActivateVersionBody`` in ``src/api/models.py`` requires
   * ``{"version": "<version_string>"}`` — sending no body returns 422
   * "Field required: body". The caller resolves which version to push from
   * the registry (see ``ModelSelectPanel``).
   */
  async activateModel(
    modelName: string,
    version: string,
    opts?: ApiClientOptions,
  ): Promise<unknown> {
    const res = await fetch(`/api/models/${encodeURIComponent(modelName)}/activate`, {
      method: 'POST',
      headers: buildHeaders(authedOpts(opts)),
      body: JSON.stringify({ version }),
    });
    return JSONOrThrow<unknown>(res);
  },

  async listLocations(opts?: ApiClientOptions): Promise<{ count: number; locations: LocationPreset[] }> {
    const res = await fetch('/geo/locations', { headers: buildHeaders(opts) });
    return JSONOrThrow<{ count: number; locations: LocationPreset[] }>(res);
  },

  async geocode(query: string, opts?: ApiClientOptions): Promise<GeocodeResult | null> {
    const res = await fetch(`/geo/geocode?q=${encodeURIComponent(query)}`, {
      headers: buildHeaders(opts),
    });
    if (res.status === 404) return null;
    return JSONOrThrow<GeocodeResult>(res);
  },

  async getTrend(
    lat: number,
    lon: number,
    days = 7,
    radiusKm = 25,
    opts?: ApiClientOptions,
  ): Promise<TrendResponse> {
    const res = await fetch(
      `/analytics/trend?lat=${lat}&lon=${lon}&days=${days}&radius_km=${radiusKm}`,
      { headers: buildHeaders(opts) },
    );
    return JSONOrThrow<TrendResponse>(res);
  },
};

/**
 * Mock predict — used by the right-diagnostic panel when the API is not
 * reachable (demo mode). Mirrors the V4 `runInference` mock fallback.
 *
 * Stays deterministic for the same lat/lon so the UI doesn't thrash between
 * renders. Includes SHAP-style top_features so the right panel still shows
 * a populated SHAP list.
 */
export function mockPredict(lat: number, lon: number): PredictionResult {
  // Deterministic-ish score from lat/lon so the panel doesn't twitch.
  const seed = Math.abs(Math.sin(lat * 0.91 + lon * 0.53)) % 1;
  const riskScore = Math.min(0.99, Math.max(0.05, 0.4 + seed * 0.55));
  return {
    risk_score: Number(riskScore.toFixed(3)),
    risk_level: getRiskLevel(riskScore),
    confidence: 0.78,
    confidence_interval: { p10: Math.max(0, riskScore - 0.08), p90: Math.min(1, riskScore + 0.08) },
    cnn_probability: riskScore - 0.02,
    lgbm_probability: riskScore + 0.01,
    shap_explanation: {
      top_features: [
        { name: 'temperature_2m', value: 0.31 },
        { name: 'humidity_rel', value: 0.22 },
        { name: 'ndvi_anom', value: 0.18 },
        { name: 'wind_speed', value: 0.14 },
        { name: 'fuel_moisture', value: 0.09 },
        { name: 'precip_24h', value: 0.05 },
      ],
    },
    factors: { high_temp: 0.42, low_humidity: 0.31, dry_fuel: 0.27 },
    model_agreement: 0.96,
    run_id: `mock-${Date.now()}`,
    latency_ms: 0,
    timestamp: new Date().toISOString(),
    status: 'DEMO',
  };
}

/** Mock 7-day trend for the demo-mode chart when /analytics/trend is unreachable. */
export function mockTrend(lat: number, lon: number, current: number | null): TrendResponse {
  const today = current ?? 0.5;
  const seed = Math.abs(Math.sin(lat * 0.71 + lon * 0.43));
  const series: TrendSeriesPoint[] = [];
  for (let i = 6; i >= 0; i--) {
    const noise = (seed * (i + 1)) % 0.13;
    const base = Math.max(0.05, Math.min(1, today + 0.06 * -i - noise));
    const date = new Date();
    date.setDate(date.getDate() - i);
    const d = date.toISOString().slice(0, 10);
    series.push({
      date: d,
      fire_rate: Number(base.toFixed(3)),
      p10: Math.max(0, base - 0.08),
      p50: base,
      p90: Math.min(1, base + 0.08),
      count: 24 + Math.floor(seed * 12),
    });
  }
  return { lat, lon, radius_km: 25, days: 7, series };
}
