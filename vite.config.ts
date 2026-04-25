import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const backendHost = process.env.BACKEND_HOST || '127.0.0.1';
const backendPort = process.env.BACKEND_PORT || '8000';
const frontendPort = Number(process.env.FRONTEND_PORT || '5177');
const backendProxyTarget = `http://${backendHost}:${backendPort}`;

export default defineConfig({
  root: 'frontend',
  plugins: [react()],
  server: {
    port: frontendPort,
    proxy: {
      '/api': backendProxyTarget,
      '/media': backendProxyTarget,
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
});
