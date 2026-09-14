/**
 * Deleting a task, from the user's side.
 *
 * The two things worth holding on screen: a deletion asks before it happens and
 * says what it will take, and afterwards the task is actually gone from history
 * rather than merely hidden.
 */

import { expect, test, type Page } from '@playwright/test';

async function finishedTask(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore an example' }).click();
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  await page.getByRole('button', { name: 'Task history' }).click();
  await expect(page.locator('.history-row')).toHaveCount(1);
}

test('deleting a task asks first, and says what goes with it', async ({ page }) => {
  await finishedTask(page);
  await page.getByRole('button', { name: /^Delete the task/ }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('Every session, plan, step and image under this task');
  await expect(dialog).toContainText('cannot be undone');
  // Nothing has happened yet.
  await page.getByRole('button', { name: 'Keep it' }).click();
  await expect(page.locator('.history-row')).toHaveCount(1);
});

test('a deleted task leaves history, with a receipt', async ({ page }) => {
  await finishedTask(page);
  await page.getByRole('button', { name: /^Delete the task/ }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Delete the task' }).click();

  await expect(page.getByText('nothing of that task is left')).toBeVisible();
  await expect(page.locator('.history-row')).toHaveCount(0);
  await expect(page.getByText('A fresh page.')).toBeVisible();
  await page.screenshot({ path: 'test-results/deletion.png', animations: 'disabled' });
});
