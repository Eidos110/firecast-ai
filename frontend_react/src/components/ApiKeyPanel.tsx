/**
 * ApiKeyPanel — left sidebar X-API-Key configuration block.
 *
 * Reads/writes the persisted API key consumed by `authedOpts()` in
 * `src/api/client.ts`. Without a stored key, every endpoint gated by
 * `Depends(get_api_key)` (`/predict`, `/api/models/*`, `/predict/aoi`)
 * returns HTTP 401 and the SPA silently falls back to mock predictions
 * (see `ModelSelectPanel.runInference`). Mounting this panel gives the
 * engineer a visible place to paste the secret defined via `API_SECRET_KEY`
 * in the backend `.env`, instead of dropping a key into localStorage from a
 * browser devtools console.
 *
 * On Save / Clear the panel bumps an `invalidatedAt` version counter on the
 * `models` and `health` query keys so react-query refetches them with the
 * freshly-populated header — otherwise cached 401 responses would linger
 * until the cache TTL elapses.
 */
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { clearApiKey, storeApiKey } from '../api/client';
import { queryKeys } from '../api/hooks';
import { useInferenceStore } from '../store/inferenceStore';

const API_KEY_STORAGE = 'firecast-api-key';

function readInitialKey(): string {
  if (typeof window === 'undefined') return '';
  try {
    return window.localStorage.getItem(API_KEY_STORAGE) ?? '';
  } catch {
    return '';
  }
}

export function ApiKeyPanel(): JSX.Element {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const pushApiLog = useInferenceStore((s) => s.pushApiLog);
  const [draft, setDraft] = useState<string>(readInitialKey);
  const [saved, setSaved] = useState<boolean>(() => !!readInitialKey());
  const [reveal, setReveal] = useState<boolean>(false);
  const [justSaved, setJustSaved] = useState<boolean>(false);

  function invalidateAuthedQueries(): void {
    // Cached 401 responses would otherwise persist until their staleTime
    // elapses; clear them so the next render re-issues with the new header.
    qc.invalidateQueries({ queryKey: queryKeys.models() });
    qc.invalidateQueries({ queryKey: queryKeys.health() });
  }

  function onSave(): void {
    const trimmed = storeApiKey(draft);
    if (trimmed) {
      setSaved(true);
      setJustSaved(true);
      pushApiLog('ok', t('spa.api_key.log_saved'));
      window.setTimeout(() => setJustSaved(false), 1500);
    } else {
      setSaved(false);
      pushApiLog('warn', t('spa.api_key.log_empty'));
    }
    invalidateAuthedQueries();
  }

  function onClear(): void {
    clearApiKey();
    setDraft('');
    setSaved(false);
    pushApiLog('warn', t('spa.api_key.log_cleared'));
    invalidateAuthedQueries();
  }

  return (
    <section aria-labelledby="api-key-heading" className="fc-section">
      <h4 id="api-key-heading" className="fc-section-title">
        {t('spa.api_key.title')}
      </h4>

      <div className="fc-field">
        <span className="fc-field-label">{t('spa.api_key.label')}</span>
        <div style={{ display: 'flex', gap: 6 }}>
          <input
            type={reveal ? 'text' : 'password'}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={t('spa.api_key.placeholder')}
            aria-label={t('spa.api_key.label')}
            autoComplete="off"
            spellCheck={false}
            className="fc-input fc-mono"
            style={{ flex: 1 }}
          />
          <button
            type="button"
            onClick={() => setReveal((r) => !r)}
            aria-pressed={reveal}
            title={reveal ? t('spa.api_key.hide') : t('spa.api_key.reveal')}
            aria-label={reveal ? t('spa.api_key.hide') : t('spa.api_key.reveal')}
            className="fc-btn-secondary fc-btn-compact"
            style={{ minWidth: 36, padding: '4px 8px' }}
          >
            {reveal ? '\u{1F441}' : '\u{1F512}'}
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
        <button
          type="button"
          onClick={onSave}
          className="fc-btn-primary fc-btn-compact"
          style={{ flex: 1 }}
        >
          {justSaved ? '\u2713 ' + t('spa.api_key.saved') : t('spa.api_key.save')}
        </button>
        <button
          type="button"
          onClick={onClear}
          disabled={!saved && draft.length === 0}
          className="fc-btn-secondary fc-btn-compact"
          style={{ flex: 1 }}
        >
          {t('spa.api_key.clear')}
        </button>
      </div>

      <div
        aria-live="polite"
        style={{
          marginTop: 6,
          fontSize: 11,
          color: saved ? 'var(--color-success)' : 'var(--color-text-muted)',
        }}
      >
        {saved ? t('spa.api_key.status_set') : t('spa.api_key.status_unset')}
      </div>
    </section>
  );
}

export default ApiKeyPanel;
