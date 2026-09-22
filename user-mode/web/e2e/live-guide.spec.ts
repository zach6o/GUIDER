import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

test('automatic guide explains an outdated backend and retries saved-key support', async ({ page }) => {
  let outdated = true;
  const connections: Record<string, unknown>[] = [];
  await page.route('**/api/v1/local-guide/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204 });
    if (path.endsWith('/saved-keys')) return outdated
      ? route.fulfill({ status: 404, json: { error: { code: 'invalid_request', message: 'Invalid request.' } } })
      : route.fulfill({ json: { available: true, providers: [] } });
    if (path.endsWith('/connection') && route.request().method() === 'POST') {
      connections.push(route.request().postDataJSON());
      return route.fulfill({ json: { connection_token: 'synthetic-capability', provider: 'openai',
        display_name: 'OpenAI', model: 'gpt-4.1-mini', expires_in_seconds: 1800 } });
    }
    return route.fulfill({ status: 204 });
  });
  await page.goto('/#live');
  await page.getByRole('button', { name: 'Automatic guide', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('backend is out of date');
  await page.getByLabel('OpenAI API key').fill('sk-synthetic-connection-regression');
  await page.getByRole('checkbox', { name: /Allow my goal/ }).check();
  await expect(page.getByRole('button', { name: 'Connect OpenAI' })).toBeDisabled();
  expect(connections).toHaveLength(0);
  outdated = false;
  await page.getByRole('button', { name: 'Retry backend connection' }).click();
  const remember = page.getByRole('checkbox', { name: /Remember this key securely/ });
  await expect(remember).toBeEnabled();
  await expect(remember).toBeChecked();
  await remember.uncheck();
  await remember.check();
  await expect(page.getByRole('button', { name: 'Connect OpenAI' })).toBeEnabled();
  await page.getByRole('button', { name: 'Connect OpenAI' }).click();
  await expect(page.getByRole('button', { name: 'Disconnect', exact: true })).toBeVisible();
  expect(connections).toHaveLength(1);
  expect(connections[0].remember_key).toBe(true);
});

const guidance = {
  observation: 'The terminal cannot find the requests package.',
  next_step: 'Check which Python interpreter this terminal is using.',
  where: 'In the selected terminal, type python --version.',
  check_for: 'The interpreter version printed below the command.',
  question: '', disposition: 'guide',
};

async function simulatedWindow(page: Page) {
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getDisplayMedia', { value: async () => {
      const canvas = document.createElement('canvas'); canvas.width = 960; canvas.height = 540;
      const ctx = canvas.getContext('2d')!;
      ctx.fillStyle = '#19241e'; ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#eef5e9'; ctx.font = '26px monospace';
      ctx.fillText('PS> python app.py', 35, 85);
      ctx.fillText("ModuleNotFoundError: No module named 'requests'", 35, 170);
      const stream = canvas.captureStream(5);
      const track = stream.getVideoTracks()[0], originalStop = track.stop.bind(track);
      Object.defineProperty(track, 'label', { value: 'Demo Python terminal' });
      track.stop = () => { document.documentElement.dataset.captureStopped = 'true'; originalStop(); };
      const settings = track.getSettings.bind(track);
      track.getSettings = () => ({ ...settings(), displaySurface: 'window' });
      return stream;
    } });
  });
}

async function connect(page: Page) {
  await page.goto('/#live');
  await page.bringToFront();
  await page.getByRole('button', { name: 'AI screen guide', exact: true }).click();
  await page.getByLabel('OpenAI API key').fill('sk-test-not-real-key-1234567890');
  await page.getByRole('checkbox', { name: 'I agree to send reviewed frames' }).check();
  await page.getByRole('button', { name: 'Connect OpenAI' }).click();
  await expect(page.getByText('OpenAI connected · gpt-4.1-mini')).toBeVisible();
  await expect(page.getByLabel('OpenAI API key')).toHaveCount(0);
  await page.getByLabel('What are you trying to do?').fill('Help me run my Python app');
  await page.getByRole('button', { name: 'Share a window', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Window sharing on' })).toBeVisible();
}

test('real capture adapter, explicit cloud review, answer, disconnect', async ({ page }, testInfo) => {
  await simulatedWindow(page);
  const sent: Record<string, unknown>[] = [];
  await page.route('**/api/v1/local-guide/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/saved-keys')) return route.fulfill({ json: { available: false, providers: [] } });
    const headers = { 'Access-Control-Allow-Origin': 'http://127.0.0.1:5173',
      'Access-Control-Allow-Headers': 'authorization,content-type',
      'Access-Control-Allow-Methods': 'POST,DELETE,OPTIONS' };
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
    if (path.endsWith('/checks')) {
      sent.push(route.request().postDataJSON());
      return route.fulfill({ json: guidance, headers });
    }
    if (route.request().method() === 'DELETE' || path.endsWith('/cancel')) return route.fulfill({ status: 204, headers });
    return route.fulfill({ json: { connection_token: 'capability-test-only', model: 'gpt-4.1-mini', expires_in_seconds: 1800 }, headers });
  });
  await page.setViewportSize({ width: 1440, height: 1050 });
  await connect(page);
  await page.getByRole('button', { name: 'Check screen', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'A quick privacy check.' })).toBeVisible();
  expect(sent).toHaveLength(0);
  await expect(page.getByRole('button', { name: 'Send to OpenAI' })).toBeDisabled();
  await page.getByRole('checkbox', { name: 'I reviewed this image' }).check();
  await page.getByRole('button', { name: 'Send to OpenAI' }).click();
  await expect(page.getByRole('heading', { name: guidance.next_step })).toBeVisible();
  expect(sent).toHaveLength(1);
  expect(sent[0].reviewed).toBe(true);
  expect(String(sent[0].image_base64)).toMatch(/^iVBOR/);
  expect(JSON.stringify(sent[0])).not.toContain('sk-test');
  if (process.env.GUIDE_CAPTURE_EVIDENCE) {
    await page.screenshot({ path: testInfo.outputPath('live-guidance.png'), fullPage: true, animations: 'disabled' });
  }
  await page.getByRole('button', { name: 'Stop sharing', exact: true }).click();
  await expect(page.getByRole('heading', { name: guidance.next_step })).toHaveCount(0);
  await expect(page.locator('html')).toHaveAttribute('data-capture-stopped', 'true');
  await expect(page.getByRole('status').filter({ hasText: 'Window sharing off' })).toBeVisible();
  await page.getByRole('button', { name: 'Disconnect & clear key' }).click();
  await expect(page.getByLabel('OpenAI API key')).toHaveValue('');
});


