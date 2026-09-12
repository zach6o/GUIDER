import { expect, test } from '@playwright/test';

test('synthetic screenshot journey, deletion, and responsive workspace', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const mediaRequests: string[] = [];
  page.on('request', request => { if (request.method() !== 'GET') mediaRequests.push(request.url()); });
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'What would you like to figure out?' })).toBeVisible();
  await page.screenshot({ path: 'test-results/home-desktop.png', fullPage: true, animations: 'disabled' });
  await page.getByRole('button', { name: 'Explore an example' }).click();
  await expect(page.getByLabel('What would you like to do?')).toHaveValue("Why won't my Python file run?");
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await expect(page.getByRole('heading', { name: 'A quick privacy check.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Upload this image' })).toBeDisabled();
  await page.getByRole('checkbox', { name: 'I reviewed this image' }).check();
  await page.getByRole('button', { name: 'Upload this image' }).click();
  await page.getByRole('button', { name: 'Explain this screenshot' }).click();
  await expect(page.getByText('Python cannot find the requests package', { exact: false })).toBeVisible();
  await expect(page.locator('.evidence-marker')).toHaveCount(1);
  await page.screenshot({ path: 'test-results/explanation-desktop.png', fullPage: true, animations: 'disabled' });
  await page.getByRole('button', { name: 'Delete screenshot and analysis' }).click();
  await expect(page.getByText('Image and its analysis have been deleted.')).toBeVisible();
  await expect(page.locator('.evidence-marker')).toHaveCount(0);
  await page.getByRole('button', { name: 'Task history', exact: true }).click();
  await expect(page.getByRole('button', { name: /Why won't my Python file run/ })).toBeVisible();
  await page.getByRole('button', { name: 'Guider home' }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'test-results/home-mobile.png', fullPage: true, animations: 'disabled' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
  expect(mediaRequests).toEqual([]);
});

test('keyboard masking changes pixels and prevents false fixture recognition', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore an example' }).click();
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('spinbutton', { name: 'x', exact: true }).fill('0');
  await page.getByRole('spinbutton', { name: 'y', exact: true }).fill('0');
  await page.getByRole('spinbutton', { name: 'width', exact: true }).fill('960');
  await page.getByRole('spinbutton', { name: 'height', exact: true }).fill('400');
  await page.getByRole('button', { name: 'Hide selected area' }).click();
  await expect(page.getByRole('button', { name: 'Undo' })).toBeEnabled();
  await page.getByRole('checkbox', { name: 'I reviewed this image' }).check();
  await page.getByRole('button', { name: 'Upload this image' }).click();
  const image = page.getByRole('img', { name: 'Your uploaded screenshot' });
  const pixel = await image.evaluate((element: HTMLImageElement) => {
    const canvas = document.createElement('canvas'); canvas.width = 960; canvas.height = 400;
    const ctx = canvas.getContext('2d')!; ctx.drawImage(element, 0, 0);
    return Array.from(ctx.getImageData(400, 200, 1, 1).data);
  });
  expect(pixel).toEqual([17, 24, 21, 255]);
  await page.getByRole('button', { name: 'Explain this screenshot' }).click();
  await expect(page.getByText('this demo cannot interpret arbitrary screenshots', { exact: false })).toBeVisible();
  await expect(page.locator('.evidence-marker')).toHaveCount(0);
});
