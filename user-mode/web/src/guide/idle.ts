/**
 * Noticing that nobody is there, and saying only what can honestly be known.
 *
 * A web page cannot see mouse movement or keystrokes in other applications, so
 * this measures the two things it genuinely observes: the shared window has not
 * changed, and nobody has touched Guider. That is what the copy says too — never
 * "you walked away", which would be a guess dressed as a fact.
 *
 * Four stages, each firing once, and the last one stops watching rather than
 * asking again. Nothing is lost at any stage: stopping is the ordinary stop, and
 * the session stays exactly as resumable as it was a second earlier.
 */

export type IdleStage = 'offer' | 'remind' | 'warn' | 'stop';

export interface IdleStep {
  stage: IdleStage;
  afterMs: number;
  message: string;
}

/** The staging from doc 22, in one place so the copy and the timing cannot drift
 *  apart. Every message describes what was observed, not what the user did. */
export const IDLE_STEPS: readonly IdleStep[] = [
  {
    stage: 'offer',
    afterMs: 30_000,
    message: 'Nothing has changed for a while. Want this step explained differently?',
  },
  {
    stage: 'remind',
    afterMs: 60_000,
    message: 'Still on the same step. Guider is here when you are ready.',
  },
  {
    stage: 'warn',
    afterMs: 180_000,
    message: 'Watching will switch off shortly, and your place will be kept.',
  },
  {
    stage: 'stop',
    afterMs: 300_000,
    message: 'Watching switched off after five quiet minutes. Your place is saved.',
  },
];

export interface IdleOptions {
  now?: () => number;
  /** Fired once per stage, in order. */
  onStage: (step: IdleStep) => void;
}

/**
 * Tracks quiet time and announces each stage once.
 *
 * Deliberately not a timer: the caller already has a frame loop and a UI, so
 * this is driven by `activity()` and `check()`. That keeps it testable without
 * fake clocks in the DOM, and keeps the page from holding a timer alive after
 * the guide is gone.
 */
export class IdleWatcher {
  private since: number;
  private fired = new Set<IdleStage>();
  private readonly now: () => number;

  constructor(private readonly options: IdleOptions) {
    this.now = options.now ?? (() => Date.now());
    this.since = this.now();
  }

  /** Something happened: a changed frame, a press, an answer. Everything resets,
   *  including stages already announced, because the quiet period is over. */
  activity(): void {
    this.since = this.now();
    this.fired.clear();
  }

  get quietMs(): number {
    return this.now() - this.since;
  }

  /** Announce whichever stages the quiet time has now passed. Returns the last
   *  one announced, so a caller can act on `stop` without inspecting state. */
  check(): IdleStage | null {
    let last: IdleStage | null = null;
    for (const step of IDLE_STEPS) {
      if (this.quietMs >= step.afterMs && !this.fired.has(step.stage)) {
        this.fired.add(step.stage);
        this.options.onStage(step);
        last = step.stage;
      }
    }
    return last;
  }

  /** After a stop, the watcher should not keep counting toward another one. */
  reset(): void {
    this.since = this.now();
    this.fired = new Set(['offer', 'remind', 'warn', 'stop']);
  }
}
