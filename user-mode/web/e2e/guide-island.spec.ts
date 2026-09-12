import { expect, test, type Page } from '@playwright/test';

async function confirmedPlan(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore an example' }).click();
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await expect(page.getByText('STEP-BY-STEP · VERSION 1')).toBeVisible();
  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  await expect(page.getByText('This plan is confirmed.')).toBeVisible();
}

const island = (page: Page) => page.locator('.guide-island');
const count = (page: Page) => island(page).locator('.island-count');
const status = (page: Page) => island(page).locator('.island-status');
const announcement = (page: Page) => island(page).getByRole('status').first();

test('a whole guide can be run without touching the mouse', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await confirmedPlan(page);

  // Reach the start control by keyboard alone, then drive every step the same way.
  await page.getByRole('button', { name: 'Start the steps' }).focus();
  await page.keyboard.press('Enter');
  await expect(island(page)).toBeVisible();
  await expect(count(page)).toBeVisible();

  for (const ordinal of [1, 2, 3]) {
    await expect(count(page)).toHaveText(`Step ${ordinal} of 3`);
    await page.getByRole('button', { name: 'I’ve done this' }).focus();
    await page.keyboard.press('Enter');
    // A claim is not progress: the guide asks before it advances.
    await expect(page.getByText('Did this happen:', { exact: false })).toBeVisible();
    await expect(page.getByText('Nothing has been checked on screen.', { exact: false }))
      .toBeVisible();
    await page.getByRole('button', { name: 'Yes, that happened' }).focus();
    await page.keyboard.press('Enter');
  }

  await expect(status(page)).toHaveText('All done');
  await expect(page.getByText('Nothing was verified on screen.', { exact: false })).toBeVisible();
  await page.screenshot({ path: 'test-results/island-finished.png', animations: 'disabled' });
  expect(errors).toEqual([]);
});

test('saying the step did not happen keeps the guide on that step', async ({ page }) => {
  await confirmedPlan(page);
  await page.getByRole('button', { name: 'Start the steps' }).click();
  await page.getByRole('button', { name: 'I’ve done this' }).click();
  await page.getByRole('button', { name: 'Not yet' }).click();

  await expect(count(page)).toHaveText('Step 1 of 3');
  await expect(page.getByText('That is not done yet.', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'I’ve done this' })).toBeVisible();
});

test('every state is announced in words and a glyph, not only in colour', async ({ page }) => {
  await confirmedPlan(page);
  await page.getByRole('button', { name: 'Start the steps' }).click();

  await expect(announcement(page)).toHaveAttribute('aria-live', 'polite');
  await expect(announcement(page)).toContainText('On this step');
  await expect(announcement(page)).toContainText('Step 1 of 3');
  await expect(status(page)).toHaveText('On this step');

  // A state that needs a decision interrupts, and says so in text.
  await page.getByRole('button', { name: 'I’ve done this' }).click();
  await expect(announcement(page)).toHaveAttribute('aria-live', 'assertive');
  await expect(status(page)).toHaveText('Needs you');
  await expect(island(page)).toHaveAttribute('data-state', 'attention');
});

test('pausing refuses progress until the guide is resumed', async ({ page }) => {
  await confirmedPlan(page);
  await page.getByRole('button', { name: 'Start the steps' }).click();
  await page.getByRole('button', { name: 'Pause the guide' }).click();
  await expect(page.getByRole('button', { name: 'Resume the guide' })).toBeVisible();
  await expect(status(page)).toHaveText('Paused');

  await page.getByRole('button', { name: 'I’ve done this' }).click();
  // Still on step one, and no question asked: a paused guide accepts nothing.
  await expect(page.getByText('Did this happen:', { exact: false })).toHaveCount(0);
  await expect(count(page)).toHaveText('Step 1 of 3');

  await page.getByRole('button', { name: 'Resume the guide' }).click();
  await page.getByRole('button', { name: 'I’ve done this' }).click();
  await expect(page.getByText('Did this happen:', { exact: false })).toBeVisible();
});

test('skip moves past a step and the explanation stays available', async ({ page }) => {
  await confirmedPlan(page);
  await page.getByRole('button', { name: 'Start the steps' }).click();
  await expect(island(page).locator('.island-why summary')).toBeVisible();
  await page.getByRole('button', { name: 'Skip' }).click();
  await expect(count(page)).toHaveText('Step 2 of 3');
});

test('the island collapses to a logo and reopens', async ({ page }) => {
  await confirmedPlan(page);
  await page.getByRole('button', { name: 'Start the steps' }).click();
  const dot = page.getByRole('button', { name: 'Collapse the guide' });
  await expect(dot).toHaveAttribute('aria-expanded', 'true');
  await dot.click();
  await expect(count(page)).toHaveCount(0);
  await page.getByRole('button', { name: /Expand the guide/ }).click();
  await expect(count(page)).toBeVisible();
});

test('reduced motion removes the animation without removing the state', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await confirmedPlan(page);
  await page.getByRole('button', { name: 'Start the steps' }).click();
  await page.getByRole('button', { name: 'I’ve done this' }).click();

  const animation = await island(page).locator('.island-ring').evaluate(
    element => getComputedStyle(element).animationName,
  );
  expect(animation).toBe('none');
  // The state is still conveyed, just not by movement.
  await expect(status(page)).toHaveText('Needs you');
});

test('closing the guide leaves the plan intact', async ({ page }) => {
  await confirmedPlan(page);
  await page.getByRole('button', { name: 'Start the steps' }).click();
  await page.getByRole('button', { name: 'Close the guide' }).click();
  await expect(island(page)).toHaveCount(0);
  await expect(page.getByText('This plan is confirmed.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start the steps' })).toBeEnabled();
});