test('stop cancels a pending check and a late answer never appears', async ({ page }) => {
  await simulatedWindow(page);
  let release!: () => void;
  const delay = new Promise<void>(resolve => { release = resolve; });
  let sent = false;
  await page.route('**/api/v1/local-guide/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/saved-keys')) return route.fulfill({ json: { available: false, providers: [] } });
    const headers = { 'Access-Control-Allow-Origin': 'http://127.0.0.1:5173',
      'Access-Control-Allow-Headers': 'authorization,content-type',
      'Access-Control-Allow-Methods': 'POST,DELETE,OPTIONS' };
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
    if (path.endsWith('/checks')) {
      sent = true; await delay;
      await route.fulfill({ json: guidance, headers }).catch(() => {}); return;
    }
    if (route.request().method() === 'DELETE' || path.endsWith('/cancel')) return route.fulfill({ status: 204, headers });
    return route.fulfill({ json: { connection_token: 'capability-test-only', model: 'gpt-4.1-mini', expires_in_seconds: 1800 }, headers });
  });
  await connect(page);
  await page.getByRole('button', { name: 'Check screen', exact: true }).click();
  await page.getByRole('checkbox', { name: 'I reviewed this image' }).check();
  await page.getByRole('button', { name: 'Send to OpenAI' }).click();
  await expect.poll(() => sent).toBe(true);
  await page.getByRole('button', { name: 'Stop sharing', exact: true }).click();
  release();
  await expect(page.getByRole('heading', { name: guidance.next_step })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Share a window', exact: true })).toBeEnabled();
  await expect(page.locator('html')).toHaveAttribute('data-capture-stopped', 'true');
});

test('cancel check keeps sharing and waits for cancellation before a replacement request', async ({ page }) => {
  await simulatedWindow(page);
  let releaseAnswer!: () => void, releaseCancel!: () => void;
  const answerDelay = new Promise<void>(resolve => { releaseAnswer = resolve; });
  const cancelDelay = new Promise<void>(resolve => { releaseCancel = resolve; });
  const sent: Record<string, unknown>[] = [];
  let cancelStarted = false;
  await page.route('**/api/v1/local-guide/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/saved-keys')) return route.fulfill({ json: { available: false, providers: [] } });
    const headers = { 'Access-Control-Allow-Origin': 'http://127.0.0.1:5173',
      'Access-Control-Allow-Headers': 'authorization,content-type',
      'Access-Control-Allow-Methods': 'POST,DELETE,OPTIONS' };
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
    if (path.endsWith('/cancel')) {
      cancelStarted = true; await cancelDelay;
      return route.fulfill({ status: 204, headers });
    }
    if (path.endsWith('/checks')) {
      sent.push(route.request().postDataJSON());
      if (sent.length === 1) await answerDelay;
      return route.fulfill({ json: guidance, headers }).catch(() => {});
    }
    if (route.request().method() === 'DELETE') return route.fulfill({ status: 204, headers });
    return route.fulfill({ json: { connection_token: 'capability-test-only', model: 'gpt-4.1-mini', expires_in_seconds: 1800 }, headers });
  });
  await connect(page);
  await page.getByRole('button', { name: 'Check screen', exact: true }).click();
  await page.getByRole('checkbox', { name: 'I reviewed this image' }).check();
  await page.getByRole('button', { name: 'Send to OpenAI' }).click();
  await expect.poll(() => sent.length).toBe(1);
  await page.getByRole('button', { name: 'Cancel check', exact: true }).click();
  await expect.poll(() => cancelStarted).toBe(true);
  await expect(page.getByRole('status').filter({ hasText: 'Window sharing on' })).toBeVisible();
  await expect(page.locator('html')).not.toHaveAttribute('data-capture-stopped', 'true');
  releaseAnswer();
  await page.getByRole('button', { name: 'Check screen', exact: true }).click();
  await page.getByLabel('Tell Guider what happened, or ask a question').fill('Which terminal should I use?');
  await page.getByRole('checkbox', { name: 'I reviewed this image' }).check();
  await page.getByRole('button', { name: 'Send to OpenAI' }).click();
  await expect(page.getByRole('button', { name: 'Cancel check', exact: true })).toBeVisible();
  expect(sent).toHaveLength(1);
  releaseCancel();
  await expect(page.getByRole('heading', { name: guidance.next_step })).toBeVisible();
  expect(sent).toHaveLength(2);
  expect(sent[1].question).toBe('Which terminal should I use?');
  await page.getByLabel('Tell Guider what happened, or ask a question').fill('I see Python 3.13.');
  await page.getByRole('button', { name: 'Check the updated screen', exact: true }).click();
  await expect(page.getByLabel('Tell Guider what happened, or ask a question')).toHaveValue('I see Python 3.13.');
  await page.getByRole('checkbox', { name: 'I reviewed this image' }).check();
  await page.getByRole('button', { name: 'Send to OpenAI' }).click();
  await expect(page.getByRole('heading', { name: guidance.next_step })).toBeVisible();
  expect(sent[2].previous_step).toBe(guidance.next_step);
  expect(sent[2].question).toBe('I see Python 3.13.');
});

