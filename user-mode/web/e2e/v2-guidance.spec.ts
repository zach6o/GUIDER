/**
 * What V2 looks like from the user's side, on the surfaces the demo can reach.
 *
 * The browser demo has no vision provider, so it cannot produce a context or a
 * mark — and refuses to invent either. What it can show, and what these tests
 * hold, is that the controls V2 adds behave the way the record demands: reading
 * aloud is offered rather than assumed, and nothing on screen claims a step was
 * checked when it was not.
 */

import { expect, test, type Page } from '@playwright/test';

const island = (page: Page) => page.locator('.guide-island');

async function guiding(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore an example' }).click();
  await page.getByRole('button', { name: 'Let’s figure it out' }).click();
  await page.getByRole('button', { name: 'Suggest the steps' }).click();
  await page.getByRole('button', { name: 'Confirm this plan' }).click();
  await page.getByRole('button', { name: 'Start the steps' }).click();
  await expect(island(page).locator('.island-count')).toHaveText('Step 1 of 3');
}

test('reading aloud is offered, off, and reversible', async ({ page }) => {
  await guiding(page);
  const toggle = page.getByRole('button', { name: 'Read steps aloud' });
  // Off by default: a guide that started talking when a page loaded would be a
  // guide that talked over a meeting.
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');

  await toggle.click();
  const silence = page.getByRole('button', { name: 'Stop reading steps aloud' });
  await expect(silence).toHaveAttribute('aria-pressed', 'true');
  await silence.click();
  await expect(page.getByRole('button', { name: 'Read steps aloud' }))
    .toHaveAttribute('aria-pressed', 'false');
});

test('the guide says nothing about the screen when nothing is watching', async ({ page }) => {
  await guiding(page);
  // No watching, no belief. The island must not imply it can see anything.
  await expect(island(page).locator('.island-context')).toHaveCount(0);
  await expect(island(page).locator('.island-skip-offer')).toHaveCount(0);
});

// The demo's refusal to watch at all is already held by
// `watch-consent.spec.ts`, which carries the fake window picker that exercise
// needs. Duplicating it here would duplicate the scaffolding, not the coverage.
