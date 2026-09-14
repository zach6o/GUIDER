import { describe, expect, it, vi } from 'vitest';
import { InstructionSpeaker, spokenText } from './speech';

function speaker() {
  const spoken: string[] = [];
  const api = {
    speak: vi.fn((utterance: unknown) => spoken.push(String(utterance))),
    cancel: vi.fn(),
    speaking: false,
  };
  return { api, spoken, instance: new InstructionSpeaker(api, text => text) };
}

const instruction = {
  what: 'Type python --version and press Enter.',
  where: 'In the terminal panel at the bottom.',
  confirmation_hint: 'A version number is printed.',
};

describe('what gets read aloud', () => {
  it('reads the action, then where to look, then what to listen for', () => {
    const text = spokenText(instruction);
    expect(text).toContain('Type python --version');
    expect(text).toContain('In the terminal panel');
    expect(text).toContain('You will know it worked when a version number is printed.');
  });

  it('leaves out the parts the island keeps behind a disclosure', () => {
    // Reading the explanation every time turns guidance into narration.
    const text = spokenText({ ...instruction, where: null, confirmation_hint: null });
    expect(text).toBe('Type python --version and press Enter.');
  });
});

describe('speaking', () => {
  it('cancels before every utterance rather than queueing', () => {
    const { api, instance } = speaker();
    instance.speak('first');
    instance.speak('second');
    // A queue of stale instructions would have the user hearing a step they are
    // already past.
    expect(api.cancel).toHaveBeenCalledTimes(2);
    expect(api.speak).toHaveBeenCalledTimes(2);
  });

  it('says nothing at all for empty text', () => {
    const { api, instance } = speaker();
    instance.speak('   ');
    expect(api.speak).not.toHaveBeenCalled();
  });

  it('does not repeat itself on a re-render', () => {
    const { api, instance } = speaker();
    expect(instance.speakOnce('the same step')).toBe(true);
    expect(instance.speakOnce('the same step')).toBe(false);
    expect(api.speak).toHaveBeenCalledTimes(1);
  });

  it('speaks again once the step actually changes', () => {
    const { instance, spoken } = speaker();
    instance.speakOnce('step one');
    instance.speakOnce('step two');
    expect(spoken).toEqual(['step one', 'step two']);
  });

  it('forgets what it said when cancelled, so a resume can repeat it', () => {
    const { api, instance } = speaker();
    instance.speakOnce('step one');
    instance.cancel();
    expect(instance.speakOnce('step one')).toBe(true);
    expect(api.speak).toHaveBeenCalledTimes(2);
  });
});

describe('what voice may not do', () => {
  it('exposes nothing that could settle a step', () => {
    const { instance } = speaker();
    // Voice is delivery, never authority: hearing an instruction is not
    // performing it, and this object cannot claim, skip or confirm anything.
    const surface = Object.getOwnPropertyNames(Object.getPrototypeOf(instance));
    expect(surface.sort()).toEqual(
      ['cancel', 'constructor', 'speak', 'speakOnce', 'speaking'].sort(),
    );
  });
});
