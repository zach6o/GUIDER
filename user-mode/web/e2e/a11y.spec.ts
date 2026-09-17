/**
 * The parts of the interface only a keyboard finds.
 *
 * A mouse never discovers that Tab walks out of an open dialog, and a sighted
 * user never discovers that the page still works at 200% zoom — right up until
 * it does not. These run the surfaces a keyboard user actually meets, plus the
 * policy the page is served under, which is the other thing nobody sees working.
 */

import { expect, test, type Page } from '@playwright/test';

async function guiding(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore an example' }).click();
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  await page.getByRole('button', { name: 'Start the steps' }).click();
  await expect(page.locator('.guide-island .island-count')).toHaveText('Step 1 of 3');
}

/** Whether the element with focus is inside the open dialog. */
const focusIsInDialog = (page: Page) =>
  page.evaluate(() => Boolean(document.activeElement?.closest('.watch-setup')));

test('a dialog holds the keyboard while it is open', async ({ page }) => {
  await guiding(page);
  await page.getByRole('button', { name: 'Let Guider watch this window' }).click();
  await expect(page.locator('.watch-setup')).toBeVisible();

  // Focus moves in on its own, rather than being left behind on the button.
  expect(await focusIsInDialog(page)).toBe(true);

  // More presses than the dialog has controls: if Tab escaped even once, one of
  // these lands on the page behind it.
  for (let press = 0; press < 12; press++) {
    await page.keyboard.press('Tab');
    expect(await focusIsInDialog(page)).toBe(true);
  }
  await page.keyboard.press('Shift+Tab');
  expect(await focusIsInDialog(page)).toBe(true);
});

test('escape closes the dialog and gives the keyboard back', async ({ page }) => {
  await guiding(page);
  const open = page.getByRole('button', { name: 'Let Guider watch this window' });
  await open.click();
  await expect(page.locator('.watch-setup')).toBeVisible();

  await page.keyboard.press('Escape');
  await expect(page.locator('.watch-setup')).toHaveCount(0);
  // Back where it started: the control that opened the dialog, not the top of
  // the document.
  await expect(open).toBeFocused();
});

test('the guide is usable at 200% zoom on a small screen', async ({ page }) => {
  // 640x512 at 200% is the 1280x1024 desktop a reader with low vision is on.
  await page.setViewportSize({ width: 640, height: 512 });
  await guiding(page);

  const island = page.locator('.guide-island');
  await expect(island).toBeVisible();
  // Nothing may push the page sideways: a horizontal scrollbar at this size is
  // the classic symptom of a fixed width nobody tested.
  const overflows = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
  expect(overflows).toBe(false);
});

test('the page is served under a policy, and nothing on it is blocked', async ({ page }) => {
  const violations: string[] = [];
  page.on('console', message => {
    if (message.text().includes('Content Security Policy')) violations.push(message.text());
  });

  const response = await page.goto('/');
  // The header is the one that can refuse framing; the meta tag is the floor
  // under a static host that forgets it.
  const policy = response?.headers()['content-security-policy'] ?? '';
  expect(policy).toContain("frame-ancestors 'none'");
  await expect(page.locator('meta[http-equiv="Content-Security-Policy"]'))
    .toHaveAttribute('content', /default-src 'self'/);

  await page.getByRole('button', { name: 'Explore an example' }).click();
  await expect(page.getByRole('button', { name: 'Let’s figure it out' })).toBeVisible();
  expect(violations).toEqual([]);
});

test.describe('the dark theme', () => {
  test.use({ colorScheme: 'dark' });

  test('paints the whole page, not half of it', async ({ page }) => {
    await guiding(page);
    // Every surface reads from the palette, so a card that stayed white would be
    // a literal that escaped it — the half-converted theme this change exists to
    // avoid. Sampling the deepest card on the page catches that.
    const lightness = await page.evaluate(() => {
      const value = (el: Element) => {
        const [r, g, b] = getComputedStyle(el).backgroundColor.match(/\d+/g)!.map(Number);
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
      };
      return {
        body: value(document.body),
        panel: value(document.querySelector('.guide-island .island-panel')!),
      };
    });
    expect(lightness.body).toBeLessThan(0.25);
    expect(lightness.panel).toBeLessThan(0.25);
  });

  test('keeps the step readable against it', async ({ page }) => {
    await guiding(page);
    const ratio = await page.evaluate(() => {
      const channel = (v: number) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
      const luminance = (colour: string) => {
        const [r, g, b] = colour.match(/\d+/g)!.map(Number).map(v => channel(v / 255));
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
      };
      const step = document.querySelector('.guide-island .island-panel h2')
        ?? document.querySelector('.guide-island .island-panel')!;
      const panel = document.querySelector('.guide-island .island-panel')!;
      const front = luminance(getComputedStyle(step).color) + 0.05;
      const back = luminance(getComputedStyle(panel).backgroundColor) + 0.05;
      return Math.max(front, back) / Math.min(front, back);
    });
    expect(ratio).toBeGreaterThanOrEqual(4.5);
  });
});