test('the key can belong to either service, and the page says which', async ({ page }) => {
  await page.goto('/#live');
  await page.getByRole('button', { name: 'AI screen guide', exact: true }).click();

  // Whatever is offered, the page asks for that service's key and its models.
  await expect(page.getByLabel('OpenAI API key')).toBeVisible();
  await page.getByLabel('Service').selectOption('anthropic');

  await expect(page.getByLabel('Claude API key')).toBeVisible();
  await expect(page.getByLabel('Vision model')).toHaveValue('claude-opus-5');
  await expect(page.getByRole('checkbox', { name: /reviewed frames to Claude/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Connect Claude' })).toBeVisible();
  await expect(page.getByRole('link', { name: /Claude.s data policies/ })).toBeVisible();

  // And switching back restores the other one, key field included.
  await page.getByLabel('Service').selectOption('openai');
  await expect(page.getByLabel('OpenAI API key')).toBeVisible();
  await expect(page.getByLabel('Vision model')).toHaveValue('gpt-4.1-mini');
});

test('Claude review and answer identify the actual destination', async ({ page }) => {
  await simulatedWindow(page);
  const sent: Record<string, unknown>[] = [];
  await page.route('**/api/v1/local-guide/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/saved-keys')) return route.fulfill({ json: { available: false, providers: [] } });
    const headers = { 'Access-Control-Allow-Origin': 'http://127.0.0.1:5173',
      'Access-Control-Allow-Headers': 'authorization,content-type',
      'Access-Control-Allow-Methods': 'POST,DELETE,OPTIONS' };
    if (route.request().method() === 'OPTIONS' || route.request().method() === 'DELETE'
      || path.endsWith('/cancel')) return route.fulfill({ status: 204, headers });
    if (path.endsWith('/checks')) {
      sent.push(route.request().postDataJSON());
      return route.fulfill({ json: guidance, headers });
    }
    expect(route.request().postDataJSON().provider).toBe('anthropic');
    return route.fulfill({ json: { connection_token: 'synthetic-claude', provider: 'anthropic',
      display_name: 'Claude', model: 'claude-haiku-4-5', expires_in_seconds: 1800 }, headers });
  });
  await page.goto('/#live');
  await page.bringToFront();
  await page.getByRole('button', { name: 'AI screen guide', exact: true }).click();
  await page.getByLabel('Service').selectOption('anthropic');
  await page.getByLabel('Vision model').selectOption('claude-haiku-4-5');
  await page.getByLabel('Claude API key').fill('sk-ant-synthetic-not-a-real-key');
  await page.getByRole('checkbox', { name: /I agree to send reviewed frames/ }).check();
  await page.getByRole('button', { name: 'Connect Claude' }).click();
  await page.getByLabel('What are you trying to do?').fill('Help me run Python');
  await page.getByRole('button', { name: 'Share a window', exact: true }).click();
  await page.getByRole('button', { name: 'Check screen', exact: true }).click();
  await expect(page.getByText(/Destination: Claude/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Send to Claude' })).toBeDisabled();
  expect(sent).toHaveLength(0);
  await page.getByRole('checkbox', { name: 'I reviewed this image' }).check();
  await page.getByRole('button', { name: 'Send to Claude' }).click();
  await expect(page.getByRole('img', { name: 'Reviewed frame sent to Claude for this answer' })).toBeVisible();
  expect(sent).toHaveLength(1);
  await expect(page.getByText(/Reviewed images pass through your local backend to Claude/)).toBeVisible();
  await page.getByRole('button', { name: 'Disconnect & clear key' }).click();
  await expect(page.getByLabel('Claude API key')).toHaveValue('');
});
