/**
 * Step progression, shared by the practice demo and live guidance.
 *
 * This mirrors `app/guide/engine.py`: acting on a step is a *claim*, and a claim
 * advances nothing. Only evidence does. The two are separate actions here for the
 * same reason they are separate records on the server — collapsing them is the
 * mistake ADR-010 exists to prevent.
 *
 * The engine knows nothing about what the steps describe, so the offline demo can
 * exercise the same code path a server-driven session uses.
 */

export type Phase = 'ready' | 'checking' | 'complete';

/** Why the guide is asking the user to try again. The caller supplies the copy. */
export type Correction = '' | 'wrong_target' | 'missing_evidence';

export interface GuideStep {
  id: string;
  /** What the step points at, named when correcting a wrong action. */
  target: string;
}

export interface GuideState {
  step: number;
  phase: Phase;
  paused: boolean;
  correction: Correction;
}

export type GuideAction =
  | { type: 'act'; target: string }
  | { type: 'verify'; passed: boolean }
  | { type: 'pause' }
  | { type: 'resume' }
  | { type: 'restart' };

export const initialGuideState: GuideState = {
  step: 0, phase: 'ready', paused: false, correction: '',
};

export const isComplete = (state: GuideState) => state.phase === 'complete';

/** Whether this action would be accepted right now. A paused guide accepts none. */
export function accepts(state: GuideState, action: GuideAction): boolean {
  if (action.type === 'act') return !state.paused && state.phase === 'ready';
  if (action.type === 'verify') return !state.paused && state.phase === 'checking';
  return true;
}

export function guideReducer(
  steps: readonly GuideStep[], state: GuideState, action: GuideAction,
): GuideState {
  switch (action.type) {
    case 'restart':
      return { ...initialGuideState };
    case 'pause':
      return { ...state, paused: true };
    case 'resume':
      return { ...state, paused: false };
    case 'act': {
      if (!accepts(state, action)) return state;
      // A wrong action is not progress and not an error: correct and stay put.
      if (action.target !== steps[state.step].id) {
        return { ...state, correction: 'wrong_target' };
      }
      // Claimed, not done. Verification decides.
      return { ...state, phase: 'checking', correction: '' };
    }
    case 'verify': {
      if (!accepts(state, action)) return state;
      if (!action.passed) return { ...state, phase: 'ready', correction: 'missing_evidence' };
      if (state.step === steps.length - 1) return { ...state, phase: 'complete', correction: '' };
      return { ...state, step: state.step + 1, phase: 'ready', correction: '' };
    }
  }
}
