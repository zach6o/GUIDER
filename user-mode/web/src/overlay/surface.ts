/**
 * Where the guide sits while the user works.
 *
 * [ADR-016](../../../../docs/user-mode-guide/adr/016-web-first-tiered-observation.md)
 * names three surfaces and calls the last two first-class modes rather than
 * degradations: a Document Picture-in-Picture window, the island on the page
 * beside the user's work, and the page with the user's own window mirrored into
 * it. Only the first is Chromium-only, and doc 20 lists its absence on Safari
 * and Firefox as a risk precisely because a fallback discovered late is a
 * fallback nobody designed.
 *
 * So this module makes the choice explicit and always visible. A surface this
 * browser cannot open is listed with the reason it cannot, never hidden: a user
 * on Firefox should learn that the floating window is a Chromium feature, not
 * silently receive a different product from the one the documentation
 * describes.
 *
 * Nothing here captures, encodes or sends anything. The mirror is a local video
 * element and is not the observation path: watching has its own consent, its own
 * window choice and its own masking step, and asks for them separately even
 * while a mirror is on screen.
 */

import { pipSupported } from './pip';

export type GuideSurface = 'floating' | 'page' | 'mirror';

export interface SurfaceOption {
  id: GuideSurface;
  label: string;
  /** What the user gets, in one line. */
  description: string;
  available: boolean;
  /** Why not, when it is unavailable. Shown, not swallowed. */
  reason: string;
}

export const floatingSupported = () => pipSupported();

export const mirrorSupported = () =>
  typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getDisplayMedia;

export function surfaceOptions(): SurfaceOption[] {
  return [
    {
      id: 'floating',
      label: 'A floating window',
      description: 'The guide sits on top of your other windows.',
      available: floatingSupported(),
      reason: floatingSupported()
        ? ''
        : 'Your browser cannot open one yet. Chrome and Edge can; Safari and Firefox cannot.',
    },
    {
      id: 'page',
      label: 'Beside your work',
      description: 'The guide stays on this page. Put it next to the app you are using.',
      available: true,
      reason: '',
    },
    {
      id: 'mirror',
      label: 'With your window mirrored here',
      description: 'Your chosen window is shown on this page, under the guide.',
      available: mirrorSupported(),
      reason: mirrorSupported()
        ? ''
        : 'Sharing a window needs desktop Chrome or Edge on localhost or HTTPS.',
    },
  ];
}

/** Always the page.
 *
 * A floating OS window and a window share are both deliberate acts: one takes
 * over the user's screen furniture, the other opens a picker. Preselecting
 * either would make pressing Start do something the user did not ask for, and
 * the page is the one surface every browser has. Availability decides what can
 * be picked, never what is picked for you. */
export function defaultSurface(): GuideSurface {
  return 'page';
}

/** What to tell the user when a surface could not be opened after they picked
 *  it. Falling back is fine; falling back silently is not. */
export function fallbackNotice(from: GuideSurface, why: 'declined' | 'unsupported'): string {
  if (from === 'floating') {
    return why === 'unsupported'
      ? 'This browser cannot open a floating window, so the guide is on the page.'
      : 'The floating window did not open, so the guide is on the page. It works the same here.';
  }
  return why === 'unsupported'
    ? 'This browser cannot mirror a window, so the guide is on the page.'
    : 'No window was shared, so the guide is on the page without a mirror.';
}

/** Copy for the mirror panel. Stated every time it is on screen, because a
 *  video of the user's own desktop inside a web page should never leave anyone
 *  guessing whether it is being read. */
export const MIRROR_NOTE =
  'This mirror stays on your machine. Guider is not looking at it: watching is '
  + 'separate, off by default, and asks for its own permission.';
