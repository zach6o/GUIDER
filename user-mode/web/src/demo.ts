import type {
  Analysis, Claimed, CurrentInstruction, GuideApi, GuideEventPage, ImportAccepted, Instruction,
  Operation, Outcome, Plan, Screenshot, SelfReported, Session, Step, Summary, Task,
} from './types';

/** Small on purpose: a demo with three tasks should still show the control that
 *  asks for more, because a control nobody ever sees is a control nobody tests. */
const DEMO_HISTORY_PAGE = 5;
const tasks = new Map<string, Task>();
const sessions = new Map<string, Session>();
const images = new Map<string, { blob: Blob; screenshot: Screenshot }>();
const operations = new Map<string, Operation>();
const plans = new Map<string, Plan>();
const instructions = new Map<string, Instruction>();
const claims = new Map<string, { id: string; step_id: string; status: string; version: number }>();
// Steps the user has said they did. Mirrors a `user_reported` VerificationResult
// on the server: enough to stop handing the step out, never enough to verify it.
const selfReported = new Map<string, Set<string>>();
const stuck = new Set<string>();
const summaries = new Map<string, Summary>();
const events = new Map<string, GuideEventPage['items']>();

// Mirrors FIXTURE_PLAN in the backend fixture provider, so the offline demo shows
// the same roadmap the development adapter produces.
const demoSteps = [
  { title: 'Open the terminal', action: 'Open the integrated terminal in your editor.',
    expected_result: 'A shell prompt appears in a panel.',
    success_criterion: 'A command prompt is visible and accepts typing.',
    fallback: 'Use the View menu, then Terminal.',
    explanation: 'The interpreter reports what went wrong in the terminal, not the editor.' },
  { title: 'Show which interpreter is running',
    action: 'Type `python -c "import sys; print(sys.executable)"` and press Enter.',
    expected_result: 'A file path to a python executable is printed.',
    success_criterion: 'A path ending in python or python.exe is visible in the output.',
    fallback: 'If `python` is not found, try `py -c` on Windows or `python3 -c` elsewhere.',
    explanation: 'A package installed for one interpreter is invisible to another. Knowing which one runs your code is what makes the next step meaningful.' },
  { title: 'List what that interpreter can see',
    action: 'Type `python -c "import requests"` and press Enter.',
    expected_result: 'Either nothing is printed, or the same ModuleNotFoundError appears.',
    success_criterion: 'The command finishes and its output is visible.',
    fallback: 'If the prompt does not return, press Ctrl+C and try again.',
    explanation: 'Silence means the package is available to this interpreter. Repeating the error confirms the package is genuinely missing here.' },
];
/**
 * The same reading and the same refusals the server performs, in the browser.
 *
 * Mirrors `app/imports/text.py` and `app/imports/redact.py`: structure only, no
 * interpretation, recognized secrets dropped before anything is stored, and text
 * that addresses Guider removed rather than carried into a step. A demo that
 * accepted an injected instruction the server refuses would teach the wrong
 * thing in the only place most people look.
 */
const INJECTION = new RegExp([
  'ignore\\s+(all\\s+|any\\s+|the\\s+)?(previous|prior|earlier|above)\\s+(instructions?|messages?|rules?|prompts?)',
  'disregard\\s+(all\\s+|any\\s+|the\\s+)?(previous|prior|earlier|above)',
  'you\\s+are\\s+now\\s+',
  'from\\s+now\\s+on[,:]?\\s+you',
  '^\\s*(system|developer|assistant)\\s*:',
  'act\\s+as\\s+(the\\s+)?(system|developer|guider)',
  'new\\s+instructions?\\s*:',
  'override\\s+(your|the)\\s+(policy|rules|instructions)',
].join('|'), 'i');
const SECRETS: RegExp[] = [
  /\bsk-ant-[A-Za-z0-9_-]{8,}/gi, /\bsk-[A-Za-z0-9_-]{16,}/gi,
  /\b(?:AKIA|ASIA)[0-9A-Z]{12,}/g, /\bgh[pousr]_[A-Za-z0-9]{20,}/g,
  /\bBearer\s+[A-Za-z0-9._-]{12,}/gi,
  /\b(api[_\- ]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*\S+/gi,
  /\b[a-z][a-z0-9+.-]*:\/\/[^\s/@:]+:[^\s/@]+@\S+/gi,
];
const STEP_MARKER = /^\s*(?:step\s*)?\d{1,2}[.)]\s+(\S.*)$/i;
const BULLET = /^\s*[-*•]\s+(\S.*)$/;
const SPEAKER = /^\s*(you|user|me|human|assistant|chatgpt|claude|gemini)\s*:\s*/i;
// Mirrors RESTRICTED in app/guide/guard.py: a step proposing one of these is
// kept so the user sees it, and marked blocked so it can never be instructed.
const RESTRICTED = /\b(install|uninstall|delete|remove|send|publish|push|commit|reset|format|sudo|chmod|chown|password|purchase|payment|transfer|administrator)\b|\b(rm|del|rmdir|Remove-Item|Set-ExecutionPolicy)\s|\bapi\s*key\b/i;

