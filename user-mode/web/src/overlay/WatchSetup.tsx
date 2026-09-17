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
  /** Opens the browser's own window picker. Must be called inside the click. */
  chooseWindow: () => Promise<MediaStream | null>;
  /** Hands over the chosen window and the mask, and switches watching on. */
  onStart: (stream: MediaStream, masks: MaskArea[], consentVersion: string) => Promise<void>;
  onCancel: () => void;
}

type Stage = 'notice' | 'scope';
const MIN_AREA = 0.005;

export function WatchSetup({ chooseWindow, onStart, onCancel }: WatchSetupProps) {
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

  async function choose() {
    setError('');
    try {
      const stream = await chooseWindow();
      if (!stream) return;
      live.current = stream;
      setStage('scope');
      // The element exists on the next paint; attach then.
      queueMicrotask(() => {
        if (video.current) {
          video.current.srcObject = stream;
          void video.current.play().catch(() => {});
        }
      });
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
        <p className="muted">{NOTICE_SUMMARY}</p>
        <div className="notice-sections">
          {NOTICE.map(section => <article key={section.heading}>
            <h3>{section.heading}</h3>
            <p>{section.body}</p>
          </article>)}
        </div>
        <p className="privacy-note"><ShieldCheck size={14} /> {NOTICE_COUNTER_PROMISE}</p>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="plan-buttons">
          <button className="text-button" onClick={onCancel}>Not now</button>
          <button className="primary" onClick={() => void choose()}>Choose a window</button>
        </div>
        <small>Notice version {NOTICE_VERSION}. Watching stays off until you press start.</small>
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
        {error && <p className="error" role="alert">{error}</p>}
        <div className="plan-buttons">
          <button className="text-button" disabled={busy} onClick={onCancel}>Cancel</button>
          <button className="primary" disabled={busy} onClick={() => void start()}>
            {busy ? 'Switching on…' : 'Start watching'}
          </button>
        </div>
        <small>You can stop watching at any time, in one tap, from the guide.</small>
      </>}
    </section>
  </div>;
}
