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

export const NOTICE_VERSION = 'observation-draft-1';

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
    heading: 'What is kept',
    body: 'Nothing. Pictures are used to answer one question — did this step happen — and are '
      + 'never saved, not by Guider and not in any backup. Guider keeps only the answer and a '
      + 'count of how many pictures it looked at.',
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
    body: 'One tap, any time, in the guide. Watching stops immediately, including any check '
      + 'already in progress. Guider never watches anything else on your screen, never types, '
      + 'never clicks, and never acts for you.',
  },
];

export const NOTICE_COUNTER_PROMISE =
  'Guider will show you how many pictures it has looked at, the whole time it is watching.';
