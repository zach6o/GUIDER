/**
 * Reading the notice, choosing the window, and hiding what should not be seen.
 *
 * Three things happen here in one order, and none of them can be skipped: the
 * user reads what continuous watching means, picks exactly one window, and then
 * sees that window with the chance to paint over anything private. Only after
 * that is watching switched on, against the version of the notice actually shown.
 */

import { useEffect, useRef, useState } from 'react';
import { Eye, EyeOff, RotateCcw, ShieldCheck, X } from 'lucide-react';
import { NOTICE, NOTICE_COUNTER_PROMISE, NOTICE_SUMMARY, NOTICE_VERSION } from '../guide/consent';
import type { MaskArea } from './frameSource';
import { useFocusTrap } from '../a11y';

export interface WatchSetupProps {
  personalProvider?: string;
  floatingGuide?: { enabled: boolean; supported: boolean; onChange: (enabled: boolean) => void };
  /** Opens the browser's own window picker. Must be called inside the click. */
  chooseWindow: () => Promise<MediaStream | null>;
  /** Hands over the chosen window and the mask, and switches watching on. */
  onStart: (stream: MediaStream, masks: MaskArea[], consentVersion: string) => Promise<void>;
  onCancel: () => void;
}

type Stage = 'notice' | 'scope';
const MIN_AREA = 0.005;

