import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowLeft, ArrowRight, Check, CheckCircle2, ChevronRight, CircleHelp,
  ClipboardPaste, Code2, Compass, EyeOff, FileImage, GitBranch, History, ImagePlus, LoaderCircle,
  ListChecks, LogOut, Pause, Play, Plus, ScanLine, ShieldCheck, Square, Terminal, Trash2, X, Zap } from 'lucide-react';
import { api, isDemo, supabase } from './api';
import { ImageEditor } from './ImageEditor';
import { LiveGuide } from './LiveGuide';
import { prepareImage } from './image';
import { GuideIsland } from './overlay/GuideIsland';
import { closeFloatingWindow, openFloatingWindow, pipSupported, type FloatingWindow } from './overlay/pip';
import type { IslandState } from './overlay/states';
import { islandStateFor, stuckMessage, useLiveGuide } from './guide/live';
import { Watcher } from './guide/watching';
import { createFrameSource, type MaskArea } from './overlay/frameSource';
import { WatchSetup } from './overlay/WatchSetup';
import { ScreenCapture } from './screenCapture';
import type {
  Analysis, Category, ImportedConversation, ImportSource, Plan, Screenshot, Session, Task,
} from './types';

const categories: { id: Category; label: string; icon: typeof Code2 }[] = [
  { id: 'setup', label: 'Set something up', icon: Zap }, { id: 'run', label: 'Run a project', icon: Play },
  { id: 'debug', label: 'Fix a problem', icon: Code2 }, { id: 'understand', label: 'Understand something', icon: CircleHelp },
  { id: 'test', label: 'Test my work', icon: CheckCircle2 }, { id: 'git_github', label: 'Git & GitHub', icon: GitBranch },
];
type Page = 'home' | 'task' | 'plan' | 'history' | 'privacy' | 'live';
const SOURCE_LABELS: Record<ImportSource, string> = {
  chatgpt: 'ChatGPT', claude: 'Claude', gemini: 'Gemini', other: 'another assistant',
};
type HistoryItem = { session: Session; task_title: string };

