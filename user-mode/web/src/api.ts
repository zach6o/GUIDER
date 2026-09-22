import { createClient } from '@supabase/supabase-js';
import type { CurrentInstruction, GuideApi, ObservationState, Summary } from './types';
import { demoApi } from './demo';

const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
export const supabase = url && key ? createClient(url, key, {
  auth: { flowType: 'pkce', persistSession: Boolean(import.meta.env.VITE_PERSONAL_API_URL), autoRefreshToken: true, detectSessionInUrl: true },
}) : null;
export const isDemo = !supabase;
let identityGeneration = 0;
supabase?.auth.onAuthStateChange(event => {
  if (event === 'SIGNED_OUT' || event === 'SIGNED_IN') identityGeneration++;
});
const base = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1/guide';

/** Carries the status and code so a caller can tell "nothing here" from "went
 *  wrong", and "the budget ran out" from "the session stopped". */
export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly code = '') { super(message); }
}

export async function request<T>(path: string, init: RequestInit = {}, binary = false): Promise<T> {
  const generation = identityGeneration;
  const { data } = await supabase!.auth.getSession();
  if (!data.session) throw new Error('Sign in to continue.');
  const headers = new Headers(init.headers);
  headers.set('Authorization', `Bearer ${data.session.access_token}`);
  if (init.method === 'POST') headers.set('Idempotency-Key', crypto.randomUUID());
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${base}${path}`, { ...init, headers, cache: 'no-store' });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    if (response.status === 401) {
      // Clear local credentials and trigger the application's capture cleanup.
      await supabase!.auth.signOut({ scope: 'local' });
    }
    throw new ApiError(
      error?.error?.message || 'Could not reach Guider. Please try again.', response.status,
      error?.error?.code || '',
    );
  }
  const result = binary ? await response.blob() as T : (await response.json()).data as T;
  if (generation !== identityGeneration) throw new ApiError('Sign in again to continue.', 401);
  return result;
}

const post = <T,>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) });
const remote: GuideApi = {
  revisePlan: (plan, session, steps) => post(`/plans/${plan.id}/revisions`, {
    expected_version: session.state_version, plan_version: plan.version, steps,
  }),
  exportSession: id => request(`/sessions/${id}/export`),
  create: input => post('/tasks', input),
  importConversation: (text, source) => post('/imports/conversations', { text, source }),
  history: (cursor, filters = {}) => {
    const query = new URLSearchParams();
    if (cursor) query.set('cursor', cursor);
    for (const [name, value] of Object.entries(filters)) if (value) query.set(name, value);
    return request(`/sessions?${query}`);
  },
  task: id => request(`/tasks/${id}`),
  session: id => request(`/sessions/${id}`),
  upload: (task, session, file, replaces) => {
    const body = new FormData();
    body.append('file', file, 'redacted-screenshot.png');
    body.append('metadata', JSON.stringify({
      session_id: session.id, expected_version: session.state_version,
      source: 'manual', purpose: 'context', captured_at: new Date().toISOString(),
      ...(replaces ? { replaces_screenshot_id: replaces.id } : {}),
    }));
    return request(`/tasks/${task.id}/screenshots`, { method: 'POST', body });
  },
  content: id => request(`/screenshots/${id}/content`, {}, true),
  analyze: (task, session, screenshot) => post(`/tasks/${task.id}/analyses`, {
    session_id: session.id, expected_version: session.state_version,
    screenshot_ids: [screenshot.id], question: task.goal,
  }),
  requestPlan: (task, session) => post(`/tasks/${task.id}/plans`, {
    session_id: session.id, expected_version: session.state_version,
  }),
  plan: id => request(`/plans/${id}`),
  sessionPlan: id => request(`/sessions/${id}/plan`),
  confirmPlan: (plan, session) => post(`/plans/${plan.id}/confirm`, {
    expected_version: session.state_version, plan_version: plan.version,
  }),
  operation: id => request(`/operations/${id}`),
  deleteImage: id => request(`/screenshots/${id}`, { method: 'DELETE' }),
  deleteTask: id => request(`/tasks/${id}`, { method: 'DELETE' }),
  deleteSession: id => request(`/sessions/${id}`, { method: 'DELETE' }),
  // The phrase is typed by the user and sent verbatim: a header nobody sends by
  // accident is what stops a misrouted request from erasing an account.
  deleteAccount: () => request('/account', {
    method: 'DELETE', headers: { 'X-Confirm-Deletion': 'delete-my-guide-account' },
  }),
  pause: id => post(`/sessions/${id}/pause`, { reason: 'user' }),
  stop: id => post(`/sessions/${id}/stop`, { reason: 'user' }),
  start: session => post(`/sessions/${session.id}/start`, {
    expected_version: session.state_version, observation_mode: 'screenshot_only',
  }),
  // 404 is the honest answer to "what am I on now?" when nothing is waiting on
  // the user, so it is a state here rather than an error. Anything else still is.
  instruction: async id => {
    try {
      return await request<CurrentInstruction>(`/sessions/${id}/instruction`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },
  claim: (session, stepId, statement) => post(`/sessions/${session.id}/steps/${stepId}/claim`, {
    expected_version: session.state_version, statement,
  }),
  selfReport: (session, stepId, claimId, said) =>
    post(`/sessions/${session.id}/steps/${stepId}/verifications`, {
      expected_version: session.state_version, claim_id: claimId, self_report: said,
    }),
  // The other arm of the same route. A screenshot is checked by a worker, so
  // this answers with an operation to follow rather than a result.
  checkEvidence: (session, stepId, claimId, screenshotId) =>
    post(`/sessions/${session.id}/steps/${stepId}/verifications`, {
      expected_version: session.state_version, claim_id: claimId,
      evidence_ids: [screenshotId],
    }),
  skipStep: (session, stepId, reason) => post(`/sessions/${session.id}/steps/${stepId}/skip`, {
    expected_version: session.state_version, reason,
  }),
  events: (id, after, waitMs, signal) => request(
    `/sessions/${id}/events?after=${after}&wait_ms=${waitMs}`, { signal },
  ),
  complete: (session, outcome, said) => post(`/sessions/${session.id}/completion`, {
    expected_version: session.state_version, outcome, self_report: said,
  }),
  // A summary exists only once a task has ended; before that, 409 is the answer.
  summary: async id => {
    try {
      return await request<Summary>(`/sessions/${id}/summary`);
    } catch (error) {
      if (error instanceof ApiError && [404, 409].includes(error.status)) return null;
      throw error;
    }
  },
  // Doc 05 makes this expensive on purpose: the pointer is withdrawn, watching
  // is revoked and the session blocks. The island asks before calling it.
  reportIncorrect: (session, stepId, text) => post(`/sessions/${session.id}/feedback`, {
    expected_version: session.state_version, kind: 'incorrect_guidance', step_id: stepId, text,
  }),
  // checkpoint_reviewed is sent as true because the island shows the user where
  // the task got to before this button exists to press (doc 05).
  resume: (session, mode) => post(`/sessions/${session.id}/resume`, {
    expected_version: session.state_version, mode, checkpoint_reviewed: true,
  }),
  retryStep: (session, stepId, reason) => post(
    `/sessions/${session.id}/steps/${stepId}/retries`,
    { expected_version: session.state_version, reason },
  ),
  replan: (session, reason) => post(`/sessions/${session.id}/replan`, {
    expected_version: session.state_version, reason,
  }),
  startWatching: (session, consentVersion) => post(`/sessions/${session.id}/observation`, {
    expected_version: session.state_version, consent_version: consentVersion, accepted: true,
  }),
  // Stopping takes no version and no key: a control that stops something must
  // not fail for being pressed at a bad moment, or twice.
  stopWatching: id => request<ObservationState>(
    `/sessions/${id}/observation`, { method: 'DELETE' },
  ),
  // The context tick. Same frame discipline as `observe`: held in memory on both
  // ends, never stored, and the answer is a belief rather than a verdict.
  observeContext: (session, imageBase64, admittedAt, signal) => request(
    `/sessions/${session.id}/context`,
    {
      method: 'POST',
      body: JSON.stringify({
        expected_version: session.state_version, image_base64: imageBase64,
        admitted_at: admittedAt,
      }),
      signal,
    },
  ),
  skipForward: (session, stepId, stepIds) => post(
    `/sessions/${session.id}/steps/${stepId}/skip-forward`,
    { expected_version: session.state_version, step_ids: stepIds },
  ),
  // One tick. The frame is held in memory on both ends and never stored.
  observe: (session, imageBase64, admittedAt, signal) => request(
    `/sessions/${session.id}/observe`,
    {
      method: 'POST', signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expected_version: session.state_version, image_base64: imageBase64,
        admitted_at: admittedAt,
      }),
    },
  ),
};
export const api: GuideApi = isDemo ? demoApi : remote;
