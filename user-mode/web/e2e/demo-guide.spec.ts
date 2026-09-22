import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

async function openDemo(page: Page) {
  await page.goto('/#live');
  await expect(page.getByRole('heading', { name: 'Open Settings.', exact: true })).toBeVisible();
}

async function select(page: Page, name: string, next: string) {
  await page.getByRole('button', { name, exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Checking sample change' })).toBeVisible();
  await expect(page.getByRole('heading', { name: next, exact: true })).toBeVisible();
}

test('sample clicks automatically verify, move hints, finish and replay without cloud requests', async ({ page }, testInfo) => {
  let requests = 0;
  await page.route('**/api/v1/local-guide/**', route => { requests++; return route.abort(); });
  await page.setViewportSize({ width: 1440, height: 1050 });
  await openDemo(page);
  await expect(page.getByLabel('OpenAI API key')).toHaveCount(0);
  await expect(page.getByRole('note')).toContainText('Click Settings here');
  await page.getByRole('button', { name: 'Open sample notes' }).click();
  await expect(page.getByText('Try Settings, marked by the green outline.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Open Settings.', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('automatic-hints-desktop.png'), fullPage: true, animations: 'disabled' });
  await select(page, 'Settings', 'Choose Appearance.');
  await expect(page.getByRole('note')).toContainText('Click Appearance');
  await select(page, 'Appearance', 'Select the dark theme.');
  await expect(page.getByRole('note')).toContainText('Tap Dark theme');
  await page.screenshot({ path: testInfo.outputPath('theme-hint-desktop.png'), fullPage: true, animations: 'disabled' });
  await select(page, 'Dark theme', 'Save the change.');
  await expect(page.getByLabel('Interactive sample app')).toHaveClass(/theme-dark/);
  await expect(page.getByRole('note')).toContainText('Click Save changes');
  await select(page, 'Save changes', 'The sample task is complete.');
  await expect(page.getByText('Appearance saved · Dark', { exact: true })).toBeVisible();
  await expect(page.getByRole('note')).toHaveCount(0);
  await page.getByRole('button', { name: 'Replay demo', exact: true }).click();
  await expect(page.getByLabel('Interactive sample app')).toHaveClass(/theme-light/);
  await expect(page.getByRole('note')).toContainText('Click Settings here');
  expect(requests).toBe(0);
});

test('automatic playback pauses, resumes and completes all sample actions', async ({ page }) => {
  await openDemo(page);
  await page.getByRole('button', { name: 'Watch automatically', exact: true }).click();
  await page.getByRole('button', { name: 'Pause guide', exact: true }).click();
  await expect(page.getByRole('note')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Settings', exact: true })).toBeDisabled();
  // Wait beyond the playback deadline to prove pause cancels scheduled actions.
  await page.waitForTimeout(2800);
  await expect(page.getByLabel('Interactive sample app')).toContainText('Make this workspace');
  await page.getByRole('button', { name: 'Resume guide', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'The sample task is complete.' })).toBeVisible({ timeout: 20000 });
  await expect(page.getByText('Appearance saved · Dark', { exact: true })).toBeVisible();
});

test('pause during verification and restart discard pending progression', async ({ page }) => {
  await openDemo(page);
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await page.getByRole('button', { name: 'Pause guide', exact: true }).click();
  await page.waitForTimeout(1300);
  await expect(page.getByRole('listitem').filter({ hasText: 'Settings' })).toHaveAttribute('aria-current', 'step');
  await page.getByRole('button', { name: 'Resume guide', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Choose Appearance.' })).toBeVisible();
  await page.getByRole('button', { name: 'Appearance', exact: true }).click();
  await page.getByRole('button', { name: 'Start over', exact: true }).click();
  await page.waitForTimeout(1300);
  await expect(page.getByRole('heading', { name: 'Open Settings.', exact: true })).toBeVisible();
  await expect(page.getByRole('note')).toContainText('Click Settings here');
});

test('mirroring shows an interactive demo overlay and closes tracks on stop and mode change', async ({ page }, testInfo) => {
  let requests = 0;
  await page.route('**/api/v1/local-guide/**', route => { requests++; return route.abort(); });
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getDisplayMedia', { value: async () => {
      const canvas = document.createElement('canvas'); canvas.width = 960; canvas.height = 700;
      const ctx = canvas.getContext('2d')!;
      ctx.fillStyle = '#21364a'; ctx.fillRect(0, 0, 960, 700);
      ctx.fillStyle = '#afcee5'; ctx.font = '28px sans-serif'; ctx.fillText('Your mirrored window', 25, 55);
      const stream = canvas.captureStream(5), track = stream.getVideoTracks()[0];
      const stop = track.stop.bind(track), settings = track.getSettings.bind(track);
      track.stop = () => { document.documentElement.dataset.captureStopped = 'true'; stop(); };
      Object.defineProperty(track, 'label', { value: 'Synthetic browser window' });
      track.getSettings = () => ({ ...settings(), displaySurface: 'window' });
      return stream;
    } });
  });
  await page.setViewportSize({ width: 1440, height: 1050 });
  await openDemo(page);
  await page.getByRole('button', { name: 'Mirror my window', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Mirroring on' })).toBeVisible();
  await expect(page.getByLabel('Local mirrored window')).toBeVisible();
  await expect(page.getByText('Practice overlay', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Resume guide', exact: true }).click();
  await select(page, 'Settings', 'Choose Appearance.');
  await page.screenshot({ path: testInfo.outputPath('mirrored-practice-overlay.png'), fullPage: true, animations: 'disabled' });
  await page.getByRole('button', { name: 'Fullscreen demo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Exit fullscreen demo', exact: true })).toBeVisible();
  await expect(page.getByRole('note')).toContainText('Click Appearance');
  await page.getByRole('button', { name: 'Exit fullscreen demo', exact: true }).click();
  await page.getByRole('button', { name: 'Change window', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-capture-stopped', 'true');
  await expect(page.getByRole('status').filter({ hasText: 'Mirroring on' })).toBeVisible();
  await page.getByRole('button', { name: 'Stop mirroring', exact: true }).click();
  await expect(page.getByLabel('Local mirrored window')).toBeHidden();
  await expect(page.getByRole('button', { name: 'Resume guide', exact: true })).toBeVisible();
  await expect(page.getByRole('note')).toHaveCount(0);
  await page.getByRole('button', { name: 'Mirror my window', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Mirroring on' })).toBeVisible();
  await page.evaluate(() => { delete document.documentElement.dataset.captureStopped; });
  await page.getByRole('button', { name: 'AI screen guide', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-capture-stopped', 'true');
  expect(requests).toBe(0);
});

test('mobile hints stay inside the preview and all sample controls work by keyboard', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openDemo(page);
  for (const [name, next] of [['Settings', 'Choose Appearance.'], ['Appearance', 'Select the dark theme.'], ['Dark theme', 'Save the change.'], ['Save changes', 'The sample task is complete.']]) {
    const hint = await page.getByRole('note').boundingBox();
    expect(hint).not.toBeNull();
    expect(hint!.x).toBeGreaterThanOrEqual(0);
    expect(hint!.x + hint!.width).toBeLessThanOrEqual(390);
    await page.getByRole('button', { name, exact: true }).focus();
    if (name === 'Dark theme') await page.screenshot({ path: testInfo.outputPath('mobile-theme-hint.png'), fullPage: true, animations: 'disabled' });
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: next, exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('dismissed mirror picker leaves the practice app resumable', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getDisplayMedia', { value: async () => { throw new DOMException('Dismissed', 'NotAllowedError'); } });
  });
  await openDemo(page);
  await page.getByRole('button', { name: 'Mirror my window', exact: true }).click();
  await expect(page.getByText('No window selected. Resume the practice demo whenever you are ready.')).toBeVisible();
  await page.getByRole('button', { name: 'Resume guide', exact: true }).click();
  await select(page, 'Settings', 'Choose Appearance.');
});
