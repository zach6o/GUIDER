/** Owns actual browser tracks. Never persists or uploads a MediaStream. */
export class ScreenCapture {
  private stream: MediaStream | null = null;
  private generation = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private cleanup: (() => void) | null = null;

  get active() { return this.stream !== null; }
  get handle() {
    const track = this.stream?.getVideoTracks()[0] as (MediaStreamTrack & {
      getCaptureHandle?: () => { handle: string } | null;
    }) | undefined;
    return track?.getSettings().displaySurface === 'browser' ? track.getCaptureHandle?.()?.handle || '' : '';
  }

  /** A temporarily muted source still belongs to this capture, but has no fresh pixels. */
  get ready() {
    const track = this.stream?.getVideoTracks()[0];
    return Boolean(track && track.readyState === 'live' && !track.muted);
  }

  stop() {
    this.generation++;
    this.cleanup?.(); this.cleanup = null;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.stream?.getTracks().forEach(track => track.stop());
    this.stream = null;
  }

  async start(
    onStopped: (reason: string) => void,
    allowHidden: () => boolean = () => false,
    options: { keepOnMute?: boolean } = {},
  ): Promise<MediaStream | null> {
    this.stop();
    const generation = this.generation;
    if (!navigator.mediaDevices?.getDisplayMedia) {
      throw new Error('Window sharing requires desktop Chrome or Edge on localhost or HTTPS.');
    }
    const displayOptions: DisplayMediaStreamOptions & Record<string, unknown> = {
      video: { displaySurface: 'window', frameRate: { ideal: 5, max: 10 } }, audio: false,
      monitorTypeSurfaces: 'exclude', selfBrowserSurface: 'exclude',
      surfaceSwitching: 'exclude', systemAudio: 'exclude',
    };
    // Must remain directly inside a user click; no await before the picker invocation.
    const stream = await navigator.mediaDevices.getDisplayMedia(displayOptions);
    if (generation !== this.generation) { stream.getTracks().forEach(t => t.stop()); return null; }
    const video = stream.getVideoTracks()[0];
    const surface = video?.getSettings().displaySurface;
    if (!video || !['window', 'browser'].includes(surface || '')) {
      stream.getTracks().forEach(t => t.stop());
      throw new Error('Choose a single application window or browser tab, rather than an entire display.');
    }
    if ((document.hidden && !allowHidden()) || navigator.onLine === false || video.readyState === 'ended'
        || (video.muted && !options.keepOnMute)) {
      stream.getTracks().forEach(track => track.stop());
      onStopped('The selected window is unavailable. Keep Guider visible and choose a window again.');
      return null;
    }
    stream.getAudioTracks().forEach(track => { track.stop(); stream.removeTrack(track); });
    this.stream = stream;
    const end = () => { this.stop(); onStopped('Sharing ended. Choose a window again when you’re ready.'); };
    const unavailable = () => {
      if (options.keepOnMute) return; // Browser tab transitions can temporarily pause frames.
      this.stop(); onStopped('The shared window is unavailable. Sharing is off.');
    };
    const hidden = () => { if (document.hidden && !allowHidden()) { this.stop(); onStopped('Sharing stopped because Guider was hidden.'); } };
    const offline = () => { this.stop(); onStopped('You’re offline. Sharing has stopped.'); };
    video.addEventListener('ended', end);
    video.addEventListener('mute', unavailable);
    document.addEventListener('visibilitychange', hidden);
    window.addEventListener('offline', offline);
    window.addEventListener('pagehide', end);
    this.cleanup = () => {
      video.removeEventListener('ended', end); video.removeEventListener('mute', unavailable);
      document.removeEventListener('visibilitychange', hidden);
      window.removeEventListener('offline', offline); window.removeEventListener('pagehide', end);
    };
    this.timer = setTimeout(() => { this.stop(); onStopped('The 15-minute sharing permission expired. Choose a window again.'); }, 15 * 60 * 1000);
    return stream;
  }

  async snapshot(video: HTMLVideoElement): Promise<Blob> {
    const generation = this.generation;
    const track = this.stream?.getVideoTracks()[0];
    if (!track || track.readyState !== 'live' || track.muted || video.readyState < 2
        || !video.videoWidth || !video.videoHeight) throw new Error('The window is not ready. Bring it into view and try again.');
    const scale = Math.min(1, 2560 / Math.max(video.videoWidth, video.videoHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext('2d')!.drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(
      value => value ? resolve(value) : reject(new Error('Could not capture this window.')), 'image/png',
    ));
    // Clear backing pixels even if the callback races Stop.
    canvas.width = canvas.height = 0;
    if (generation !== this.generation || !this.stream) throw new DOMException('Capture canceled', 'AbortError');
    return blob;
  }
}
