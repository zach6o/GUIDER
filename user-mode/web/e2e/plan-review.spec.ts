import { expect, test } from '@playwright/test';

async function startTask(page: import('@playwright/test').Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore an example' }).click();
  await expect(page.getByLabel('What would you like to do?')).toHaveValue("Why won't my Python file run?");
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await expect(page.getByRole('heading', { name: 'A quick privacy check.' })).toBeVisible();
}

test('create, review and confirm a plan before anything starts', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1100 });
  await startTask(page);

  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await expect(page.getByRole('heading', { name: /Why won't my Python file run/ })).toBeVisible();
  await expect(page.getByText('Awaiting your review')).toBeVisible();

  // Nothing is confirmed until the user says so.
  await expect(page.getByText('Guider suggests 3 steps', { exact: false })).toBeVisible();
  await expect(page.locator('.plan-steps > li')).toHaveCount(3);
  await expect(page.getByRole('heading', { name: 'Open the terminal' })).toBeVisible();
  await expect(page.getByText('What this assumes')).toBeVisible();
  await expect(page.getByText('not from a planner model', { exact: false })).toBeVisible();
  await page.screenshot({ path: 'test-results/plan-review-desktop.png', fullPage: true, animations: 'disabled' });

  // Explain mode is per step and collapsed by default.
  const why = page.getByRole('button', { name: 'Why this step?' }).first();
  await expect(why).toHaveAttribute('aria-expanded', 'false');
  await why.click();
  await expect(page.getByText('The interpreter reports what went wrong', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Hide why' }).click();
  await expect(page.getByText('The interpreter reports what went wrong', { exact: false })).toBeHidden();

  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  await expect(page.getByText('Plan confirmed.', { exact: false })).toBeVisible();
  await expect(page.getByText('This plan is confirmed.')).toBeVisible();
  await expect(page.getByText('Version 1 is the one Guider will follow.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Confirm this plan' })).toHaveCount(0);

  expect(errors).toEqual([]);
});

test('a replacement plan supersedes the first and is reviewed again', async ({ page }) => {
  await startTask(page);
  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await expect(page.getByText('STEP-BY-STEP · VERSION 1')).toBeVisible();

  await page.getByRole('button', { name: 'Suggest a different plan' }).click();
  await expect(page.getByText('STEP-BY-STEP · VERSION 2')).toBeVisible();
  // A new version arrives unconfirmed, exactly like the first.
  await expect(page.getByText('Awaiting your review')).toBeVisible();

  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  await expect(page.getByText('Version 2 is the one Guider will follow.')).toBeVisible();
});

test('the plan stays reachable from the task and works on a small screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await startTask(page);
  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await expect(page.locator('.plan-steps > li')).toHaveCount(3);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/plan-review-mobile.png', fullPage: true, animations: 'disabled' });

  await page.getByRole('button', { name: 'Back to the task' }).click();
  await expect(page.getByRole('heading', { name: 'A plan is ready · version 1' })).toBeVisible();
  await page.getByRole('button', { name: 'Review the plan' }).click();
  await expect(page.getByText('STEP-BY-STEP · VERSION 1')).toBeVisible();
});
