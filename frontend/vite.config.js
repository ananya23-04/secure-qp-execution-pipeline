import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const api = 'http://localhost:8000';

export default defineConfig({
  base: '/app/',                       // the API container serves the build under /app/
  plugins: [react()],
  build: { outDir: '../backend/app/static', emptyOutDir: true },
  server: {                            // `npm run dev` proxies API calls to the running backend
    proxy: Object.fromEntries(['/auth', '/submissions', '/review', '/moderation', '/pipeline', '/exams', '/health']
      .map((p) => [p, api])),
  },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/setupTests.js'] },
});
