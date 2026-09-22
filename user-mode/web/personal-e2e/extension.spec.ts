import { cpSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium, expect, test } from '@playwright/test';

test('installed extension guides the captured tab, clears stale arrows and stops from its ball', async ({}, testInfo) => {
  test.setTimeout(120000);
  const extension = testInfo.outputPath('extension');
  mkdirSync(extension, { recursive: true }); cpSync(resolve('../extension'), extension, { recursive: true });
  // Test-only host grant replaces clicking the browser toolbar, which Playwright
  // cannot drive. The distributed extension only has activeTab + scripting.
  const manifest = JSON.parse(readFileSync(resolve(extension, 'manifest.json'), 'utf8'));
  manifest.host_permissions = ['http://127.0.0.1/*'];
  writeFileSync(resolve(extension, 'manifest.json'), JSON.stringify(manifest));
  const context = await chromium.launchPersistentContext(testInfo.outputPath('profile'), {
    headless: true, channel: 'chromium', executablePath: process.env.GUIDE_EXTENSION_BROWSER,
    args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`,
      '--auto-select-tab-capture-source-by-title=Guider Extension Target'],
    viewport: { width: 1100, height: 800 },
  });
  try {
    const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
    const extensionId = new URL(worker.url()).host;
    const page = await context.newPage();
    const auth = JSON.parse(readFileSync('../backend/.local/personal-browser-auth.json', 'utf8'));
    await page.route('https://fixture.supabase.co/auth/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith('/otp')) return route.fulfill({ json: {} });
      if (path.endsWith('/user')) return route.fulfill({ json: auth.user });
      return route.fulfill({ json: { access_token: auth.access_token, token_type: 'bearer',
        expires_in: 3600, refresh_token: 'synthetic-refresh', user: auth.user } });
    });
    await page.goto('http://127.0.0.1:5175/');
    await page.getByLabel('Email', { exact: true }).fill('personal@example.test');
    await page.getByRole('button', { name: 'Email me a sign-in code' }).click();
    await page.getByLabel('Email code').fill('123456');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Let’s work through it.' })).toBeVisible();
    await expect(page.getByText('Checking your Guider connection…')).toHaveCount(0);
    if (await page.getByRole('button', { name: 'Forget saved key' }).isVisible()) await page.getByRole('button', { name: 'Forget saved key' }).click();
    await page.getByLabel('OpenAI API key').fill('sk-synthetic-personal-browser-key');
    await page.getByRole('checkbox', { name: /Allow my goal/ }).check();
    await page.getByRole('button', { name: 'Connect OpenAI' }).click();
    await page.getByLabel('What would you like to do?').fill('Set up VS Code');
    await page.getByRole('button', { name: 'Analyze and make a plan' }).click();
    await page.getByRole('checkbox', { name: /I reviewed this plan/ }).check();
    await page.getByRole('button', { name: 'Confirm plan', exact: true }).click();

    const target = await context.newPage();
    await target.route('**/extension-target', route => route.fulfill({ contentType: 'text/html', body:
      '<!doctype html><title>Guider Extension Target</title><body style="margin:0;background:#f2f6fa;font:20px system-ui;height:2000px"><h1>VS Code setup</h1><button style="position:fixed;left:45%;top:36%;padding:24px">Windows download</button></body>' }));
    await target.goto('http://127.0.0.1:5175/extension-target');
    const popup = await context.newPage(); await popup.goto(`chrome-extension://${extensionId}/popup.html`);
    const bind = (type: string, url: string) => popup.evaluate(async ({ type, url }) => {
      const api = (globalThis as any).chrome;
      const [tab] = await api.tabs.query({ url });
      return api.runtime.sendMessage({ type, tabId: tab.id });
    }, { type, url });
    expect((await bind('connect-controller', 'http://127.0.0.1:5175/')).message).toContain('Guider connected');
    await expect(page.getByText(/Extension connected\. Open the website/)).toBeVisible();
    expect((await bind('connect-target', target.url())).message).toContain('Guide ball enabled');
    await expect(page.getByText(/Tab guide ready: Guider Extension Target/)).toBeVisible();
    await expect(target.getByRole('button', { name: 'Open guide options' })).toBeVisible();
    let currentPlan: Record<string, unknown>, frames = 0, lastPixels = '';
    page.on('response', async response => {
      if (response.url().endsWith('/watch') && response.request().method() === 'POST' && response.ok()) currentPlan = await response.json();
    });
    await page.route('**/plans/*/frames', async route => {
      frames++; lastPixels = route.request().postDataJSON().image_base64;
      return route.fulfill({ json: { plan: currentPlan, advanced: false, guidance: {
        observation: 'The download page is visible.', action: 'Click the Windows download button.',
        where: 'Near the center of this tab.', step_complete: false, confidence: .99,
        target: { x: .5, y: .4, label: 'Windows download' }, disposition: 'guide',
      } } });
    });
    await page.bringToFront();
    await page.getByRole('button', { name: 'Choose window and permissions' }).click();
    await page.getByRole('button', { name: 'Choose a window', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Hide anything Guider should not see.' })).toBeVisible();
    await page.getByRole('button', { name: 'Start watching', exact: true }).click();
    await target.bringToFront();
    const hint = target.getByRole('note', { name: 'Screen hint: Windows download' });
    await expect(hint).toBeVisible({ timeout: 30000 });
    await expect(target.getByText('Click the Windows download button.')).toBeVisible();
    const bounds = await target.getByRole('button', { name: 'Open guide options' }).boundingBox();
    expect(bounds?.width).toBe(56); expect(bounds?.height).toBe(56);
    expect(frames).toBeGreaterThan(0);
    const pixel = await page.evaluate(async encoded => {
      const image = new Image(); image.src = `data:image/jpeg;base64,${encoded}`; await image.decode();
      const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
      const ctx = canvas.getContext('2d')!; ctx.drawImage(image, 0, 0);
      return Array.from(ctx.getImageData(image.width - 48, image.height - 48, 1, 1).data).slice(0, 3);
    }, lastPixels);
    expect(pixel.every((value, index) => Math.abs(value - [242, 246, 250][index]) < 10)).toBe(true);
    await target.screenshot({ path: testInfo.outputPath('guidance-on-shared-tab.png') });
    await target.evaluate(() => window.scrollTo(0, 180));
    await expect(hint).toBeHidden();
    await target.getByRole('button', { name: 'Open guide options' }).click();
    await target.getByRole('button', { name: 'Stop screen sharing', exact: true }).click();
    await expect(target.getByText('Sharing is off', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Stop sharing', exact: true })).toBeHidden();
    // A mismatched capture identity must never send a frame or guide another tab.
    const stoppedFrames = frames;
    await page.bringToFront();
    await page.getByRole('button', { name: 'Choose window and permissions' }).click();
    await page.getByRole('button', { name: 'Choose a window', exact: true }).click();
    await page.getByLabel('Preview of the window Guider will watch').evaluate((video: HTMLVideoElement) => {
      const track = (video.srcObject as MediaStream).getVideoTracks()[0];
      Object.defineProperty(track, 'getCaptureHandle', { value: () => ({ handle: 'another-tab' }) });
    });
    await page.getByRole('button', { name: 'Start watching', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Share the exact browser tab');
    expect(frames).toBe(stoppedFrames);

    await page.getByRole('button', { name: 'Choose window and permissions' }).click();
    await page.getByRole('button', { name: 'Choose a window', exact: true }).click();
    await page.getByRole('button', { name: 'Start watching', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Stop sharing', exact: true })).toBeVisible();
    await target.reload();
    await expect(page.getByRole('button', { name: 'Stop sharing', exact: true })).toBeHidden();
    await expect(target.locator('[data-guider-overlay]')).toHaveCount(0);
    // Re-enable after navigation, then verify Exit removes the injected UI.
    expect((await bind('connect-target', target.url())).message).toContain('Guide ball enabled');
    await expect(target.getByRole('button', { name: 'Open guide options' })).toBeVisible();
    await target.getByRole('button', { name: 'Open guide options' }).click();
    await target.getByRole('button', { name: 'Exit guide', exact: true }).click();
    await expect(target.locator('[data-guider-overlay]')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Use saved OpenAI key' })).toBeVisible();
  } finally { await context.close(); }
});
