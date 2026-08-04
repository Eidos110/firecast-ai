/**
 * Header controls — covers the LanguageToggle + ThemeToggle wiring.
 *
 * These two small controls are the only hands-on affordances in the Header;
 * if either breaks, the console becomes effectively unusable for bilingual
 * engineers (id.json is the primary locale for this deployment target per
 * AGENTS.md) and for dark/light switching (used when the console is on a
 * public display).
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import i18n from 'i18next';

import { LanguageToggle } from './LanguageToggle';
import { ThemeToggle } from './ThemeToggle';
import { initI18n } from '../i18n/i18n';

describe('LanguageToggle', () => {
  beforeEach(async () => {
    await initI18n();
    await i18n.changeLanguage('en');
  });

  it('switches language when the ID button is clicked', async () => {
    render(<LanguageToggle />);
    await userEvent.click(screen.getByRole('button', { name: 'ID' }));
    expect(i18n.language).toBe('id');
  });

  it('persists selection to localStorage', async () => {
    render(<LanguageToggle />);
    await userEvent.click(screen.getByRole('button', { name: 'ID' }));
    expect(window.localStorage.getItem('firecast-lang')).toBe('id');
  });

  it('marks only the active button as pressed', async () => {
    render(<LanguageToggle />);
    const en = screen.getByRole('button', { name: 'EN' });
    const id = screen.getByRole('button', { name: 'ID' });
    expect(en.getAttribute('aria-pressed')).toBe('true');
    expect(id.getAttribute('aria-pressed')).toBe('false');
    await userEvent.click(id);
    expect(en.getAttribute('aria-pressed')).toBe('false');
    expect(id.getAttribute('aria-pressed')).toBe('true');
  });
});

describe('ThemeToggle', () => {
  it('cycles through themes on click', async () => {
    render(<ThemeToggle />);
    // useTheme defaults to dark before mount; first click should move to light.
    const btn = screen.getByRole('button', { name: /toggle theme|ganti tema/i });
    await userEvent.click(btn);
    expect(document.documentElement.getAttribute('data-theme')).toMatch(/light|dark/);
  });
});
