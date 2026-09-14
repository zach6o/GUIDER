/**
 * The three surfaces, and what a browser without one is told.
 *
 * The rule these tests exist for is ADR-016's: side-by-side and mirrored preview
 * are first-class modes, not consolation prizes. So an unavailable surface is
 * still offered as a listed option carrying its reason, and a surface that fails
 * to open produces a sentence rather than silence.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  defaultSurface, fallbackNotice, floatingSupported, mirrorSupported, surfaceOptions,
} from './surface';

function withPictureInPicture(present: boolean) {
  vi.stubGlobal('window', present
    ? { documentPictureInPicture: { requestWindow: async () => ({}), window: null } }
    : {});
}

function withDisplayMedia(present: boolean) {
  vi.stubGlobal('navigator', { mediaDevices: present ? { getDisplayMedia: async () => ({}) } : {} });
}

afterEach(() => vi.unstubAllGlobals());

describe('what this browser can offer', () => {
  it('finds the floating window only where the API exists', () => {
    withPictureInPicture(false);
    expect(floatingSupported()).toBe(false);
    withPictureInPicture(true);
    expect(floatingSupported()).toBe(true);
  });

  it('offers the page whatever the browser is', () => {
    withPictureInPicture(false);
    withDisplayMedia(false);
    const page = surfaceOptions().find(option => option.id === 'page');
    expect(page?.available).toBe(true);
    expect(page?.reason).toBe('');
  });

  it('lists a surface it cannot open, with the reason, rather than hiding it', () => {
    withPictureInPicture(false);
    withDisplayMedia(false);
    const options = surfaceOptions();
    // All three are still offered: a mode this browser lacks is still part of
    // the product, and a user who is never told is left guessing.
    expect(options.map(option => option.id)).toEqual(['floating', 'page', 'mirror']);
    const floating = options[0];
    expect(floating.available).toBe(false);
    expect(floating.reason).toContain('Safari and Firefox cannot');
    expect(options[2].reason).toContain('Chrome or Edge');
  });

  it('says nothing is wrong when everything is available', () => {
    withPictureInPicture(true);
    withDisplayMedia(true);
    expect(surfaceOptions().every(option => option.available)).toBe(true);
    expect(surfaceOptions().every(option => option.reason === '')).toBe(true);
    expect(mirrorSupported()).toBe(true);
  });
});

describe('which surface is offered first', () => {
  it('starts on the page even where a floating window is available', () => {
    // Opening an OS window is the user's decision to make, not a default that
    // happens to them when they press Start.
    withPictureInPicture(true);
    withDisplayMedia(true);
    expect(defaultSurface()).toBe('page');
  });

  it('never preselects the mirror, which would open a picker unasked', () => {
    withPictureInPicture(false);
    withDisplayMedia(true);
    expect(defaultSurface()).not.toBe('mirror');
  });
});

describe('when a surface does not open', () => {
  it('says the guide is on the page instead, and that it still works', () => {
    expect(fallbackNotice('floating', 'declined')).toContain('works the same here');
    expect(fallbackNotice('floating', 'unsupported')).toContain('cannot open a floating window');
  });

  it('distinguishes a declined window share from a browser that cannot share', () => {
    expect(fallbackNotice('mirror', 'declined')).toContain('No window was shared');
    expect(fallbackNotice('mirror', 'unsupported')).toContain('cannot mirror');
  });
});
