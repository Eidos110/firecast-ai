import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Force apache-arrow to use browser build
      'apache-arrow': resolve(__dirname, 'node_modules/apache-arrow/Arrow.dom.js')
    }
  },
  base: './',  // Use relative paths for assets (required for Streamlit components)
  build: {
    outDir: 'build',
    // Audit priority 5 — code-split the vendor bundles so the app entry
    // loads faster on slow mobile links. Leaflet alone is ~140 KB gzipped
    // and pulls its own CSS; isolating it lets app code updates ship
    // without invalidating the leaflet chunk hash.
    rollupOptions: {
      output: {
        // Keep file names human-friendly for debugging; hash-less chunk
        // names are required for the Streamlit static-component loader.
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name].[ext]',
        manualChunks: {
          // External mapping lib — heavy, rarely changes.
          'vendor-leaflet': ['leaflet'],
          'vendor-leaflet-draw': ['leaflet-draw'],
          // React + ReactDOM are imported once; isolating shrinks app code
          // diff churn (no repo-wide bundle bump when only deps bump).
          'vendor-react': ['react', 'react-dom'],
          // Streamlit component bridge — stable boundary; isolates its
          // postMessage wiring from app bundle.
          'vendor-streamlit': ['streamlit-component-lib']
        }
      }
    },
    // Bump threshold so vendor chunks don't trigger a warning.
    chunkSizeWarningLimit: 700
  },
  server: {
    port: 3000
  }
})