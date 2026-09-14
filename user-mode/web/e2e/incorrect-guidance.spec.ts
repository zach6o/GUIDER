/**
 * Saying the guidance is wrong.
 *
 * This is the one control that costs the user their running guide, so it has to
 * behave like it: it asks before it acts, it says what it will cost, and once
 * pressed it stops pointing at anything rather than leaving a stale instruction
 * on screen. Doc 05 calls for exactly that, and the browser demo mirrors the
 * server so the promise is the same with or without a backend.
 */

import { expect, test, type Page } from '@playwright/test';

const island = (page: Page) => page.locator('.guide-island');

async function guiding(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore an example' }).click();
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  await page.getByRole('button', { name: 'Start the steps' }).click();
  await expect(island(page).locator('.island-count')).toHaveText('Step 1 of 3');
}

test('the report asks first, and says what it will cost', async ({ page }) => {
  await guiding(page);
  await page.getByRole('button', { name: 'This guidance is wrong' }).click();

  await expect(island(page).locator('.island-report')).toContainText(
    'This stops the guide and switches watching off',
  );
  // Nothing has happened yet: the step is still the current one.
  await expect(island(page).locator('.island-count')).toHaveText('Step 1 of 3');
  await expect(island(page)).toContainText('Open the terminal');
});

test('changing your mind leaves the guide exactly where it was', async ({ page }) => {
  await guiding(page);
  await page.getByRole('button', { name: 'This guidance is wrong' }).click();
  await page.getByRole('button', { name: 'Keep going' }).click();

  await expect(island(page).locator('.island-report')).toHaveCount(0);
  await expect(island(page).locator('.island-count')).toHaveText('Step 1 of 3');
  await page.getByRole('button', { name: 'I’ve done this' }).click();
  await expect(page.getByText('Did this happen:', { exact: false })).toBeVisible();
});

test('confirming it stops the guide pointing at anything', async ({ page }) => {
  await guiding(page);
  await page.getByRole('button', { name: 'This guidance is wrong' }).click();
  await page.getByRole('button', { name: 'Yes, this is wrong' }).click();

  const blocked = island(page).locator('.island-blocked');
  await expect(blocked).toContainText('stopped pointing at this step');
  await expect(blocked).toContainText('Nothing is pointing at your screen');
  // No step, no instruction, and nothing left to claim.
  await expect(island(page).locator('.island-count')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'I’ve done this' })).toHaveCount(0);
  await page.screenshot({ path: 'test-results/incorrect-guidance.png', animations: 'disabled' });
});
