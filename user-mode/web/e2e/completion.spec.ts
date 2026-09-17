import { expect, test } from '@playwright/test';

test('edit and reorder a confirmed plan creates a draft requiring confirmation', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore an example' }).click();
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  await page.getByRole('button', { name: 'Edit or reorder steps' }).click();
  const editor = page.getByRole('form', { name: 'Edit plan' });
  await editor.getByRole('textbox', { name: 'Title', exact: true }).first().fill('Inspect the terminal');
  await page.getByRole('button', { name: 'Move step 1 down' }).click();
  await page.getByRole('button', { name: 'Save revised plan' }).click();
  await expect(page.getByRole('button', { name: 'Confirm this plan' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start the steps' })).toHaveCount(0);
  await expect(page.locator('.plan-step').nth(1)).toContainText('Inspect the terminal');
  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  await page.getByRole('button', { name: 'Start the steps' }).click();
  await expect(page.locator('.guide-island')).toContainText('Show which interpreter');
});

test('history filters and exports the selected record', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('What would you like to do?').fill('Understand Python output');
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('button', { name: 'Guider home' }).click();
  await page.getByLabel('What would you like to do?').fill('Understand Docker output');
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('button', { name: 'Task history', exact: true }).click();
  await expect(page.locator('.history-row')).toHaveCount(2);
  await page.getByLabel('Search your tasks').fill('Docker');
  await page.getByRole('button', { name: 'Search history' }).click();
  await expect(page.locator('.history-row')).toHaveCount(1);
  await expect(page.locator('.history-row')).toContainText('Docker');
  const downloading = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export the task Understand Docker output' }).click();
  expect((await downloading).suggestedFilename()).toMatch(/^guider-.*\.json$/);
  await page.getByRole('button', { name: 'Clear filters' }).click();
  await expect(page.locator('.history-row')).toHaveCount(2);
});

test('reopening history retains the saved plan and task link', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore an example' }).click();
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  const link = page.url();
  expect(link).toContain('#session/');
  await page.getByRole('button', { name: 'Task history', exact: true }).click();
  await page.locator('.history-row > button').first().click();
  await expect(page.getByText('This plan is confirmed.')).toBeVisible();
  await expect(page).toHaveURL(link);
});

test('dictation asks first and only fills the task after transcript review', async ({ page }) => {
  await page.addInitScript(() => {
    class Recognition {
      onresult: ((event: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      start() { this.onresult?.({ results: [{ isFinal: true, 0: { transcript: 'Explain the terminal output' } }] }); }
      stop() { this.onend?.(); }
      abort() {}
    }
    Object.defineProperty(window, 'SpeechRecognition', { value: Recognition });
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Dictate your task' }).click();
  await expect(page.getByRole('button', { name: 'Start dictation' })).toBeDisabled();
  await page.getByRole('checkbox', { name: 'Allow my browser' }).check();
  await page.getByRole('button', { name: 'Start dictation' }).click();
  await page.getByRole('button', { name: 'Stop listening' }).click();
  await page.getByLabel('Review transcript').fill('Explain this Python output');
  await expect(page.getByLabel('What would you like to do?')).toHaveValue('');
  await page.getByRole('button', { name: 'Use this text' }).click();
  await expect(page.getByLabel('What would you like to do?')).toHaveValue('Explain this Python output');
  await expect(page.getByRole('heading', { name: 'What would you like to figure out?' })).toBeVisible();
});
