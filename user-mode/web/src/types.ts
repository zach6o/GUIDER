export type Category = 'setup' | 'run' | 'debug' | 'understand' | 'test' | 'git_github';
export interface Task {
  id: string; title: string; goal: string; category: Category; application_key: string;
  status: string; current_session_id: string | null; created_at: string; updated_at: string;
}
export interface Session {
  id: string; task_id: string; state: string; state_version: number; control_epoch: number;
  observation_mode: 'screenshot_only' | 'window'; outcome: string | null;
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
  id: string; kind?: 'analyze' | 'plan';
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
export interface Receipt { id: string; status: string; online_purge_due_at: string }
export interface TaskInput { goal: string; category: Category; application_key: string }
export interface GuideApi {
  create(input: TaskInput): Promise<{ task: Task; session: Session }>;
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
}
