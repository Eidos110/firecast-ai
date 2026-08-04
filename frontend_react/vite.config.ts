import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // SPA standalone (no longer a Streamlit component) — base still relative
  // so the bundle works behind arbitrary reverse-proxy path prefixes.
  base: './',
  build: {
    outDir: 'build',
    rollupOptions: {
      output: {
        // Stable, predictable file names so post-deploy caches hit.
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name].[ext]',
        manualChunks: {
          'vendor-leaflet': ['leaflet'],
          'vendor-leaflet-draw': ['leaflet-draw'],
          'vendor-react': ['react', 'react-dom'],
          'vendor-charts': ['recharts'],
          'vendor-query': ['@tanstack/react-query'],
        },
      },
    },
    chunkSizeWarningLimit: 900,
  },
  server: {
    port: 3000,
    // Proxy API calls to the FastAPI backend during dev (start_api.py runs :8000).
    proxy: {
      '/predict': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/api': 'http://localhost:8000',
      '/geo': 'http://localhost:8000',
      '/analytics': 'http://localhost:8000',
    },
  },
})
