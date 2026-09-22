import { readFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';

async function identity(page: Page) {
  const auth = JSON.parse(readFileSync('../backend/.local/personal-browser-auth.json', 'utf8'));
  await page.route('https://fixture.supabase.co/auth/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/otp')) return route.fulfill({ json: {} });
    if (path.endsWith('/logout')) return route.fulfill({ status: 204 });
    if (path.endsWith('/user')) return route.fulfill({ json: auth.user });
    return route.fulfill({ json: { access_token: auth.access_token, token_type: 'bearer',
      expires_in: 3600, refresh_token: 'synthetic-refresh', user: auth.user } });
  });
  await page.goto('/');
  await page.getByLabel('Email', { exact: true }).fill('personal@example.test');
  await page.getByRole('button', { name: 'Email me a sign-in code' }).click();
  await page.getByLabel('Email code').fill('123456');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Let’s work through it.' })).toBeVisible();
  await expect(page.getByText('Checking your Guider connection…')).toHaveCount(0);
  const forget = page.getByRole('button', { name: 'Forget saved key' });
  if (await forget.isVisible()) await forget.click();
  await expect(page.getByLabel('OpenAI API key')).toBeVisible();
}

async function fakeWindow(page: Page, switchOnPick = false) {
  await page.addInitScript(switchOnPick => {
    Object.defineProperty(navigator.mediaDevices, 'getDisplayMedia', { value: async () => {
      const canvas = document.createElement('canvas'); canvas.width = 960; canvas.height = 540;
      const ctx = canvas.getContext('2d')!; ctx.fillStyle = '#123456'; ctx.fillRect(0, 0, 960, 540);
      ctx.fillStyle = 'white'; ctx.font = '30px sans-serif'; ctx.fillText('VS Code', 100, 100);
      const stream = canvas.captureStream(5), track = stream.getVideoTracks()[0];
      Object.defineProperty(track, 'label', { value: 'Synthetic VS Code window' });
      const settings = track.getSettings.bind(track), stop = track.stop.bind(track);
      track.getSettings = () => ({ ...settings(), displaySurface: switchOnPick ? 'browser' : 'window' });
      track.stop = () => { document.documentElement.dataset.captureStopped = 'true'; stop(); };
      if (switchOnPick) {
        Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
        document.dispatchEvent(new Event('visibilitychange'));
      }
      return stream;
    } });
  }, switchOnPick);
}

