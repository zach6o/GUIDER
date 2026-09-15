/**
 * Tier 2: sending an admitted frame, and living with the answer.
 *
 * `observer.ts` decides whether a frame is worth anything without touching the
 * network. This file is the only place a frame leaves the machine, and it does
 * so under every limit the consent notice promises (doc 21):
 *
 *   - only while a step is waiting on the user
 *   - only after the local gate admitted the frame
 *   - masked regions are painted out before encoding, here, never server-side
 *   - one request in flight at a time, and the counter shown is the server's
 *
 * Nothing is retained. A frame exists as a string for the length of one request
 * and is dropped whether it was accepted, refused or abandoned.
 */

import { MotionGate, type Decision } from './observer';
import type { ContextTick, GuideApi, ObservationTick, Session } from '../types';

/** How often the cheap local comparison runs. Sending is far rarer. */
export const SAMPLE_INTERVAL_MS = 500;

export interface FrameSource {
  /** A 64x64 grayscale thumbnail for the gate, or null when the window is not
   *  ready. Never sent anywhere. */
  sample(): Uint8Array | null;
  /** The masked frame, base64-encoded without a data: prefix. */
  encode(): Promise<string>;
}

export interface WatchHooks {
  /** The session as the rest of the app currently knows it, for its version. */
  session(): Session | null;
  /** Observation runs only while a step is actually waiting. */
  awaitingAction(): boolean;
  /** Server-side counters, so the overlay never shows a number of its own. */
  onCounters(framesObserved: number, callsRemaining: number): void;
  /** A verdict worth acting on: `ask` needs a person, `advance` already moved. */
  onTick(tick: ObservationTick): void;
  /** What the guide now believes is on screen, and what it wants to do about
   *  it. Arrives on every admitted frame; `changed` is false most of the time. */
  onContext?(tick: ContextTick): void;
  /** Something the user should read: budget spent, provider unable to read. */
  onNotice(message: string): void;
  /** Watching ended, with the reason to show. */
  onStopped(reason: string): void;
}

export type WatchStatus = 'off' | 'watching' | 'sending';

/** Reasons the loop gives up on its own. Each one keeps the guide running. */
const STOPPING_CODES = new Set(['observation_off', 'observation_stopped', 'session_stopped']);

export class Watcher {
  private gate = new MotionGate();
  private timer: ReturnType<typeof setInterval> | null = null;
  private inFlight: AbortController | null = null;
  private budget = 0;
  private sending = false;
  private toldAboutReading = false;

  constructor(
    private readonly api: GuideApi,
    private readonly source: FrameSource,
    private readonly hooks: WatchHooks,
  ) {}

  get status(): WatchStatus {
    if (!this.timer) return 'off';
    return this.sending ? 'sending' : 'watching';
  }

  /** Switch watching on, against the exact notice the user was shown. */
  async start(consentVersion: string): Promise<void> {
    const session = this.hooks.session();
    if (!session) throw new Error('Start the guide before switching watching on.');
    const state = await this.api.startWatching(session, consentVersion);
    this.budget = state.observation_calls_remaining;
    this.hooks.onCounters(state.frames_observed, state.observation_calls_remaining);
    this.gate.reset();
    this.timer ??= setInterval(() => void this.pump(Date.now()), SAMPLE_INTERVAL_MS);
  }

  /**
   * One tap. The loop stops here first so nothing new is sent, the request in
   * flight is abandoned, and the server increments `control_epoch` so a frame
   * already with a provider cannot come back and advance a step.
   */
  async stop(reason: string, notify = true): Promise<void> {
    const session = this.hooks.session();
    this.halt();
    try {
      if (session) {
        const state = await this.api.stopWatching(session.id);
        this.hooks.onCounters(state.frames_observed, state.observation_calls_remaining);
      }
    } finally {
      if (notify) this.hooks.onStopped(reason);
    }
  }

  /** Local half of stopping: no network, always safe to call twice. */
  halt(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.inFlight?.abort();
    this.inFlight = null;
    this.sending = false;
    this.gate.reset();
  }

  /** One sampling tick. Exposed so it can be driven directly under test. */
  async pump(now: number): Promise<Decision | 'idle'> {
    if (!this.timer || this.sending) return 'idle';
    const gray = this.source.sample();
    if (!gray) return 'idle';
    const decision = this.gate.consider(gray, now, {
      awaitingAction: this.hooks.awaitingAction(),
      budgetRemaining: this.budget,
    });
    if (decision === 'exhausted') {
      await this.spent('Guider has watched as much as this task allows. '
        + 'Keep going and tell it when a step is done.');
      return decision;
    }
    if (decision !== 'admit') return decision;
    await this.send(now);
    return decision;
  }

  private async send(now: number): Promise<void> {
    const session = this.hooks.session();
    if (!session) return;
    this.sending = true;
    const controller = new AbortController();
    this.inFlight = controller;
    try {
      const image = await this.source.encode();
      const admittedAt = new Date(now).toISOString();
      // One frame, encoded once, used for both questions. Encoding it twice
      // would double the work on the user's machine for no more information —
      // and the two calls are already counted against one budget server-side.
      if (this.hooks.onContext) {
        try {
          this.hooks.onContext(
            await this.api.observeContext(session, image, admittedAt, controller.signal),
          );
        } catch (contextError) {
          // Context is an improvement, never a requirement. A guide that stopped
          // checking steps because it could not describe the screen would be
          // worse than one that just checks steps.
          await this.handle(contextError);
        }
      }
      const tick = await this.api.observe(
        session, image, admittedAt, controller.signal,
      );
      this.budget = tick.observation_calls_remaining;
      this.hooks.onCounters(tick.frames_observed, tick.observation_calls_remaining);
      // A development observer that cannot read frames says so once, rather than
      // leaving a counter ticking up beside nothing happening.
      if (tick.anomaly === 'unreadable' && !this.toldAboutReading) {
        this.toldAboutReading = true;
        this.hooks.onNotice(tick.note);
      }
      this.hooks.onTick(tick);
    } catch (error) {
      await this.handle(error);
    } finally {
      this.sending = false;
      if (this.inFlight === controller) this.inFlight = null;
    }
  }

  private async handle(error: unknown): Promise<void> {
    if (error instanceof DOMException && error.name === 'AbortError') return;
    const failure = error as { status?: number; code?: string; message?: string };
    const code = failure.code ?? '';
    if (code === 'observation_budget_spent') {
      await this.spent(failure.message ?? 'Watching has run out for this task.');
      return;
    }
    if (STOPPING_CODES.has(code)) {
      this.halt();
      this.hooks.onStopped(failure.message ?? 'Watching was switched off.');
      return;
    }
    // A tick is disposable: rate limits and "no step waiting right now" are
    // answered by simply not sending the next one yet.
    if (code === 'rate_limited' || code === 'observation_in_progress') return;
    if (failure.status === 409) return;
    this.halt();
    this.hooks.onStopped(failure.message ?? 'Watching stopped because Guider could not be reached.');
  }

  /** Running out is a supported mode, not a failure: the guide keeps going. */
  private async spent(message: string): Promise<void> {
    this.budget = 0;
    this.halt();
    this.hooks.onNotice(message);
    const session = this.hooks.session();
    if (session) {
      try {
        const state = await this.api.stopWatching(session.id);
        this.hooks.onCounters(state.frames_observed, state.observation_calls_remaining);
      } catch {
        // Already off, or unreachable. Locally it is off either way.
      }
    }
    this.hooks.onStopped(message);
  }
}
