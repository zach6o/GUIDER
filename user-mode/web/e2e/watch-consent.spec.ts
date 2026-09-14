/**
 * The consent surface, driven the way a person drives it.
 *
 * The demo has no backend and no vision provider, so it cannot watch anything —
 * and says so rather than simulating a verdict about a real screen. What these
 * scenarios cover is everything before that point: the notice is read first, a
 * window is chosen second, private areas are painted out third, and watching is
 * only ever switched on by an explicit press.
 */

import { expect, test, type Page } from '@playwright/test';

async function simulatedWindow(page: Page) {
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getDisplayMedia', { value: async () => {
      const canvas = document.createElement('canvas'); canvas.width = 960; canvas.height = 540;
      const ctx = canvas.getContext('2d')!;
      ctx.fillStyle = '#1b2620'; ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#eef5e9'; ctx.font = '24px monospace';
      ctx.fillText('PS> python app.py', 40, 90);
      const stream = canvas.captureStream(5);
      const track = stream.getVideoTracks()[0];
      const settings = track.getSettings.bind(track);
      track.getSettings = () => ({ ...settings(), displaySurface: 'window' });
      const stop = track.stop.bind(track);
      track.stop = () => { document.documentElement.dataset.captureStopped = 'true'; stop(); };
      return stream;
    } });
  });
}

async function guiding(page: Page) {
  await simulatedWindow(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore an example' }).click();
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  await page.getByRole('button', { name: 'Start the steps' }).click();
  await expect(page.locator('.guide-island .island-count')).toHaveText('Step 1 of 3');
}

const dialog = (page: Page) => page.locator('.watch-setup');

test('the notice is read before a window is ever chosen', async ({ page }) => {
  await guiding(page);
  await page.getByRole('button', { name: 'Let Guider watch this window' }).click();

  await expect(dialog(page)).toBeVisible();
  await expect(dialog(page)).toContainText('only while a step is waiting on you');
  await expect(dialog(page)).toContainText('never leaves your computer');
  await expect(dialog(page)).toContainText('Never the picture. Pictures are used and discarded, never saved');
  await expect(dialog(page)).toContainText('200 checks and 30 minutes');
  await expect(dialog(page)).toContainText('One tap, any time');
  // The version the agreement is recorded against is on screen, not implied.
  await expect(dialog(page)).toContainText('Notice version observation-draft-2');
  // Nothing has been shared yet: the picker is the next press, not this one.
  await expect(page.locator('.watch-preview')).toHaveCount(0);
});

test('declining leaves the guide running and nothing shared', async ({ page }) => {
  await guiding(page);
  await page.getByRole('button', { name: 'Let Guider watch this window' }).click();
  await page.getByRole('button', { name: 'Not now' }).click();

  await expect(dialog(page)).toHaveCount(0);
  await expect(page.locator('.island-frames')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'I’ve done this' })).toBeVisible();
});

test('the chosen window is shown so private areas can be painted out first', async ({ page }) => {
  await guiding(page);
  await page.getByRole('button', { name: 'Let Guider watch this window' }).click();
  await page.getByRole('button', { name: 'Choose a window' }).click();

  const preview = page.locator('.watch-preview');
  await expect(preview).toBeVisible();
  await expect(dialog(page)).toContainText('Nothing hidden yet');

  const box = (await preview.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.2, box.y + box.height * 0.2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.6, { steps: 8 });
  await page.mouse.up();

  await expect(page.locator('.watch-mask')).toHaveCount(1);
  await expect(dialog(page)).toContainText('1 area hidden');
  await page.screenshot({ path: 'test-results/watch-mask.png', animations: 'disabled' });

  await page.getByRole('button', { name: 'Undo' }).click();
  await expect(page.locator('.watch-mask')).toHaveCount(0);
});

test('the demo says it cannot watch rather than pretending to', async ({ page }) => {
  await guiding(page);
  await page.getByRole('button', { name: 'Let Guider watch this window' }).click();
  await page.getByRole('button', { name: 'Choose a window' }).click();
  await page.getByRole('button', { name: 'Start watching' }).click();

  await expect(page.getByRole('alert')).toContainText('needs a signed-in task');
  // No counter appears, because nothing was ever looked at.
  await expect(page.locator('.island-frames')).toHaveCount(0);
});

test('cancelling the scope step stops the shared window', async ({ page }) => {
  await guiding(page);
  await page.getByRole('button', { name: 'Let Guider watch this window' }).click();
  await page.getByRole('button', { name: 'Choose a window' }).click();
  await expect(page.locator('.watch-preview')).toBeVisible();

  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog(page)).toHaveCount(0);
  await expect.poll(
    () => page.evaluate(() => document.documentElement.dataset.captureStopped),
  ).toBe('true');
});
