/**
 * The island, driven by a server session.
 *
 * Everything the user sees here comes from the Guide Engine: the current step is
 * whichever step the server published an instruction for, and progress happens
 * because a route accepted a claim or a self-report, never because this file
 * decided a step was done. `web/src/guide/engine.ts` remains the offline
 * practice demo's reducer; this is its live counterpart.
 *
 * The honesty rule of ADR-010 survives the move: "I've done this" records a
 * claim, saying it happened records a `user_reported` verification, and neither
 * one ever marks a step verified. The copy says so, because the record does.
 */

import { useCallback, useEffect, useReducer, useRef } from 'react';
import type { CurrentInstruction, GuideApi, Instruction, Session, Step } from '../types';
import { followEvents } from './events';
import type { IslandState } from '../overlay/states';

export type LivePhase =
  | 'idle' | 'starting' | 'waiting' | 'asking' | 'preparing' | 'finished' | 'blocked' | 'error';

export interface LiveState {
  phase: LivePhase;
  instruction: Instruction | null;
  step: Step | null;
  /** The claim the current question is about. Null when the observer asked
   *  first, because then the user has not claimed anything yet. */
  claimId: string | null;
  /** Who raised the current question. An observer's `ask` band is evidence
   *  worth a question, never enough to advance on its own. */
  askedBy: 'user' | 'observer' | null;
  correction: string;
  error: string;
  paused: boolean;
  /** Why the session says it is going nowhere, if it has said so. Nothing about
   *  being stuck changes what the guide does; it only offers a way out. */
  stuck: string;
  /** Set once the user has said the guidance was wrong and the server has
   *  blocked the session. The guide stops here rather than pointing again. */
  blocked: string;
}

export type LiveAction =
  | { type: 'start' }
  | { type: 'instruction'; current: CurrentInstruction }
  | { type: 'preparing' }
  | { type: 'claimed'; claimId: string }
  | { type: 'observer_ask' }
  | { type: 'stuck'; reason: string }
  | { type: 'not_yet' }
  | { type: 'blocked'; message: string }
  | { type: 'resumed' }
  | { type: 'finished' }
  | { type: 'failed'; message: string }
  | { type: 'pause' }
  | { type: 'resume' };

export const initialLiveState: LiveState = {
  phase: 'idle', instruction: null, step: null, claimId: null, askedBy: null,
  correction: '', error: '', paused: false, stuck: '', blocked: '',
};

export function liveReducer(state: LiveState, action: LiveAction): LiveState {
  switch (action.type) {
    case 'start':
      return { ...initialLiveState, phase: 'starting' };
    case 'instruction':
      return {
        ...state, phase: 'waiting', instruction: action.current.instruction,
        step: action.current.step, claimId: null, askedBy: null, error: '',
        // A new step is a fresh start: whatever was stuck was about the old one.
        // The same step reworded is not — being stuck is about the step, so a
        // retry must not wipe the notice that the retry itself just raised.
        stuck: state.step?.id === action.current.step.id ? state.stuck : '',
      };
    case 'preparing':
      // The step stays on screen until the next instruction replaces it, so the
      // island never blanks between steps.
      return { ...state, phase: 'preparing', claimId: null, askedBy: null, correction: '' };
    case 'claimed':
      return {
        ...state, phase: 'asking', claimId: action.claimId, askedBy: 'user', correction: '',
      };
    case 'stuck':
      return { ...state, stuck: action.reason };
    case 'observer_ask':
      // Middle-band evidence: ask once, with one tap, and never advance on it.
      if (state.phase !== 'waiting' || state.paused) return state;
      return { ...state, phase: 'asking', claimId: null, askedBy: 'observer', correction: '' };
    case 'not_yet':
      return {
        ...state, phase: 'waiting', claimId: null, askedBy: null,
        correction: 'Still on this step. Try it again, or skip it.',
      };
    case 'finished':
      return {
        ...state, phase: 'finished', instruction: null, step: null, claimId: null, askedBy: null,
      };
    case 'blocked':
      // Nothing is current any more: the server withdrew the instruction, so the
      // island must not keep showing it as something to do.
      return {
        ...state, phase: 'blocked', blocked: action.message, instruction: null, step: null,
        claimId: null, askedBy: null, correction: '', stuck: '',
      };
    case 'resumed':
      // Back from blocked or paused. The step arrives on the event stream when
      // the engine has one, so this only clears what the stop left behind.
      return {
        ...state, phase: 'preparing', blocked: '', error: '', correction: '', paused: false,
      };
    case 'failed':
      return { ...state, phase: 'error', error: action.message };
    case 'pause':
      return { ...state, paused: true };
    case 'resume':
      return { ...state, paused: false };
  }
}

