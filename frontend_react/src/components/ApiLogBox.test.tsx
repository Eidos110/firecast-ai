/**
 * ApiLogBox tests — covers ROADMAP §3-M (i18n-aware error rendering).
 *
 * The log surfaces raw exception strings for failed /predict calls such as
 * ``422 body did not match schema``. The component must translate the
 * embedded HTTP code into a friendly localised message (English by default)
 * while keeping the raw text available via the ``title`` tooltip for
 * engineers who need to debug.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import i18n from 'i18next';

import { ApiLogBox } from './ApiLogBox';
import { useInferenceStore } from '../store/inferenceStore';
import { initI18n } from '../i18n/i18n';

describe('ApiLogBox — i18n error mapping (ROADMAP §3-M)', () => {
  beforeEach(async () => {
    await initI18n();
    await i18n.changeLanguage('en');
    // Reset the apiLogs slice for deterministic assertions between tests.
    useInferenceStore.setState({ apiLogs: [] });
  });

  it('renders the empty state when no API calls have been logged', () => {
    render(<ApiLogBox />);
    expect(screen.getByText(/No inference run yet/i)).toBeTruthy();
  });

  it('translates a 422 error into "Validation error" (en)', () => {
    useInferenceStore.setState({
      apiLogs: [
        {
          ts: '2026-08-04T00:00:00Z',
          level: 'err',
          message: '422 body did not match schema',
        },
      ],
    });
    render(<ApiLogBox />);
    expect(screen.getByText(/Validation error/i)).toBeTruthy();
  });

  it('keeps the raw payload in the ``title`` tooltip for engineers', () => {
    useInferenceStore.setState({
      apiLogs: [
        {
          ts: '2026-08-04T00:00:00Z',
          level: 'err',
          message: '422 body did not match schema',
        },
      ],
    });
    render(<ApiLogBox />);
    const translated = screen.getByText(/Validation error/i) as HTMLElement;
    expect(translated.title).toBe('422 body did not match schema');
  });

  it('falls back to the raw message when the code is unmapped', () => {
    useInferenceStore.setState({
      apiLogs: [
        { ts: '2026-08-04T00:00:00Z', level: 'err', message: 'weird non-HTTP failure' },
      ],
    });
    render(<ApiLogBox />);
    expect(screen.getByText('weird non-HTTP failure')).toBeTruthy();
  });

  it('leaves OK entries untouched', () => {
    useInferenceStore.setState({
      apiLogs: [
        { ts: '2026-08-04T00:00:00Z', level: 'ok', message: 'prediction complete' },
      ],
    });
    render(<ApiLogBox />);
    expect(screen.getByText('prediction complete')).toBeTruthy();
  });

  it('renders localised 422 message when user switches to Bahasa Indonesia', async () => {
    useInferenceStore.setState({
      apiLogs: [
        { ts: '2026-08-04T00:00:00Z', level: 'err', message: 'HTTP 422: validation failed' },
      ],
    });
    await i18n.changeLanguage('id');
    render(<ApiLogBox />);
    expect(screen.getByText(/Kesalahan validasi/i)).toBeTruthy();
  });
});
