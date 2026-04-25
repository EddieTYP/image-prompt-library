import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({ root: 'frontend', plugins: [react()], server: { port: 5177, proxy: { '/api': 'http://127.0.0.1:8787', '/media': 'http://127.0.0.1:8787' } }, build: { outDir: 'dist', emptyOutDir: true } });
