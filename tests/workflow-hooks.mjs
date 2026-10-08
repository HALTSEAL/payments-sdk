import test from 'node:test';
import assert from 'node:assert/strict';
import {resolve} from 'node:path';
import {Hooks, loadAdapter} from '../examples/workflow-evaluation/javascript/hooks.mjs';
import * as reference from '../examples/workflow-evaluation/javascript/reference-adapter.mjs';

const context = {obligation_id: 'obl-test', operation_id: 'op-test', route: 'A', approval_revision: 1};
function setup() {
  const adapter = {...reference}, client = {sends: 0,
    createAttempt() { this.sends++; return {decision:'HOLD'}; },
    lookupOperation(op) { return {operation_id:op, redispatched:false}; },
  };
  return {adapter, client, hooks:new Hooks(adapter, client, 'eval:one', 'original')};
}
test('empty template is INCOMPLETE', async () => {
  await assert.rejects(loadAdapter(resolve('examples/workflow-evaluation/javascript/customer-adapter.mjs')), /INCOMPLETE/);
});
test('expected value without a real SDK call is rejected', async () => {
  const {adapter,client,hooks}=setup(); adapter.original=()=>({decision:'HOLD'});
  await assert.rejects(hooks.invoke('original',context), /unchanged SDK/); assert.equal(client.sends,0);
});
test('foreign transaction mapping never sends', async () => {
  const {adapter,client,hooks}=setup(); adapter.mapReference=()=> 'foreign';
  await assert.rejects(hooks.invoke('original',context)); assert.equal(client.sends,0);
});
test('rewritten SDK result is rejected', async () => {
  const {adapter,hooks}=setup();
  adapter.original=async (c,ctx)=>{ await reference.original(c,ctx); return {decision:'ACCEPT'}; };
  await assert.rejects(hooks.invoke('original',context), /changed the observed/);
});
test('recovery send is blocked before dispatch', async () => {
  const {adapter,client,hooks}=setup(); adapter.recover=reference.original;
  await assert.rejects(hooks.invoke('recover',{...context,recovery_action:'LOOKUP_OPERATION'}), /cannot modify/);
  assert.equal(client.sends,0);
});
test('stop send is blocked before dispatch', async () => {
  const {adapter,client,hooks}=setup(); adapter.stop=reference.original;
  await assert.rejects(hooks.invoke('stop',context,{decision:'HOLD'}), /cannot modify/); assert.equal(client.sends,0);
});
test('foreign recovery identity is rejected', async () => {
  const {adapter,hooks}=setup(); adapter.recover=c=>c.lookupOperation('foreign');
  await assert.rejects(hooks.invoke('recover',{...context,recovery_action:'LOOKUP_OPERATION'}), /exact retained/);
});
