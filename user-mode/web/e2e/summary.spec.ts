/**
 * What a finished task says about itself.
 *
 * The phase-4 exit gate, from the user's side: steps something checked and steps
 * the user reported are visibly different things on the page, and a task where
 * nothing was checked never claims otherwise.
 */

import { expect, test, type Page } from '@playwright/test';

const island = (page: Page) => page.locator('.guide-island');

async function runWholePlan(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore an example' }).click();
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  await page.getByRole('button', { name: 'Start the steps' }).click();

  for (const ordinal of [1, 2, 3]) {
    await expect(island(page).locator('.island-count')).toHaveText(`Step ${ordinal} of 3`);
    await page.getByRole('button', { name: 'I’ve done this' }).click();
    await page.getByRole('button', { name: 'Yes, that happened' }).click();
  }
  await expect(island(page).locator('.island-status')).toHaveText('All done');
}

test('a task finished on the user’s word says exactly that', async ({ page }) => {
  await runWholePlan(page);
  await expect(island(page)).toContainText('Guider checked only what it could see');
  await page.getByRole('button', { name: 'Finish this task' }).click();

  await expect(page.getByRole('heading', { name: 'You said this is done.' })).toBeVisible();
  await expect(page.getByText('FINISHED ON YOUR WORD')).toBeVisible();
  await expect(page.getByText('This is your own account of the work', { exact: false }))
    .toBeVisible();
  // Never the other claim.
  await expect(page.getByText('Every required step was checked.')).toHaveCount(0);
  await page.screenshot({ path: 'test-results/summary-user-reported.png', animations: 'disabled' });
});

test('checked steps and reported steps are shown as different things', async ({ page }) => {
  await runWholePlan(page);
  await page.getByRole('button', { name: 'Finish this task' }).click();

  await expect(page.getByText('0 checked on screen')).toBeVisible();
  await expect(page.getByText('3 on your word')).toBeVisible();
  // Every step carries its own label, not one shared "done" tick.
  const labels = await page.locator('.summary-step small').allInnerTexts();
  // The label is rendered uppercase; compare on the words, not the casing.
  expect(labels.map(label => label.toLowerCase()))
    .toEqual(['you reported this', 'you reported this', 'you reported this']);
  await expect(page.locator('.summary-step.checked')).toHaveCount(0);
});

test('a skipped step is named rather than counted away', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore an example' }).click();
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  await page.getByRole('button', { name: 'Start the steps' }).click();

  await page.getByRole('button', { name: 'Skip' }).click();
  for (const ordinal of [2, 3]) {
    await expect(island(page).locator('.island-count')).toHaveText(`Step ${ordinal} of 3`);
    await page.getByRole('button', { name: 'I’ve done this' }).click();
    await page.getByRole('button', { name: 'Yes, that happened' }).click();
  }
  await page.getByRole('button', { name: 'Finish this task' }).click();

  await expect(page.getByText('1 was skipped.', { exact: false })).toBeVisible();
  await expect(page.getByText('Step 1 was skipped', { exact: false })).toBeVisible();
});

test('a finished task opens its summary from history', async ({ page }) => {
  await runWholePlan(page);
  await page.getByRole('button', { name: 'Finish this task' }).click();
  await page.getByRole('button', { name: 'See your tasks' }).click();

  await expect(page.getByRole('heading', { name: 'Your task history.' })).toBeVisible();
  await page.locator('.history-list button').first().click();
  await expect(page.getByRole('heading', { name: 'You said this is done.' })).toBeVisible();
  await expect(page.getByText('3 on your word')).toBeVisible();
});
