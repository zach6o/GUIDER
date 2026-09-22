export interface TabGuideStatus {
  connected: boolean;
  target: { handle: string; label: string; revision: number } | null;
}
export interface TabGuideMessage {
  active: boolean; finished: boolean; approval: boolean; busy: boolean;
  title: string; message: string; where: string;
  target: { x: number; y: number; label: string } | null;
}
export const noTabGuide: TabGuideStatus = { connected: false, target: null };

/** Explicitly installed extension relay. Never sends keys, plans or image pixels. */
export class TabGuideBridge {
  status: TabGuideStatus = noTabGuide;
  private prepared = new Map<string, () => void>();
  private receive: ((event: MessageEvent) => void) | null = null;
  private post(type: string, data = {}) {
    window.postMessage({ source: 'guider-page', type, ...data }, location.origin);
  }
  start(onStatus: (status: TabGuideStatus) => void, onCommand: (command: string) => void) {
    this.receive = event => {
      if (event.source !== window || event.origin !== location.origin || event.data?.source !== 'guider-extension') return;
      const data = event.data;
      if (data.type === 'status') {
        const target = data.target;
        this.status = { connected: data.connected === true, target: target && typeof target.handle === 'string'
          && typeof target.label === 'string' && Number.isSafeInteger(target.revision) ? target : null };
        onStatus(this.status);
      }
      if (data.handle !== this.status.target?.handle) return;
      if (data.type === 'prepared') this.prepared.get(data.id)?.();
      if (data.type === 'command' && typeof data.command === 'string') onCommand(data.command);
    };
    window.addEventListener('message', this.receive); this.post('hello');
    return () => {
      if (this.receive) window.removeEventListener('message', this.receive);
      this.post('shutdown'); this.prepared.clear(); this.status = noTabGuide;
    };
  }
  publish(handle: string, state: TabGuideMessage) {
    if (handle && handle === this.status.target?.handle) this.post('state', {
      ...state, handle, revision: this.status.target.revision,
    });
  }
  /** Wait for the target overlay to disappear and a new capture frame to arrive. */
  async prepareFrame(handle: string, video: HTMLVideoElement, signal: AbortSignal): Promise<boolean> {
    if (handle !== this.status.target?.handle || signal.aborted) return false;
    const id = crypto.randomUUID();
    return new Promise<boolean>(resolve => {
      let callback: number | undefined;
      const finish = (ready: boolean) => {
        clearTimeout(timer); signal.removeEventListener('abort', aborted); this.prepared.delete(id);
        if (callback !== undefined) video.cancelVideoFrameCallback(callback);
        resolve(ready && !signal.aborted && handle === this.status.target?.handle);
      };
      const aborted = () => finish(false);
      const timer = setTimeout(() => finish(false), 1500);
      this.prepared.set(id, () => {
        if (!video.requestVideoFrameCallback) { finish(false); return; }
        callback = video.requestVideoFrameCallback(() => finish(true));
      });
      signal.addEventListener('abort', aborted, { once: true });
      this.post('prepare', { handle, id });
    });
  }
  restore(handle: string) { this.post('restore', { handle }); }
  disconnect() { this.post('shutdown'); }
}