export default function App() {
  const [page, setPage] = useState<Page>(() => location.hash === '#live' ? 'live' : 'home');
  const [sharing, setSharing] = useState(false);
  const [goal, setGoal] = useState('');
  const [category, setCategory] = useState<Category>('debug');
  const [application, setApplication] = useState('unknown');
  const [task, setTask] = useState<Task | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [draft, setDraft] = useState<Blob | null>(null);
  const [screenshot, setScreenshot] = useState<Screenshot | null>(null);
  const [imageUrl, setImageUrl] = useState('');
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [openStep, setOpenStep] = useState('');
  const [guiding, setGuiding] = useState(false);
  const [watchOpen, setWatchOpen] = useState(false);
  // Null means watching is off. A number is the server's own count of frames.
  const [framesObserved, setFramesObserved] = useState<number | null>(null);
  const [watchNotice, setWatchNotice] = useState('');
  const [pasteOpen, setPasteOpen] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [importSource, setImportSource] = useState<ImportSource>('chatgpt');
  // Set only for a plan that came from a pasted conversation, so the screen can
  // say where it came from and what the guard did to it.
  const [provenance, setProvenance] = useState<ImportedConversation | null>(null);
  const [floating, setFloating] = useState<FloatingWindow | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [signedIn, setSignedIn] = useState(isDemo);
  const [authOpen, setAuthOpen] = useState(false);
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [codeSent, setCodeSent] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const watchVideo = useRef<HTMLVideoElement>(null);
  const capture = useRef(new ScreenCapture());
  const watcher = useRef<Watcher | null>(null);
  const goalInput = useRef<HTMLTextAreaElement>(null);
  const generation = useRef(0);
  const actionSequence = useRef(0);

  useEffect(() => {
    if (!supabase) return;
    const { data } = supabase.auth.onAuthStateChange((_event, current) => setSignedIn(Boolean(current)));
    return () => data.subscription.unsubscribe();
  }, []);
  useEffect(() => () => { if (imageUrl) URL.revokeObjectURL(imageUrl); }, [imageUrl]);
  useEffect(() => {
    if (!signedIn) return;
    void api.history().then(data => setHistory(data.items)).catch(() => {});
  }, [signedIn, page, task]);
  useEffect(() => () => { generation.current++; }, []);
  useEffect(() => () => { closeFloatingWindow(floating); }, [floating]);

  function navigate(next: Page) {
    if (busy) return;
    generation.current++; setPage(next); setError(''); setNotice('');
    window.history.replaceState(null, '', next === 'live' ? '#live' : location.pathname);
  }
  function reset() {
    generation.current++; setTask(null); setSession(null); setScreenshot(null); setAnalysis(null);
    setDraft(null); setImageUrl(''); setGoal(''); setPage('home'); setError(''); setNotice('');
    setPlan(null); setOpenStep('');
  }
  async function work(label: string, action: () => Promise<void>) {
    const actionId = ++actionSequence.current;
    setError(''); setNotice(''); setBusy(label);
    try { await action(); } catch (error) { setError(error instanceof Error ? error.message : 'Something went wrong. Please try again.'); }
    finally { if (actionSequence.current === actionId) setBusy(''); }
  }
  async function selectFile(file: Blob) {
    await work('Preparing image…', async () => { setDraft(await prepareImage(file)); setPage(task ? 'task' : 'home'); });
  }
  async function createTask() {
    if (!goal.trim()) { setError('Tell Guider what you would like to do.'); goalInput.current?.focus(); return; }
    if (!signedIn) { setAuthOpen(true); return; }
    await work('Creating your task…', async () => {
      const created = await api.create({ goal: goal.trim(), category, application_key: application });
      setTask(created.task); setSession(created.session); setPage('task'); setAnalysis(null); setScreenshot(null);
    });
  }
  /**
   * Continue from a conversation the user already had. The text is data: it can
   * only ever produce a draft plan, which is reviewed like any other.
   */
  async function importConversation() {
    if (transcript.trim().length < 20) {
      setError('Paste the part of the conversation with the steps in it.');
      return;
    }
    if (!signedIn) { setAuthOpen(true); return; }
    const token = ++generation.current;
    await work('Reading the conversation…', async () => {
      const accepted = await api.importConversation(transcript.trim(), importSource);
      if (generation.current !== token) return;
      setTask(accepted.task); setSession(accepted.session);
      setPasteOpen(false); setTranscript('');
      for (let attempt = 0; attempt < 20; attempt++) {
        if (!isDemo) await new Promise(resolve => setTimeout(resolve, 2000));
        if (generation.current !== token) return;
        const operation = await api.operation(accepted.operation_id);
        if (generation.current !== token) return;
        if (operation.status === 'succeeded' && operation.result_id) {
          setPlan(await api.plan(operation.result_id));
          setTask(await api.task(accepted.task.id));
          setSession(await api.session(accepted.session.id));
          setProvenance(accepted.imported);
          setOpenStep(''); setPage('plan');
          setNotice(accepted.imported.redactions > 0
            ? `${accepted.imported.redactions} thing that looked like a secret was removed before anything was stored.`
            : 'Read from your conversation. Nothing has started — review the steps first.');
          return;
        }
        if (['failed', 'canceled'].includes(operation.status)) {
          throw new Error(operation.error?.message
            || 'Guider could not find a goal and steps in that text.');
        }
      }
      throw new Error('Reading the conversation is taking too long. Try again in a moment.');
    });
  }

  async function example() {
    await work('Preparing the example…', async () => {
      const blob = await fetch('/fixtures/python-error.png').then(response => {
        if (!response.ok) throw new Error('The example image could not be loaded.');
        return response.blob();
      });
      setGoal("Why won't my Python file run?"); setCategory('debug'); setApplication('powershell');
      setDraft(await prepareImage(blob)); setNotice('The example contains synthetic data. Create your task to continue.');
      setPage('home');
    });
  }
  async function upload(blob: Blob) {
    if (!task || !session) return;
    await work('Uploading image…', async () => {
      const current = await api.session(session.id);
      const uploaded = await api.upload(task, current, blob, screenshot || undefined);
      setSession(uploaded.session); setScreenshot(uploaded.screenshot); setAnalysis(null); setDraft(null);
      setImageUrl(URL.createObjectURL(await api.content(uploaded.screenshot.id)));
      setNotice(isDemo ? 'Image is ready in this browser tab.' : 'Your image was saved privately for up to 24 hours.');
    });
  }
  async function analyze() {
    if (!task || !session || !screenshot) return;
    const token = ++generation.current;
    await work('Preparing an explanation…', async () => {
      const current = await api.session(session.id);
      const pending = await api.analyze(task, current, screenshot);
      if (generation.current !== token) return;
      setSession(pending.session);
      for (let attempt = 0; attempt < 20; attempt++) {
        if (!isDemo) await new Promise(resolve => setTimeout(resolve, 2000));
        if (generation.current !== token) return;
        const operation = await api.operation(pending.operation_id);
        if (generation.current !== token) return;
        if (operation.status === 'succeeded') {
          setAnalysis(operation.result); setSession(await api.session(session.id)); return;
        }
        if (['failed', 'canceled'].includes(operation.status)) throw new Error(operation.error?.message || 'Analysis was canceled.');
      }
      throw new Error('The explanation is taking too long. Pause this task and try again later.');
    });
  }
  async function buildPlan() {
    if (!task || !session) return;
    const token = ++generation.current;
    await work('Working out the steps…', async () => {
      const current = await api.session(session.id);
      setProvenance(null);
      const pending = await api.requestPlan(task, current);
      if (generation.current !== token) return;
      setSession(pending.session);
      for (let attempt = 0; attempt < 20; attempt++) {
        if (!isDemo) await new Promise(resolve => setTimeout(resolve, 2000));
        if (generation.current !== token) return;
        const operation = await api.operation(pending.operation_id);
        if (generation.current !== token) return;
        if (operation.status === 'succeeded' && operation.result_id) {
          setPlan(await api.plan(operation.result_id));
          setSession(await api.session(session.id));
          setOpenStep(''); setPage('plan');
          return;
        }
        if (['failed', 'canceled'].includes(operation.status)) {
          throw new Error(operation.error?.message || 'The plan could not be prepared.');
        }
      }
      throw new Error('Preparing the plan is taking too long. Try again in a moment.');
    });
  }
  // The island runs the session on the server: the step it shows is the one the
  // Guide Engine published an instruction for, and it advances only when a route
  // accepts a claim and a self-report.
  const live = useLiveGuide(api, session);
  const guide = useRef(live);
  useEffect(() => { guide.current = live; });
  const guideSteps = (plan?.steps ?? []).filter(step => step.policy_disposition !== 'block');
  const activeStep = live.state.step;
  const islandState: IslandState = islandStateFor(live.state);

  /** Local teardown of watching: tracks stopped, loop halted, counter cleared. */
  function releaseWatching() {
    watcher.current?.halt();
    watcher.current = null;
    capture.current.stop();
    if (watchVideo.current) watchVideo.current.srcObject = null;
    setFramesObserved(null);
  }
  async function stopWatching(reason: string) {
    const running = watcher.current;
    releaseWatching();
    setWatchNotice(reason);
    try { await running?.stop(reason, false); } catch { /* off locally either way */ }
  }
  async function beginWatching(stream: MediaStream, masks: MaskArea[], consentVersion: string) {
    const video = watchVideo.current;
    if (!video) return;
    video.srcObject = stream;
    await video.play().catch(() => {});
    const source = createFrameSource(video, () => masks);
    const running = new Watcher(api, source, {
      session: () => guide.current.session,
      awaitingAction: () => guide.current.awaitingAction(),
      onCounters: frames => setFramesObserved(frames),
      // A middle-band verdict is worth one question and nothing more.
      onTick: tick => { if (tick.decision === 'ask') guide.current.observerAsked(); },
      onNotice: setWatchNotice,
      onStopped: reason => { releaseWatching(); setWatchNotice(reason); },
    });
    watcher.current = running;
    await running.start(consentVersion);
    setWatchOpen(false);
    setWatchNotice('');
  }

  /**
   * Ask for a replacement plan and show it for review. The guide stops here on
   * purpose: what comes back is a draft, and nothing continues until the user
   * has confirmed it.
   */
  async function askForNewPlan() {
    const operationId = await live.replan();
    if (!operationId) return;
    void stopWatching('Watching stopped while the plan is rewritten.');
    setGuiding(false);
    live.close();
    const token = ++generation.current;
    await work('Working out what is left…', async () => {
      for (let attempt = 0; attempt < 20; attempt++) {
        if (!isDemo) await new Promise(resolve => setTimeout(resolve, 2000));
        if (generation.current !== token) return;
        const operation = await api.operation(operationId);
        if (generation.current !== token) return;
        if (operation.status === 'succeeded' && operation.result_id) {
          setPlan(await api.plan(operation.result_id));
          setSession(await api.session(live.session!.id));
          setOpenStep(''); setPage('plan');
          setNotice('Here is a new plan for what is left. What you have already done is kept.');
          return;
        }
        if (['failed', 'canceled'].includes(operation.status)) {
          throw new Error(operation.error?.message || 'A new plan could not be prepared.');
        }
      }
      throw new Error('Preparing the plan is taking too long. Try again in a moment.');
    });
  }

  function stopGuiding() {
    void stopWatching('Watching stopped with the guide.');
    live.close();
    setGuiding(false);
    setFloating((current: FloatingWindow | null) => { closeFloatingWindow(current); return null; });
  }
  async function startGuiding(floatingRequested = false) {
    setGuiding(true);
    // The floating window is a deliberate choice, never the default: on the page
    // is a supported shape, and it is the only one Safari and Firefox have.
    if (floatingRequested) {
      // Must stay inside the click: the window will not open after an await.
      setFloating(await openFloatingWindow(() => {
        setFloating(null); setGuiding(false); live.close();
      }));
    }
    await live.start();
  }
  async function confirmPlan() {
    if (!plan || !session) return;
    await work('Confirming the plan…', async () => {
      const current = await api.session(session.id);
      const confirmed = await api.confirmPlan(plan, current);
      setPlan(confirmed.plan); setSession(confirmed.session);
      setNotice('Plan confirmed. Start the steps whenever you are ready.');
    });
  }
  async function deleteImage() {
    if (!screenshot) return;
    generation.current++;
    await work('Deleting image…', async () => {
      const receipt = await api.deleteImage(screenshot.id);
      setScreenshot(null); setAnalysis(null); setImageUrl(''); setDraft(null);
      if (session) setSession(await api.session(session.id));
      setNotice(receipt.status === 'purged' ? 'Image and its analysis have been deleted.' : 'Deletion requested. The image is no longer accessible.');
    });
  }
  async function restrict(stop: boolean) {
    if (!session) return;
    actionSequence.current++;
    generation.current++;
    // Priority controls remain available while an analysis is pending.
    try {
      const result = await (stop ? api.stop(session.id) : api.pause(session.id));
      setSession(result); setBusy(''); setAnalysis(null);
      setNotice(stop ? 'Task stopped. No outcome has been verified.' : 'Paused. You can still share a screenshot for an explanation.');
    } catch (error) { setError((error as Error).message); }
  }
  async function openTask(item: HistoryItem) {
    await work('Opening task…', async () => {
      const [saved, current] = await Promise.all([api.task(item.session.task_id), api.session(item.session.id)]);
      setTask(saved); setSession(current); setPage('task'); setDraft(null); setScreenshot(null); setAnalysis(null); setImageUrl('');
    });
  }
  const terminal = session && ['completed', 'failed', 'expired'].includes(session.state);

  return <div className="app-shell">
    <aside className="sidebar">
      <button className="brand" onClick={() => navigate('home')} disabled={!!busy} aria-label="Guider home"><span className="brand-mark"><Compass size={24} strokeWidth={1.8} /></span>guider<span className="brand-dot">.</span></button>
      <span className="workspace-label">YOUR EVERYDAY GUIDE</span>
      <nav aria-label="Main navigation">
        <button className={page === 'live' ? 'nav-item selected' : 'nav-item'} disabled={!!busy} onClick={() => navigate('live')}><ScanLine size={19} /> Live screen guide</button>
        <button className={page === 'home' || page === 'task' ? 'nav-item selected' : 'nav-item'} disabled={!!busy} onClick={() => navigate(task ? 'task' : 'home')}><Compass size={19} /> My workspace <span className="nav-dot" /></button>
        <button className={page === 'history' ? 'nav-item selected' : 'nav-item'} disabled={!!busy} onClick={() => navigate('history')}><History size={19} /> Task history</button>
        <button className={page === 'privacy' ? 'nav-item selected' : 'nav-item'} disabled={!!busy} onClick={() => navigate('privacy')}><ShieldCheck size={19} /> Privacy & control</button>
      </nav>
      <div className="sidebar-note"><div className="little-orbit"><Compass size={28} /></div><h3>You’re in the driver’s seat.</h3><p>Guider explains. You make the moves.</p><span><EyeOff size={14} /> {sharing ? 'Window sharing on' : 'Screen observation off'}</span></div>
      <div className="profile"><div className="avatar">{isDemo ? 'D' : 'Y'}</div><div><strong>{isDemo ? 'Demo workspace' : signedIn ? 'Your workspace' : 'Welcome to Guider'}</strong><small>{isDemo ? 'Just exploring' : signedIn ? 'Signed in privately' : 'Sign in to save tasks'}</small></div>
        {!isDemo && <button className="icon-button" aria-label={signedIn ? 'Sign out' : 'Sign in'} onClick={() => {
          if (signedIn) void work('Signing out…', async () => { if (session && !terminal) await api.stop(session.id); await supabase!.auth.signOut(); reset(); setHistory([]); });
          else setAuthOpen(true);
        }}><LogOut size={17} /></button>}
      </div>
    </aside>

    <div className="main-shell">
      <header className="topbar"><span className="breadcrumb">Workspace <ChevronRight size={14} /><strong>{page === 'live' ? 'Live screen guide' : page === 'home' ? 'A fresh start' : page === 'task' ? 'Screenshot help' : page === 'plan' ? 'Your plan' : page === 'history' ? 'Task history' : 'Privacy & control'}</strong></span>
        <span className="mode-label"><span />{page === 'live' ? (sharing ? 'Window sharing on' : 'Screen guide') : isDemo ? 'Local demo' : 'Screenshot mode'}</span></header>
      <main>
        {isDemo && page !== 'live' && <div className="demo-banner"><span><span className="tiny-tag">PREVIEW</span> A place to try Guider. Everything stays in this tab and clears on refresh.</span><button onClick={() => navigate('privacy')} disabled={!!busy}>How it works <ArrowRight size={14} /></button></div>}
        {error && <div className="message error" role="alert">{error}<button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><X size={16} /></button></div>}
        {notice && <div className="message notice" role="status"><Check size={17} />{notice}</div>}
        <div className="sr-only" role="status">{busy}</div>
        {page === 'live' && <LiveGuide onSharingChange={setSharing} />}

        {page === 'home' && <div className="home-content">
          <section className="welcome"><div className="eyebrow"><span className="small-line" /> A LITTLE DIRECTION GOES A LONG WAY</div><h1>What would you<br />like to <span>figure out?</span></h1><p>A confusing error. A new tool. That one thing that won’t work.<br className="desktop-break" /> Let’s take it one step at a time.</p></section>
          <section className="screen-callout"><span className="brand-mark"><ScanLine size={23} /></span><div><h2>See how screen guidance works.</h2><p>Try a guided demo and mirror your window. No API key needed.</p></div><button className="primary" onClick={() => navigate('live')}>Guide me on screen <ArrowRight size={17} /></button></section>
          <section className="composer" aria-label="Start a task">
            <label className="sr-only" htmlFor="goal">What would you like to do?</label><textarea ref={goalInput} id="goal" maxLength={4000} value={goal} onChange={event => setGoal(event.target.value)} placeholder="Tell me what you’re trying to do…" />
            <div className="composer-bottom"><button className={draft ? 'attach-button attached' : 'attach-button'} onClick={() => input.current?.click()} disabled={!!busy}><ImagePlus size={18} />{draft ? 'Screenshot attached' : 'Add a screenshot'}{draft && <Check size={14} />}</button><button className="primary" disabled={!!busy} onClick={() => void createTask()}>{busy ? <LoaderCircle className="spin" size={17} /> : <>Let’s figure it out <ArrowRight size={18} /></>}</button></div>
          </section>
          <div className="composer-caption"><ShieldCheck size={14} /> You choose what to share. Guider never controls your computer.</div>
          <section className="import-card" aria-label="Continue from a conversation">
            {!pasteOpen
              ? <div className="import-intro"><span className="brand-mark"><ClipboardPaste size={22} /></span>
                  <div><h2>Already asked another assistant?</h2><p>Paste the conversation and Guider will turn its steps into a plan you can follow here.</p></div>
                  <button className="text-button" disabled={!!busy} onClick={() => { setPasteOpen(true); setError(''); }}>Paste a conversation <ArrowRight size={16} /></button>
                </div>
              : <>
                  <div className="section-heading compact"><h2>Paste the conversation.</h2><span>Up to 32 KB of text.</span></div>
                  <label className="app-select">It came from <select value={importSource} onChange={event => setImportSource(event.target.value as ImportSource)} disabled={!!busy}>
                    <option value="chatgpt">ChatGPT</option><option value="claude">Claude</option><option value="gemini">Gemini</option><option value="other">Somewhere else</option>
                  </select></label>
                  <label className="sr-only" htmlFor="transcript">Conversation text</label>
                  <textarea id="transcript" value={transcript} maxLength={32768} placeholder="Paste the part with the steps in it…" onChange={event => setTranscript(event.target.value)} disabled={!!busy} />
                  <p className="privacy-note"><ShieldCheck size={14} /> Pasted text is treated as information, never as instructions. Anything that looks like a key or password is removed before it is stored, and nothing starts until you confirm the plan.</p>
                  <div className="plan-buttons"><button className="text-button" disabled={!!busy} onClick={() => { setPasteOpen(false); setTranscript(''); }}>Cancel</button>
                    <button className="primary" disabled={!!busy} onClick={() => void importConversation()}>{busy ? <LoaderCircle className="spin" size={17} /> : <>Read the steps <ArrowRight size={17} /></>}</button></div>
                </>}
          </section>
          <section className="category-section"><div className="section-heading compact"><h2>What kind of help?</h2><span>A starting point is enough.</span></div><div className="categories">{categories.map(item => <button key={item.id} className={category === item.id ? 'category active' : 'category'} aria-pressed={category === item.id} onClick={() => setCategory(item.id)}><item.icon size={18} />{item.label}</button>)}</div>
            <label className="app-select">Working in <select value={application} onChange={event => setApplication(event.target.value)}><option value="unknown">Not sure yet</option><option value="vscode">VS Code</option><option value="powershell">PowerShell / Terminal</option><option value="chrome">Chrome</option><option value="edge">Microsoft Edge</option><option value="github">GitHub</option><option value="docker_desktop">Docker Desktop</option></select></label></section>
          <section className="example-card"><div className="example-copy"><span className="eyebrow">NOT SURE WHERE TO START?</span><h2>Try a little “aha” moment.</h2><p>See how a Python error becomes something you understand.</p><button className="text-button" onClick={() => void example()} disabled={!!busy}>Explore an example <ArrowRight size={17} /></button></div><div className="mini-terminal" aria-hidden="true"><div className="terminal-top"><i /><i /><i /><span>python app.py</span></div><code>&gt; import requests<br /><span>ModuleNotFoundError</span></code><div className="terminal-hint"><span><Compass size={16} /></span> Let’s make sense of this.</div></div></section>
          <section className="how-it-works"><span className="eyebrow">FROM STUCK TO UNDERSTOOD</span><div>{[{ icon: FileImage, title: 'Share the context', text: 'A goal and a screenshot are a great start.' }, { icon: ScanLine, title: 'Find some clarity', text: 'Understand what’s happening on screen.' }, { icon: ArrowRight, title: 'Take the next step', text: 'You stay in control of every action.' }].map((step, index) => <article key={step.title}><span className="step-number">0{index + 1}</span><step.icon size={19} /><h3>{step.title}</h3><p>{step.text}</p></article>)}</div></section>
          {history.length > 0 && <button className="continue-link" onClick={() => void openTask(history[0])} disabled={!!busy}><History size={17} /><span>Continue: {history[0].task_title}</span><ArrowRight size={17} /></button>}
        </div>}

        {page === 'task' && task && session && <div className="task-content">
          <button className="text-button back-link" disabled={!!busy} onClick={reset}><ArrowLeft size={16} /> Start a new task</button>
          <div className="task-heading"><div><span className="eyebrow">{task.category.replace('_', ' & ')} · {task.application_key.replace('_', ' ')}</span><h1>{task.title}</h1></div><span className="status-pill">{terminal ? 'Stopped' : session.state === 'paused' ? 'Paused' : 'Screenshot help'}</span></div>
          <div className="session-controls"><span><EyeOff size={15} /> Observation off</span><div><button onClick={() => void restrict(false)} disabled={!!terminal || session.state === 'paused'}><Pause size={15} /> Pause</button><button onClick={() => void restrict(true)} disabled={!!terminal}><Square size={13} /> Stop</button></div></div>
          {!terminal && <section className="plan-callout"><span className="brand-mark"><ListChecks size={22} /></span><div><h2>{plan ? `A plan is ready · version ${plan.version}` : 'Want the whole route first?'}</h2><p>{plan ? (plan.status === 'confirmed' ? 'You confirmed this plan. Review it any time.' : 'Review the suggested steps and confirm when you’re happy.') : 'Guider can suggest the steps for this goal. You review them before anything begins.'}</p></div><button className="primary" disabled={!!busy} onClick={() => plan ? navigate('plan') : void buildPlan()}>{busy === 'Working out the steps…' ? <><LoaderCircle size={16} className="spin" /> {busy}</> : plan ? <>Review the plan <ArrowRight size={17} /></> : <>Suggest the steps <ArrowRight size={17} /></>}</button></section>}
          {terminal ? <section className="empty-panel"><CheckCircle2 size={32} /><h2>A good place to pause.</h2><p>Your task was stopped. No outcome has been verified.</p><button className="primary" onClick={reset}>Start another task <Plus size={17} /></button>{screenshot && <button className="text-button danger" disabled={!!busy} onClick={() => void deleteImage()}><Trash2 size={16} /> Delete screenshot and analysis</button>}</section> : draft ? <ImageEditor key={String(draft.size) + draft.type} initial={draft} busy={!!busy} onUpload={blob => void upload(blob)} onCancel={() => setDraft(null)} /> : !screenshot ? <section className="upload-panel" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); if (!busy && event.dataTransfer.files[0]) void selectFile(event.dataTransfer.files[0]); }}><div className="upload-icon"><ImagePlus size={30} /></div><span className="eyebrow">LET’S SEE THE CONTEXT</span><h2>A screenshot is a good start.</h2><p>Share the error or the part that’s confusing.<br />You’ll get to crop and hide private details first.</p><button className="primary" onClick={() => input.current?.click()} disabled={!!busy}>Choose a screenshot <ArrowDown size={16} /></button><small>or drop it here · PNG, JPEG, WebP · Up to 10 MiB</small></section> : <div className="analysis-layout"><section className="evidence-card"><div className="section-heading"><h2>Your screenshot</h2><button className="icon-button danger" aria-label="Delete screenshot and analysis" onClick={() => void deleteImage()} disabled={!!busy}><Trash2 size={17} /></button></div><div className="image-stage"><div className="result-image"><img src={imageUrl} alt="Your uploaded screenshot" />{analysis?.observations.map((item, index) => item.bbox && <div key={index} title={item.label} className="evidence-marker" style={{ left: `${item.bbox.x * 100}%`, top: `${item.bbox.y * 100}%`, width: `${item.bbox.width * 100}%`, height: `${item.bbox.height * 100}%` }}><span>{index + 1}</span></div>)}</div></div><p className="privacy-note"><ShieldCheck size={14} /> {isDemo ? 'In this tab only · Cleared on refresh' : 'Private · Expires within 24 hours'}</p><button className="text-button" disabled={!!busy} onClick={() => input.current?.click()}><ImagePlus size={16} /> Replace screenshot</button></section><section className="explanation-card"><div className="guide-heading"><span className="brand-mark"><Compass size={22} /></span><div><strong>A little clarity</strong><small>Development example</small></div></div>{analysis ? <><h2>Here’s what we can tell.</h2><p>{analysis.explanation}</p>{analysis.observations.map((item, index) => <div className="observation" key={index}><span>{index + 1}</span>{item.label}</div>)}{analysis.context_request && <div className="context-question"><CircleHelp size={20} /><p>{analysis.context_request}</p></div>}<span className="privacy-note">Explanation only. No task outcome has been verified.</span></> : <><h2>Ready when you are.</h2><p>The development adapter recognizes the synthetic Python example. Other images will receive a request for context.</p><button className="primary" disabled={!!busy} onClick={() => void analyze()}>{busy ? <><LoaderCircle size={16} className="spin" /> {busy}</> : <>Explain this screenshot <ArrowRight size={17} /></>}</button></>}</section></div>}
        </div>}

        {page === 'plan' && task && session && plan && <div className="plan-content">
          <button className="text-button back-link" disabled={!!busy} onClick={() => navigate('task')}><ArrowLeft size={16} /> Back to the task</button>
          <div className="task-heading"><div><span className="eyebrow">STEP-BY-STEP · VERSION {plan.version}</span><h1>{task.title}</h1></div><span className="status-pill">{plan.status === 'confirmed' ? 'Confirmed' : 'Awaiting your review'}</span></div>
          {provenance && <section className="provenance" role="note"><ClipboardPaste size={16} />
            <div><strong>From a conversation you pasted.</strong>
              <small>Read word for word from {SOURCE_LABELS[provenance.source]}, not written by Guider, and not checked against your screen.{provenance.steps_blocked > 0 && ` ${provenance.steps_blocked} step needs review before Guider will walk you through it.`}</small></div>
          </section>}
          <p className="muted plan-intro">Guider suggests {plan.steps.length} steps. Read them over — nothing starts until you say so, and you perform every action yourself.</p>
          {plan.assumptions.length > 0 && <section className="assumptions" aria-label="Assumptions"><span className="eyebrow">WHAT THIS ASSUMES</span><ul>{plan.assumptions.map((item, index) => <li key={index}><CircleHelp size={15} />{item}</li>)}</ul></section>}
          <ol className="plan-steps">{plan.steps.map(step => <li key={step.id} className={step.policy_disposition === 'block' ? 'plan-step blocked' : 'plan-step'}>
            <span className="plan-ordinal">{step.ordinal}</span>
            <div className="plan-body">
              <h3>{step.title}{step.policy_disposition === 'block' && <span className="blocked-tag">Needs separate review</span>}</h3>
              <p className="plan-action">{step.action}</p>
              <p className="plan-expected"><Check size={14} /> {step.expected_result}</p>
              {step.explanation && <><button className="text-button explain-toggle" aria-expanded={openStep === step.id} onClick={() => setOpenStep(openStep === step.id ? '' : step.id)}><CircleHelp size={15} /> {openStep === step.id ? 'Hide why' : 'Why this step?'}</button>
                {openStep === step.id && <div className="plan-why"><p>{step.explanation}</p>{step.fallback && <p><strong>If that doesn’t work:</strong> {step.fallback}</p>}</div>}</>}
            </div>
          </li>)}</ol>
          <section className="plan-actions">
            {plan.status === 'confirmed'
              ? <><CheckCircle2 size={22} /><div><strong>This plan is confirmed.</strong><small>Version {plan.version} is the one Guider will follow.</small></div><div className="plan-buttons">{pipSupported() && <button className="text-button" disabled={!!busy || guiding} onClick={() => void startGuiding(true)}>Open in a floating window</button>}<button className="primary" disabled={!!busy || guiding} onClick={() => void startGuiding()}>{guiding ? 'Guide running' : 'Start the steps'} <ArrowRight size={16} /></button></div></>
              : <><div><strong>Happy with these steps?</strong><small>Confirming records the version. You can ask for a different plan instead.</small></div><div className="plan-buttons"><button className="text-button" disabled={!!busy} onClick={() => void buildPlan()}>Suggest a different plan</button><button className="primary" disabled={!!busy} onClick={() => void confirmPlan()}>{busy ? <><LoaderCircle size={16} className="spin" /> {busy}</> : <>Confirm this plan <Check size={17} /></>}</button></div></>}
          </section>
          <p className="privacy-note"><ShieldCheck size={14} /> A plan is a suggestion. Guider never performs these steps for you.</p>
        </div>}

        {page === 'history' && <div className="simple-page"><span className="eyebrow">PICK UP WHERE YOU LEFT OFF</span><h1>Your task history.</h1><p className="muted">{isDemo ? 'Tasks from this browser tab. Refreshing clears the demo.' : 'Your private tasks, newest first. Reopen a task to share fresh evidence.'}</p>{history.length ? <div className="history-list">{history.map(item => <button disabled={!!busy} key={item.session.id} onClick={() => void openTask(item)}><span className="history-icon"><Terminal size={21} /></span><span><strong>{item.task_title}</strong><small>{new Date(item.session.created_at).toLocaleDateString()} · {item.session.outcome || item.session.state.replaceAll('_', ' ')}</small></span><ArrowRight size={19} /></button>)}</div> : <section className="empty-panel"><History size={34} /><h2>A fresh page.</h2><p>Your tasks will appear here once you start.</p><button className="primary" onClick={reset}>Start a task <ArrowRight size={17} /></button></section>}</div>}
        {page === 'privacy' && <div className="simple-page"><span className="eyebrow">ALWAYS YOUR CALL</span><h1>A guide. On your terms.</h1><p className="muted">You choose the context. You take the actions.</p><div className="privacy-sections"><article><EyeOff size={23} /><div><h2>Observation is off.</h2><p>Live screen guide can preview a window or tab you choose. It sends only frames you review and submit to OpenAI. Sharing stops when you leave that view or hide Guider. There is no microphone, recording, typing, or clicking.</p></div></article><article><ShieldCheck size={23} /><div><h2>{isDemo ? 'This demo stays in your tab.' : 'Screenshots are private.'}</h2><p>{isDemo ? 'Your task and image live in browser memory. They are not sent to the API or an AI provider, and they disappear when you refresh or close this tab.' : 'Images go to your configured Guider development backend, expire within 24 hours, and can be deleted with their analysis. The local development storage is not approved for real customer media.'}</p></div></article><article><ScanLine size={23} /><div><h2>OpenAI when you connect.</h2><p>Live screen guide uses your OpenAI API key for actual visual guidance. You review each outgoing frame. The original screenshot demo still uses a fixed example. Cloud keys are kept only in local backend memory and cleared on disconnect or expiry.</p></div></article><article><Trash2 size={23} /><div><h2>Delete what you share.</h2><p>Use the trash button beside an uploaded screenshot to remove its pixels and associated explanation. Task and account erasure controls are still on the implementation roadmap.</p></div></article></div></div>}
        <footer><span className="footer-brand">guider.</span><span>A little help. A lot more possibility.</span><span>YOU DO. WE GUIDE.</span></footer>
      </main>
    </div>
    {guiding && plan && <GuideIsland
      state={islandState}
      step={activeStep}
      instruction={live.state.instruction}
      ordinal={activeStep?.ordinal ?? (live.state.phase === 'finished' ? guideSteps.length : 0)}
      total={guideSteps.length}
      asking={live.state.phase === 'asking'}
      correction={live.state.error || live.state.correction}
      paused={live.state.paused}
      observerAsked={live.state.askedBy === 'observer'}
      stuck={live.state.stuck ? stuckMessage(live.state.stuck) : ''}
      onReplan={() => void askForNewPlan()}
      framesObserved={framesObserved}
      watchNotice={watchNotice}
      mount={floating?.mount ?? null}
      onStartWatching={() => { setWatchNotice(''); setWatchOpen(true); }}
      onStopWatching={() => void stopWatching('You switched watching off.')}
      onClaim={() => void live.claim()}
      onAnswer={happened => void live.answer(happened)}
      onTogglePause={live.togglePause}
      onSkip={() => void live.skip()}
      onClose={stopGuiding}
    />}
    {watchOpen && <WatchSetup
      chooseWindow={() => capture.current.start(reason => void stopWatching(reason))}
      onStart={beginWatching}
      onCancel={() => { setWatchOpen(false); capture.current.stop(); }}
    />}
    {/* The watched window lives here for as long as watching is on: the setup
        dialog closes, and its frames must keep arriving. It is never shown. */}
    <video ref={watchVideo} className="sr-only" muted playsInline aria-hidden="true" tabIndex={-1} />
    <input ref={input} type="file" className="sr-only" tabIndex={-1} accept="image/png,image/jpeg,image/webp" aria-label="Choose screenshot file" onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void selectFile(file); }} />
    {authOpen && <div className="modal-backdrop"><section className="auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title"><button className="icon-button modal-close" aria-label="Close sign in" onClick={() => setAuthOpen(false)}><X size={20} /></button><span className="brand-mark"><Compass size={26} /></span><h2 id="auth-title">Your own little workspace.</h2><p>Sign in with an email code to save private tasks.</p><form onSubmit={event => { event.preventDefault(); void work('Signing in…', async () => {
      if (codeSent) { const result = await supabase!.auth.verifyOtp({ email, token: code, type: 'email' }); if (result.error) throw result.error; setAuthOpen(false); setCode(''); setCodeSent(false); }
      else { const result = await supabase!.auth.signInWithOtp({ email }); if (result.error) throw result.error; setCodeSent(true); }
    }); }}><label>Email address<input type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} required disabled={codeSent} /></label>{codeSent && <label>Email code<input value={code} inputMode="numeric" autoComplete="one-time-code" onChange={event => setCode(event.target.value)} required minLength={6} maxLength={8} /></label>}<button className="primary" disabled={!!busy}>{busy || (codeSent ? 'Verify code' : 'Email me a code')}<ArrowRight size={17} /></button></form>{error && <p className="error" role="alert">{error}</p>}<small>Your session stays in memory and ends when you close or refresh this page.</small></section></div>}
  </div>;
}
