export type Decision = 'ACCEPT' | 'HOLD' | 'REFUSE' | 'REGISTERED' | 'REVOKED' | 'OBSERVED';
export type PaymentState = 'PREPARED' | 'EXPOSED' | 'PENDING' | 'IN_TRANSIT' | 'PAID' | 'CLOSED' | 'FAILED_REVIEW' | 'NEVER_DISPATCHED';
export type ExecutionOutcome = PaymentState | 'UNKNOWN' | 'PREPARED_BLOCKED';
export interface AttemptRecord {
  attempt_id: string; obligation_id: string; route: 'A' | 'B' | 'C';
  state: PaymentState; execution_outcome: ExecutionOutcome;
  amount_minor: number; approval_revision: number; ever_paid: boolean;
  original_payment_id: string | number | null;
  source_evidence_digest: string | null; closure_profile: string | null;
  [key: string]: unknown;
}
export interface Result {
  decision?: Decision; reason?: string; obligation_id?: string; attempt_id?: string;
  execution_outcome?: ExecutionOutcome; state?: PaymentState;
  historical_decision?: boolean; redispatched?: boolean; attempt?: AttemptRecord; attempts?: AttemptRecord[];
  available_principal_minor?: number; approval_revision?: number; approval_expires_at_ns?: string;
  approval_status?: 'APPROVED' | 'REVOKED'; original_payment_id?: string | number | null;
  mode: 'local-evaluation'; production: 'NO_GO'; [key: string]: unknown;
}
export interface RecoveryContext {
  readonly api_origin: string;
  readonly request_kind: string;
  readonly action: 'LOOKUP_OPERATION' | 'LOOKUP_ATTEMPT' | 'REPEAT_READ' | 'REVIEW_SOURCE';
  readonly identity_kind: 'OPERATION_ID' | 'ATTEMPT_ID' | 'OBLIGATION_ID' | 'SOURCE_APPROVAL';
  readonly identity_value: string | null;
  readonly request_fingerprint: string;
  readonly operation_id: string | null;
  readonly attempt_id: string | null;
  readonly obligation_id: string | null;
  readonly approval_revision: number | null;
  readonly request_may_have_executed: boolean;
}
export interface RequestEvent {
  readonly request_kind: string; readonly request_fingerprint: string;
  readonly request_id: string | null; readonly status: number | null;
  readonly result: 'response' | 'api_error' | 'unknown'; readonly duration_ms: number;
}
export class ValidationError extends TypeError {}
export class APIError extends Error {
  code: string; status: number; recovery?: RecoveryContext; requestId?: string | null;
  constructor(code: string, status: number, recovery?: RecoveryContext, requestId?: string | null);
}
export class TransportError extends Error {
  code: string; status: number | null; requestId: string | null;
  recovery: RecoveryContext; operationId: string | null; attemptId: string | null;
  obligationId: string | null; recoveryAction: RecoveryContext['action'];
  identityKind: RecoveryContext['identity_kind']; identityValue: string | null;
  requestFingerprint: string;
}
export class UncertainDispatch extends TransportError {}
export class Client {
  constructor(options: { baseUrl: string; apiKey: string; timeoutMs?: number;
    fetchImpl?: typeof fetch; onEvent?: (event: RequestEvent) => void | Promise<void> });
  close(): void;
  approveSource(signedSourceJson: string): Promise<Result>;
  obligation(id: string): Promise<Result>;
  createAttempt(id: string, options: { operationId: string; route: 'A' | 'B' | 'C'; approvalRevision: number }): Promise<Result>;
  lookupOperation(id: string): Promise<Result>;
  attempt(id: string): Promise<Result>;
  recover(id: string): Promise<Result>;
  cancel(id: string): Promise<Result>;
  resume(id: string, options: { approvalRevision: number }): Promise<Result>;
}
