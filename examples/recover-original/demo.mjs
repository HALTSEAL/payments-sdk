import fs from 'node:fs/promises';
import {Client, UncertainDispatch} from '@haltseal/payments-evaluation';
const origin = process.argv[2] ?? 'http://127.0.0.1:8799';
async function http(path, body, key) {
  const r = await fetch(origin + path, {method: body === undefined ? 'GET' : 'POST',
    headers: {'Content-Type': 'application/json', ...(key ? {Authorization: 'Bearer ' + key} : {})},
    ...(body !== undefined ? {body: JSON.stringify(body)} : {}), signal: AbortSignal.timeout(15000)});
  const out = await r.json(); if (!r.ok) throw new Error(out.error); return out;
}
const s = await http('/sandbox/session', {});
if (s.sandbox_profile !== 'fixed-http-fixtures') throw new Error('Wrong sandbox profile');
const client = new Client({baseUrl: origin, apiKey: s.api_key, timeoutMs: 15000});
const records = [];
const require = (ok, label) => { if (!ok) throw new Error(label); };
let original;
try { await client.createAttempt(s.obligation_id, {operationId: 'demo-original', route: 'A', approvalRevision: 1});
  throw new Error('Expected the fixture to withhold the successful original reply'); }
catch (e) {
  if (!(e instanceof UncertainDispatch)) throw e;
  require(e.operationId === 'demo-original' && e.recoveryAction === 'LOOKUP_OPERATION', 'Recovery context');
  original = await client.lookupOperation(e.operationId, {obligationId: e.obligationId});
  require(original.historical_decision && !original.redispatched, 'Original lookup');
  records.push({step: 'original lookup after withheld reply', result: original});
}
const backup = await client.createAttempt(s.obligation_id, {operationId: 'demo-backup', route: 'B', approvalRevision: 1});
require(backup.decision === 'HOLD', 'Unknown must hold'); records.push({step: 'unresolved replacement', result: backup});
await http('/sandbox/fixture', {action: 'inject-closure'}, s.api_key);
const closed = await client.recover(original.attempt_id);
require(closed.state === 'CLOSED', 'Closure must be observed'); records.push({step: 'recover injected closure', result: closed});
const stale = await client.createAttempt(s.obligation_id, {operationId: 'demo-stale', route: 'B', approvalRevision: 1});
require(stale.decision === 'HOLD', 'Stale approval must hold'); records.push({step: 'stale approval', result: stale});
await http('/sandbox/fixture', {action: 'fresh-approval'}, s.api_key);
const fresh = await client.createAttempt(s.obligation_id, {operationId: 'demo-replacement', route: 'B', approvalRevision: 2});
require(fresh.decision === 'ACCEPT' && fresh.execution_outcome === 'PAID', 'Fresh replacement');
records.push({step: 'fresh replacement and predefined PAID fixture', result: fresh});
const again = await client.createAttempt(s.obligation_id, {operationId: 'demo-after-paid', route: 'C', approvalRevision: 2});
require(again.decision === 'REFUSE', 'Paid history'); records.push({step: 'paid history', result: again});
const report = await http('/sandbox/report', undefined, s.api_key);
require(report.synthetic_dispatches === 2 && report.original_lookup_redispatches === 0, 'Dispatch counts');
report.sdk_results = records;
await fs.writeFile('javascript-synthetic-result.json', JSON.stringify(report, null, 2) + '\n'); client.close();
console.log('PASS: original lookup; UNKNOWN HOLD; closure; stale HOLD; fresh ACCEPT; PAID REFUSE.');
console.log('Synthetic HTTP fixtures only. No payment kernel, native provider or customer qualification.');
console.log('Record: javascript-synthetic-result.json');
