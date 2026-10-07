import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {Client, APIError, TransportError, UncertainDispatch, ValidationError} from '@haltseal/payments-evaluation';
const [origin, matrix, output] = process.argv.slice(2);
const cases = JSON.parse(await fs.readFile(matrix, 'utf8'));
const key = 'fixture-secret-not-for-output';
const results = [];
const stats = async () => (await fetch(origin + '/__test__/stats')).json();
for (const c of cases) {
  const events = [];
  const before = (await stats())[c.id] ?? 0;
  const client = new Client({baseUrl: origin, apiKey: key, timeoutMs: c.timeout_ms ?? 2000,
                             onEvent: event => events.push(event)});
  try {
    const started = performance.now();
    try {
      if (c.kind === 'create') await client.createAttempt('test-obligation', {operationId: c.id, route: 'A', approvalRevision: 1});
      else if (c.kind === 'lookup') await client.lookupOperation(c.id);
      else if (c.kind === 'source') await client.approveSource(c.raw_source ?? JSON.stringify({test_case: c.id}));
      else if (c.kind === 'resume') await client.resume(c.id, {approvalRevision: 1});
      else await client[c.kind](c.id);
      assert.fail('Expected recovery error: ' + c.id);
    } catch (error) {
      assert.ok(error instanceof APIError || error instanceof TransportError, c.id);
      assert.equal(error.constructor.name, c.expected_error, c.id);
      if (c.expected_code) {
        assert.equal(error.code, c.expected_code, c.id);
        assert.ok(performance.now() - started < 800, 'Caller exceeded total deadline');
      }
      const context = error.recovery;
      assert.equal(context.action, c.action, c.id);
      assert.equal(context.request_may_have_executed, !['lookup', 'attempt'].includes(c.kind));
      if (c.kind === 'create') {
        assert.equal(error.operationId, c.id); assert.equal(error.obligationId, 'test-obligation');
      } else if (c.kind !== 'source') assert.equal(context.identity_value, c.id);
      assert.match(context.request_fingerprint, /^[a-f0-9]{64}$/);
      assert.ok(!JSON.stringify({context, events}).includes(key));
      assert.ok(Object.isFrozen(context));
      assert.throws(() => { context.action = 'SEND_AGAIN'; }, TypeError);
      assert.equal(((await stats())[c.id] ?? 0) - before, 1, 'Automatic resend: ' + c.id);
      results.push({id: c.id, error: error.constructor.name, recovery: context, sends: 1});
    }
  } finally { client.close(); }
}
const before = await stats();
const client = new Client({baseUrl: origin, apiKey: key});
for (const options of [{operationId: 'bad\n', route: 'A', approvalRevision: 1},
                       {operationId: 'valid', route: 'D', approvalRevision: 1},
                       {operationId: 'valid', route: 'A', approvalRevision: true}]) {
  assert.throws(() => client.createAttempt('test-obligation', options), ValidationError);
}
client.close(); await assert.rejects(client.attempt('valid'), ValidationError);
for (const baseUrl of ['http://example.com', origin + '/path', 'https://key@example.com'])
  assert.throws(() => new Client({baseUrl, apiKey: key}), ValidationError);
assert.deepEqual(await stats(), before); assert.ok(!Object.hasOwn(before, 'unexpected'));
await fs.writeFile(output, JSON.stringify(results, null, 2) + '\n');
console.log(`PASS: JavaScript ${cases.length} HTTP failure cases, 7 zero-send validation/lifecycle checks.`);
