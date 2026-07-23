/* eslint-disable */
/**
 * Tailwind config for the FireCast React component kit (Fase 4).
 *
 * Reads design tokens from `../frontend/themes/tokens.json` so that Tailwind
 * utility classes & arbitrary references stay in sync with the single source
 * of truth shared by the Streamlit shell (Python `theme.py`) and the React
 * shell (`theme/tokens.ts`).
 *
 * The PostCSS plugin is NOT required to be installed for the existing Streamlit
 * component build (Vite drops it); this file is a ready-to-use scaffold for
 * projects that bring in tailwindcss. If `tailwindcss` is installed, you can run
 * `npx tailwind -c tailwind.config.cjs -i src/index.css -o dist/tw.css --minify`.
 */
const tokens = require('../frontend/themes/tokens.json');

function val(node) {
  if (node && typeof node === 'object' && 'value' in node) return node.value;
  return node;
}
function section(name) {
  const node = tokens[name] || {};
  const out = {};
  for (const [k, v] of Object.entries(node)) {
    if (typeof k === 'string' && k.startsWith('$')) continue;
    out[k] = val(v);
  }
  return out;
}
function nested(sectionName) {
  const node = tokens[sectionName] || {};
  const out = {};
  for (const [groupKey, groupVal] of Object.entries(node)) {
    if (typeof groupKey === 'string' && groupKey.startsWith('$')) continue;
    if (!groupVal || typeof groupVal !== 'object') continue;
    const sub = {};
    for (const [k, v] of Object.entries(groupVal)) {
      if (typeof k === 'string' && k.startsWith('$')) continue;
      sub[k] = val(v);
    }
    out[groupKey] = sub;
  }
  return out;
}

const riskColors = section('color')?.risk || {};
const riskBgColors = section('color')?.risk_bg || {};
const dark = section('color')?.dark || {};
const light = section('color')?.light || {};
const base = section('color')?.base || {};
const spacing = section('spacing');
const radius = section('radius');
const shadow = section('shadow');
const typography = section('typography');

module.exports = {
  content: ['./src/**/*.{ts,tsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        // Brand + accessibility palette (mirrors `theme.PALETTE`).
        primary: val(base.primary),
        'primary-light': val(base.primary_light),
        'primary-dark': val(base.primary_dark),
        accent: val(base.accent),
        success: val(base.success),
        info: val(base.info),
        warning: val(base.warning),
        error: val(base.error),
        // Risk tier colours — pull from `risk` section so the map keeps "rendah/sedang/..." semantics.
        'risk-rendah': riskColors.rendah,
        'risk-sedang': riskColors.sedang,
        'risk-tinggi': riskColors.tinggi,
        'risk-sangat-tinggi': riskColors.sangat_tinggi,
        // Dark-mode surface tokens (default; light via [data-theme=light]).
        surface: dark.surface,
        'surface-hover': dark.surface_hover,
        background: dark.background,
        text: dark.text,
        'text-secondary': dark.text_secondary,
        'text-muted': dark.text_muted,
        border: dark.border,
      },
      spacing,
      borderRadius: radius,
      boxShadow: shadow,
      fontFamily: {
        sans: typography.font_primary,
        mono: typography.font_secondary,
      },
      fontSize: typography.font_size,
      minHeight: {
        touch: (section('a11y') || {}).touch_target_min || '44px',
      },
      backgroundImage: {
        'risk-rendah': riskBgColors.rendah,
        'risk-sedang': riskBgColors.sedang,
        'risk-tinggi': riskBgColors.tinggi,
        'risk-sangat-tinggi': riskBgColors.sangat_tinggi,
      },
    },
  },
  plugins: [],
};
