import { afterEach, describe, expect, it, vi } from 'vitest';
import { ScreenCapture } from './screenCapture';

function fakeStream(surface = 'window') {
  const track = Object.assign(new EventTarget(), {
    stop: vi.fn(), getSettings: () => ({ displaySurface: surface }),
  });
  const stream = { getTracks: () => [track], getVideoTracks: () => [track], getAudioTracks: () => [] };
  return { stream: stream as unknown as MediaStream, track };
}

function setup(picker: () => Promise<MediaStream>) {
  vi.stubGlobal('navigator', { mediaDevices: { getDisplayMedia: vi.fn(picker) } });
  vi.stubGlobal('document', Object.assign(new EventTarget(), { hidden: false }));
  vi.stubGlobal('window', new EventTarget());
}

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('browser capture lifecycle', () => {
  it('closes every track when stopped', async () => {
    const { stream, track } = fakeStream(); setup(async () => stream);
    const capture = new ScreenCapture(); await capture.start(vi.fn());
    expect(capture.active).toBe(true); capture.stop();
    expect(track.stop).toHaveBeenCalledOnce(); expect(capture.active).toBe(false);
  });
  it('rejects full-monitor sharing and closes its stream', async () => {
    const { stream, track } = fakeStream('monitor'); setup(async () => stream);
    await expect(new ScreenCapture().start(vi.fn())).rejects.toThrow('single application window');
    expect(track.stop).toHaveBeenCalledOnce();
  });
  it('discards a picker result returned after stop', async () => {
    const { stream, track } = fakeStream();
    let resolve!: (stream: MediaStream) => void;
    setup(() => new Promise(done => { resolve = done; }));
    const capture = new ScreenCapture(); const opening = capture.start(vi.fn());
    capture.stop(); resolve(stream);
    expect(await opening).toBeNull(); expect(track.stop).toHaveBeenCalledOnce();
  });
  it('stops on source ended, hidden Guider, and offline', async () => {
    for (const event of ['ended', 'visibilitychange', 'offline']) {
      const { stream, track } = fakeStream(); setup(async () => stream);
      const capture = new ScreenCapture(), stopped = vi.fn(); await capture.start(stopped);
      if (event === 'ended') track.dispatchEvent(new Event(event));
      else if (event === 'visibilitychange') {
        Object.assign(document, { hidden: true }); document.dispatchEvent(new Event(event));
      } else window.dispatchEvent(new Event(event));
      expect(track.stop).toHaveBeenCalledOnce(); expect(stopped).toHaveBeenCalledOnce();
      expect(capture.active).toBe(false);
    }
  });
  it('expires without an automatic restart', async () => {
    vi.useFakeTimers(); const { stream, track } = fakeStream(); setup(async () => stream);
    const capture = new ScreenCapture(), stopped = vi.fn(); await capture.start(stopped);
    vi.advanceTimersByTime(15 * 60 * 1000);
    expect(track.stop).toHaveBeenCalledOnce(); expect(stopped).toHaveBeenCalledOnce();
    expect(navigator.mediaDevices.getDisplayMedia).toHaveBeenCalledOnce();
  });
  it('rejects a picker result if Guider became hidden while the picker was open', async () => {
    const { stream, track } = fakeStream();
    let resolve!: (stream: MediaStream) => void;
    setup(() => new Promise(done => { resolve = done; }));
    const capture = new ScreenCapture(), stopped = vi.fn();
    const opening = capture.start(stopped);
    Object.assign(document, { hidden: true });
    resolve(stream);
    expect(await opening).toBeNull();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(stopped).toHaveBeenCalledOnce();
    expect(capture.active).toBe(false);
  });
  it('stops when the selected track becomes unavailable', async () => {
    const { stream, track } = fakeStream(); setup(async () => stream);
    const capture = new ScreenCapture(), stopped = vi.fn(); await capture.start(stopped);
    track.dispatchEvent(new Event('mute'));
    expect(track.stop).toHaveBeenCalledOnce(); expect(stopped).toHaveBeenCalledOnce();
    expect(capture.active).toBe(false);
  });
});
