export type Category = 'setup' | 'run' | 'debug' | 'understand' | 'test' | 'git_github';
export interface Task {
  id: string; title: string; goal: string; category: Category; application_key: string;
  status: string; current_session_id: string | null; created_at: string; updated_at: string;
}
export interface Session {
  id: string; task_id: string; state: string; state_version: number; control_epoch: number;
  observation_mode: 'screenshot_only' | 'window'; outcome: string | null;
  current_step_id?: string | null; confirmed_plan_version?: number | null;
  observation_active?: boolean; frames_observed?: number;
  created_at: string; expires_at: string;
}
export interface Screenshot {
  id: string; task_id: string; session_id: string | null; width: number; height: number;
  status: string; expires_at: string; version: number;
}
export interface Box { x: number; y: number; width: number; height: number }
export interface Analysis {
  id: string; screenshot_ids: string[];
  observations: { label: string; bbox: Box | null; confidence: number }[];
  explanation: string; needs_context: boolean; context_request: string | null;
}
export interface Operation {
  id: string; kind?: 'analyze' | 'plan' | 'instruct';
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled';
  result: Analysis | null; result_id?: string | null; error: { message: string } | null;
}
export interface Step {
  id: string; ordinal: number; title: string; action: string;
  expected_result: string; success_criterion: string; fallback: string; explanation: string;
  application_key: string; risk: 'low' | 'medium' | 'high';
  policy_disposition: 'allow' | 'confirm' | 'block';
  evidence_kind: 'visual' | 'text' | 'self_report'; required: boolean;
  status: string; attempt_count: number; verified_at: string | null;
}
export interface Plan {
  id: string; task_id: string; session_id: string; version: number;
  status: 'draft' | 'confirmed' | 'superseded'; assumptions: string[];
  policy_version: string; confirmed_at: string | null; steps: Step[];
  created_at: string; updated_at: string;
}
export interface Instruction {
  id: string; session_id: string; step_id: string; version: number;
  status: 'ready' | 'superseded' | 'invalidated';
  what: string; where: string; why: string | null;
  confirmation_hint: string; cannot_find_hint: string; created_at: string;
}
export interface CurrentInstruction { instruction: Instruction; step: Step; session: Session }
export interface Claimed { claim_id: string; step: Step; session: Session; verified: false }
export interface Verification {
  id: string; session_id: string; step_id: string; claim_id: string | null;
  status: 'pending' | 'passed' | 'mismatch' | 'inconclusive' | 'user_reported' | 'canceled';
  verifier_kind: 'visual' | 'text' | 'self_report';
  reason: string; observed_confidence: number | null; evidence_available: boolean;
  instruction_version: number; created_at: string;
}
/** A self-report never passes a step; `verified` is false by construction. */
export interface SelfReported {
  verification: Verification; step: Step; session: Session; verified: false;
  next_operation_id: string | null;
}
export interface Skipped { step: Step; session: Session; next_operation_id: string | null }
export interface GuideEventPage {
  items: {
    sequence: number; state_version: number; control_epoch: number;
    type: string; payload: Record<string, unknown>; created_at: string;
  }[];
  next_after: number;
}
export interface ObservationState {
  active: boolean; frames_observed: number; observation_calls_remaining: number;
  consent_version: string; session: Session;
}
export interface ObservationTick {
  decision: 'advance' | 'ask' | 'wait';
  confidence: number; ui_changed: boolean;
  anomaly: 'none' | 'different_os' | 'different_app' | 'outdated_ui' | 'error_dialog' | 'unreadable';
  note: string; frames_observed: number; observation_calls_remaining: number; session: Session;
}
export type ImportSource = 'chatgpt' | 'claude' | 'gemini' | 'other';
export interface ImportedConversation {
  id: string; source: ImportSource; redactions: number;
  steps_extracted: number; steps_blocked: number; created_at: string;
}
export interface ImportAccepted {
  task: Task; session: Session; operation_id: string; imported: ImportedConversation;
}
export interface Receipt { id: string; status: string; online_purge_due_at: string }
export interface TaskInput { goal: string; category: Category; application_key: string }
export interface GuideApi {
  create(input: TaskInput): Promise<{ task: Task; session: Session }>;
  importConversation(text: string, source: ImportSource): Promise<ImportAccepted>;
  history(): Promise<{ items: { session: Session; task_title: string }[] }>;
  task(id: string): Promise<Task>;
  session(id: string): Promise<Session>;
  upload(task: Task, session: Session, file: Blob, replaces?: Screenshot): Promise<{ screenshot: Screenshot; session: Session }>;
  content(id: string): Promise<Blob>;
  analyze(task: Task, session: Session, screenshot: Screenshot): Promise<{ operation_id: string; session: Session }>;
  requestPlan(task: Task, session: Session): Promise<{ operation_id: string; session: Session }>;
  plan(id: string): Promise<Plan>;
  confirmPlan(plan: Plan, session: Session): Promise<{ plan: Plan; session: Session }>;
  operation(id: string): Promise<Operation>;
  deleteImage(id: string): Promise<Receipt>;
  pause(id: string): Promise<Session>;
  stop(id: string): Promise<Session>;
  start(session: Session): Promise<{ operation_id: string; session: Session }>;
  instruction(id: string): Promise<CurrentInstruction | null>;
  claim(session: Session, stepId: string, statement: string): Promise<Claimed>;
  selfReport(session: Session, stepId: string, claimId: string, said: string): Promise<SelfReported>;
  skipStep(session: Session, stepId: string, reason: 'not_applicable' | 'already_done' | 'cannot_do'): Promise<Skipped>;
  events(id: string, after: number, waitMs: number, signal?: AbortSignal): Promise<GuideEventPage>;
  replan(session: Session, reason: 'stuck' | 'anomaly' | 'user'): Promise<{ operation_id: string; session: Session }>;
  startWatching(session: Session, consentVersion: string): Promise<ObservationState>;
  stopWatching(id: string): Promise<ObservationState>;
  observe(session: Session, imageBase64: string, admittedAt: string, signal?: AbortSignal): Promise<ObservationTick>;
}
