/**
 * Getting stuck, and getting a different plan for what is left.
 *
 * The two rules this has to show are the ones a person would care about: being
 * stuck never moves the guide on its own, and a replacement plan keeps what has
 * already been done instead of starting the task over.
 */

import { expect, test, type Page } from '@playwright/test';

const island = (page: Page) => page.locator('.guide-island');
const count = (page: Page) => island(page).locator('.island-count');

async function guiding(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore an example' }).click();
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  await page.getByRole('button', { name: 'Start the steps' }).click();
  await expect(count(page)).toHaveText('Step 1 of 3');
}

/** Say the step is done, then that it did not happen, then say it again. */
async function getStuck(page: Page) {
  await page.getByRole('button', { name: 'I’ve done this' }).click();
  await page.getByRole('button', { name: 'Not yet' }).click();
  await page.getByRole('button', { name: 'I’ve done this' }).click();
}

test('a step that is not working out is said out loud, and nothing moves', async ({ page }) => {
  await guiding(page);
  await getStuck(page);

  await expect(island(page).locator('.island-stuck')).toContainText('not working out');
  await expect(island(page).locator('.island-stuck')).toContainText(
    'What you have already done is kept',
  );
  // Still the same step, and still waiting on the user.
  await expect(count(page)).toHaveText('Step 1 of 3');
  await expect(page.getByText('Did this happen:', { exact: false })).toBeVisible();
});

test('a replacement plan keeps the finished steps and replaces the rest', async ({ page }) => {
  await guiding(page);
  // Finish step one honestly first, so there is something to keep.
  await page.getByRole('button', { name: 'I’ve done this' }).click();
  await page.getByRole('button', { name: 'Yes, that happened' }).click();
  await expect(count(page)).toHaveText('Step 2 of 3');

  await getStuck(page);
  await page.getByRole('button', { name: 'Ask for a different plan' }).click();

  await expect(page.getByText('STEP-BY-STEP · VERSION 2')).toBeVisible();
  await expect(page.getByText('Here is a new plan for what is left', { exact: false }))
    .toBeVisible();
  // The step already done is still there, in place, followed by the new ones.
  await expect(page.locator('ol > li').first()).toContainText('Open the terminal');
  await expect(page.getByText('Describe what you can see')).toBeVisible();
  await expect(page.getByText('Try the last step once more, slowly')).toBeVisible();
  // The guide is not running while a plan is waiting to be confirmed.
  await expect(island(page)).toHaveCount(0);
  await page.screenshot({ path: 'test-results/replan-review.png', animations: 'disabled' });
});

test('confirming the new plan continues past what was already done', async ({ page }) => {
  await guiding(page);
  await page.getByRole('button', { name: 'I’ve done this' }).click();
  await page.getByRole('button', { name: 'Yes, that happened' }).click();
  await getStuck(page);
  await page.getByRole('button', { name: 'Ask for a different plan' }).click();

  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  await expect(page.getByText('This plan is confirmed.')).toBeVisible();
  await page.getByRole('button', { name: 'Start the steps' }).click();

  // Three steps again: the kept one, and the two proposed for the rest.
  await expect(count(page)).toHaveText('Step 2 of 3');
  await expect(island(page)).toContainText('Describe what you can see');
});
