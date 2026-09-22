import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './personal-e2e', outputDir: './test-results/personal', workers: 1, fullyParallel: false,
  timeout: 60000,
  use: { baseURL: 'http://127.0.0.1:5175', headless: true, channel: process.env.GUIDE_BROWSER_CHANNEL },
  webServer: [
    { command: `${process.platform === 'win32' ? '.venv\\Scripts\\python.exe' : '.venv/bin/python'} -m tests.personal_browser_server`, cwd: '../backend', url: 'http://127.0.0.1:8002/health', reuseExistingServer: false },
    { command: 'npm run dev -- --port 5175', url: 'http://127.0.0.1:5175', reuseExistingServer: false,
      env: { VITE_SUPABASE_URL: 'https://fixture.supabase.co', VITE_SUPABASE_PUBLISHABLE_KEY: 'synthetic-publishable-key',
        VITE_PERSONAL_API_URL: 'http://127.0.0.1:8002/api/v1/local-guide' } },
  ],
});
