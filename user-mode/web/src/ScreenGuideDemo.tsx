import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Check, CheckCircle2, Compass, Eye, LoaderCircle, Maximize2, MonitorUp,
  Moon, MousePointer2, Pause, Play, RotateCcw, Settings, Square, Sun, X } from 'lucide-react';
import { ScreenCapture } from './screenCapture';
import { correctionText, demoReducer, demoSteps, initialDemoState } from './demoGuide';
import type { DemoActionId } from './demoGuide';
import './screenGuideDemo.css';

export function ScreenGuideDemo({ onSharingChange }: { onSharingChange: (active: boolean) => void }) {
  const capture = useRef(new ScreenCapture());
  const video = useRef<HTMLVideoElement>(null);
  const surface = useRef<HTMLDivElement>(null);
  const generation = useRef(0);
  const [sharing, setSharing] = useState(false);
  const [picking, setPicking] = useState(false);
  const [source, setSource] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [fullscreen, setFullscreen] = useState(false);
  const [state, dispatch] = useReducer(demoReducer, initialDemoState);
  const step = demoSteps[state.step];
  const complete = state.phase === 'complete';
  const active = !state.paused && state.phase === 'ready';

  useEffect(() => { if (!state.paused) setNotice(''); }, [state.paused]);

  // Clicks change the sample before verification. Time alone cannot prove an action.
  useEffect(() => {
    if (state.paused || complete) return;
    if (state.phase === 'checking') {
      const timer = setTimeout(() => dispatch({ type: 'verify' }), 1000);
      return () => clearTimeout(timer);
    }
    if (state.playing) {
      const timer = setTimeout(() => dispatch({ type: 'act', target: step.id }), 2400);
      return () => clearTimeout(timer);
    }
  }, [state.paused, state.phase, state.playing, step.id, complete]);

  const stop = useCallback((message = 'Mirroring stopped. You can resume the practice demo below.') => {
    generation.current++;
    capture.current.stop();
    if (video.current) video.current.srcObject = null;
    setSharing(false); setPicking(false); setSource(''); dispatch({ type: 'pause' });
    onSharingChange(false); setNotice(message);
  }, [onSharingChange]);

  useEffect(() => {
    const activeCapture = capture.current;
    const hidden = () => { if (document.hidden) dispatch({ type: 'pause' }); };
    const pagehide = () => dispatch({ type: 'pause' });
    const changed = () => setFullscreen(document.fullscreenElement === surface.current);
    document.addEventListener('visibilitychange', hidden);
    document.addEventListener('fullscreenchange', changed);
    window.addEventListener('pagehide', pagehide);
    return () => {
      generation.current++; activeCapture.stop(); onSharingChange(false);
      document.removeEventListener('visibilitychange', hidden);
      document.removeEventListener('fullscreenchange', changed);
      window.removeEventListener('pagehide', pagehide);
    };
  }, [onSharingChange]);

  async function share() {
    if (picking) return;
    stop('');
    const current = ++generation.current;
    setPicking(true); setError('');
    try {
      const stream = await capture.current.start(stop);
      if (!stream || generation.current !== current) return;
      if (video.current) { video.current.srcObject = stream; await video.current.play(); }
      if (generation.current !== current || !capture.current.active) return;
      setSource(stream.getVideoTracks()[0].label || 'Selected window or tab');
      setSharing(true); onSharingChange(true);
      setNotice('Mirroring is on. Resume the guide to try hints in the practice overlay.');
    } catch (error) {
      if (generation.current !== current) return;
      capture.current.stop();
      if (video.current) video.current.srcObject = null;
      if (error instanceof DOMException && error.name === 'NotAllowedError') {
        setNotice('No window selected. Resume the practice demo whenever you are ready.');
      } else setError((error as Error).message);
    } finally { if (generation.current === current) setPicking(false); }
  }

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await surface.current?.requestFullscreen();
    } catch { setError('Fullscreen is unavailable in this browser. You can continue in the page.'); }
  }

  function target(id: DemoActionId, label: string, children: ReactNode, placement = 'below') {
    const highlighted = active && step.id === id;
    return <div className={`practice-target ${highlighted ? 'highlighted' : ''} hint-${placement}`}>
      <button className={`practice-control control-${id}`} onClick={() => dispatch({ type: 'act', target: id })}
        disabled={state.paused || state.phase !== 'ready'} aria-label={label}
        aria-describedby={highlighted ? 'practice-hint' : undefined} aria-pressed={id === 'dark' ? state.theme === 'dark' : undefined}>
        {children}
      </button>
      {highlighted && <div className="practice-hint" id="practice-hint" role="note">
        <span className="hint-number">{state.step + 1}</span><span>{step.hint}<small>{state.playing ? 'Demo will click this next' : 'Try this in the practice window'}</small></span>
        <MousePointer2 size={22} className={state.playing ? 'practice-pointer playing' : 'practice-pointer'} aria-hidden="true" />
      </div>}
    </div>;
  }

  const status = state.paused ? 'Guide paused' : complete ? 'Demo complete'
    : state.phase === 'checking' ? 'Checking sample change…' : state.playing ? 'Automatic demo running' : 'Waiting for your click';

  return <div className="screen-demo interactive-demo">
    <div className="live-heading"><div><span className="eyebrow">INTERACTIVE SCREEN GUIDE DEMO</span>
      <h1>A hint. A click.<br />Your next step.</h1>
      <p>Follow the floating hints, or watch the demo do the sample clicks for you.</p>
    </div><span className="demo-script-tag">Simulated guidance · No API key</span></div>

    <div className="demo-explainer"><Compass size={21} /><p>This practice app demonstrates automatic guidance and action detection. Its hints react to sample controls. Mirroring adds your window behind the practice overlay; the demo does not read or control that window.</p></div>
    {notice && <p className="message notice" role="status">{notice}</p>}
    {error && <p className="message error" role="alert">{error}</p>}

    <div className="demo-guide-layout">
      <section className="demo-screen-panel" aria-label="Screen mirror and practice app">
        <div className="demo-panel-heading"><span><MonitorUp size={18} />{sharing ? 'Mirrored window + practice overlay' : 'Interactive practice screen'}</span>
          <span className={sharing ? 'sharing-badge on' : 'sharing-badge'} role="status"><Eye size={14} />{sharing ? 'Mirroring on' : 'Sample preview'}</span></div>
        <div className={`practice-surface ${sharing ? 'with-mirror' : ''}`} ref={surface}>
          <div className="practice-desktop-bar"><span><MonitorUp size={14} />{sharing ? 'LOCAL MIRROR · SIMULATED OVERLAY' : 'DEMO DESKTOP'}</span>
            <button onClick={() => void toggleFullscreen()} aria-label={fullscreen ? 'Exit fullscreen demo' : 'Fullscreen demo'}>{fullscreen ? <X size={16} /> : <Maximize2 size={16} />}</button></div>
          <video className={sharing ? 'practice-mirror visible' : 'practice-mirror'} ref={video} muted autoPlay playsInline aria-label="Local mirrored window" />
          <div className={`practice-window theme-${state.theme}`} aria-label="Interactive sample app">
            <div className="practice-titlebar"><span className="practice-window-dots" aria-hidden="true"><i /><i /><i /></span><span>{sharing ? 'Practice overlay' : 'Sample workspace'}</span><small>SIMULATION</small></div>
            <div className="practice-app-toolbar"><span><Compass size={20} /> My workspace</span>{target('settings', 'Settings', <><Settings size={16} />Settings</>, 'below-left')}</div>
            {state.page === 'workspace' ? <div className="practice-home">
              <span className="practice-kicker">YOUR SAMPLE TASK</span><h3>Make this workspace<br />easier on your eyes.</h3><p>Switch the practice app to a dark theme and save it.</p>
              <div className="practice-document"><span /><span /><span /></div>
              <button className="practice-notes" onClick={() => dispatch({ type: 'act', target: 'other' })} disabled={!active}>Open sample notes</button>
            </div> : <div className="practice-settings">
              <nav aria-label="Sample settings"><span>SETTINGS</span><button className={state.tab === 'general' ? 'selected' : ''} disabled={!active} onClick={() => dispatch({ type: 'act', target: 'other' })}>General</button>
                {target('appearance', 'Appearance', <><Sun size={15} />Appearance</>, 'below')}
              </nav>
              <div className="practice-settings-content">
                {state.tab === 'general' ? <><h3>General</h3><p>Manage your sample workspace.</p><div className="practice-setting-row"><span>Workspace name</span><strong>My workspace</strong></div><div className="practice-setting-row"><span>Language</span><strong>English</strong></div></>
                  : <><h3>Appearance</h3><p>Choose a theme for your workspace.</p><div className="practice-theme-options"><button className="practice-light" aria-label="Light theme" aria-pressed={state.theme === 'light'} disabled={!active} onClick={() => dispatch({ type: 'act', target: 'other' })}><span className="theme-swatch light"><i /><i /></span><Sun size={15} />Light</button>
                    {target('dark', 'Dark theme', <><span className="theme-swatch dark"><i /><i /></span><Moon size={15} />Dark{state.theme === 'dark' && <Check size={15} />}</>, 'below-left')}</div>
                    <div className="practice-save-row"><p>{state.saved ? 'Appearance saved · Dark' : state.theme === 'dark' ? 'You have an unsaved change.' : 'Current theme: Light'}</p>{target('save', 'Save changes', <><Check size={15} />Save changes</>, 'above-left')}</div></>}
              </div>
            </div>}
          </div>
          <div className={`practice-overlay-status ${state.phase === 'checking' ? 'checking' : ''}`} role="status">
            {state.phase === 'checking' && !state.paused ? <LoaderCircle size={16} className="spin" /> : complete ? <CheckCircle2 size={16} /> : <Compass size={16} />}
            <span>{status}<small>{complete ? 'Sample outcome verified' : `Step ${state.step + 1} of ${demoSteps.length} · ${state.phase === 'checking' ? step.evidence : step.title}`}</small></span>
            {!complete && <button onClick={() => dispatch({ type: state.paused ? 'resume' : 'pause' })} aria-label={state.paused ? 'Resume overlay guide' : 'Pause overlay guide'}>{state.paused ? <Play size={16} /> : <Pause size={16} />}</button>}
          </div>
        </div>
        {sharing && <p className="shared-source">Sharing: <strong>{source}</strong></p>}
        <div className="demo-mirror-controls"><button className="text-button" disabled={picking} onClick={() => void share()}><MonitorUp size={16} />{picking ? 'Choose in your browser…' : sharing ? 'Change window' : 'Mirror my window'}</button>
          {(sharing || picking) && <button className="text-button danger" onClick={() => stop()}><Square size={13} />Stop mirroring</button>}</div>
        <p className="demo-local-note">{sharing ? 'Your mirror stays local. Hints point only to the practice overlay. Stop mirroring returns to the sample desktop.' : 'Click the highlighted sample controls. Guider checks the change and updates the hint automatically.'}</p>
      </section>

      <section className="demo-instruction-panel" aria-label="Demo guidance">
        <div className="guide-heading"><span className="brand-mark"><Compass size={23} /></span><div><strong>Your screen guide</strong><small>Sample task: switch to a dark theme</small></div></div>
        <div className="demo-current-step" aria-live="polite" aria-atomic="true"><span className="eyebrow">{complete ? 'DEMO COMPLETE' : `STEP ${state.step + 1} OF ${demoSteps.length}`}</span>
          <h2>{complete ? 'The sample task is complete.' : state.paused ? 'Continue when you’re ready.' : step.title}</h2>
          <p>{complete ? 'The practice app is now using its saved dark theme. Each hint advanced after its expected sample change appeared.' : state.paused ? 'Hints and automatic progression are paused. Resume to continue from this step.' : step.instruction}</p></div>
        {!complete && <div className="demo-evidence"><span>{state.phase === 'checking' ? 'CHECKING THE SAMPLE' : 'WHAT THE DEMO SEES'}</span><p>{state.phase === 'checking' ? step.evidence : step.observation}</p></div>}
        {correctionText(state) && <p className="demo-correction" role="status">{correctionText(state)}</p>}
        <ol className="interactive-progress" aria-label="Demo progress">{demoSteps.map((item, index) => <li key={item.id} aria-current={!complete && state.step === index ? 'step' : undefined} className={complete || index < state.step ? 'done' : state.step === index ? 'current' : ''}><span>{complete || index < state.step ? <Check size={14} /> : index + 1}</span><div>{item.target}<small>{complete || index < state.step ? 'Sample change verified' : state.step === index ? state.phase === 'checking' ? 'Checking…' : 'Current step' : 'Up next'}</small></div></li>)}</ol>
        <div className="interactive-demo-actions">
          {complete ? <button className="primary" onClick={() => dispatch({ type: 'restart' })}><RotateCcw size={16} />Replay demo</button>
            : <button className="primary" onClick={() => dispatch({ type: state.paused ? 'resume' : 'pause' })}>{state.paused ? <Play size={16} /> : <Pause size={16} />}{state.paused ? 'Resume guide' : 'Pause guide'}</button>}
          <button className="demo-watch-button" onClick={() => dispatch({ type: state.playing ? 'practice' : 'watch' })}>{state.playing ? <MousePointer2 size={16} /> : <Play size={16} />}{state.playing ? 'Try it myself' : 'Watch automatically'}</button>
          {!complete && <button className="text-button demo-restart" onClick={() => dispatch({ type: 'restart' })}><RotateCcw size={14} />Start over</button>}
        </div>
        <p className="demo-local-note">{state.playing ? 'Playback performs clicks only in this sample app.' : 'You click. The demo checks and advances. No Next button needed.'}</p>
      </section>
    </div>
    <p className="live-footnote">This demonstrates automatic guidance, target hints, action checks and a floating overlay inside the browser. It does not analyze or control other apps. AI screen guide remains a separate, manually reviewed screen-check flow.</p>
  </div>;
}