export function islandStateFor(state: LiveState): IslandState {
  if (state.phase === 'error' || state.phase === 'blocked') return 'error';
  if (state.paused) return 'idle';
  if (state.phase === 'finished') return 'finished';
  if (state.phase === 'asking') return 'attention';
  if (state.phase === 'starting' || state.phase === 'preparing') return 'thinking';
  return 'watching';
}

/** How the session's own reason reads to the person waiting on it. */
export function stuckMessage(reason: string): string {
  if (reason.startsWith('anomaly:')) {
    return 'What Guider can see no longer matches this plan.';
  }
  if (reason === 'repeated_attempts') return 'This step is not working out.';
  return 'This is taking longer than the plan expected.';
}

/** Events that mean the current step may have changed. Anything else is history. */
const REFRESH_ON = new Set([
  'instruction.ready', 'plan.steps_exhausted', 'step.awaiting_action', 'session.blocked',
]);
const LONG_POLL_MS = 25_000;

export interface LiveGuide {
  state: LiveState;
  session: Session | null;
  /** Whether a step is genuinely waiting on the user right now. The observer
   *  may only look while this is true. */
  awaitingAction: () => boolean;
  start: () => Promise<void>;
  claim: () => Promise<void>;
  answer: (happened: boolean) => Promise<void>;
  skip: () => Promise<void>;
  /** An observer verdict in the middle band: worth one question, nothing more. */
  observerAsked: () => void;
  /** Say the current guidance was wrong. Expensive by design (doc 05): the
   *  pointer is withdrawn, watching is revoked and the session blocks. */
  reportIncorrect: (said: string) => Promise<void>;
  /** Pick a blocked or paused task back up. Nothing about watching comes back
   *  with it: that is a fresh decision with its own notice. */
  resumeGuide: () => Promise<void>;
  /** Ask for this step in different words. Not a claim, not a skip. */
  retry: (said: string) => Promise<void>;
  /** Ask for a replacement plan for whatever is left. Resolves with the
   *  operation to follow, or null when there is nothing to replan. */
  replan: () => Promise<string | null>;
  togglePause: () => void;
  close: () => void;
}

/**
 * Runs one server session for the island.
 *
 * The session's own event stream is the source of truth for "what am I on now":
 * an instruction is published by a worker, not by the request that asked for it,
 * so the client follows `GuidanceEvent.sequence` and refetches when it hears.
 */
