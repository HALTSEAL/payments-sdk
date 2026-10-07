#!/usr/bin/env node
/** Explicit synthetic exercise. Application Client calls never start this demo. */
import fs from 'node:fs/promises';
import {Client, UncertainDispatch} from './index.mjs';

const HOSTED_ORIGIN = 'https://haltseal.com';
const MAX_RESPONSE = 1_048_576;
const require = (ok, label) => { if (!ok) throw new Error(label); };

function fixtureOrigin(value) {
  value = value.replace(/\/+$/, '');
  if (value === HOSTED_ORIGIN) return value;
  const match = /^http:\/\/(?:127\.0\.0\.1|\[::1\]):([0-9]{1,5})$/.exec(value);
  require(match && Number(match[1]) >= 1 && Number(match[1]) <= 65535, 'Literal loopback fixture origin required');
  return value;
}

async function http(origin, path, body, key) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  let reader;
  try {
    const response = await fetch(origin + path, {
      method: body === undefined ? 'GET' : 'POST', redirect: 'error', signal: controller.signal,
      headers: {'Content-Type': 'application/json', Accept: 'application/json', ...(key ? {Authorization: 'Bearer ' + key} : {})},
      ...(body === undefined ? {} : {body: JSON.stringify(body)}),
    });
    require(response.status === 200 && response.headers.get('content-type')?.split(';')[0].trim() === 'application/json', 'Fixture JSON response required');
    reader = response.body.getReader();
    const parts = []; let size = 0;
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      size += value.byteLength; require(size <= MAX_RESPONSE, 'Fixture response limit exceeded'); parts.push(value);
    }
    const bytes = new Uint8Array(size); let offset = 0;
    for (const part of parts) {bytes.set(part, offset); offset += part.byteLength;}
    const result = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
    require(result && typeof result === 'object' && !Array.isArray(result), 'Fixture object required');
    return result;
  } finally {
    clearTimeout(timer); controller.abort();
    if (reader) {try {await reader.cancel();} catch {} reader.releaseLock();}
  }
}

async function exercise(origin) {
  const session = await http(origin, '/sandbox/session', {});
  require(session.sandbox_profile === 'fixed-http-fixtures' && session.production === 'NO_GO'
    && session.api_origin === origin && /^hs_sandbox_[a-f0-9]{32}$/.test(session.api_key)
    && typeof session.obligation_id === 'string', 'Fixed synthetic session required');
  const client = new Client({baseUrl: origin, apiKey: session.api_key, timeoutMs: 15000});
  const results = [];
  const retain = (step, result, condition) => {require(condition, 'Unexpected synthetic recovery result'); results.push({step, result});};
  try {
    let original;
    try {
      await client.createAttempt(session.obligation_id, {operationId: 'demo-original', route: 'A', approvalRevision: 1});
      throw new Error('Expected a withheld original reply');
    } catch (lost) {
      if (!(lost instanceof UncertainDispatch)) throw lost;
      require(lost.operationId === 'demo-original' && lost.recoveryAction === 'LOOKUP_OPERATION', 'Original recovery identity required');
      original = await client.lookupOperation(lost.operationId, {obligationId: lost.obligationId});
      retain('original lookup after withheld reply', original,
        original.historical_decision === true && original.redispatched === false && original.execution_outcome === 'UNKNOWN');
    }
    const backup = await client.createAttempt(session.obligation_id, {operationId: 'demo-backup', route: 'B', approvalRevision: 1});
    retain('unresolved replacement', backup, backup.decision === 'HOLD');
    await http(origin, '/sandbox/fixture', {action: 'inject-closure'}, session.api_key);
    const closed = await client.recover(original.attempt_id);
    retain('recover injected closure', closed, closed.state === 'CLOSED');
    const stale = await client.createAttempt(session.obligation_id, {operationId: 'demo-stale', route: 'B', approvalRevision: 1});
    retain('stale approval', stale, stale.decision === 'HOLD');
    await http(origin, '/sandbox/fixture', {action: 'fresh-approval'}, session.api_key);
    const fresh = await client.createAttempt(session.obligation_id, {operationId: 'demo-replacement', route: 'B', approvalRevision: 2});
    retain('fresh replacement and predefined PAID fixture', fresh, fresh.decision === 'ACCEPT' && fresh.execution_outcome === 'PAID');
    const again = await client.createAttempt(session.obligation_id, {operationId: 'demo-after-paid', route: 'C', approvalRevision: 2});
    retain('paid history', again, again.decision === 'REFUSE');
    const report = await http(origin, '/sandbox/report', undefined, session.api_key);
    require(report.synthetic_dispatches === 2 && report.original_lookup_redispatches === 0, 'Unexpected synthetic dispatch counts');
    const metadata = JSON.parse(await fs.readFile(new URL('./package.json', import.meta.url), 'utf8'));
    Object.assign(report, {sdk_results: results, sdk_version: metadata.version, sdk_package: metadata.name});
    const encoded = JSON.stringify(report);
    require(!encoded.includes(session.api_key) && !encoded.includes('"api_key"'), 'Credential-free report required');
    return report;
  } finally {client.close();}
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length === 1 && ['--help', '-h'].includes(args[0])) {
    console.log('haltseal-payments-demo [--output NEW_FILE.json] [--origin http://127.0.0.1:PORT]');
    console.log('Default: https://haltseal.com. Fixed synthetic fixtures, no real funds.'); return;
  }
  let origin = HOSTED_ORIGIN, output;
  for (let i = 0; i < args.length; i += 2) {
    require(i + 1 < args.length && ['--origin', '--output'].includes(args[i]), 'Invalid demo arguments');
    if (args[i] === '--origin') origin = args[i + 1]; else output = args[i + 1];
  }
  origin = fixtureOrigin(origin);
  if (output) {
    try {await fs.lstat(output); throw new Error('Choose a new output file');}
    catch (error) {if (error.code !== 'ENOENT') throw error;}
  }
  const report = await exercise(origin);
  if (output) await fs.writeFile(output, JSON.stringify(report, null, 2) + '\n', {flag: 'wx', mode: 0o600});
  console.log('PASS: original lookup; UNKNOWN HOLD; closure; stale HOLD; fresh ACCEPT; PAID REFUSE.');
  console.log('Synthetic dispatches: 2. Original lookup redispatches: 0.');
  console.log('Fixed synthetic HTTP fixtures. No real funds or production qualification.');
  if (output) console.log('Record: ' + output);
  console.log('Next: https://haltseal.com/pricing/#workflow');
}

main().catch(() => {
  console.error('Sandbox exercise stopped. Keep the original identity; an unavailable reply grants no replacement.');
  process.exitCode = 1;
});
