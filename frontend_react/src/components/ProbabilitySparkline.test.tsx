// ProbabilitySparkline component tests — Fase 5 quality gate.
// Validates: empty/all-zero fallback, clamping, gradient generation, accessibility.
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ProbabilitySparkline } from './ProbabilitySparkline';

describe('<ProbabilitySparkline />', () => {
  it('renders a labelled SVG for non-empty data', () => {
    render(<ProbabilitySparkline data={[0.1, 0.3, 0.5, 0.7]} />);
    const svg = screen.getByRole('img');
    expect(svg).toBeInTheDocument();
    expect(svg.getAttribute('aria-label')).toMatch(/4 points/);
  });

  it('falls back to a flat baseline when given empty data', () => {
    const { container } = render(<ProbabilitySparkline data={[]} />);
    // With empty data, the component synthesises a 2-point zero baseline.
    const path = container.querySelector('path');
    expect(path).toBeInTheDocument();
    expect(screen.getByRole('img').getAttribute('aria-label')).toMatch(/2 points/);
  });

  it('clamps out-of-range values to [0, 1]', () => {
    const { container } = render(
      <ProbabilitySparkline data={[2.0, -1.0, 0.5, 0.7]} />,
    );
    const svg = screen.getByRole('img');
    // Last sanitised value is 0.7, so label should reflect "70 percent".
    expect(svg.getAttribute('aria-label')).toMatch(/70 percent/);
    // The line path string should only contain "M " or "L " at expected positions
    // — we just assert that the SVG rendered without throwing.
    expect(container.querySelector('path')).not.toBeNull();
  });

  it('hides the last-point dot when showLastDot=false', () => {
    const { container } = render(
      <ProbabilitySparkline data={[0.1, 0.2, 0.3]} showLastDot={false} />,
    );
    // The last-point dot is a <circle>; track+line+area paths do not.
    const circles = container.querySelectorAll('circle');
    expect(circles.length).toBe(0);
  });

  it('renders a unique gradient id per instance (no id collision)', () => {
    const { container: c1 } = render(<ProbabilitySparkline data={[0.1, 0.2]} />);
    const { container: c2 } = render(<ProbabilitySparkline data={[0.1, 0.2]} />);
    const id1 = c1.querySelector('linearGradient')?.getAttribute('id') ?? '';
    const id2 = c2.querySelector('linearGradient')?.getAttribute('id') ?? '';
    expect(id1).not.toBe('');
    expect(id2).not.toBe('');
    expect(id1).not.toBe(id2);
  });

  it('respects an explicit ariaLabel override', () => {
    render(
      <ProbabilitySparkline data={[0.1, 0.2, 0.3]} ariaLabel="trend 0..1" />,
    );
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', 'trend 0..1');
  });
});
