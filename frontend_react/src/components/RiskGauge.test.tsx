// RiskGauge component tests — Fase 5 quality gate.
// Validates: score clamping, risk-tier mapping, accessibility labels, SVG arc math.
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RiskGauge } from './RiskGauge';

describe('<RiskGauge />', () => {
  it('renders a low-risk gauge for score=0.1', () => {
    render(<RiskGauge score={0.1} />);
    const gauge = screen.getByRole('img');
    expect(gauge).toBeInTheDocument();
    // aria-label includes "10 percent" (tokens emit spelled-out percent).
    expect(gauge.getAttribute('aria-label')).toMatch(/10 percent/);
    expect(gauge.getAttribute('aria-label')).toMatch(/Low/);
  });

  it('clamps scores above 1 to 100% (extreme risk)', () => {
    render(<RiskGauge score={1.5} />);
    const gauge = screen.getByRole('img');
    expect(gauge.getAttribute('aria-label')).toMatch(/100 percent/);
    expect(gauge.getAttribute('aria-label')).toMatch(/Extreme/);
  });

  it('clamps negative scores to 0% (low risk)', () => {
    render(<RiskGauge score={-0.4} />);
    const gauge = screen.getByRole('img');
    expect(gauge.getAttribute('aria-label')).toMatch(/0 percent/);
    expect(gauge.getAttribute('aria-label')).toMatch(/Low/);
  });

  it('treats NaN as 0% (defensive default)', () => {
    render(<RiskGauge score={Number.NaN} />);
    const gauge = screen.getByRole('img');
    expect(gauge.getAttribute('aria-label')).toMatch(/0 percent/);
  });

  it('uses the tier boundary 0.5 to flip to "High"', () => {
    render(<RiskGauge score={0.5} />);
    const gauge = screen.getByRole('img');
    expect(gauge.getAttribute('aria-label')).toMatch(/High/);
  });

  it('respects an explicit ariaLabel override', () => {
    render(<RiskGauge score={0.42} ariaLabel="custom aria" />);
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', 'custom aria');
  });

  it('hides the centre label when showLabel is false', () => {
    const { container } = render(<RiskGauge score={0.7} showLabel={false} />);
    // When hidden, no percent text node is rendered.
    expect(container.textContent).not.toMatch(/70 percent/);
  });

  it('renders two concentric circles (track + value arc)', () => {
    const { container } = render(<RiskGauge score={0.6} />);
    const circles = container.querySelectorAll('circle');
    expect(circles.length).toBe(2);
  });
});
