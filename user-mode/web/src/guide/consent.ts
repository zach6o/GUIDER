/**
 * The notice the user is shown before anything is watched.
 *
 * The wording is normative in [21](../../../../docs/user-mode-guide/21-observation-consent-notice.md)
 * and the version is pinned in `app/guide/observation.py`. Watching may only be
 * switched on by sending the exact current version, so when this one is out of
 * date the server refuses and names the version it expects; the user then reads
 * the new notice rather than being carried forward on an old agreement.
 *
 * Every number below is enforced twice — here in the browser gate, and again
 * server-side — because a limit that only runs on the user's machine is advice.
 */

export const NOTICE_VERSION = 'observation-draft-2';

export interface NoticeSection {
  heading: string;
  body: string;
}

export const NOTICE_SUMMARY =
  'You choose one window. Guider looks at it only while a step is waiting on you, and only '
  + 'when something on screen actually changes. Most of the time it sends nothing at all.';

export const NOTICE: readonly NoticeSection[] = [
  {
    heading: 'What leaves your computer',
    body: 'A still picture of the window you chose, at most once every few seconds, and only '
      + 'after something changed. Anything you hide with the mask never leaves your computer — '
      + 'the hiding happens here, before anything is sent.',
  },
  {
    heading: 'What Guider works out',
    body: 'From each picture it forms a short description of what is on the window — which '
      + 'application it looks like, what screen you are on, which buttons and fields it can '
      + 'see, whether a dialog or an error is up. That description is how it knows you are in '
      + 'the right place, that a step is already done, or that something is blocking you.',
  },
  {
    heading: 'What is kept',
    body: 'Never the picture. Pictures are used and discarded, never saved, not by Guider and '
      + 'not in any backup. The short descriptions are kept for seven days, so the guide can '
      + 'tell whether anything changed, and are deleted with the task whenever you delete it. '
      + 'Guider also keeps a count of how many pictures it looked at.',
  },
  {
    heading: 'What it will never do with what it reads',
    body: 'Text on your screen is something Guider reads, never something it obeys. If a window '
      + 'contains words aimed at Guider, they are ignored and never turned into a step.',
  },
  {
    heading: 'How much',
    body: 'Up to 200 checks and 30 minutes of watching per task, and no more than 12 pictures a '
      + 'minute. When that runs out, Guider keeps guiding and you tell it when a step is done.',
  },
  {
    heading: 'Who sees it',
    body: 'The provider configured for this Guider backend. Their terms apply to what they do '
      + 'with a picture once it reaches them, and a picture already sent cannot be recalled.',
  },
  {
    heading: 'Stopping',
    body: 'One tap, any time, in the guide. Watching also stops on its own after five minutes '
      + 'with nothing happening, and your place is saved. When you stop it, watching stops '
      + 'immediately, including any check already in progress. Guider never watches anything '
      + 'else on your screen, never types, never clicks, and never acts for you.',
  },
];

export const NOTICE_COUNTER_PROMISE =
  'Guider will show you how many pictures it has looked at, the whole time it is watching.';