export function useLiveGuide(api: GuideApi, session: Session | null): LiveGuide {
  const [state, dispatch] = useReducer(liveReducer, initialLiveState);
  const current = useRef<Session | null>(session);
  const following = useRef<AbortController | null>(null);
  const running = useRef(false);

  // Never adopt an older session than the one already held. `session` is a prop
  // captured when the page rendered, so a caller that hands back what it read
  // there — after a claim, a report or a resume has already moved the session on
  // — would otherwise push this guide backwards and the next request would be
  // refused for a stale version.
  useEffect(() => {
    const held = current.current;
    if (!session || !held || session.id !== held.id
      || session.state_version > held.state_version) {
      current.current = session;
    }
  }, [session]);
  useEffect(() => () => following.current?.abort(), []);

  const fail = useCallback((error: unknown) => {
    dispatch({
      type: 'failed',
      message: error instanceof Error ? error.message : 'The guide stopped unexpectedly.',
    });
  }, []);

  const refresh = useCallback(async () => {
    const id = current.current?.id;
    if (!id) return;
    const next = await api.instruction(id);
    // No instruction yet is not the same as no steps left: a worker publishes
    // the next one, and `plan.steps_exhausted` is what says the plan is over.
    if (!next) return;
    current.current = next.session;
    dispatch({ type: 'instruction', current: next });
  }, [api]);

  const follow = useCallback((id: string) => {
    following.current?.abort();
    const controller = new AbortController();
    following.current = controller;
    void followEvents({
      fetchPage: (after, signal) => api.events(id, after, LONG_POLL_MS, signal),
      onEvents: events => {
        const stuck = events.filter(event => event.type === 'session.stuck_detected').at(-1);
        if (stuck) {
          dispatch({ type: 'stuck', reason: String(stuck.payload.reason ?? '') });
        }
        if (events.some(event => event.type === 'plan.steps_exhausted')) {
          // Every step has been dealt with. Nothing here claims they passed.
          dispatch({ type: 'finished' });
          return;
        }
        if (events.some(event => REFRESH_ON.has(event.type))) void refresh().catch(fail);
      },
      signal: controller.signal,
    });
  }, [api, fail, refresh]);

  const act = useCallback(async (action: () => Promise<void>) => {
    if (running.current) return;
    running.current = true;
    try { await action(); } catch (error) { fail(error); } finally { running.current = false; }
  }, [fail]);

  const start = useCallback(() => act(async () => {
    const session = current.current;
    if (!session) return;
    dispatch({ type: 'start' });
    const started = await api.start(session);
    current.current = started.session;
    // The first instruction is published by a worker, so it arrives on the event
    // stream rather than in this response.
    follow(session.id);
  }), [act, api, follow]);

  const claim = useCallback(() => act(async () => {
    const session = current.current;
    const step = state.step;
    if (!session || !step || state.paused) return;
    const claimed = await api.claim(session, step.id, 'Marked done in the guide.');
    current.current = claimed.session;
    dispatch({ type: 'claimed', claimId: claimed.claim_id });
  }), [act, api, state.step, state.paused]);

  const answer = useCallback((happened: boolean) => act(async () => {
    let session = current.current;
    const step = state.step;
    if (!session || !step || state.paused) return;
    if (!happened) {
      dispatch({ type: 'not_yet' });
      return;
    }
    let claimId = state.claimId;
    if (!claimId) {
      // The observer asked, so there is no claim yet. Answering yes is the
      // user's word, and is recorded as exactly that before anything moves.
      const claimed = await api.claim(session, step.id, 'Confirmed when Guider asked.');
      current.current = claimed.session;
      session = claimed.session;
      claimId = claimed.claim_id;
    }
    const reported = await api.selfReport(
      session, step.id, claimId, 'The user said this step was done.',
    );
    current.current = reported.session;
    // Recorded as user_reported, never as a pass. The next step arrives on the
    // event stream when the engine has one ready.
    dispatch({ type: 'preparing' });
  }), [act, api, refresh, state.step, state.claimId, state.paused]);

  const skip = useCallback(() => act(async () => {
    const session = current.current;
    const step = state.step;
    if (!session || !step || state.paused) return;
    const skipped = await api.skipStep(session, step.id, 'not_applicable');
    current.current = skipped.session;
    dispatch({ type: 'preparing' });
  }), [act, api, refresh, state.step, state.paused]);

  const observerAsked = useCallback(() => dispatch({ type: 'observer_ask' }), []);

  const reportIncorrect = useCallback((said: string) => act(async () => {
    const session = current.current;
    const step = state.step;
    if (!session || !step) return;
    const recorded = await api.reportIncorrect(session, step.id, said);
    current.current = recorded.session;
    // Watching is already off server-side; stop listening too, because the
    // session will publish nothing more until the user resumes it.
    following.current?.abort();
    following.current = null;
    dispatch({
      type: 'blocked',
      message: recorded.verification_withdrawn
        ? 'Thanks. That step is no longer marked as checked, and Guider has stopped watching.'
        : 'Thanks. Guider has stopped pointing at this step and stopped watching.',
    });
  }), [act, api, state.step]);

  const resumeGuide = useCallback(() => act(async () => {
    const session = current.current;
    if (!session) return;
    const resumed = await api.resume(session, 'screenshot_only');
    current.current = resumed.session;
    dispatch({ type: 'resumed' });
    // The stream was dropped when the session stopped, so start listening again
    // before the fresh instruction is published.
    follow(session.id);
  }), [act, api, follow]);

  const retry = useCallback((said: string) => act(async () => {
    const session = current.current;
    const step = state.step;
    if (!session || !step || state.paused) return;
    const pending = await api.retryStep(session, step.id, said);
    current.current = pending.session;
    // The same step, in different words. Nothing about it has moved.
    dispatch({ type: 'preparing' });
  }), [act, api, state.step, state.paused]);

  const replan = useCallback(async (): Promise<string | null> => {
    const session = current.current;
    if (!session) return null;
    try {
      const pending = await api.replan(session, state.stuck.startsWith('anomaly:')
        ? 'anomaly' : state.stuck ? 'stuck' : 'user');
      current.current = pending.session;
      // The guide stops following the old plan here: what comes back is a draft
      // the user reviews before anything continues.
      following.current?.abort();
      following.current = null;
      dispatch({ type: 'preparing' });
      return pending.operation_id;
    } catch (error) {
      fail(error);
      return null;
    }
  }, [api, fail, state.stuck]);

  const awaitingAction = useCallback(
    () => state.phase === 'waiting' && !state.paused && state.step !== null,
    [state.phase, state.paused, state.step],
  );

  const togglePause = useCallback(() => {
    // Local to the island on purpose: with watching off nothing is running on
    // the server to pause, and the session's own pause has no resume route yet.
    dispatch({ type: state.paused ? 'resume' : 'pause' });
  }, [state.paused]);

  const close = useCallback(() => {
    following.current?.abort();
    following.current = null;
  }, []);

  return {
    state, session: current.current, awaitingAction,
    start, claim, answer, skip, observerAsked, reportIncorrect, resumeGuide, retry, replan,
    togglePause, close,
  };
}
