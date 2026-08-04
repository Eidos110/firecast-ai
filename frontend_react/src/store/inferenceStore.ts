/**
 * FireCast application inference store (Zustand).
 *
 * Single global store for cross-component state — replaces the Streamlit
 * `st.session_state` bridge. Kept intentionally small; UI-local ephemeral
 * state (hover/active toggle for layer rows) stays in component useState.
 */
import { create } from 'zustand';

import type { RiskTierLabel } from '../theme/tokens';

/** A single GeoJSON FeatureCollection produced by /predict/aoi batch. */
export interface PredictionOverlay {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    geometry: { type: string; coordinates: number[] | number[][] | number[][][] };
    properties: {
      prediction: number;
      risk_level: RiskTierLabel;
      latitude: number;
      longitude: number;
      [k: string]: unknown;
    };
  }>;
}

/** Summary for a single /predict invocation. */
export interface PredictionResult {
  risk_score: number;
  risk_level: RiskTierLabel;
  confidence: number | null;
  confidence_interval: { p10?: number; p90?: number } | null;
  cnn_probability: number | null;
  lgbm_probability: number | null;
  shap_explanation: { top_features?: Array<{ name: string; value: number }> } | null;
  factors: Record<string, number> | null;
  model_agreement: number | null;
  run_id: string;
  latency_ms: number;
  timestamp: string;
  status: string;
  [k: string]: unknown;
}

export interface ApiLogEntry {
  ts: string; // ISO timestamp
  level: 'ok' | 'warn' | 'err';
  message: string;
}

export type LayerId =
  | 'risk_heatmap'
  | 'active_fire'
  | 'predicted_spread'
  | 'wind_vectors'
  | 'fuel_moisture'
  | 'topography'
  | 'satellite_viirs'
  | 'roads';

interface LayerState {
  id: LayerId;
  label: string;
  active: boolean;
  opacity: number; // 0..1
}

interface ModelInfo {
  version: string;
  type: string; // 'new' | 'legacy'
  auc: number | null;
  drift: number | null;
}

interface InferenceStore {
  // ── Selection ──
  selectedCell: { lat: number; lon: number } | null;
  setSelectedCell: (cell: { lat: number; lon: number } | null) => void;

  // ── AOI ──
  selectedAoi: GeoJSON.Feature | null;
  setSelectedAoi: (aoi: GeoJSON.Feature | null) => void;
  aoiOverlay: PredictionOverlay | null;
  setAoiOverlay: (overlay: PredictionOverlay | null) => void;

  // ── Layers ──
  layers: LayerState[];
  toggleLayer: (id: LayerId) => void;
  setLayerOpacity: (id: LayerId, opacity: number) => void;

  // ── Model & run ──
  activeModel: ModelInfo | null;
  setActiveModel: (m: ModelInfo | null) => void;
  runId: string;
  setRunId: (id: string) => void;

  // ── Forecast horizon (timeline scrubber) ──
  horizonHours: number; // -24 .. +72
  setHorizonHours: (h: number) => void;
  isPlaying: boolean;
  setIsPlaying: (v: boolean) => void;

  // ── ROADMAP §3-W1: selected prediction date ──
  // ISO date string ("YYYY-MM-DD") picked via Header's date input; used by
  // /predict callers to anchor the inference window to a specific day
  // instead of "today". ``null`` ⇒ "today" (production default).
  selectedPredictionDate: string | null;
  setSelectedPredictionDate: (iso: string | null) => void;

  // ── Prediction result & API log ──
  prediction: PredictionResult | null;
  setPrediction: (p: PredictionResult | null) => void;
  latencyMs: number | null;
  apiLogs: ApiLogEntry[];
  pushApiLog: (level: ApiLogEntry['level'], message: string) => void;
  clearApiLogs: () => void;
}

const DEFAULT_LAYERS: LayerState[] = [
  { id: 'risk_heatmap', label: 'Fire Risk Heatmap', active: true, opacity: 0.75 },
  { id: 'active_fire', label: 'Active Fire Points', active: true, opacity: 0.75 },
  { id: 'predicted_spread', label: 'Predicted Spread (24h)', active: false, opacity: 0.6 },
  { id: 'wind_vectors', label: 'Wind Vectors', active: true, opacity: 0.7 },
  { id: 'fuel_moisture', label: 'Fuel Moisture', active: false, opacity: 0.6 },
  { id: 'topography', label: 'Topography (DEM)', active: false, opacity: 0.5 },
  { id: 'satellite_viirs', label: 'Satellite VIIRS', active: false, opacity: 0.7 },
  { id: 'roads', label: 'Roads & Infrastructure', active: false, opacity: 0.6 },
];

function makeRunId(): string {
  const d = new Date();
  const ts = d.toISOString().slice(0, 19).replace(/[-:T]/g, '');
  return `fc-${ts}`;
}

export const useInferenceStore = create<InferenceStore>((set) => ({
  selectedCell: null,
  setSelectedCell: (cell) => set({ selectedCell: cell }),

  selectedAoi: null,
  setSelectedAoi: (aoi) => set({ selectedAoi: aoi }),
  aoiOverlay: null,
  setAoiOverlay: (overlay) => set({ aoiOverlay: overlay }),

  layers: DEFAULT_LAYERS,
  toggleLayer: (id) =>
    set((s) => ({
      layers: s.layers.map((l) => (l.id === id ? { ...l, active: !l.active } : l)),
    })),
  setLayerOpacity: (id, opacity) =>
    set((s) => ({
      layers: s.layers.map((l) => (l.id === id ? { ...l, opacity } : l)),
    })),

  activeModel: null,
  setActiveModel: (m) => set({ activeModel: m }),
  runId: makeRunId(),
  setRunId: (id) => set({ runId: id }),

  horizonHours: 0,
  setHorizonHours: (h) => set({ horizonHours: h }),
  isPlaying: false,
  setIsPlaying: (v) => set({ isPlaying: v }),

  // ROADMAP §3-W1: selected prediction date. ``null`` is the production
  // default and means "today"; the Header date input writes an ISO
  // YYYY-MM-DD string here when the user picks a specific day, and
  // downstream /predict callers read it to anchor their inference window.
  selectedPredictionDate: null,
  setSelectedPredictionDate: (iso) => set({ selectedPredictionDate: iso }),

  prediction: null,
  setPrediction: (p) => set({ prediction: p, latencyMs: p?.latency_ms ?? null }),
  latencyMs: null,

  apiLogs: [],
  pushApiLog: (level, message) =>
    set((s) => {
      const entry: ApiLogEntry = { ts: new Date().toISOString(), level, message };
      const next = [...s.apiLogs, entry];
      // Circular buffer — keep the last 50 (PLAN §5 Task 1.1).
      if (next.length > 50) next.shift();
      return { apiLogs: next };
    }),
  clearApiLogs: () => set({ apiLogs: [] }),
}));
