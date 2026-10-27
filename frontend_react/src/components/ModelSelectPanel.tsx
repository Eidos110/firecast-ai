/**
 * ModelSelectPanel — left sidebar model configuration block (V4 mockup).
 *
 * Reads the active model from the global store; surfaces a model picker,
 * forecast-horizon select, and a "Run Inference" button that triggers a
 * /predict call. V4 reads back the chosen model from `useModels` so the
 * dropdown enumerates backend-registered versions instead of a hardcoded
 * two-entry list. Falls back to the two demo entries when /api/models is
 * unreachable (PLAN §7 risk register).
 *
 * The mutation runs through `usePredict` (react-query v5). The button's busy
 * state derives from `mutation.isPending`, and the global store gets the
 * result via `setPrediction` — no ad-hoc useState to keep things single-
 * sourced. Errors are piped to the ApiLogBox via `pushApiLog('err', ...)`
 * and a deterministic demo-mode fallback (`mockPredict`) keeps the UI live
 * even when the backend is fully down.
 */
import { useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { queryKeys, useActivateModel, useModels, usePredict } from '../api/hooks';
import { mockPredict, type PredictPayload } from '../api/client';
import { useInferenceStore } from '../store/inferenceStore';
import { toast } from '../store/toastStore';

// Sentinel values that survive across i18n locale switches. The visible label
// is resolved via t('spa.model.fallback.new'|'legacy') at render time.
const FALLBACK_MODEL_VALUES = ['new', 'legacy'] as const;

const HORIZON_OPTIONS = [
  { value: 1, label: 'H+1 (1h)' },
  { value: 6, label: 'H+6 (6h)' },
  { value: 24, label: 'H+24 (1 day)' },
  { value: 72, label: 'H+72 (3 days)' },
] as const;

type ModelChoice = 'new' | 'legacy';

/**
 * Resolve the version string to send to ``/api/models/{name}/activate``.
 *
 * Mirrors the registry's own CSV endeavour: prefer the active entry for the
 * logical model name, otherwise fall back to the top (newest) version. If
 * the registry is unreachable/empty we fall back to a sentinel so the
 * activate endpoint still receives a syntactically-valid ``{"version": ...}``
 * body (the 422 "Field required: body" error came from sending NO body at
 * all; an empty version string here at least clears the validation gate).
 */
function resolveRegistryVersion(
  registry: { models: Record<string, Array<{ version: string; is_active?: boolean }>> } | undefined,
  registryName: string,
): string {
  const versions = registry?.models?.[registryName];
  if (!versions || versions.length === 0) return 'active';
  const active = versions.find((v) => v.is_active);
  return (active ?? versions[0]).version || 'active';
}

export function ModelSelectPanel(): JSX.Element {
  const { t } = useTranslation();
  const [modelType, setModelType] = useState<ModelChoice>('new');
  const selectedCell = useInferenceStore((s) => s.selectedCell);
  const setHorizonHours = useInferenceStore((s) => s.setHorizonHours);
  const horizonHours = useInferenceStore((s) => s.horizonHours);
  const setPrediction = useInferenceStore((s) => s.setPrediction);
  const setRunId = useInferenceStore((s) => s.setRunId);
  const pushApiLog = useInferenceStore((s) => s.pushApiLog);
  const setActiveModel = useInferenceStore((s) => s.setActiveModel);
  const [threshold, setThreshold] = useState(0.5);

  const mutation = usePredict();
  const activateMutation = useActivateModel();
  const modelsQuery = useModels(/* enabled= */ true);
  const qc = useQueryClient();

  // Build the dropdown. When /api/models succeeds this is the union of all
  // registered versions; otherwise we keep the two-entry fallback for the
  // engineer console's demo run.
  const modelOptions = useMemo<Array<{ value: ModelChoice; label: string }>>(() => {
    const fallback: Array<{ value: ModelChoice; label: string }> = FALLBACK_MODEL_VALUES.map((v) => ({
      value: v,
      label: t(`spa.model.fallback.${v}`),
    }));
    const registry = modelsQuery.data;
    if (!registry || registry.count === 0) return fallback;
    const out: Array<{ value: ModelChoice; label: string }> = [];
    let hasNew = false;
    let hasLegacy = false;
    for (const [name, versions] of Object.entries(registry.models)) {
      // Heuristic: model keys like "stacking" or "ensemble" -> 'new'.
      const tier = /new|stack|causal|gru/i.test(name) ? 'new' : 'legacy';
      if (tier === 'new') hasNew = true;
      else hasLegacy = true;
      const topVersion = versions[0];
      out.push({
        value: tier,
        label: `${name}${topVersion ? ' · ' + (topVersion.version ?? '') : ''}`,
      });
    }
    if (!hasNew) out.unshift({ value: 'new', label: t('spa.model.fallback.new') });
    if (!hasLegacy) out.push({ value: 'legacy', label: t('spa.model.fallback.legacy') });
    // Deduplicate by (value,label).
    return Array.from(new Map(out.map((o) => [`${o.value}|${o.label}`, o])).values());
  }, [modelsQuery.data, t]);

  async function runInference(): Promise<void> {
    if (!selectedCell) {
      pushApiLog('warn', t('spa.model.no_cell_selected'));
      return;
    }
    const t0 = performance.now();
    // ROADMAP §3-W1: forward the scrubber date (if any) so the backend
    // re-anchors the temporal features. ``null`` from the store means
    // "today", which is exactly the legacy default — so we just leave the
    // field undefined in the payload rather than serialising null.
    const referenceDate = useInferenceStore.getState().selectedPredictionDate;
    const payload: PredictPayload = {
      temperature: 30, // demo values; sidebar weather form not yet built
      humidity: 55,
      wind_speed: 6,
      latitude: selectedCell.lat,
      longitude: selectedCell.lon,
      fuel_moisture: 20,
      model_type: modelType,
      ...(referenceDate ? { reference_date: referenceDate } : {}),
    };
    pushApiLog('ok', `POST /predict model=${modelType}…`);
    try {
      const result = await mutation.mutateAsync(payload);
      setPrediction(result);
      // ``run_id`` is always set by the backend now (see geo_api.py:run_id
      // block); guard anyway so a future backend regression can't crash
      // the UI with "can't access property 'split' of undefined".
      const runId = (result.run_id as string | undefined) ?? '';
      setRunId(runId);
      const versionPart = runId ? runId.split('-')[0] : modelType;
      setActiveModel({ version: versionPart, type: modelType, auc: null, drift: null });
      pushApiLog(
        'ok',
        `200 p_fire=${result.risk_score != null ? result.risk_score.toFixed(3) : '?'} ${runId} ${result.latency_ms ?? 0}ms`,
      );
      toast.success(
        t('spa.toast.predict_success', {
          score: result.risk_score != null ? result.risk_score.toFixed(3) : '?',
        }),
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      pushApiLog('err', `${msg} — falling back to mock`);
      toast.error(t('spa.toast.predict_failed', { msg }));
      const mock = mockPredict(selectedCell.lat, selectedCell.lon);
      setPrediction({ ...mock, latency_ms: Math.round(performance.now() - t0) });
      setRunId(mock.run_id);
    }
  }

  return (
    <section aria-labelledby="model-heading" className="fc-section">
      <h4 id="model-heading" className="fc-section-title">
        {t('spa.model.label')}
      </h4>

      <label className="fc-field">
        <span className="fc-field-label">{t('spa.model.label')}</span>
        <select
          value={modelType}
          onChange={(e) => setModelType(e.target.value as ModelChoice)}
          className="fc-input"
        >
          {modelOptions.map((m) => (
            <option key={`${m.value}|${m.label}`} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </label>

      <label className="fc-field">
        <span className="fc-field-label">{t('spa.model.forecast_horizon')}</span>
        <select
          value={horizonHours}
          onChange={(e) => setHorizonHours(Number(e.target.value))}
          className="fc-input"
        >
          {HORIZON_OPTIONS.map((h) => (
            <option key={h.value} value={h.value}>
              {h.label}
            </option>
          ))}
        </select>
      </label>

      <div className="fc-field">
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span className="fc-field-label">{t('spa.model.confidence_threshold')}</span>
          <span className="fc-mono">{threshold.toFixed(2)}</span>
        </div>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
          aria-label={t('spa.model.confidence_threshold')}
          className="fc-range"
        />
      </div>

      <button
        type="button"
        onClick={runInference}
        disabled={mutation.isPending || activateMutation.isPending || !selectedCell}
        className="fc-btn-primary fc-btn-compact"
        style={{ width: '100%', marginTop: 4 }}
      >
        {mutation.isPending
          ? t('spa.model.run_inference_busy')
          : `▶ ${t('spa.model.run_inference')}`}
      </button>

      <button
        type="button"
        onClick={() => {
          const registryName = modelType === 'new' ? 'stacking' : 'legacy';
          const version = resolveRegistryVersion(modelsQuery.data, registryName);
          activateMutation.mutate(
            { modelName: registryName, version },
            {
              onSuccess: () => {
                pushApiLog('ok', `Model ${registryName} v${version} activated`);
                toast.success(t('spa.toast.model_activated', { name: registryName, version }));
                // Refresh the models list so the "active" badge updates and
                // subsequent /predict run_id reflects the freshly activated row.
                qc.invalidateQueries({ queryKey: queryKeys.models() });
              },
              onError: (err) => {
                pushApiLog('err', `activate: ${err.message}`);
                toast.error(t('spa.toast.model_activate_failed', { msg: err.message }));
              },
            },
          );
        }}
        disabled={activateMutation.isPending}
        className="fc-btn-secondary fc-btn-compact"
        style={{ width: '100%', marginTop: 4, fontSize: 11 }}
      >
        {activateMutation.isPending
          ? t('spa.model.run_inference_busy')
          : t('spa.model.set_active_server')}
      </button>

      <div aria-live="polite" style={{ marginTop: 6, fontSize: 11, color: 'var(--color-text-muted)' }}>
        {selectedCell
          ? t('spa.model.selected_cell', {
              lat: selectedCell.lat.toFixed(4),
              lon: selectedCell.lon.toFixed(4),
            })
          : t('spa.model.no_cell_selected')}
      </div>
    </section>
  );
}

export default ModelSelectPanel;
