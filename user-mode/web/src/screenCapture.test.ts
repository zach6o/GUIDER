import { afterEach, describe, expect, it, vi } from 'vitest';
import { ScreenCapture } from './screenCapture';

function fakeStream(surface = 'window') {
  const track = Object.assign(new EventTarget(), {
    stop: vi.fn(), getSettings: () => ({ displaySurface: surface }), readyState: 'live', muted: false,
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
  it('permits a hidden page only while its floating control is available', async () => {
    const { stream, track } = fakeStream(); setup(async () => stream);
    let floating = true;
    const capture = new ScreenCapture(), stopped = vi.fn();
    await capture.start(stopped, () => floating);
    Object.assign(document, { hidden: true });
    document.dispatchEvent(new Event('visibilitychange'));
    expect(capture.active).toBe(true);
    floating = false;
    document.dispatchEvent(new Event('visibilitychange'));
    expect(capture.active).toBe(false);
    expect(track.stop).toHaveBeenCalledOnce();
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
  it('keeps automatic tab capture when the picker switches focus and while working in another tab', async () => {
    const { stream, track } = fakeStream('browser');
    setup(async () => { Object.assign(document, { hidden: true }); return stream; });
    const capture = new ScreenCapture(), stopped = vi.fn();
    expect(await capture.start(stopped, () => true, { keepOnMute: true })).toBe(stream);
    document.dispatchEvent(new Event('visibilitychange'));
    expect(capture.active).toBe(true);
    expect(capture.ready).toBe(true);
    expect(track.stop).not.toHaveBeenCalled();
    expect(stopped).not.toHaveBeenCalled();
    window.dispatchEvent(new Event('pagehide'));
    expect(capture.active).toBe(false);
    expect(track.stop).toHaveBeenCalledOnce();
  });
  it('waits for initially muted automatic capture and recovers without reopening the picker', async () => {
    const { stream, track } = fakeStream('browser'); track.muted = true;
    setup(async () => stream);
    const capture = new ScreenCapture(), stopped = vi.fn();
    expect(await capture.start(stopped, () => true, { keepOnMute: true })).toBe(stream);
    expect(capture.active).toBe(true); expect(capture.ready).toBe(false);
    track.muted = false; track.dispatchEvent(new Event('unmute'));
    expect(capture.ready).toBe(true);
    track.muted = true; track.dispatchEvent(new Event('mute'));
    expect(capture.active).toBe(true); expect(capture.ready).toBe(false);
    expect(track.stop).not.toHaveBeenCalled(); expect(stopped).not.toHaveBeenCalled();
    track.dispatchEvent(new Event('ended'));
    expect(capture.active).toBe(false); expect(capture.ready).toBe(false);
    expect(track.stop).toHaveBeenCalledOnce(); expect(stopped).toHaveBeenCalledOnce();
    expect(navigator.mediaDevices.getDisplayMedia).toHaveBeenCalledOnce();
  });
  it('does not resume after explicit Stop during a temporary mute', async () => {
    const { stream, track } = fakeStream('browser'); setup(async () => stream);
    const capture = new ScreenCapture(); await capture.start(vi.fn(), () => true, { keepOnMute: true });
    track.muted = true; track.dispatchEvent(new Event('mute'));
    capture.stop();
    track.muted = false; track.dispatchEvent(new Event('unmute'));
    expect(capture.active).toBe(false); expect(capture.ready).toBe(false);
    expect(track.stop).toHaveBeenCalledOnce();
  });
});
