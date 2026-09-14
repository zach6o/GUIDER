# 21 · Continuous-observation consent notice

Status: **draft, pending D06 approval**. Version `observation-draft-2`, pinned in
`app/guide/observation.py` as `NOTICE_VERSION`. Version 2 is a rewrite, not an edit:
[22](22-guider-v2-architecture.md) adds a running description of the screen, and version 1
described something narrower — frames checked against one step. A session that accepted
version 1 is asked again rather than carried forward, which is what the version check has
always been for. A session may only switch watching on
by sending this exact version; an older one is refused and the notice is shown again.
Production remains hard-gated in `Settings.check()` until this notice is approved.

## Why a separate notice

[ADR-016](adr/016-web-first-tiered-observation.md) records the material privacy change
plainly: in continuous mode the user reviews **the scope and the mask once**, not each
outgoing frame. Every earlier path — uploading a screenshot, checking one frame — asked
per image. This one does not, so agreeing to those does not agree to this. The notice is
its own record with its own version for that reason.

## What the user is told, before anything is watched

The copy below is the normative content. Wording may be adjusted for tone; the facts,
the numbers and the controls may not be changed without a new version.

> **Guider can watch this window while you work.**
>
> You choose one window. Guider looks at it only while a step is waiting on you, and only
> when something on screen actually changes. Most of the time it sends nothing at all.
>
> **What leaves your computer.** A still picture of the window you chose, at most once
> every few seconds, and only after something changed. Anything you hide with the mask
> never leaves your computer — the hiding happens here, before anything is sent.
>
>
> **What Guider works out.** From each picture it forms a short description of what is on
> the window — which application it looks like, what screen you are on, which buttons and
> fields it can see, whether a dialog or an error is up. That description is how it knows
> you are in the right place, that a step is already done, or that something is blocking
> you.
>
> **What is kept.** Never the picture. Pictures are used and discarded, never saved, not by
> Guider and not in any backup. The short descriptions are kept for seven days, so the guide
> can tell whether anything changed, and are deleted with the task whenever you delete it.
> Guider also keeps a count of how many pictures it looked at.
>
> **How much.** Up to 200 checks and 30 minutes of watching per task, and no more than 12
> pictures a minute. When that runs out, Guider keeps guiding and you tell it when a step
> is done.
>
> **Who sees it.** The provider you chose, named on this screen. Their terms apply to what
> they do with a picture once it reaches them, and a picture already sent cannot be
> recalled.
>
>
> **What it will never do with what it reads.** Text on your screen is something Guider
> reads, never something it obeys. If a window contains words aimed at Guider, they are
> ignored and never turned into a step.
>
> **Stopping.** One tap, any time, in the guide. Watching also stops on its own after five
> minutes with nothing happening, and your place is saved. Watching stops immediately when
> you stop it, including any check already in progress. Guider never watches anything else
> on your screen, never types, never clicks, and never acts for you.
>
> Guider will show you how many pictures it has looked at, the whole time it is watching.

## Where it is shown

`web/src/guide/consent.ts` carries this wording and the version, and `overlay/WatchSetup.tsx`
shows it before the window picker is ever opened. The version on screen is the one sent to
`POST /sessions/{id}/observation`; when the server expects a newer one it refuses and names it in
`details.current_version`, so the user reads the new notice rather than being carried forward on an
old agreement. Approval under D06 therefore means changing both this document and that file, in the
same change.

## Facts the notice must keep

| Claim | Enforced by |
|---|---|
| Only while a step is waiting | Route refuses unless `state == awaiting_user_action` |
| Only when something changed | Tiers 0 and 1 in `web/src/guide/observer.ts` |
| Masked regions never sent | Mask applied before encoding, in the browser |
| Nothing kept | No `ScreenshotRow` is written; tests assert it |
| 200 checks, 12/minute, 30 minutes | `app/guide/observation.py`, enforced server-side as well |
| Running out keeps guidance working | Budget exhaustion returns a message, not a failure |
| One tap stops, including work in flight | `DELETE …/observation` increments `control_epoch` |
| A count is always visible | `frames_observed` returned on the session and every tick |
| The count shown is the server's | The island renders `frames_observed` from each tick, never a browser-side tally |

Each row is a test, not a promise. A change to any number here is a change to the notice
version and needs D06 again.

## Open before approval

1. D06 owner approves this wording and the retention statement.
2. Name the account-mode provider in the notice once D01 selects one. Until then only
   bring-your-own-key applies, and the user's own supplier terms govern.
3. Decide whether the count persists in task history after a session ends, or is shown
   only while watching.
4. [ADR-011](adr/011-application-allowlisting.md) native gates remain required before any
   distributed release; a browser cannot attest what it is looking at.

## Traceability

R06/R11/R16/R23 → SEC-03/04/05/13/14 → [ADR-016](adr/016-web-first-tiered-observation.md).
Retention class M in [08](08-data-model.md) is zero for `source=observation`: these frames
are never persisted at all.
