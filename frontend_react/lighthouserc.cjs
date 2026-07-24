// Lighthouse CI configuration — Audit priority 5.
// Run: npx @lhci/cli autorun  OR  npm run lhci
// In CI this is invoked against the Streamlit dev server (port 8501) and the
// vite preview server (port 4173) to cover both the Streamlit shell and the
// React component-kit bundle. Score thresholds are intentionally lenient to
// keep the audit informational rather than blocking the build; tighten once
// the baselines are stable.
//
// Requires Node 18+ and either Chrome (CI installs puppeteer's chrome) or
// the system chrome. See package.json "lhci" script.

/** @type {import('@lhci/types').LhciConfig} */
module.exports = {
  ci: {
    collect: {
      // The vite preview server hosts the React component-kit only.
      // For Streamlit we'd use 8501, but lhci does not handle python servers
      // gracefully across CI matrices, so we only measure the React bundle
      // (which is the one most likely to regress on bundle size).
      url: ['http://localhost:4173/'],
      startServerCommand: 'npm run preview -- --port 4173 --strictPort',
      startServerReadyPattern: 'Local:',
      numberOfRuns: 3,
      // Skip chrome install if puppeteer already provides one.
      settings: {
        preset: 'desktop',
        // Disable emulated mobile throttle for the React shell — Streamlit
        // is desktop-first; the React component is embedded in an iframe.
      },
    },
    assert: {
      // Informational baseline. Tighten the floor scores after a few real
      // runs to lock in performance gains (e.g. after image lazy-loading).
      assertions: {
        'categories:performance': ['warn', { minScore: 0.6 }],
        'categories:accessibility': ['error', { minScore: 0.85 }],
        'categories:best-practices': ['warn', { minScore: 0.85 }],
        'categories:seo': ['warn', { minScore: 0.8 }],
      },
    },
    upload: {
      // Save the run artifacts to /.lighthouseci so engineers can diff
      // locally between commits. CI can also publish to a public dashboard
      // when a token is provided via LHCI_SERVER_TOKEN.
      target: 'filesystem',
      outputDir: '.lighthouseci',
      reportFilenamePattern: '%%PATHNAME%%-%%DATETIME%%-report.%%EXTENSION%%',
    },
  },
};