function redactTranscript(text: string): { text: string; redactions: number } {
  let redactions = 0;
  let clean = text;
  for (const pattern of SECRETS) {
    clean = clean.replace(pattern, match => {
      redactions++;
      const labelled = /^([A-Za-z_\- ]+)\s*[:=]/.exec(match);
      return labelled ? `${labelled[1]}: [removed]` : '[removed]';
    });
  }
  return { text: clean, redactions };
}

function readTranscript(text: string) {
  const lines = text.split('\n');
  const steps = lines
    .map(line => (STEP_MARKER.exec(line) ?? BULLET.exec(line))?.[1] ?? '')
    .map(action => action.replace(/\s+/g, ' ').trim())
    .filter(action => action.length >= 8 && !INJECTION.test(action))
    .slice(0, 12);
  const goal = lines
    .map(line => line.replace(SPEAKER, '').trim())
    .find(line => line.length >= 12 && !STEP_MARKER.test(line) && !BULLET.test(line)
      && !INJECTION.test(line)) ?? '';
  return { goal, steps };
}

const uid = () => crypto.randomUUID();
const timestamp = () => new Date().toISOString();
const expiry = () => new Date(Date.now() + 86_400_000).toISOString();
const clone = <T,>(value: T): T => structuredClone(value);
const requireItem = <T,>(map: Map<string, T>, id: string): T => {
  const value = map.get(id);
  if (!value) throw new Error('This item is no longer available in the demo.');
  return value;
};

function emit(session: Session, type: string, payload: Record<string, unknown> = {}) {
  const log = events.get(session.id) ?? [];
  log.push({
    sequence: log.length + 1, state_version: session.state_version,
    control_epoch: session.control_epoch, type, payload, created_at: timestamp(),
  });
  events.set(session.id, log);
}

function move(session: Session, state: string, reason: string) {
  const from = session.state;
  session.state = state; session.state_version++;
  if (from !== state) emit(session, 'session.state_changed', { from, to: state, reason });
}

function confirmedPlanFor(session: Session): Plan {
  for (const plan of plans.values()) {
    if (plan.session_id === session.id && plan.status === 'confirmed') return plan;
  }
  throw new Error('Confirm a plan before starting.');
}

const OPEN = ['pending', 'instruction_ready', 'awaiting_user_action', 'user_claimed'];
const SETTLED = ['verified', 'skipped'];
// Attempts on one step before the guide says it is going nowhere. Mirrors
// STUCK_ATTEMPTS in app/guide/replan.py.
const STUCK_ATTEMPTS = 2;
// What the fixture planner proposes for whatever is left. Mirrors FIXTURE_REPLAN.
const demoReplanSteps = [
  { title: 'Describe what you can see',
    action: 'Write down what the window shows now, in your own words.',
    expected_result: 'You have a short description of the current screen.',
    success_criterion: 'A description of the current screen exists.',
    fallback: 'If the window is gone, reopen the application first.',
    explanation: 'The previous steps assumed something that is no longer true. What is on screen now is where a working plan has to start.' },
  { title: 'Try the last step once more, slowly',
    action: 'Repeat the step you were on, pausing after each part.',
    expected_result: 'Either the step works, or you can say exactly where it stops.',
    success_criterion: 'The step completes, or the point where it fails is identified.',
    fallback: 'If nothing happens at all, close and reopen the application.',
    explanation: 'A step that fails halfway looks the same as one that never started. Knowing which it is decides what comes next.' },
];

function nextOpenStep(session: Session): Step | null {
  const reported = selfReported.get(session.id) ?? new Set<string>();
  return confirmedPlanFor(session).steps.find(step => OPEN.includes(step.status)
    && step.policy_disposition !== 'block' && !reported.has(step.id)) ?? null;
}

function retireInstructions(session: Session) {
  for (const existing of instructions.values()) {
    if (existing.session_id === session.id && existing.status === 'ready') {
      existing.status = 'superseded';
    }
  }
}

/** The demo's stand-in for the `instruct` role. Fixed text, like the backend
 *  fixture provider: no model runs in this browser. */
function publishInstruction(session: Session, step: Step): Instruction {
  retireInstructions(session);
  const version = [...instructions.values()].filter(item => item.step_id === step.id).length + 1;
  const instruction: Instruction = {
    id: uid(), session_id: session.id, step_id: step.id, version, status: 'ready',
    what: step.action, where: `In ${step.application_key.replace('_', ' ')}.`,
    why: step.explanation || null,
    confirmation_hint: step.expected_result,
    cannot_find_hint: step.fallback || 'Tell Guider what you can see instead.',
    created_at: timestamp(),
  };
  instructions.set(instruction.id, instruction);
  step.status = 'instruction_ready';
  session.current_step_id = step.id;
  emit(session, 'instruction.ready', { instruction_id: instruction.id, step_id: step.id, version });
  move(session, 'instruction_ready', 'instruction_ready');
  move(session, 'awaiting_user_action', 'instruction_published');
  step.status = 'awaiting_user_action';
  emit(session, 'step.awaiting_action', { step_id: step.id });
  return instruction;
}

