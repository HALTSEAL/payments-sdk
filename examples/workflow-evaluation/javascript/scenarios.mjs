// Customer hook scenario client. Run through the scoped engine kit.
import {readFileSync} from 'node:fs';
import {Client, UncertainDispatch} from '@haltseal/payments';

import {Hooks, loadAdapter} from './hooks.mjs';
const adapter = await loadAdapter(process.env.EVAL_ADAPTER);
const need = (value, message) => { if (!value) throw new Error(message); };
const stage = process.env.V2_STAGE;
const previous = JSON.parse(process.env.V2_PREVIOUS || '{}');
const c = new Client({baseUrl: process.env.V2_URL, apiKey: process.env.V2_KEY});
const hooks = new Hooks(adapter, c, process.env.EVAL_REFERENCE, stage);
try {
  let oid;
  if (['original', 'presigned', 'replacement', 'paid'].includes(stage)) {
    // Keep signed nanosecond integers in their original JSON text.
    const approved = await c.approveSource(readFileSync(process.env.V2_SOURCE, 'utf8'));
    need(approved.decision === 'REGISTERED', 'Signed approval rejected');
    oid = approved.obligation_id;
  } else oid = previous.obligation_id;
  const create = async (op, route='B', revision=1) => {
    const context = {obligation_id: oid, operation_id: 'v2:'+op, route, approval_revision: revision};
    if (route === 'C') return c.createAttempt(oid, {operationId:'v2:'+op, route, approvalRevision:revision});
    const result = await hooks.invoke(route === 'A' ? 'original' : 'replacement', context);
    if (['HOLD', 'REFUSE'].includes(result.decision)) await hooks.invoke('stop', context, result);
    return result;
  };
  const lookupOriginal = () => hooks.invoke('recover', {obligation_id: oid,
    operation_id: 'v2:original', recovery_action: 'LOOKUP_OPERATION'});
  const recoverAttempt = aid => hooks.invoke('recover', {obligation_id: oid,
    attempt_id: aid, recovery_action: 'LOOKUP_ATTEMPT'});
  let result;
  if (stage === 'original') {
    try { await create('original', 'A'); throw new Error('Lost acknowledgement not exercised'); }
    catch (e) { need(e instanceof UncertainDispatch && e.operationId === 'v2:original' && e.recoveryAction === 'LOOKUP_OPERATION', 'Wrong create recovery identity'); }
    const found = await lookupOriginal();
    need(found.redispatched === false, 'Lookup redispatched');
    for (const route of ['A','B','C']) need((await create('unknown:'+route,route)).decision === 'HOLD', 'UNKNOWN released another route');
    need((await c.obligation(oid)).available_principal_minor === 0, 'UNKNOWN released capacity');
    result = {obligation_id:oid, attempt_id:found.attempt_id, lookup_redispatched:false, unknown_routes:['HOLD','HOLD','HOLD']};
  } else if (stage === 'restart') {
    const found = await lookupOriginal();
    need(found.attempt_id === previous.attempt_id && found.redispatched === false, 'Restart changed original');
    need((await recoverAttempt(found.attempt_id)).state === 'PENDING', 'Restart did not observe original');
    need((await create('after-restart')).decision === 'HOLD', 'Restart released backup');
    need((await c.obligation(oid)).available_principal_minor === 0, 'Restart released reserved principal');
    result = {...previous, restart_preserved_identity:true};
  } else if (stage === 'closure') {
    try { await c.cancel(previous.attempt_id); throw new Error('Lost cancel acknowledgement not exercised'); }
    catch (e) { need(e instanceof UncertainDispatch && e.attemptId === previous.attempt_id && e.recoveryAction === 'LOOKUP_ATTEMPT', 'Wrong cancel recovery identity'); }
    need((await recoverAttempt(previous.attempt_id)).state === 'CLOSED', 'Exact closure not observed');
    need((await create('old-approval')).decision === 'HOLD', 'Closure reused old approval');
    result = {...previous, closure_state:'CLOSED', old_approval:'HOLD'};
  } else if (stage === 'presigned') {
    need((await create('presigned','B',2)).reason === 'APPROVAL_MUST_BE_ISSUED_AFTER_CLOSURE', 'Presigned replacement admitted');
    result = {...previous, presigned_approval:'HOLD'};
  } else if (stage === 'replacement') {
    const contenders = await Promise.all(Array.from({length:8},(_,i)=>create('race:'+i,'B',3)));
    const winners = contenders.filter(r=>r.decision==='ACCEPT');
    need(winners.length === 1 && contenders.every(r=>['ACCEPT','HOLD'].includes(r.decision)), 'Race did not conserve authority');
    const aid = winners[0].attempt_id;
    need(winners[0].execution_outcome === 'UNKNOWN', 'Provider reply loss not exercised');
    need((await recoverAttempt(aid)).state === 'EXPOSED', 'Replacement original not recovered');
    try { await c.resume(aid,{approvalRevision:3}); throw new Error('Lost resume acknowledgement not exercised'); }
    catch (e) { need(e instanceof UncertainDispatch && e.attemptId === aid && e.recoveryAction === 'LOOKUP_ATTEMPT', 'Wrong resume recovery identity'); }
    need((await recoverAttempt(aid)).state === 'PENDING', 'Funded original not recovered');
    need((await c.resume(aid,{approvalRevision:3})).decision === 'HOLD', 'Funding was repeated');
    need((await create('third-unknown','C',3)).decision === 'HOLD', 'Successor released third route');
    result = {...previous, replacement_attempt_id:aid, race_contenders:8, race_winners:1,
              replacement_unknown:true, funding_redispatched:false, third_route:'HOLD'};
  } else if (stage === 'paid') {
    need((await recoverAttempt(previous.replacement_attempt_id)).state === 'PAID', 'Paid replacement not observed');
    const decisions = [];
    for (const route of ['A','B','C']) decisions.push((await create('paid:'+route,route,4)).decision);
    need(decisions.every(r=>r==='REFUSE'), 'Paid history was reminted');
    result = {...previous, after_paid_routes:decisions};
  } else throw new Error('Unknown stage');
  process.stdout.write(JSON.stringify({...result, adapter_kind: adapter.adapterKind, hook_events: hooks.events})+'\n');
} finally { await c.close(); }
