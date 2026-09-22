import { afterEach, describe, expect, it, vi } from 'vitest';
import { TabGuideBridge } from './tabGuideBridge';

function setup() {
  const win = Object.assign(new EventTarget(), { postMessage: vi.fn() });
  vi.stubGlobal('window', win); vi.stubGlobal('location', { origin: 'https://guider.test' });
  const deliver = (data: object, origin = 'https://guider.test', source: unknown = win) => {
    win.dispatchEvent(Object.assign(new Event('message'), { source, origin,
      data: { source: 'guider-extension', ...data } }));
  };
  const bridge = new TabGuideBridge(), status = vi.fn(), command = vi.fn();
  const dispose = bridge.start(status, command);
  return { win, deliver, bridge, status, command, dispose };
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('explicit tab extension bridge', () => {
  it('ignores other frames/origins and commands for a different capture identity', () => {
    const { deliver, bridge, status, command, dispose } = setup();
    const ready = { type: 'status', connected: true, target: { handle: 'chosen', label: 'Tab', revision: 0 } };
    deliver(ready, 'https://other.test'); deliver(ready, 'https://guider.test', {});
    expect(status).not.toHaveBeenCalled();
    deliver(ready); expect(bridge.status.target?.handle).toBe('chosen');
    deliver({ type: 'command', handle: 'another-tab', command: 'approve' });
    expect(command).not.toHaveBeenCalled();
    deliver({ type: 'command', handle: 'chosen', command: 'stop' });
    expect(command).toHaveBeenCalledWith('stop'); dispose();
  });
  it('requires both overlay acknowledgement and a fresh video frame before upload', async () => {
    const { deliver, win, bridge, dispose } = setup();
    deliver({ type: 'status', connected: true, target: { handle: 'chosen', label: 'Tab', revision: 0 } });
    let frame!: () => void;
    const video = { requestVideoFrameCallback: vi.fn(callback => { frame = callback; return 3; }), cancelVideoFrameCallback: vi.fn() };
    const result = bridge.prepareFrame('chosen', video as unknown as HTMLVideoElement, new AbortController().signal);
    const request = win.postMessage.mock.calls.at(-1)![0];
    deliver({ type: 'prepared', handle: 'another-tab', id: request.id });
    expect(video.requestVideoFrameCallback).not.toHaveBeenCalled();
    deliver({ type: 'prepared', handle: 'chosen', id: request.id });
    frame(); expect(await result).toBe(true); dispose();
  });
  it('cancels waiting capture on Stop and ignores late acknowledgement', async () => {
    const { deliver, win, bridge, dispose } = setup();
    deliver({ type: 'status', connected: true, target: { handle: 'chosen', label: 'Tab', revision: 0 } });
    const video = { requestVideoFrameCallback: vi.fn(), cancelVideoFrameCallback: vi.fn() };
    const controller = new AbortController();
    const result = bridge.prepareFrame('chosen', video as unknown as HTMLVideoElement, controller.signal);
    const request = win.postMessage.mock.calls.at(-1)![0];
    controller.abort(); expect(await result).toBe(false);
    deliver({ type: 'prepared', handle: 'chosen', id: request.id });
    expect(video.requestVideoFrameCallback).not.toHaveBeenCalled(); dispose();
  });
  it('times out without a fresh frame and never treats old pixels as ready', async () => {
    vi.useFakeTimers();
    const { deliver, bridge, dispose } = setup();
    deliver({ type: 'status', connected: true, target: { handle: 'chosen', label: 'Tab', revision: 0 } });
    const video = { requestVideoFrameCallback: vi.fn(), cancelVideoFrameCallback: vi.fn() };
    const result = bridge.prepareFrame('chosen', video as unknown as HTMLVideoElement, new AbortController().signal);
    await vi.advanceTimersByTimeAsync(1500); expect(await result).toBe(false); dispose();
  });
});
