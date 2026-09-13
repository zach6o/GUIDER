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
  | 'idle' | 'starting' | 'waiting' | 'asking' | 'preparing' | 'finished' | 'error';

export interface LiveState {
  phase: LivePhase;
  instruction: Instruction | null;
  step: Step | null;
  /** The claim the current question is about. Only set while phase is `asking`. */
  claimId: string | null;
  correction: string;
  error: string;
  paused: boolean;
}

export type LiveAction =
  | { type: 'start' }
  | { type: 'instruction'; current: CurrentInstruction }
  | { type: 'preparing' }
  | { type: 'claimed'; claimId: string }
  | { type: 'not_yet' }
  | { type: 'finished' }
  | { type: 'failed'; message: string }
  | { type: 'pause' }
  | { type: 'resume' };

export const initialLiveState: LiveState = {
  phase: 'idle', instruction: null, step: null, claimId: null,
  correction: '', error: '', paused: false,
};

export function liveReducer(state: LiveState, action: LiveAction): LiveState {
  switch (action.type) {
    case 'start':
      return { ...initialLiveState, phase: 'starting' };
    case 'instruction':
      return {
        ...state, phase: 'waiting', instruction: action.current.instruction,
        step: action.current.step, claimId: null, error: '',
      };
    case 'preparing':
      // The step stays on screen until the next instruction replaces it, so the
      // island never blanks between steps.
      return { ...state, phase: 'preparing', claimId: null, correction: '' };
    case 'claimed':
      return { ...state, phase: 'asking', claimId: action.claimId, correction: '' };
    case 'not_yet':
      return {
        ...state, phase: 'waiting', claimId: null,
        correction: 'Still on this step. Try it again, or skip it.',
      };
    case 'finished':
      return { ...state, phase: 'finished', instruction: null, step: null, claimId: null };
    case 'failed':
      return { ...state, phase: 'error', error: action.message };
    case 'pause':
      return { ...state, paused: true };
    case 'resume':
      return { ...state, paused: false };
  }
}

export function islandStateFor(state: LiveState): IslandState {
  if (state.phase === 'error') return 'error';
  if (state.paused) return 'idle';
  if (state.phase === 'finished') return 'finished';
  if (state.phase === 'asking') return 'attention';
  if (state.phase === 'starting' || state.phase === 'preparing') return 'thinking';
  return 'watching';
}

/** Events that mean the current step may have changed. Anything else is history. */
const REFRESH_ON = new Set([
  'instruction.ready', 'plan.steps_exhausted', 'step.awaiting_action', 'session.blocked',
]);
const LONG_POLL_MS = 25_000;

export interface LiveGuide {
  state: LiveState;
  session: Session | null;
  start: () => Promise<void>;
  claim: () => Promise<void>;
  answer: (happened: boolean) => Promise<void>;
  skip: () => Promise<void>;
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

  useEffect(() => { current.current = session; }, [session]);
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
    const session = current.current;
    const step = state.step;
    if (!session || !step || !state.claimId || state.paused) return;
    if (!happened) {
      dispatch({ type: 'not_yet' });
      return;
    }
    const reported = await api.selfReport(
      session, step.id, state.claimId, 'The user said this step was done.',
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

  const togglePause = useCallback(() => {
    // Local to the island on purpose: with watching off nothing is running on
    // the server to pause, and the session's own pause has no resume route yet.
    dispatch({ type: state.paused ? 'resume' : 'pause' });
  }, [state.paused]);

  const close = useCallback(() => {
    following.current?.abort();
    following.current = null;
  }, []);

  return { state, session: current.current, start, claim, answer, skip, togglePause, close };
}
