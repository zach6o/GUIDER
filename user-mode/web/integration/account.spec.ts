import { readFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';

function identity() {
  return JSON.parse(readFileSync('../backend/.local/browser-auth.json', 'utf8'));
}

async function signIn(page: Page) {
  const auth = identity();
  await page.route('https://fixture.supabase.co/auth/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/otp')) return route.fulfill({ json: {} });
    if (path.endsWith('/logout')) return route.fulfill({ status: 204 });
    if (path.endsWith('/user')) return route.fulfill({ json: auth.user });
    if (path.endsWith('/verify') || path.endsWith('/token')) return route.fulfill({ json: {
      access_token: auth.access_token, token_type: 'bearer', expires_in: 3600,
      refresh_token: 'synthetic-refresh-token', user: auth.user,
    } });
    await route.abort();
  });
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.getByLabel('Email address').fill('browser@example.test');
  await page.getByRole('button', { name: 'Email me a code' }).click();
  await page.getByLabel('Email code').fill('123456');
  await page.getByRole('button', { name: 'Verify code' }).click();
  await expect(page.getByText('Signed in privately')).toBeVisible();
}

test('saved plan survives refresh and another sign-in through the real API', async ({ page }) => {
  await page.goto('/');
  await signIn(page);
  await page.getByLabel('What would you like to do?').fill('Find the Python interpreter');
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  const link = page.url();
  expect(link).toContain('#session/');
  await page.reload();
  await expect(page.getByText('Sign in to save tasks')).toBeVisible();
  await signIn(page);
  await expect(page.getByText('This plan is confirmed.')).toBeVisible();
  await expect(page).toHaveURL(link);
  await page.getByRole('button', { name: 'Edit or reorder steps' }).click();
  await page.getByRole('textbox', { name: 'Title', exact: true }).first().fill('Inspect Python');
  await page.getByRole('button', { name: 'Save revised plan' }).click();
  await expect(page.getByRole('button', { name: 'Confirm this plan' })).toBeVisible();
  await expect(page.locator('.plan-step').first()).toContainText('Inspect Python');
});

test('settings persist without returning the saved credential', async ({ page }) => {
  await page.goto('/#providers');
  await signIn(page);
  await page.getByRole('combobox', { name: 'Provider', exact: true }).selectOption('anthropic');
  await page.getByLabel('API key').fill('synthetic-private-key');
  await page.getByRole('checkbox').check();
  const saved = page.waitForResponse(response => response.url().endsWith('/providers/bindings'));
  await page.getByRole('button', { name: 'Save connection' }).click();
  expect(await (await saved).text()).not.toContain('synthetic-private-key');
  await expect(page.getByText('Connection saved.', { exact: false })).toBeVisible();
  await expect(page.getByLabel('API key')).toHaveValue('');
  await page.getByRole('button', { name: 'Remove plan tasks connection' }).click();
  await expect(page.getByRole('button', { name: 'Remove plan tasks connection' })).toHaveCount(0);
});

test('expired API identity clears private UI and allows sign-in again', async ({ page }) => {
  await page.goto('/');
  await signIn(page);
  await page.route('http://127.0.0.1:8001/api/v1/guide/tasks', route => route.continue({
    headers: { ...route.request().headers(), authorization: `Bearer ${identity().expired_token}` },
  }));
  await page.getByLabel('What would you like to do?').fill('Private unsaved task');
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await expect(page.getByText('Sign in to save tasks')).toBeVisible();
  await expect(page.getByLabel('What would you like to do?')).toHaveValue('');
  await page.unroute('http://127.0.0.1:8001/api/v1/guide/tasks');
  await signIn(page);
});

test('sign-out clears the workspace even when stopping the task fails', async ({ page }) => {
  await page.goto('/');
  await signIn(page);
  await page.getByLabel('What would you like to do?').fill('A task to sign out of');
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await expect(page).toHaveURL(/#session\//);
  await page.route('**/sessions/*/stop', route => route.fulfill({ status: 503, json: {
    error: { code: 'dependency_unavailable', message: 'Service unavailable.' },
  } }));
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByText('Sign in to save tasks')).toBeVisible();
  await expect(page.getByLabel('What would you like to do?')).toHaveValue('');
  await expect(page.locator('.guide-island')).toHaveCount(0);
});

test('a late successful response cannot restore private task data after sign-out', async ({ page }) => {
  await page.goto('/');
  await signIn(page);
  let release!: () => void;
  const delayed = new Promise<void>(resolve => { release = resolve; });
  let captured = false;
  await page.route('http://127.0.0.1:8001/api/v1/guide/tasks', async route => {
    const response = await route.fetch();
    captured = true;
    await delayed;
    await route.fulfill({ response });
  });
  await page.getByLabel('What would you like to do?').fill('This late task must stay private');
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await expect.poll(() => captured).toBe(true);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByText('Sign in to save tasks')).toBeVisible();
  release();
  await expect(page.getByRole('alert')).toContainText('Sign in again');
  await expect(page.getByLabel('What would you like to do?')).toHaveValue('');
  await expect(page).not.toHaveURL(/#session\//);
});
