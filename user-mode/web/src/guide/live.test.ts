import { describe, expect, it } from 'vitest';
import {
  islandStateFor, initialLiveState, liveReducer, stuckMessage, type LiveState,
} from './live';
import type { CurrentInstruction, Instruction, Step } from '../types';

const step = (overrides: Partial<Step> = {}): Step => ({
  id: 'step-1', ordinal: 1, title: 'Open the terminal', action: 'Open the terminal panel.',
  expected_result: 'A prompt appears.', success_criterion: 'A prompt accepts typing.',
  fallback: 'Use the View menu.', explanation: 'Errors are printed there.',
  application_key: 'vscode', risk: 'low', policy_disposition: 'allow', evidence_kind: 'visual',
  required: true, status: 'awaiting_user_action', attempt_count: 0, verified_at: null,
  ...overrides,
});

const instruction: Instruction = {
  id: 'instruction-1', session_id: 'session-1', step_id: 'step-1', version: 1, status: 'ready',
  what: 'Open the terminal panel.', where: 'In the editor.', why: 'The error is printed there.',
  confirmation_hint: 'A prompt appears.', cannot_find_hint: 'Use the View menu.',
  created_at: '2026-09-13T00:00:00Z',
};

const published = (overrides: Partial<Step> = {}): CurrentInstruction => ({
  instruction, step: step(overrides), session: {} as CurrentInstruction['session'],
});

const reduce = (...actions: Parameters<typeof liveReducer>[1][]): LiveState =>
  actions.reduce(liveReducer, initialLiveState);

describe('following a server session', () => {
  it('shows the step the engine published an instruction for', () => {
    const state = reduce({ type: 'start' }, { type: 'instruction', current: published() });
    expect(state.phase).toBe('waiting');
    expect(state.step?.id).toBe('step-1');
    expect(state.instruction?.what).toBe('Open the terminal panel.');
    expect(islandStateFor(state)).toBe('watching');
  });

  it('waits while the next instruction is being prepared', () => {
    const state = reduce(
      { type: 'start' }, { type: 'instruction', current: published() }, { type: 'preparing' },
    );
    // The previous step stays on screen; only the phase changes.
    expect(state.step?.id).toBe('step-1');
    expect(islandStateFor(state)).toBe('thinking');
  });
});

describe('claiming a step', () => {
  const claimed = reduce(
    { type: 'start' },
    { type: 'instruction', current: published() },
    { type: 'claimed', claimId: 'claim-1' },
  );

  it('asks rather than advancing, and says which claim it is asking about', () => {
    expect(claimed.phase).toBe('asking');
    expect(claimed.claimId).toBe('claim-1');
    expect(claimed.step?.id).toBe('step-1');
    expect(islandStateFor(claimed)).toBe('attention');
  });

  it('stays on the step when the user says it has not happened', () => {
    const state = liveReducer(claimed, { type: 'not_yet' });
    expect(state.phase).toBe('waiting');
    expect(state.step?.id).toBe('step-1');
    expect(state.claimId).toBeNull();
    expect(state.correction).toContain('Still on this step');
  });

  it('drops the claim once the answer has been sent', () => {
    const state = liveReducer(claimed, { type: 'preparing' });
    expect(state.claimId).toBeNull();
    expect(state.correction).toBe('');
  });
});

describe('reaching the end', () => {
  it('reports that the plan is finished without a current step', () => {
    const state = reduce(
      { type: 'start' }, { type: 'instruction', current: published() }, { type: 'finished' },
    );
    expect(state.step).toBeNull();
    expect(state.instruction).toBeNull();
    expect(islandStateFor(state)).toBe('finished');
  });
});

describe('interruptions', () => {
  const running = reduce({ type: 'start' }, { type: 'instruction', current: published() });

  it('shows a pause over the running state, and lifts it again', () => {
    const paused = liveReducer(running, { type: 'pause' });
    expect(islandStateFor(paused)).toBe('idle');
    expect(islandStateFor(liveReducer(paused, { type: 'resume' }))).toBe('watching');
  });

  it('shows a failure in its own state rather than as progress', () => {
    const failed = liveReducer(running, { type: 'failed', message: 'Could not reach Guider.' });
    expect(failed.error).toBe('Could not reach Guider.');
    expect(islandStateFor(failed)).toBe('error');
    // An error outranks a pause: a stopped guide must not read as paused.
    expect(islandStateFor(liveReducer(failed, { type: 'pause' }))).toBe('error');
  });
});

describe('a guide that is going nowhere', () => {
  const running = reduce({ type: 'start' }, { type: 'instruction', current: published() });

  it('says so without changing what the guide is doing', () => {
    const state = liveReducer(running, { type: 'stuck', reason: 'repeated_attempts' });
    expect(state.stuck).toBe('repeated_attempts');
    expect(state.phase).toBe('waiting');
    expect(state.step?.id).toBe('step-1');
    expect(islandStateFor(state)).toBe('watching');
  });

  it('forgets it once the guide is on a different step', () => {
    const stuck = liveReducer(running, { type: 'stuck', reason: 'no_progress' });
    const moved = liveReducer(stuck, { type: 'instruction', current: published({ ordinal: 2 }) });
    expect(moved.stuck).toBe('');
  });

  it('puts the session reason into words without inventing a cause', () => {
    expect(stuckMessage('anomaly:different_app')).toContain('no longer matches');
    expect(stuckMessage('repeated_attempts')).toContain('not working out');
    expect(stuckMessage('no_progress')).toContain('taking longer');
  });
});

describe('saying the guidance was wrong', () => {
  const running = reduce({ type: 'start' }, { type: 'instruction', current: published() });

  it('stops showing a step, because the server withdrew the pointer', () => {
    const blocked = liveReducer(running, {
      type: 'blocked', message: 'Guider has stopped watching.',
    });
    expect(blocked.phase).toBe('blocked');
    expect(blocked.step).toBeNull();
    expect(blocked.instruction).toBeNull();
    expect(blocked.blocked).toBe('Guider has stopped watching.');
    expect(islandStateFor(blocked)).toBe('error');
  });

  it('clears a question and a stuck notice that were about the old step', () => {
    const asking = reduce(
      { type: 'start' },
      { type: 'instruction', current: published() },
      { type: 'stuck', reason: 'repeated_attempts' },
      { type: 'claimed', claimId: 'claim-1' },
    );
    const blocked = liveReducer(asking, { type: 'blocked', message: 'Stopped.' });
    expect(blocked.claimId).toBeNull();
    expect(blocked.askedBy).toBeNull();
    expect(blocked.stuck).toBe('');
  });

  it('reads as stopped even while the guide was paused', () => {
    const paused = liveReducer(running, { type: 'pause' });
    expect(islandStateFor(liveReducer(paused, { type: 'blocked', message: 'Stopped.' })))
      .toBe('error');
  });
});
