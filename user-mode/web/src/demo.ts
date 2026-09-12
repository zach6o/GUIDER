import type { Analysis, GuideApi, Operation, Plan, Screenshot, Session, Task } from './types';

const tasks = new Map<string, Task>();
const sessions = new Map<string, Session>();
const images = new Map<string, { blob: Blob; screenshot: Screenshot }>();
const operations = new Map<string, Operation>();
const plans = new Map<string, Plan>();

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
const uid = () => crypto.randomUUID();
const timestamp = () => new Date().toISOString();
const expiry = () => new Date(Date.now() + 86_400_000).toISOString();
const clone = <T,>(value: T): T => structuredClone(value);
const requireItem = <T,>(map: Map<string, T>, id: string): T => {
  const value = map.get(id);
  if (!value) throw new Error('This item is no longer available in the demo.');
  return value;
};

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
  async history() {
    return clone({ items: [...sessions.values()].reverse().map(session => ({ session,
      task_title: requireItem(tasks, session.task_id).title })) });
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
  async pause(id) {
    const session = requireItem(sessions, id);
    if (session.state !== 'completed') { session.state = 'paused'; session.state_version++; session.control_epoch++; }
    return clone(session);
  },
  async stop(id) {
    const session = requireItem(sessions, id);
    session.state = 'completed'; session.outcome = 'stopped'; session.state_version++;
    return clone(session);
  },
};