test('automatic tab sharing survives picker focus changes and temporary frame loss', async ({ page }) => {
  await fakeWindow(page, true);
  await identity(page);
  await page.getByLabel('OpenAI API key').fill('sk-synthetic-personal-browser-key');
  await page.getByRole('checkbox', { name: /Allow my goal/ }).check();
  await page.getByRole('button', { name: 'Connect OpenAI' }).click();
  await page.getByLabel('What would you like to do?').fill('Set up VS Code');
  await page.getByRole('button', { name: 'Analyze and make a plan' }).click();
  await page.getByRole('checkbox', { name: /I reviewed this plan/ }).check();
  await page.getByRole('button', { name: 'Confirm plan', exact: true }).click();
  await page.getByRole('button', { name: 'Choose window and permissions' }).click();
  await page.getByRole('button', { name: 'Choose a window', exact: true }).click();
  const preview = page.getByLabel('Preview of the window Guider will watch');
  await expect.poll(() => preview.evaluate((element: HTMLVideoElement) => element.videoWidth)).toBeGreaterThan(0);
  expect(await page.evaluate(() => document.hidden)).toBe(true);
  await expect(page.locator('html')).not.toHaveAttribute('data-capture-stopped', 'true');
  let frames = 0;
  page.on('request', request => { if (request.url().endsWith('/frames')) frames++; });
  await page.getByLabel('Keep the guide ball visible over other tabs').uncheck();
  await page.getByRole('button', { name: 'Start watching', exact: true }).click();
  const watched = page.getByLabel('Window watched by Guider');
  await watched.evaluate((element: HTMLVideoElement) => {
    const track = (element.srcObject as MediaStream).getVideoTracks()[0];
    Object.defineProperty(track, 'muted', { configurable: true, value: true });
    track.dispatchEvent(new Event('mute'));
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(page.getByText('The shared tab is temporarily unavailable. I’ll continue when its picture returns.')).toBeVisible();
  await expect(page.locator('html')).not.toHaveAttribute('data-capture-stopped', 'true');
  expect(frames).toBe(0);
  await watched.evaluate((element: HTMLVideoElement) => {
    const track = (element.srcObject as MediaStream).getVideoTracks()[0];
    Object.defineProperty(track, 'muted', { configurable: true, value: false });
    track.dispatchEvent(new Event('unmute'));
  });
  await expect(page.getByRole('button', { name: 'I approve this step' })).toBeVisible({ timeout: 15000 });
  expect(frames).toBe(1);
  await expect(page.locator('html')).not.toHaveAttribute('data-capture-stopped', 'true');
  await watched.evaluate((element: HTMLVideoElement) => {
    (element.srcObject as MediaStream).getVideoTracks()[0].dispatchEvent(new Event('ended'));
  });
  await expect(page.locator('html')).toHaveAttribute('data-capture-stopped', 'true');
  await expect(page.getByRole('button', { name: 'Stop sharing', exact: true })).toBeHidden();
});

test('saved key survives refresh; actual API enforces plan consent and step approval', async ({ page }) => {
  await fakeWindow(page);
  await identity(page);
  await page.getByLabel('OpenAI API key').fill('sk-synthetic-personal-browser-key');
  await expect(page.getByLabel('Remember this key securely')).toBeChecked();
  await page.getByRole('checkbox', { name: /Allow my goal/ }).check();
  await page.getByRole('button', { name: 'Connect OpenAI' }).click();
  await expect(page.getByRole('button', { name: 'Disconnect', exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Use saved OpenAI key' })).toBeVisible();
  await expect(page.getByLabel('OpenAI API key')).toHaveCount(0);
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage })))
    .not.toContain('sk-synthetic-personal-browser-key');
  await page.getByRole('checkbox', { name: /Allow my goal/ }).check();
  await page.getByRole('button', { name: 'Use saved OpenAI key' }).click();
  await page.getByLabel('What would you like to do?').fill('Set up VS Code');
  await page.getByLabel('Paste steps you already have').fill('Open the official website, then install VS Code.');
  await page.getByRole('button', { name: 'Analyze and make a plan' }).click();
  await expect(page.getByRole('button', { name: 'Confirm plan', exact: true })).toBeDisabled();
  await page.getByRole('checkbox', { name: /I reviewed this plan/ }).check();
  await page.getByRole('button', { name: 'Confirm plan', exact: true }).click();
  let frames = 0;
  page.on('request', request => { if (request.url().endsWith('/frames')) frames++; });
  await page.getByRole('button', { name: 'Choose window and permissions' }).click();
  await expect(page.getByText(/automatically send selected, masked screenshots to OpenAI/)).toBeVisible();
  expect(frames).toBe(0);
  await page.getByRole('button', { name: 'Choose a window', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Hide anything Guider should not see.' })).toBeVisible();
  expect(frames).toBe(0);
  await page.getByLabel('Keep the guide ball visible over other tabs').uncheck();
  await page.getByRole('button', { name: 'Start watching', exact: true }).click();
  await expect(page.getByRole('button', { name: 'I approve this step' })).toBeVisible({ timeout: 15000 });
  const assistant = page.getByRole('complementary', { name: 'Guide assistant' });
  await expect(assistant.getByText('Step complete — one quick approval')).toBeVisible();
  await expect(assistant.locator('img, video')).toHaveCount(0);
  expect(frames).toBe(1);
  await page.screenshot({ path: 'test-results/personal/automatic-guidance.png', fullPage: true });
  await page.getByRole('button', { name: 'I approve this step' }).click();
  await expect(page.getByText('Plan complete. Screen sharing has stopped.')).toBeVisible({ timeout: 20000 });
  await expect(assistant.getByText('You’re all done!')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-capture-stopped', 'true');
  expect(frames).toBe(2);
  await page.getByRole('button', { name: 'Forget key', exact: true }).click();
  await expect(page.getByLabel('OpenAI API key')).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('OpenAI API key')).toBeVisible();
});

test('screen arrow stays on the preview; round button opens pause and exit options', async ({ page }) => {
  await fakeWindow(page);
  await identity(page);
  // This UI scenario controls the model's proposed target; other tests exercise the real API.
  let currentPlan: Record<string, unknown>;
  page.on('response', async response => {
    if (response.url().endsWith('/watch') && response.request().method() === 'POST' && response.ok()) {
      currentPlan = await response.json();
    }
  });
  await page.route('**/plans/*/frames', async route => {
    await route.fulfill({ json: { plan: currentPlan, advanced: false, guidance: {
      observation: 'The page is visible.', action: 'Click the Windows download button.',
      where: 'Look in the center of the shared window.', step_complete: false, confidence: 0.99,
      target: { x: 0.5, y: 0.4, label: 'Windows download' }, disposition: 'guide',
    } } });
  });
  await page.getByLabel('OpenAI API key').fill('sk-synthetic-personal-browser-key');
  await page.getByRole('checkbox', { name: /Allow my goal/ }).check();
  await page.getByRole('button', { name: 'Connect OpenAI' }).click();
  await page.getByLabel('What would you like to do?').fill('Set up VS Code');
  await page.getByRole('button', { name: 'Analyze and make a plan' }).click();
  await page.getByRole('checkbox', { name: /I reviewed this plan/ }).check();
  await page.getByRole('button', { name: 'Confirm plan', exact: true }).click();
  await page.getByRole('button', { name: 'Choose window and permissions' }).click();
  await page.getByRole('button', { name: 'Choose a window', exact: true }).click();
  await page.getByLabel('Keep the guide ball visible over other tabs').uncheck();
  await page.getByRole('button', { name: 'Start watching', exact: true }).click();
  const assistant = page.getByRole('complementary', { name: 'Guide assistant' });
  await expect(assistant.getByText('Click the Windows download button.')).toBeVisible();
  const hint = page.getByRole('note', { name: 'Screen hint: Windows download' });
  await expect(hint).toBeVisible();
  await expect(assistant.locator('img, video')).toHaveCount(0);
  expect(await hint.evaluate(element => element.closest('.personal-video') !== null)).toBe(true);
  const bounds = await page.getByRole('button', { name: 'Open guide options' }).boundingBox();
  expect(bounds?.width).toBe(56);
  expect(bounds?.height).toBe(56);
  await page.locator('.personal-preview').scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'test-results/personal/guide-ball-and-arrow.png' });
  await page.getByRole('button', { name: 'Dismiss guide message' }).click();
  await expect(page.getByRole('region', { name: 'Guide message' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Open guide options' }).click();
  await page.getByRole('button', { name: 'Show current step' }).click();
  await expect(assistant.getByText('Click the Windows download button.')).toBeVisible();
  await page.getByRole('button', { name: 'Open guide options' }).click();
  await page.getByRole('button', { name: 'Pause guidance', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-capture-stopped', 'true');
  await expect(hint).toHaveCount(0);
  await expect(assistant.getByText('Sharing is off')).toBeVisible();
  await page.getByRole('button', { name: 'Open guide options' }).click();
  await page.getByRole('button', { name: 'Exit guide', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Use saved OpenAI key' })).toBeVisible();
  await expect(assistant).toHaveCount(0);
  await page.getByRole('button', { name: 'Forget saved key' }).click();
  await expect(page.getByLabel('OpenAI API key')).toBeVisible();
});

test('closing the real floating window and signing out both stop capture', async ({ page }) => {
  await fakeWindow(page);
  await identity(page);
  await page.getByLabel('OpenAI API key').fill('sk-synthetic-personal-browser-key');
  await page.getByRole('checkbox', { name: /Allow my goal/ }).check();
  await page.getByRole('button', { name: 'Connect OpenAI' }).click();
  await page.getByLabel('What would you like to do?').fill('Set up VS Code');
  await page.getByRole('button', { name: 'Analyze and make a plan' }).click();
  await page.getByRole('checkbox', { name: /I reviewed this plan/ }).check();
  await page.getByRole('button', { name: 'Confirm plan', exact: true }).click();
  await page.getByRole('button', { name: 'Choose window and permissions' }).click();
  await page.getByRole('button', { name: 'Choose a window', exact: true }).click();
  await expect(page.getByLabel('Keep the guide ball visible over other tabs')).toBeChecked();
  await page.getByRole('button', { name: 'Start watching', exact: true }).click();
  await expect.poll(() => page.evaluate(() => Boolean(
    (window as unknown as { documentPictureInPicture: { window: Window | null } }).documentPictureInPicture.window,
  ))).toBe(true);
  await expect.poll(() => page.evaluate(() => {
    const popup = (window as unknown as { documentPictureInPicture: { window: Window } }).documentPictureInPicture.window;
    const ball = popup.document.querySelector('.guide-assistant-ball')?.getBoundingClientRect();
    return { width: ball?.width, height: ball?.height, media: popup.document.querySelectorAll('img, video').length };
  })).toEqual({ width: 56, height: 56, media: 0 });
  await expect(page.getByRole('button', { name: 'Stop sharing', exact: true })).toBeVisible();
  await page.evaluate(() => {
    (window as unknown as { documentPictureInPicture: { window: Window } }).documentPictureInPicture.window.close();
  });
  await expect(page.getByRole('complementary', { name: 'Guide assistant' }).getByText('Floating control closed. Sharing stopped.')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-capture-stopped', 'true');
  await page.evaluate(() => delete document.documentElement.dataset.captureStopped);
  await page.getByRole('button', { name: 'Choose window and permissions' }).click();
  await page.getByRole('button', { name: 'Choose a window', exact: true }).click();
  await page.getByRole('button', { name: 'Start watching', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Stop sharing', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your guide, on any computer.' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-capture-stopped', 'true');
});
