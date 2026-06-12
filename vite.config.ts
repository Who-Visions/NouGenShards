import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Frontend lives in ui/; build output goes to dist/ (tauri.conf frontendDist).
export default defineConfig({
  root: 'ui',
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    target: 'chrome105',
  },
});
