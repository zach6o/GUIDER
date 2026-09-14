/**
 * Getting a stopped guide moving again.
 *
 * Before these routes existed a guide could be stopped four ways and resumed
 * none, so saying the guidance was wrong meant losing the task. What matters on
 * screen is that coming back is offered where the task stopped, that it does not
 * quietly switch watching back on, and that asking for a step again is visibly
 * not the same as saying it is done.
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

test('a task stopped by a wrong-guidance report can be picked back up', async ({ page }) => {
  await guiding(page);
  await page.getByRole('button', { name: 'This guidance is wrong' }).click();
  await page.getByRole('button', { name: 'Yes, this is wrong' }).click();

  const blocked = island(page).locator('.island-blocked');
  await expect(blocked).toContainText('watching stays off until you switch it on again');
  await page.getByRole('button', { name: 'Pick this task up again' }).click();

  // Back on the same step: the user said the guidance was wrong, not that the
  // step was done.
  await expect(island(page).locator('.island-count')).toHaveText('Step 1 of 3');
  await expect(island(page)).toContainText('Open the terminal');
  await expect(page.getByText('Watching is still off')).toBeVisible();
  await page.screenshot({ path: 'test-results/recovery-resumed.png', animations: 'disabled' });
});

test('asking for a step again is not saying it is done', async ({ page }) => {
  await guiding(page);
  await page.getByRole('button', { name: 'Say this a different way' }).click();

  // Same step, same position, nothing claimed and nothing checked.
  await expect(island(page).locator('.island-count')).toHaveText('Step 1 of 3');
  await expect(page.getByText('Did this happen:', { exact: false })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'I’ve done this' })).toBeVisible();
});

test('rewording the same step twice is reported as going nowhere', async ({ page }) => {
  await guiding(page);
  await page.getByRole('button', { name: 'Say this a different way' }).click();
  await page.getByRole('button', { name: 'Say this a different way' }).click();

  await expect(island(page).locator('.island-stuck')).toContainText('not working out');
  await expect(page.getByRole('button', { name: 'Ask for a different plan' })).toBeVisible();
  // Still nothing moved: being stuck is said out loud and acted on by nobody.
  await expect(island(page).locator('.island-count')).toHaveText('Step 1 of 3');
});