/** Prepare whatever comes next, or report that the plan is finished. Nothing
 *  here marks a step verified; this demo cannot check a screen either. */
function prepareNextStep(session: Session) {
  move(session, 'processing', 'next_step_requested');
  const step = nextOpenStep(session);
  if (!step) {
    retireInstructions(session);
    session.current_step_id = null;
    move(session, 'awaiting_user_action', 'steps_exhausted');
    emit(session, 'plan.steps_exhausted', {});
    return null;
  }
  return publishInstruction(session, step);
}

function currentStep(session: Session): { instruction: Instruction; step: Step } | null {
  const instruction = [...instructions.values()]
    .find(item => item.session_id === session.id && item.status === 'ready');
  if (!instruction) return null;
  const step = confirmedPlanFor(session).steps.find(item => item.id === instruction.step_id);
  return step ? { instruction, step } : null;
}

/**
 * The same summary the server builds, from the same records.
 *
 * Mirrors `app/guide/summary.py`: checked steps and reported steps are separate
 * lists, and the prose says which is which. A demo that told the user "all done"
 * would erase the distinction everything else here maintains.
 */
function writeSummary(session: Session, outcome: Outcome): Summary {
  const existing = summaries.get(session.id);
  if (existing) return existing;
  const plan = [...plans.values()].find(
    item => item.session_id === session.id && item.status === 'confirmed',
  );
  const steps = plan?.steps ?? [];
  const reported = selfReported.get(session.id) ?? new Set<string>();
  const verified = steps.filter(step => step.status === 'verified');
  const told = steps.filter(step => step.status !== 'verified' && reported.has(step.id));
  const skipped = steps.filter(step => step.status === 'skipped');
  const blocked = steps.filter(step => step.policy_disposition === 'block');
  const settled = new Set([...verified, ...told, ...skipped, ...blocked].map(step => step.id));
  const outstanding = steps.filter(step => !settled.has(step.id));

  const parts = [`${steps.length} step${steps.length === 1 ? '' : 's'} in this plan.`];
  if (verified.length) {
    parts.push(`${verified.length} ${verified.length === 1 ? 'was' : 'were'} checked on screen.`);
  }
  if (told.length) {
    parts.push(`${told.length} you told Guider ${told.length === 1 ? 'was' : 'were'} done; nothing checked those.`);
  }
  if (skipped.length) {
    parts.push(`${skipped.length} ${skipped.length === 1 ? 'was' : 'were'} skipped.`);
  }
  if (blocked.length) {
    parts.push(`${blocked.length} need${blocked.length === 1 ? 's' : ''} separate review and Guider did not walk you through ${blocked.length === 1 ? 'it' : 'them'}.`);
  }
  if (outstanding.length) {
    parts.push(`${outstanding.length} ${outstanding.length === 1 ? 'was' : 'were'} never started.`);
  }
  if (outcome === 'achieved') parts.push('Every required step was checked.');
  if (outcome === 'user_reported') parts.push('This is your own account of the work, not a check of it.');
  if (outcome === 'stopped') parts.push('You stopped this task.');

  const summary: Summary = {
    session_id: session.id, outcome,
    verified_steps: verified.map(step => step.id),
    unverified_steps: [...told, ...skipped, ...outstanding].map(step => step.id),
    corrections: [
      ...skipped.map(step => `Step ${step.ordinal} was skipped: ${step.title}`),
      ...blocked.map(step => `Step ${step.ordinal} needs separate review: ${step.title}`),
      ...outstanding.map(step => `Step ${step.ordinal} was never started: ${step.title}`),
    ],
    text: parts.join(' '),
    next_action: blocked.length ? `Step ${blocked[0].ordinal} still needs separate review.` : null,
    created_at: timestamp(),
  };
  summaries.set(session.id, summary);
  return summary;
}

function instructOperation(): Operation {
  const operation: Operation = {
    id: uid(), kind: 'instruct', status: 'succeeded', result: null, error: null,
  };
  operations.set(operation.id, operation);
  return operation;
}

