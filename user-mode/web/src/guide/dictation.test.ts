import { afterEach, expect, it, vi } from 'vitest';
import { Dictation, type Recognition } from './dictation';

class Fake implements Recognition {
  static last: Fake;
  continuous = false; interimResults = false; lang = '';
  onresult: Recognition['onresult'] = null;
  onerror: Recognition['onerror'] = null;
  onend: Recognition['onend'] = null;
  start = vi.fn(); stop = vi.fn(); abort = vi.fn();
  constructor() { Fake.last = this; }
}
afterEach(() => vi.useRealTimers());
it('stops microphone acquisition after 30 seconds and abandons delayed results', () => {
  vi.useFakeTimers();
  const hooks = { text: vi.fn(), ended: vi.fn(), error: vi.fn() };
  const dictation = new Dictation(Fake, hooks); dictation.start();
  vi.advanceTimersByTime(30000); expect(Fake.last.stop).toHaveBeenCalledOnce();
  vi.advanceTimersByTime(5000); expect(Fake.last.abort).toHaveBeenCalledOnce();
  expect(hooks.ended).toHaveBeenCalledOnce();
});
it('cancellation discards late transcripts', () => {
  const text = vi.fn(); const dictation = new Dictation(Fake, { text, ended: vi.fn(), error: vi.fn() });
  dictation.start(); const late = Fake.last.onresult; dictation.cancel();
  late?.({ results: [{ isFinal: true, 0: { transcript: 'Do something' } }] });
  expect(text).not.toHaveBeenCalled(); expect(Fake.last.abort).toHaveBeenCalledOnce();
});
it('provides bounded text without submitting or approving anything', () => {
  const text = vi.fn(); const dictation = new Dictation(Fake, { text, ended: vi.fn(), error: vi.fn() });
  dictation.start(); Fake.last.onresult?.({ results: [{ isFinal: true, 0: { transcript: 'x'.repeat(5000) } }] });
  expect(text).toHaveBeenCalledWith('x'.repeat(4000)); dictation.cancel();
});
