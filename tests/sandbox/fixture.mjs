/** Fixed, financially inert HTTP fixtures for the published MIT SDKs.
 * This is not the retained payment kernel, a provider adapter or a source verifier.
 * It accepts generated demo identities only and cannot execute money movement.
 */
export const SANDBOX_VERSION = '1.0.0';
export const TTL_MS = 15 * 60 * 1000;
export const MAX_CALLS = 80;
export const OBLIGATION_ID = 'sandbox-cash-4822';
export const OPERATION_IDS = new Set(['demo-original', 'demo-backup', 'demo-stale',
  'demo-replacement', 'demo-after-paid', 'demo-race-1', 'demo-race-2']);
const boundary = {mode: 'local-evaluation', production: 'NO_GO',
  sandbox_profile: 'fixed-http-fixtures', sandbox_version: SANDBOX_VERSION};

export function newSession(now = Date.now()) {
  return {created_at: now, expires_at: now + TTL_MS, calls: 0, approval_revision: 1,
    fixture_closure: false, fixture_paid: false, closure_observed: false,
    attempts: {}, operations: {}, trace: [], synthetic_dispatches: 0,
    lookup_calls: 0, original_lookup_redispatches: 0};
}
function reply(body, status = 200) { return {status, body: {...boundary, ...body}}; }
function error(code, status = 400) { return reply({error: code}, status); }
function exact(value, keys) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every(k => Object.hasOwn(value, k));
}
function amountAvailable(s) {
  return Object.values(s.attempts).some(a => a.ever_paid || a.state !== 'CLOSED') ? 0 : 1000;
}
function record(s, decision, reason, extras = {}) {
  return reply({decision, reason, obligation_id: OBLIGATION_ID,
    available_principal_minor: amountAvailable(s), ...extras});
}
function createRecord(id, route, revision, state) {
  return {attempt_id: id, obligation_id: OBLIGATION_ID, route,
    product_instance_id: 'sandbox-own-account-usd-v1',
    dispatch_intent_recorded: true, source_status: state === 'PAID' ? 'PAID' : 'UNRESOLVED',
    state, execution_outcome: state === 'PAID' ? 'PAID' : 'UNKNOWN', amount_minor: 1000,
    approval_revision: revision, ever_paid: state === 'PAID',
    original_payment_id: 'fixture-' + id, source_evidence_digest: null, closure_profile: null};
}
function historical(s, op) {
  const result = structuredClone(s.operations[op].result);
  if (result.attempt_id) result.attempt = structuredClone(s.attempts[result.attempt_id]);
  return reply({...result, operation_id: op, historical_decision: true, redispatched: false,
    available_principal_minor: amountAvailable(s)});
}
function create(s, body) {
  if (!exact(body, ['operation_id', 'route', 'approval_revision'])
    || !OPERATION_IDS.has(body.operation_id) || !['A', 'B', 'C'].includes(body.route)
    || !Number.isSafeInteger(body.approval_revision) || body.approval_revision < 1) {
    return error('FIXED_DEMO_REQUEST_REQUIRED');
  }
  const {operation_id: op, route, approval_revision: rev} = body;
  const prior = s.operations[op];
  const identity = JSON.stringify([route, rev]);
  if (prior) {
    if (prior.identity !== identity) return record(s, 'HOLD', 'REQUEST_REUSE_MISMATCH', {operation_id: op});
    return historical(s, op);
  }
  let result;
  if (Object.values(s.attempts).some(a => a.ever_paid)) {
    result = record(s, 'REFUSE', 'OBLIGATION_ALREADY_PAID', {operation_id: op});
  } else if (rev !== s.approval_revision) {
    result = record(s, 'HOLD', 'APPROVAL_REVISION_STALE', {operation_id: op});
  } else if (amountAvailable(s) === 0) {
    result = record(s, 'HOLD', 'ORIGINAL_OUTCOME_UNRESOLVED', {operation_id: op});
  } else if (s.closure_observed && rev < 2) {
    result = record(s, 'HOLD', 'FRESH_POSTCLOSURE_APPROVAL_REQUIRED', {operation_id: op});
  } else if (!Object.keys(s.attempts).length && (route !== 'A' || op !== 'demo-original')) {
    return error('START_WITH_DEMO_ORIGINAL');
  } else {
    const id = Object.keys(s.attempts).length ? 'sandbox-replacement' : 'sandbox-original';
    const a = createRecord(id, route, rev, id === 'sandbox-original' ? 'EXPOSED' : 'PAID');
    s.attempts[id] = a;
    s.synthetic_dispatches++;
    result = record(s, 'ACCEPT', 'FIXTURE_EXACT_ATTEMPT_ADMITTED',
      {operation_id: op, attempt_id: id, state: a.state, execution_outcome: a.execution_outcome});
  }
  s.operations[op] = {identity, result: result.body};
  // Persist the original before deliberately withholding its successful reply.
  if (op === 'demo-original' && result.body.decision === 'ACCEPT') {
    return error('FIXTURE_REPLY_WITHHELD_AFTER_COMMIT', 503);
  }
  return result;
}
function action(s, id, verb, body) {
  const a = s.attempts[id];
  if (!a) return error('ATTEMPT_NOT_FOUND', 404);
  if (!exact(body, verb === 'resume' ? ['approval_revision'] : [])) return error('INVALID_REQUEST');
  if (verb === 'resume') {
    if (!Number.isSafeInteger(body.approval_revision) || body.approval_revision < 1) return error('INVALID_REQUEST');
    return record(s, 'HOLD', 'NO_UNSPENT_FIXTURE_FUNDING_STEP', {attempt_id: id, state: a.state});
  }
  if (verb === 'cancel') return record(s, 'HOLD', 'CANCELLATION_IS_NOT_CLOSURE', {attempt_id: id, state: a.state});
  if (id === 'sandbox-original' && a.state !== 'CLOSED' && a.state !== 'PAID') {
    if (s.fixture_paid) {
      Object.assign(a, {state: 'PAID', execution_outcome: 'PAID', ever_paid: true, source_status: 'PAID'});
    } else if (s.fixture_closure) {
      Object.assign(a, {state: 'CLOSED', execution_outcome: 'CLOSED', source_status: 'CLOSED_NO_EFFECT',
        source_evidence_digest: '0'.repeat(64), closure_profile: 'injected-sandbox-no-effect'});
      s.closure_observed = true;
    }
  }
  return record(s, 'OBSERVED', 'FIXTURE_ORIGINAL_OBSERVED', {...structuredClone(a)});
}
function control(s, body) {
  if (!exact(body, ['action'])) return error('INVALID_REQUEST');
  const a = s.attempts['sandbox-original'];
  if (!a) return error('ORIGINAL_REQUIRED', 409);
  if (body.action === 'inject-closure') {
    if (s.fixture_paid || a.ever_paid) return error('PAID_CANNOT_CLOSE_WITHOUT_EFFECT', 409);
    s.fixture_closure = true;
  } else if (body.action === 'inject-paid') {
    if (s.fixture_closure || s.closure_observed) return error('CLOSED_FIXTURE_CANNOT_PAY', 409);
    s.fixture_paid = true;
  } else if (body.action === 'fresh-approval') {
    if (!s.closure_observed) return error('OBSERVE_CLOSURE_FIRST', 409);
    s.approval_revision = 2;
  } else return error('UNKNOWN_FIXTURE_CONTROL');
  return reply({fixture_action: body.action, approval_revision: s.approval_revision,
    available_principal_minor: amountAvailable(s), reason: 'SYNTHETIC_FIXTURE_INJECTED'});
}
export function snapshot(s) {
  return {...boundary, expires_at: new Date(s.expires_at).toISOString(),
    obligation_id: OBLIGATION_ID, amount_minor: 1000, currency: 'USD',
    approval_revision: s.approval_revision, available_principal_minor: amountAvailable(s),
    synthetic_dispatches: s.synthetic_dispatches, original_lookup_redispatches: s.original_lookup_redispatches,
    lookup_calls: s.lookup_calls, calls: s.calls, attempts: Object.values(s.attempts),
    trace: s.trace, scope: 'Fixed HTTP contract fixtures. Not the payment kernel or provider qualification.'};
}
export function execute(s, method, path, body, now = Date.now()) {
  if (now >= s.expires_at) return error('SANDBOX_EXPIRED', 401);
  if (s.calls >= MAX_CALLS) return error('SANDBOX_CALL_LIMIT', 429);
  s.calls++;
  let out;
  const url = new URL(path, 'https://fixture.invalid');
  const p = url.pathname;
  if (method === 'GET' && p === '/sandbox/report' && !url.search) out = reply(snapshot(s));
  else if (method === 'POST' && p === '/sandbox/fixture' && !url.search) out = control(s, body);
  else if (method === 'GET' && p === '/v1/payment-attempts/lookup') {
    const params = [...url.searchParams];
    const op = params.length === 1 && params[0][0] === 'operation_id' ? params[0][1] : null;
    if (!OPERATION_IDS.has(op)) out = error('FIXED_DEMO_OPERATION_REQUIRED');
    else if (!s.operations[op]) out = error('OPERATION_NOT_FOUND', 404);
    else { s.lookup_calls++; out = historical(s, op); }
  } else if (method === 'GET' && p === '/v1/payment-obligations/' + OBLIGATION_ID && !url.search) {
    out = reply({obligation_id: OBLIGATION_ID, amount_minor: 1000,
      available_principal_minor: amountAvailable(s), approval_revision: s.approval_revision,
      approval_status: 'APPROVED', approval_expires_at_ns: String(BigInt(s.expires_at) * 1_000_000n),
      attempts: Object.values(s.attempts)});
  } else if (method === 'POST' && p === '/v1/payment-obligations/' + OBLIGATION_ID + '/attempts' && !url.search) {
    out = create(s, body);
  } else if (method === 'POST' && p === '/v1/payment-obligations') {
    out = error('CUSTOM_SOURCE_IMPORT_UNAVAILABLE_IN_SANDBOX');
  } else {
    const match = /^\/v1\/payment-attempts\/(sandbox-original|sandbox-replacement)(?:\/(recover|cancel|resume))?$/.exec(p);
    if (!match || url.search) out = error('NOT_FOUND', 404);
    else if (method === 'GET' && !match[2]) {
      out = s.attempts[match[1]] ? reply(structuredClone(s.attempts[match[1]])) : error('ATTEMPT_NOT_FOUND', 404);
    } else if (method === 'POST' && match[2]) out = action(s, match[1], match[2], body);
    else out = error('METHOD_NOT_ALLOWED', 405);
  }
  // Unknown URLs may contain visitor input. Retain only fixed fixture paths.
  const tracePath = out.body.error === 'NOT_FOUND' ? '/unsupported' : p;
  s.trace.push({sequence: s.calls, method, path: tracePath, status: out.status,
    decision: out.body.decision ?? null, reason: out.body.reason ?? out.body.error ?? null});
  return out;
}