export function WatchSetup({ chooseWindow, onStart, onCancel, personalProvider, floatingGuide }: WatchSetupProps) {
  const [stage, setStage] = useState<Stage>('notice');
  const [masks, setMasks] = useState<MaskArea[]>([]);
  const [drawing, setDrawing] = useState<MaskArea | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const origin = useRef<{ x: number; y: number } | null>(null);
  const live = useRef<MediaStream | null>(null);
  const dialog = useRef<HTMLElement>(null);
  // Escape is the same as "Not now": it cancels the setup, which stops the
  // chosen window through the caller. Nothing has been switched on to undo.
  useFocusTrap(dialog, true, { onEscape: onCancel });

  useEffect(() => () => { live.current?.getTracks().forEach(track => track.stop()); }, []);

  useEffect(() => {
    const preview = video.current;
    if (stage !== 'scope' || !preview || !live.current) return;
    preview.srcObject = live.current;
    void preview.play().catch(() => {});
    return () => { preview.srcObject = null; };
  }, [stage]);

  async function choose() {
    setError('');
    try {
      const stream = await chooseWindow();
      if (!stream) return;
      live.current = stream;
      setStage('scope');
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'That window could not be shared.');
    }
  }

  function at(event: React.PointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
    };
  }

  function finishArea() {
    if (drawing && drawing.width * drawing.height >= MIN_AREA) setMasks([...masks, drawing]);
    setDrawing(null);
    origin.current = null;
  }

  async function start() {
    const stream = live.current;
    if (!stream) return;
    setBusy(true); setError('');
    try {
      // The stream outlives this dialog from here on, so it is not stopped by
      // the unmount cleanup below.
      live.current = null;
      await onStart(stream, masks, NOTICE_VERSION);
    } catch (failure) {
      live.current = stream;
      setError(failure instanceof Error ? failure.message : 'Watching could not be switched on.');
      setBusy(false);
    }
  }

  return <div className="modal-backdrop">
    <section ref={dialog} tabIndex={-1} className="watch-setup" role="dialog" aria-modal="true" aria-labelledby="watch-title">
      <button className="icon-button modal-close" aria-label="Close" onClick={onCancel}>
        <X size={20} />
      </button>

      {stage === 'notice' ? <>
        <span className="brand-mark"><Eye size={24} /></span>
        <h2 id="watch-title">Guider can watch this window while you work.</h2>
        <p className="muted">{personalProvider ? `Guider will automatically send selected, masked screenshots to ${personalProvider} to guide the plan you confirmed. This uses your API account and may incur charges.` : NOTICE_SUMMARY}</p>
        <div className="notice-sections">
          {personalProvider ? <>
            <article><h3>You choose the scope</h3><p>Share one application window or browser tab, then hide private areas. No microphone or whole-display capture. Choose a new source whenever the task moves to another window.</p></article>
            <article><h3>Automatic screen checks</h3><p>Changes are checked locally. While watching, selected frames may be sent at most six times per minute, including occasional checks while the screen is still. There are at most 120 AI requests per connection and sharing expires after 15 minutes. Guider does not save these frames.</p></article>
            <article><h3>You stay in control</h3><p>You perform every action. Sharing continues when you switch tabs or applications. Use the floating guide, return to this tab, or use your browser’s stop-sharing control to stop. Pause or Stop sharing cancels pending guidance. Closing the floating control stops sharing. A frame already sent cannot be recalled.</p></article>
          </> : NOTICE.map(section => <article key={section.heading}>
            <h3>{section.heading}</h3>
            <p>{section.body}</p>
          </article>)}
        </div>
        <p className="privacy-note"><ShieldCheck size={14} /> {personalProvider ? 'The guide shows remaining requests. Your provider controls its own retention and billing.' : NOTICE_COUNTER_PROMISE}</p>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="plan-buttons">
          <button className="text-button" onClick={onCancel}>Not now</button>
          <button className="primary" onClick={() => void choose()}>Choose a window</button>
        </div>
        <small>Watching stays off until you review the preview and press start.</small>
      </> : <>
        <span className="brand-mark"><EyeOff size={24} /></span>
        <h2 id="watch-title">Hide anything Guider should not see.</h2>
        <p className="muted">
          Drag across the preview to paint over anything private. Hidden areas are painted out in
          this browser, before any picture is sent.
        </p>
        <div
          className="watch-preview"
          onPointerDown={event => {
            origin.current = at(event);
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={event => {
            const start = origin.current;
            if (!start) return;
            const end = at(event);
            setDrawing({
              x: Math.min(start.x, end.x), y: Math.min(start.y, end.y),
              width: Math.abs(end.x - start.x), height: Math.abs(end.y - start.y),
            });
          }}
          onPointerUp={finishArea}
          onPointerCancel={finishArea}
        >
          <video ref={video} muted playsInline aria-label="Preview of the window Guider will watch" />
          {[...masks, ...(drawing ? [drawing] : [])].map((area, index) => <div
            key={index}
            className={area === drawing ? 'watch-mask drawing' : 'watch-mask'}
            style={{
              left: `${area.x * 100}%`, top: `${area.y * 100}%`,
              width: `${area.width * 100}%`, height: `${area.height * 100}%`,
            }}
          />)}
        </div>
        <div className="editor-tools">
          <button disabled={!masks.length || busy} onClick={() => setMasks(masks.slice(0, -1))}>
            <RotateCcw size={16} /> Undo
          </button>
          <span className="muted">{masks.length
            ? `${masks.length} area${masks.length === 1 ? '' : 's'} hidden`
            : 'Nothing hidden yet'}</span>
        </div>
        {floatingGuide && <>
          <label className="check-label"><input type="checkbox" checked={floatingGuide.enabled}
            disabled={busy || !floatingGuide.supported} onChange={event => floatingGuide.onChange(event.target.checked)} />
            Keep the guide ball visible over other tabs</label>
          <p className="privacy-note">{floatingGuide.supported
            ? 'Start watching opens a floating guide with step messages and Stop controls. You can move it beside your work.'
            : 'Floating guidance requires desktop Chrome or Edge. In this browser, guidance stays on the Guider page.'}</p>
        </>}
        {error && <p className="error" role="alert">{error}</p>}
        <div className="plan-buttons">
          <button className="text-button" disabled={busy} onClick={onCancel}>Cancel</button>
          <button className="primary" disabled={busy} onClick={() => void start()}>
            {busy ? 'Switching on…' : 'Start watching'}
          </button>
        </div>
        <small>{personalProvider ? 'To stop, use the guide ball’s menu, Stop sharing on the preview, or close the floating window.' : 'You can stop watching at any time, in one tap, from the guide.'}</small>
      </>}
    </section>
  </div>;
}
