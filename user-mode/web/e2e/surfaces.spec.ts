/**
 * Where the guide sits, on browsers that cannot do all three.
 *
 * ADR-016 calls side-by-side and mirrored preview first-class modes, and doc 20
 * lists Picture-in-Picture's absence on Safari and Firefox as a risk to build
 * for rather than discover. So the choice is on screen, a surface this browser
 * lacks is named with its reason instead of vanishing, and a floating window
 * that refuses to open leaves the user with a working guide and a sentence
 * explaining what happened.
 */

import { expect, test, type Page } from '@playwright/test';

const island = (page: Page) => page.locator('.guide-island');
const option = (page: Page, name: string) => page.getByRole('radio', { name, exact: false });

async function confirmedPlan(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore an example' }).click();
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  await expect(page.getByText('This plan is confirmed.')).toBeVisible();
}

test('all three surfaces are offered, whatever this browser can do', async ({ page }) => {
  await confirmedPlan(page);
  await expect(page.getByRole('radiogroup', { name: 'Guide surface' })).toBeVisible();
  await expect(option(page, 'A floating window')).toBeVisible();
  await expect(option(page, 'Beside your work')).toBeVisible();
  await expect(option(page, 'With your window mirrored here')).toBeVisible();
});

test('a browser without Picture-in-Picture is told why, not left guessing', async ({ page }) => {
  // What Safari and Firefox look like from here.
  await page.addInitScript(() => {
    Reflect.deleteProperty(window, 'documentPictureInPicture');
  });
  await confirmedPlan(page);

  const floating = option(page, 'A floating window');
  await expect(floating).toBeDisabled();
  await expect(floating).toContainText('Safari and Firefox cannot');
  // The guide still starts, on the surface this browser does have.
  await expect(option(page, 'Beside your work')).toHaveAttribute('aria-checked', 'true');
  await page.getByRole('button', { name: 'Start the steps' }).click();
  await expect(island(page)).toBeVisible();
  await expect(island(page).locator('.island-count')).toHaveText('Step 1 of 3');
});

test('a floating window that will not open falls back and says so', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'documentPictureInPicture', {
      configurable: true,
      value: { requestWindow: () => Promise.reject(new Error('blocked')), window: null },
    });
  });
  await confirmedPlan(page);
  await option(page, 'A floating window').click();
  await page.getByRole('button', { name: 'Start the steps' }).click();

  await expect(page.getByText('The floating window did not open')).toBeVisible();
  // Fallen back, not failed: the guide is running on the page.
  await expect(island(page)).toBeVisible();
  await expect(island(page).locator('.island-count')).toHaveText('Step 1 of 3');
  await page.screenshot({ path: 'test-results/surface-fallback.png', animations: 'disabled' });
});

test('the mirror says it is not being read, before it is chosen', async ({ page }) => {
  await confirmedPlan(page);
  await option(page, 'With your window mirrored here').click();
  await expect(page.getByText('This mirror stays on your machine')).toBeVisible();
  await expect(page.getByText('watching is separate, off by default')).toBeVisible();
});