// Small strict JSON reader: reject duplicate object keys, unsafe/nonfinite numbers
// and deeply nested input before fixed-field validation. Never eval request text.
export function strictJSON(text) {
  let i = 0;
  function ws() { while (i < text.length && /[ \t\r\n]/.test(text[i])) i++; }
  function string() {
    const start = i++;
    while (i < text.length) {
      if (text[i] === '\\') { i += 2; continue; }
      if (text[i++] === '"') return JSON.parse(text.slice(start, i));
    }
    throw new Error('Unterminated string');
  }
  function value(depth = 0) {
    if (depth > 8) throw new Error('Input too deep');
    ws(); const c = text[i];
    if (c === '"') return string();
    if (c === '{') {
      i++; ws(); const out = Object.create(null); const keys = new Set();
      if (text[i] === '}') { i++; return out; }
      while (true) {
        ws(); if (text[i] !== '"') throw new Error('Object key required');
        const key = string(); if (keys.has(key)) throw new Error('Duplicate key'); keys.add(key);
        ws(); if (text[i++] !== ':') throw new Error('Colon required'); out[key] = value(depth + 1); ws();
        if (text[i] === '}') { i++; return out; } if (text[i++] !== ',') throw new Error('Comma required');
      }
    }
    if (c === '[') {
      i++; ws(); const out = []; if (text[i] === ']') { i++; return out; }
      while (true) { out.push(value(depth + 1)); ws(); if (text[i] === ']') { i++; return out; }
        if (text[i++] !== ',') throw new Error('Comma required'); }
    }
    const m = /^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/.exec(text.slice(i));
    if (!m) throw new Error('Invalid JSON'); i += m[0].length; const out = JSON.parse(m[0]);
    if (typeof out === 'number' && (!Number.isFinite(out) || !Number.isSafeInteger(out))) throw new Error('Safe integer required');
    return out;
  }
  const out = value(); ws(); if (i !== text.length) throw new Error('Trailing input'); return out;
}