export const demoApi: GuideApi = {
  async create(input) {
    const task: Task = { ...input, id: uid(), title: input.goal.slice(0, 120), status: 'open',
      current_session_id: null, created_at: timestamp(), updated_at: timestamp() };
    const session: Session = { id: uid(), task_id: task.id, state: 'task_created', state_version: 1,
      control_epoch: 1, observation_mode: 'screenshot_only', outcome: null,
      created_at: timestamp(), expires_at: expiry() };
    task.current_session_id = session.id;
    tasks.set(task.id, task); sessions.set(session.id, session);
    return clone({ task, session });
  },
  async importConversation(text, source) {
    const { text: transcript, redactions } = redactTranscript(text);
    const { goal, steps } = readTranscript(transcript);
    if (!goal || !steps.length) {
      throw new Error(
        'Guider could not find a goal and steps in that text. '
        + 'Paste the part of the conversation with the steps in it.',
      );
    }
    const task: Task = {
      id: uid(), title: goal.slice(0, 120), goal, category: 'setup',
      application_key: 'unknown', status: 'open', current_session_id: null,
      created_at: timestamp(), updated_at: timestamp(),
    };
    const session: Session = {
      id: uid(), task_id: task.id, state: 'task_created', state_version: 1, control_epoch: 1,
      observation_mode: 'screenshot_only', outcome: null, current_step_id: null,
      created_at: timestamp(), expires_at: expiry(),
    };
    task.current_session_id = session.id;
    tasks.set(task.id, task); sessions.set(session.id, session);

    const plan: Plan = {
      id: uid(), task_id: task.id, session_id: session.id, version: 1, status: 'draft',
      assumptions: [
        'Read from the conversation you pasted, word for word. '
        + 'Nothing here was checked against your screen.',
      ],
      policy_version: 'development-1', confirmed_at: null,
      steps: steps.map((action, index) => ({
        id: uid(), ordinal: index + 1, title: action.slice(0, 120), action,
        expected_result: '', success_criterion: action.slice(0, 500), fallback: '',
        explanation: 'Taken word for word from the conversation you pasted.',
        application_key: 'unknown', risk: RESTRICTED.test(action) ? 'high' as const : 'low' as const,
        // The guard's verdict, not the transcript's: a restricted action is shown
        // and blocked rather than quietly dropped.
        policy_disposition: RESTRICTED.test(action) ? 'block' as const : 'allow' as const,
        evidence_kind: 'self_report' as const, required: true, status: 'pending',
        attempt_count: 0, verified_at: null,
      })),
      created_at: timestamp(), updated_at: timestamp(),
    };
    plans.set(plan.id, plan);
    move(session, 'analyzing', 'import_requested');
    move(session, 'plan_ready', 'import_ready');
    emit(session, 'plan.ready', { plan_id: plan.id, imported: true, source });
    move(session, 'awaiting_user_confirmation', 'import_published');

    const operation: Operation = {
      id: uid(), kind: 'plan', status: 'succeeded', result: null,
      result_id: plan.id, error: null,
    };
    operations.set(operation.id, operation);
    return clone<ImportAccepted>({
      task, session, operation_id: operation.id,
      imported: {
        id: uid(), source, redactions,
        steps_extracted: plan.steps.length,
        steps_blocked: plan.steps.filter(step => step.policy_disposition === 'block').length,
        created_at: timestamp(),
      },
    });
  },
  async history(cursor) {
    // Paged like the server's, so the page that asks for more is exercised here
    // too rather than only against a backend the demo never reaches.
    const all = [...sessions.values()].reverse().map(session => ({ session,
      task_title: requireItem(tasks, session.task_id).title }));
    const start = cursor ? all.findIndex(item => item.session.id === cursor) + 1 : 0;
    const page = all.slice(start, start + DEMO_HISTORY_PAGE);
    const last = page[page.length - 1];
    return clone({
      items: page,
      next_cursor: last && start + page.length < all.length ? last.session.id : null,
    });
  },
  async task(id) { return clone(requireItem(tasks, id)); },
  async session(id) { return clone(requireItem(sessions, id)); },
  async upload(task, session, blob, replaces) {
    const current = requireItem(sessions, session.id);
    if (current.state === 'completed') throw new Error('This task has stopped. Start a new task.');
    if (current.state_version !== session.state_version) throw new Error('Reload the task and try again.');
    const bitmap = await createImageBitmap(blob);
    const screenshot: Screenshot = { id: uid(), task_id: task.id, session_id: session.id,
      width: bitmap.width, height: bitmap.height, status: 'ready', version: 1, expires_at: expiry() };
    bitmap.close();
    images.set(screenshot.id, { blob, screenshot });
    if (replaces) await demoApi.deleteImage(replaces.id);
    current.state_version++;
    return clone({ screenshot, session: current });
  },
  async content(id) { return requireItem(images, id).blob; },
  async analyze(_task, session, screenshot) {
    const image = requireItem(images, screenshot.id);
    const current = requireItem(sessions, session.id);
    if (current.state === 'completed') throw new Error('This task has stopped.');
    const fixture = await fetch('/fixtures/python-error.png').then(r => r.blob());
    const pixels = async (blob: Blob) => {
      const bitmap = await createImageBitmap(blob);
      const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
      const ctx = canvas.getContext('2d')!;
      ctx.drawImage(bitmap, 0, 0); bitmap.close();
      return new Uint8Array(await crypto.subtle.digest('SHA-256', ctx.getImageData(0, 0, canvas.width, canvas.height).data));
    };
    const [a, b] = await Promise.all([pixels(image.blob), pixels(fixture)]);
    const recognized = a.every((value, index) => value === b[index]);
    const result: Analysis = { id: uid(), screenshot_ids: [screenshot.id], needs_context: true,
      observations: recognized ? [{ label: 'The missing package', confidence: 1,
        bbox: { x: .03, y: .54, width: .85, height: .13 } }] : [],
      explanation: recognized
        ? 'Python cannot find the requests package in the environment running app.py. It may be installed in a different environment, or it may not be installed yet. This is a fixed explanation of the synthetic example.'
        : 'Your image is ready, but this demo cannot interpret arbitrary screenshots. It stays in this browser tab. Try the Python example to see how an explanation looks.',
      context_request: recognized ? 'Which Python environment did you intend to use?'
        : 'Real screenshot interpretation will be available after a vision provider is configured.',
    };
    const operation: Operation = { id: uid(), status: 'succeeded', result, error: null };
    operations.set(operation.id, operation); current.state_version++;
    return clone({ operation_id: operation.id, session: current });
  },
  async requestPlan(task, session) {
    const current = requireItem(sessions, session.id);
    if (current.state_version !== session.state_version) throw new Error('Reload the task and try again.');
    for (const existing of plans.values()) {
      if (existing.session_id === current.id) existing.status = 'superseded';
    }
    const version = [...plans.values()].filter(item => item.session_id === current.id).length + 1;
    const plan: Plan = {
      id: uid(), task_id: task.id, session_id: current.id, version, status: 'draft',
      assumptions: [
        'This fixed roadmap comes from a development fixture, not from a planner model.',
        `Written for the ${task.application_key.replace('_', ' ')} workflow on this machine.`,
      ],
      policy_version: 'development-1', confirmed_at: null,
      steps: demoSteps.map((step, index) => ({
        ...step, id: uid(), ordinal: index + 1, application_key: task.application_key,
        risk: 'low', policy_disposition: 'allow', evidence_kind: 'visual', required: true,
        status: 'pending', attempt_count: 0, verified_at: null,
      })),
      created_at: timestamp(), updated_at: timestamp(),
    };
    plans.set(plan.id, plan);
    const operation: Operation = { id: uid(), kind: 'plan', status: 'succeeded', result: null,
      result_id: plan.id, error: null };
    operations.set(operation.id, operation);
    current.state = 'awaiting_user_confirmation'; current.state_version++;
    return clone({ operation_id: operation.id, session: current });
  },
  async plan(id) { return clone(requireItem(plans, id)); },
  async confirmPlan(plan, session) {
    const current = requireItem(sessions, session.id);
    const saved = requireItem(plans, plan.id);
    if (saved.status === 'superseded' || saved.version !== plan.version) {
      throw new Error('This plan was replaced. Review the current plan before starting.');
    }
    if (current.state_version !== session.state_version) throw new Error('Reload the task and try again.');
    saved.status = 'confirmed'; saved.confirmed_at = timestamp(); saved.updated_at = timestamp();
    current.state_version++;
    return clone({ plan: saved, session: current });
  },
  async operation(id) { return clone(requireItem(operations, id)); },
  async deleteImage(id) {
    images.delete(id);
    for (const operation of operations.values()) {
      if (operation.result?.screenshot_ids.includes(id)) {
        operation.result = null; operation.status = 'canceled';
      }
    }
    return { id, status: 'purged', online_purge_due_at: timestamp() };
  },
  // The same order the backend uses: children first, then the parent, then the
  // receipt. Nothing here is asynchronous, so nothing can half-delete.
  async deleteSession(id) {
    requireItem(sessions, id);
    for (const [key, row] of instructions) if (row.session_id === id) instructions.delete(key);
    for (const [key, row] of plans) if (row.session_id === id) plans.delete(key);
    for (const [key, row] of images) if (row.screenshot.session_id === id) images.delete(key);
    claims.clear();
    events.delete(id); summaries.delete(id); selfReported.delete(id); stuck.delete(id);
    sessions.delete(id);
    // The task stays: removing one attempt is not asking to forget the goal.
    return { id: uid(), status: 'purged' as const, online_purge_due_at: timestamp() };
  },
  async deleteTask(id) {
    for (const session of [...sessions.values()]) {
      if (session.task_id === id) await demoApi.deleteSession(session.id);
    }
    for (const [key, row] of images) if (row.screenshot.task_id === id) images.delete(key);
    tasks.delete(id);
    return { id: uid(), status: 'purged' as const, online_purge_due_at: timestamp() };
  },
  async deleteAccount() {
    for (const task of [...tasks.values()]) await demoApi.deleteTask(task.id);
    for (const map of [tasks, sessions, plans, instructions, claims, images, operations,
      summaries, events, selfReported]) map.clear();
    stuck.clear();
    return { id: uid(), status: 'purged' as const, online_purge_due_at: timestamp() };
  },
  async pause(id) {
    const session = requireItem(sessions, id);
    if (session.state !== 'completed') { session.state = 'paused'; session.state_version++; session.control_epoch++; }
    return clone(session);
  },
  async stop(id) {
    const session = requireItem(sessions, id);
    session.state = 'completed'; session.outcome = 'stopped'; session.state_version++;
    // A stopped task still has something worth reading in history.
    writeSummary(session, 'stopped');
    return clone(session);
  },
  async complete(session, outcome, said) {
    const current = requireItem(sessions, session.id);
    if (current.state_version !== session.state_version) {
      throw new Error('Reload the task and try again.');
    }
    if (current.state === 'completed') throw new Error('This task has already finished.');
    const plan = [...plans.values()].find(
      item => item.session_id === current.id && item.status === 'confirmed',
    );
    if (!plan) throw new Error('There is no confirmed plan to finish.');
    const reported = selfReported.get(current.id) ?? new Set<string>();
    const required = plan.steps.filter(step => step.required);
    // `achieved` is a claim about evidence, so it is checked rather than taken.
    if (outcome === 'achieved' && !required.every(step => step.status === 'verified')) {
      throw new Error(
        'Some steps have not been checked. Finish as your own account instead, '
        + 'or check the rest first.',
      );
    }
    if (outcome === 'user_reported' && !required.every(step => step.policy_disposition !== 'block'
      && (step.status === 'verified' || step.status === 'skipped' || reported.has(step.id)))) {
      throw new Error(
        'Some steps are still open, or need separate review. Skip what you are not doing first.',
      );
    }
    current.outcome = outcome;
    move(current, 'completed', outcome);
    const summary = writeSummary(current, outcome);
    if (said.trim()) summary.corrections = [...summary.corrections, `You said: ${said.trim()}`];
    const task = tasks.get(current.task_id);
    if (task) task.status = 'completed';
    return clone({ session: current, summary });
  },
  async summary(id) {
    const session = requireItem(sessions, id);
    if (session.state !== 'completed') return null;
    return clone(summaries.get(id) ?? null);
  },
  async start(session) {
    const current = requireItem(sessions, session.id);
    if (current.state_version !== session.state_version) {
      throw new Error('Reload the task and try again.');
    }
    confirmedPlanFor(current);
    move(current, 'active', 'session_started');
    emit(current, 'session.started', {});
    prepareNextStep(current);
    return clone({ operation_id: instructOperation().id, session: current });
  },
  async instruction(id) {
    const session = requireItem(sessions, id);
    const current = currentStep(session);
    if (!current) return null;
    return clone<CurrentInstruction>({ ...current, session });
  },
  async claim(session, stepId, statement) {
    const current = requireItem(sessions, session.id);
    if (current.state_version !== session.state_version) {
      throw new Error('Reload the task and try again.');
    }
    if (current.state !== 'awaiting_user_action') throw new Error('There is no step waiting on you.');
    const found = currentStep(current);
    if (!found || found.step.id !== stepId) {
      throw new Error('There is no current instruction to confirm.');
    }
    for (const existing of claims.values()) {
      if (existing.step_id === stepId && existing.status === 'user_claimed') {
        existing.status = 'superseded';
      }
    }
    const claim = {
      id: uid(), step_id: stepId, status: 'user_claimed', version: found.instruction.version,
      statement,
    };
    claims.set(claim.id, claim);
    // A claim is the user's word: the step records it and nothing advances.
    found.step.status = 'user_claimed'; found.step.attempt_count++;
    emit(current, 'step.user_claimed', { step_id: stepId, claim_id: claim.id, verified: false });
    // Saying done repeatedly on one step is the guide going nowhere. Said once,
    // and it changes no state, exactly as the server does it.
    if (found.step.attempt_count >= STUCK_ATTEMPTS && !stuck.has(current.id)) {
      stuck.add(current.id);
      emit(current, 'session.stuck_detected', { step_id: stepId, reason: 'repeated_attempts' });
    }
    move(current, current.state, 'user_claimed');
    return clone<Claimed>({
      claim_id: claim.id, step: found.step, session: current, verified: false,
    });
  },
  async selfReport(session, stepId, claimId, said) {
    const current = requireItem(sessions, session.id);
    if (current.state_version !== session.state_version) {
      throw new Error('Reload the task and try again.');
    }
    const claim = claims.get(claimId);
    if (!claim || claim.step_id !== stepId) throw new Error('That step was not confirmed yet.');
    if (claim.status !== 'user_claimed') {
      throw new Error('That confirmation was replaced by a newer one.');
    }
    if (!said.trim()) throw new Error('Say what happened, or share a screenshot to check.');
    const found = currentStep(current);
    if (!found || found.step.id !== stepId) throw new Error('There is no step waiting on you.');

    move(current, 'verifying', 'self_report_requested');
    const verification = {
      id: uid(), session_id: current.id, step_id: stepId, claim_id: claimId,
      status: 'user_reported' as const, verifier_kind: 'self_report' as const,
      reason: said.trim(), observed_confidence: null, evidence_available: false,
      instruction_version: claim.version, created_at: timestamp(),
    };
    // The step keeps `user_claimed`. Only evidence could make it verified.
    const reported = selfReported.get(current.id) ?? new Set<string>();
    reported.add(stepId); selfReported.set(current.id, reported);
    emit(current, 'verification.completed', {
      step_id: stepId, verification_id: verification.id, passed: false, status: 'user_reported',
    });
    move(current, 'awaiting_user_action', 'self_report_recorded');
    prepareNextStep(current);
    return clone<SelfReported>({
      verification, step: found.step, session: current, verified: false,
      next_operation_id: instructOperation().id,
    });
  },
  // The demo has no vision provider, so it refuses to check rather than
  // inventing a verdict about a real screenshot. Saying so is the honest
  // mirror of a backend that would look.
  async checkEvidence() {
    throw new Error(
      'This demo cannot check a screenshot: it has no vision provider. '
      + 'Tell Guider what happened instead, and it will be recorded as your word.',
    );
  },
  async skipStep(session, stepId, reason) {
    const current = requireItem(sessions, session.id);
    if (current.state_version !== session.state_version) {
      throw new Error('Reload the task and try again.');
    }
    const found = currentStep(current);
    if (!found || found.step.id !== stepId) throw new Error('There is no step waiting on you.');
    found.step.status = 'skipped';
    emit(current, 'step.skipped', { step_id: stepId, reason });
    prepareNextStep(current);
    return clone({
      step: found.step, session: current, next_operation_id: instructOperation().id,
    });
  },
  // Doc 05: the user calling guidance wrong withdraws the pointer, undoes any
  // pass they contradicted, revokes watching and blocks the session. Nothing in
  // this browser observes, so only the first, third and fourth ever apply here.
  async reportIncorrect(session, stepId, text) {
    const current = requireItem(sessions, session.id);
    if (current.state_version !== session.state_version) {
      throw new Error('Reload the task and try again.');
    }
    const plan = confirmedPlanFor(current);
    const step = plan.steps.find(item => item.id === stepId);
    if (!step) throw new Error('Say which step the guidance was wrong about.');
    const withdrawn = step.status === 'verified';
    if (withdrawn) { step.status = 'pending'; step.verified_at = null; }
    for (const existing of instructions.values()) {
      if (existing.session_id === current.id && existing.status === 'ready') {
        existing.status = 'invalidated';
      }
    }
    current.current_step_id = null;
    emit(current, 'feedback.recorded', {
      feedback_id: uid(), kind: 'incorrect_guidance', step_id: stepId, text,
    });
    move(current, 'blocked', 'incorrect_guidance');
    return clone({
      feedback_id: uid(), session: current, step, verification_withdrawn: withdrawn,
    });
  },
  // Doc 05's resume row: back to the checkpoint, with no permission restored.
  // Nothing in this browser was ever watching, so only the first half applies.
  async resume(session, mode) {
    const current = requireItem(sessions, session.id);
    if (current.state_version !== session.state_version) {
      throw new Error('Reload the task and try again.');
    }
    if (['completed', 'failed', 'expired'].includes(current.state)) {
      throw new Error('This task has already finished.');
    }
    if (!['paused', 'blocked'].includes(current.state)) {
      throw new Error('This task is not waiting to be resumed.');
    }
    const target = mode === 'window' ? 'awaiting_screen_permission' : 'awaiting_user_action';
    move(current, target, 'resumed');
    let operationId: string | null = null;
    if (target === 'awaiting_user_action') {
      // The instruction was withdrawn when the session blocked, so the step is
      // published again rather than resuming into silence. It is found the way
      // the engine finds it — the lowest open step — because `currentStep` reads
      // a ready instruction and there is none left to read.
      const open = nextOpenStep(current);
      if (open) { publishInstruction(current, open); operationId = instructOperation().id; }
    }
    return clone({ session: current, next_operation_id: operationId });
  },
  async retryStep(session, stepId, reason) {
    const current = requireItem(sessions, session.id);
    if (current.state_version !== session.state_version) {
      throw new Error('Reload the task and try again.');
    }
    const found = currentStep(current);
    if (!found || found.step.id !== stepId) throw new Error('That is not the step you are on.');
    if (found.step.policy_disposition === 'block') {
      throw new Error('Guider will not walk you through this step. It needs separate review.');
    }
    if (found.step.attempt_count >= 3) {
      throw new Error(
        'Saying this a different way is not working. Ask for a different plan instead.',
      );
    }
    found.step.attempt_count++;
    emit(current, 'step.retry_requested', {
      step_id: stepId, attempt: found.step.attempt_count, reason,
    });
    // Rewording one step twice is the same going-nowhere signal a repeated claim
    // is, and the backend counts them the same way.
    if (found.step.attempt_count >= STUCK_ATTEMPTS && !stuck.has(current.id)) {
      stuck.add(current.id);
      emit(current, 'session.stuck_detected', { step_id: stepId, reason: 'repeated_attempts' });
    }
    publishInstruction(current, found.step);
    return clone({ operation_id: instructOperation().id, session: current });
  },
  async replan(session, reason) {
    const current = requireItem(sessions, session.id);
    if (current.state_version !== session.state_version) {
      throw new Error('Reload the task and try again.');
    }
    if (current.state !== 'awaiting_user_action') throw new Error('There is no step waiting on you.');
    const previous = confirmedPlanFor(current);
    const reported = selfReported.get(current.id) ?? new Set<string>();
    const done = previous.steps.filter(
      step => SETTLED.includes(step.status) || reported.has(step.id),
    );

    retireInstructions(current);
    current.current_step_id = null;
    emit(current, 'session.replan_requested', { reason });
    move(current, 'analyzing', 'replan');

    for (const plan of plans.values()) {
      if (plan.session_id === current.id) plan.status = 'superseded';
    }
    const version = [...plans.values()].filter(item => item.session_id === current.id).length + 1;
    const replacement: Plan = {
      id: uid(), task_id: current.task_id, session_id: current.id, version, status: 'draft',
      assumptions: [
        'This replacement roadmap comes from a development fixture, not from a planner.',
        `Asked for because the task was ${reason}.`,
        `${done.length} earlier step(s) are already done and are kept as they are.`,
      ],
      policy_version: 'development-1', confirmed_at: null,
      steps: [
        // Carried across exactly as they were, pointing back at the originals.
        ...done.map(step => ({ ...step, id: uid(), previous_step_id: step.id })),
        ...demoReplanSteps.map(step => ({
          ...step, id: uid(), ordinal: 0, application_key: previous.steps[0].application_key,
          risk: 'low' as const, policy_disposition: 'allow' as const,
          evidence_kind: 'visual' as const, required: true, status: 'pending',
          attempt_count: 0, verified_at: null,
        })),
      ].map((step, index) => ({ ...step, ordinal: index + 1 })),
      created_at: timestamp(), updated_at: timestamp(),
    };
    plans.set(replacement.id, replacement);
    // A self-reported step stays self-reported on its copy.
    for (const step of replacement.steps) {
      const origin = (step as { previous_step_id?: string }).previous_step_id;
      if (origin && reported.has(origin)) reported.add(step.id);
    }
    selfReported.set(current.id, reported);
    stuck.delete(current.id);

    move(current, 'plan_ready', 'replan_ready');
    emit(current, 'plan.ready', { plan_id: replacement.id, reason, carried_steps: done.length });
    move(current, 'awaiting_user_confirmation', 'replan_published');
    emit(current, 'plan.confirmation_required', {
      plan_id: replacement.id, version: replacement.version,
    });
    const operation: Operation = {
      id: uid(), kind: 'plan', status: 'succeeded', result: null,
      result_id: replacement.id, error: null,
    };
    operations.set(operation.id, operation);
    return clone({ operation_id: operation.id, session: current });
  },
  // Watching needs a vision provider, and this demo is a browser tab with no
  // backend and no provider. Refusing is the only honest answer: a simulated
  // verdict about a real screen would be an invented observation.
  async startWatching() {
    throw new Error(
      'Watching a window needs a signed-in task on a running Guider backend. '
      + 'This demo guides you step by step instead.',
    );
  },
  async stopWatching() {
    throw new Error('Watching was never switched on in this demo.');
  },
  async observe() {
    throw new Error('This demo never looks at your screen.');
  },
  async observeContext() {
    // The same refusal, for the same reason: describing a screen it cannot see
    // would be an invented belief, and a belief is what the guide acts on.
    throw new Error('This demo never looks at your screen.');
  },
  async skipForward(session, stepId, stepIds) {
    const current = requireItem(sessions, session.id);
    const plan = confirmedPlanFor(current);
    const settled = plan.steps.filter(step => step.id === stepId || stepIds.includes(step.id));
    for (const step of settled) step.status = 'skipped';
    emit(current, 'context.skipped_forward', { step_ids: stepIds, from_step_id: stepId });
    prepareNextStep(current);
    return clone({ session: current });
  },
  async events(id, after, waitMs) {
    const log = events.get(id) ?? [];
    const items = log.filter(event => event.sequence > after);
    // The real route long-polls. Here everything already happened, so an empty
    // answer waits a moment rather than spinning the caller's follow loop.
    if (!items.length && waitMs) await new Promise(resolve => setTimeout(resolve, 100));
    return clone({ items, next_after: items.length ? items[items.length - 1].sequence : after });
  },
};
