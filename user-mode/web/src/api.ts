import { createClient } from '@supabase/supabase-js';
import type { CurrentInstruction, GuideApi } from './types';
import { demoApi } from './demo';

const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
export const supabase = url && key ? createClient(url, key, {
  auth: { flowType: 'pkce', persistSession: false, autoRefreshToken: true, detectSessionInUrl: true },
}) : null;
export const isDemo = !supabase;
const base = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1/guide';

/** Carries the status so a caller can tell "nothing here" from "went wrong". */
export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

async function request<T>(path: string, init: RequestInit = {}, binary = false): Promise<T> {
  const { data } = await supabase!.auth.getSession();
  if (!data.session) throw new Error('Sign in to continue.');
  const headers = new Headers(init.headers);
  headers.set('Authorization', `Bearer ${data.session.access_token}`);
  if (init.method === 'POST') headers.set('Idempotency-Key', crypto.randomUUID());
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${base}${path}`, { ...init, headers, cache: 'no-store' });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new ApiError(
      error?.error?.message || 'Could not reach Guider. Please try again.', response.status,
    );
  }
  return binary ? await response.blob() as T : (await response.json()).data as T;
}

const post = <T,>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) });
const remote: GuideApi = {
  create: input => post('/tasks', input),
  history: () => request('/sessions'),
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
  confirmPlan: (plan, session) => post(`/plans/${plan.id}/confirm`, {
    expected_version: session.state_version, plan_version: plan.version,
  }),
  operation: id => request(`/operations/${id}`),
  deleteImage: id => request(`/screenshots/${id}`, { method: 'DELETE' }),
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
  skipStep: (session, stepId, reason) => post(`/sessions/${session.id}/steps/${stepId}/skip`, {
    expected_version: session.state_version, reason,
  }),
  events: (id, after, waitMs, signal) => request(
    `/sessions/${id}/events?after=${after}&wait_ms=${waitMs}`, { signal },
  ),
};
export const api: GuideApi = isDemo ? demoApi : remote;
