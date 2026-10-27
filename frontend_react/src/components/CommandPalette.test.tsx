/**
 * CommandPalette unit tests.
 *
 * The palette is the primary keyboard-driven affordance (Ctrl+K), so we pin
 * down the three behaviours most likely to regress: (1) it renders the
 * merged action list, (2) substring filter narrows it, (3) clicking an item
 * calls the action and closes the palette.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import i18n from 'i18next';

import { CommandPalette } from './CommandPalette';
import { initI18n } from '../i18n/i18n';
import { useUiStore } from '../store/uiStore';
import { useInferenceStore } from '../store/inferenceStore';

describe('<CommandPalette>', () => {
  beforeEach(async () => {
    await initI18n();
    await i18n.changeLanguage('en');
    useUiStore.setState({ paletteOpen: true });
  });

  it('renders actions for every layer plus theme/language shortcuts', () => {
    render(<CommandPalette onRequestClose={() => {}} />);
    // 8 layers + theme + language = 10 actions
    const options = screen.getAllByRole('option');
    expect(options.length).toBe(8 + 2);
  });

  it('substring filter narrows the list', () => {
    render(<CommandPalette onRequestClose={() => {}} />);
    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'theme' } });
    const options = screen.getAllByRole('option');
    expect(options.length).toBe(1);
    expect(options[0].textContent).toMatch(/Cycle theme/i);
  });

  it('clicking an action toggles the layer and closes the palette via callback', () => {
    const onCloseSpy: Array<true> = [];
    render(<CommandPalette onRequestClose={() => onCloseSpy.push(true)} />);
    const before = useInferenceStore.getState().layers.find((l) => l.id === 'roads')?.active;
    const items = screen.getAllByRole('option');
    const roads = items.find((el) => el.textContent?.match(/Roads/))!;
    fireEvent.click(roads);
    const after = useInferenceStore.getState().layers.find((l) => l.id === 'roads')?.active;
    expect(after).toBe(!before);
    expect(onCloseSpy).toHaveLength(1);
  });

  it('shows the empty state when nothing matches', () => {
    render(<CommandPalette onRequestClose={() => {}} />);
    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'zzzz-no-match' } });
    expect(screen.queryByText(/No matching commands/i)).toBeInTheDocument();
  });
});
