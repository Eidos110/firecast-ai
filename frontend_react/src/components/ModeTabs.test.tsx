/**
 * ModeTabs tests (ROADMAP §3-W3).
 *
 * Covers persona switching plus localStorage persistence. The actual
 * layout-conditional-render assertions live in App-level tests; this file
 * just verifies the tab control itself.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import i18n from 'i18next';

import { ModeTabs } from './ModeTabs';
import { useUiStore } from '../store/uiStore';
import { initI18n } from '../i18n/i18n';

describe('ModeTabs (ROADMAP §3-W3)', () => {
  beforeEach(async () => {
    await initI18n();
    await i18n.changeLanguage('en');
    window.localStorage.removeItem('firecast-ui-mode');
    useUiStore.setState({ mode: 'engineer' });
  });

  it('renders the three persona tabs as a tablist', () => {
    render(<ModeTabs />);
    const tablist = screen.getByRole('tablist', { name: /persona/i });
    expect(tablist).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /engineer/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /analyst/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /demo/i })).toBeInTheDocument();
  });

  it('marks only the active tab as selected (aria-selected)', () => {
    render(<ModeTabs />);
    expect(screen.getByRole('tab', { name: /engineer/i }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tab', { name: /analyst/i }).getAttribute('aria-selected')).toBe('false');
  });

  it('clicking analyst flips the store to analyst mode', async () => {
    render(<ModeTabs />);
    await userEvent.click(screen.getByRole('tab', { name: /analyst/i }));
    expect(useUiStore.getState().mode).toBe('analyst');
  });

  it('persists the persona choice to localStorage', async () => {
    render(<ModeTabs />);
    await userEvent.click(screen.getByRole('tab', { name: /demo/i }));
    expect(window.localStorage.getItem('firecast-ui-mode')).toBe('demo');
  });
});
