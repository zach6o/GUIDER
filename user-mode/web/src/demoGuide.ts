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
export type DemoState = {
  step: number; phase: 'ready' | 'checking' | 'complete'; paused: boolean; playing: boolean;
  page: 'workspace' | 'settings'; tab: 'general' | 'appearance'; theme: 'light' | 'dark';
  saved: boolean; correction: string;
};
export const initialDemoState: DemoState = {
  step: 0, phase: 'ready', paused: false, playing: false,
  page: 'workspace', tab: 'general', theme: 'light', saved: false, correction: '',
};
export type DemoAction = { type: 'act'; target: DemoActionId | 'other' }
  | { type: 'verify' | 'pause' | 'resume' | 'watch' | 'practice' | 'restart' };

export function demoReducer(state: DemoState, action: DemoAction): DemoState {
  switch (action.type) {
    case 'restart': return { ...initialDemoState };
    case 'pause': return { ...state, paused: true };
    case 'resume': return { ...state, paused: false };
    case 'practice': return { ...state, playing: false, paused: false };
    case 'watch': return state.phase === 'complete'
      ? { ...initialDemoState, playing: true } : { ...state, playing: true, paused: false };
    case 'act': {
      if (state.paused || state.phase !== 'ready') return state;
      if (action.target !== demoSteps[state.step].id) {
        return { ...state, correction: `Try ${demoSteps[state.step].target}, marked by the green outline.` };
      }
      const next = { ...state, phase: 'checking' as const, correction: '' };
      if (action.target === 'settings') next.page = 'settings';
      if (action.target === 'appearance') next.tab = 'appearance';
      if (action.target === 'dark') next.theme = 'dark';
      if (action.target === 'save') next.saved = true;
      return next;
    }
    case 'verify': {
      if (state.paused || state.phase !== 'checking') return state;
      const evidence = [state.page === 'settings', state.tab === 'appearance', state.theme === 'dark', state.saved && state.theme === 'dark'];
      if (!evidence[state.step]) return { ...state, phase: 'ready', correction: 'The expected sample change is missing. Try the highlighted control again.' };
      if (state.step === demoSteps.length - 1) return { ...state, phase: 'complete', playing: false };
      return { ...state, step: state.step + 1, phase: 'ready' };
    }
  }
}
