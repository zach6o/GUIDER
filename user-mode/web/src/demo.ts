import type { Analysis, GuideApi, Operation, Screenshot, Session, Task } from './types';

const tasks = new Map<string, Task>();
const sessions = new Map<string, Session>();
const images = new Map<string, { blob: Blob; screenshot: Screenshot }>();
const operations = new Map<string, Operation>();
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
