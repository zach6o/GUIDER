import { guideReducer, initialGuideState, type GuideState } from './guide/engine';

export const demoSteps = [
  { id: 'settings', title: 'Open Settings.', target: 'Settings', hint: 'Click Settings here',
    instruction: 'Click the highlighted Settings button in the practice window.',
    observation: 'The sample workspace is open in its light theme.', evidence: 'The Settings page opens.' },
  { id: 'appearance', title: 'Choose Appearance.', target: 'Appearance', hint: 'Click Appearance',
    instruction: 'Choose Appearance in the settings sidebar.',
    observation: 'Settings is open. The appearance controls are in the sidebar.', evidence: 'The theme choices become visible.' },
  { id: 'dark', title: 'Select the dark theme.', target: 'Dark theme', hint: 'Tap Dark theme',
    instruction: 'Select the Dark theme card. The sample preview will change.',
    observation: 'The sample is currently using the light theme.', evidence: 'Dark is selected and the sample preview changes.' },
  { id: 'save', title: 'Save the change.', target: 'Save changes', hint: 'Click Save changes',
    instruction: 'Click Save changes inside the practice window to finish.',
    observation: 'The dark theme is selected, with a change waiting to be saved.', evidence: 'The sample confirms that the dark theme was saved.' },
] as const;

export type DemoActionId = typeof demoSteps[number]['id'];
/** Guide progression plus the practice app's own state. The engine owns the first
 *  half and knows nothing about the second. */
export type DemoState = GuideState & {
  playing: boolean;
  page: 'workspace' | 'settings'; tab: 'general' | 'appearance'; theme: 'light' | 'dark';
  saved: boolean;
};
export const initialDemoState: DemoState = {
  ...initialGuideState, playing: false,
  page: 'workspace', tab: 'general', theme: 'light', saved: false,
};
export type DemoAction = { type: 'act'; target: DemoActionId | 'other' }
  | { type: 'verify' | 'pause' | 'resume' | 'watch' | 'practice' | 'restart' };

/** The sample change each step expects to see. This is the demo's evidence: the
 *  engine never inspects it, it only receives the verdict. */
function evidenceFor(state: DemoState): boolean {
  return [
    state.page === 'settings',
    state.tab === 'appearance',
    state.theme === 'dark',
    state.saved && state.theme === 'dark',
  ][state.step];
}

/** Engine corrections carry a reason, not copy. The demo supplies its own wording. */
export function correctionText(state: DemoState): string {
  if (state.correction === 'wrong_target') {
    return `Try ${demoSteps[state.step].target}, marked by the green outline.`;
  }
  if (state.correction === 'missing_evidence') {
    return 'The expected sample change is missing. Try the highlighted control again.';
  }
  return '';
}

export function demoReducer(state: DemoState, action: DemoAction): DemoState {
  switch (action.type) {
    case 'restart': return { ...initialDemoState };
    case 'practice': return { ...state, playing: false, paused: false };
    case 'watch': return state.phase === 'complete'
      ? { ...initialDemoState, playing: true } : { ...state, playing: true, paused: false };
    case 'pause': return { ...state, ...guideReducer(demoSteps, state, { type: 'pause' }) };
    case 'resume': return { ...state, ...guideReducer(demoSteps, state, { type: 'resume' }) };
    case 'act': {
      const next = { ...state, ...guideReducer(demoSteps, state, { type: 'act', target: action.target }) };
      // The sample only changes when the engine accepted the action.
      if (next.phase === 'checking' && state.phase !== 'checking') {
        if (action.target === 'settings') next.page = 'settings';
        if (action.target === 'appearance') next.tab = 'appearance';
        if (action.target === 'dark') next.theme = 'dark';
        if (action.target === 'save') next.saved = true;
      }
      return next;
    }
    case 'verify': {
      const next = {
        ...state, ...guideReducer(demoSteps, state, { type: 'verify', passed: evidenceFor(state) }),
      };
      // Playback stops itself at the end; the engine has no opinion on it.
      return next.phase === 'complete' ? { ...next, playing: false } : next;
    }
  }
}
