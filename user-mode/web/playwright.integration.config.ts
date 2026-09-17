import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './integration', outputDir: './test-results/integration', workers: 1, fullyParallel: false,
  use: { baseURL: 'http://127.0.0.1:5174', headless: true, channel: process.env.GUIDE_BROWSER_CHANNEL },
  webServer: [
    { command: 'uv run python -m tests.browser_server', cwd: '../backend',
      url: 'http://127.0.0.1:8001/openapi.json', reuseExistingServer: false },
    { command: 'npm run dev -- --port 5174', url: 'http://127.0.0.1:5174', reuseExistingServer: false,
      env: { VITE_SUPABASE_URL: 'https://fixture.supabase.co',
        VITE_SUPABASE_PUBLISHABLE_KEY: 'synthetic-publishable-key',
        VITE_API_URL: 'http://127.0.0.1:8001/api/v1/guide' } },
  ],
});
