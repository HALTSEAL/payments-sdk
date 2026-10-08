"""Customer hook scenario client. Run through the scoped engine evaluation kit."""
import concurrent.futures
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hooks import load_adapter, Hooks
from haltseal_payments_sdk import Client, UncertainDispatch


def need(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    stage = os.environ['V2_STAGE']
    previous = json.loads(os.environ.get('V2_PREVIOUS', '{}'))
    c = Client(os.environ['V2_URL'], os.environ['V2_KEY'])
    adapter = load_adapter(os.environ['EVAL_ADAPTER'])
    hooks = Hooks(adapter, c, os.environ['EVAL_REFERENCE'], stage)
    try:
        if stage in {'original', 'presigned', 'replacement', 'paid'}:
            approved = c.approve_source(Path(os.environ['V2_SOURCE']).read_text())
            need(approved['decision'] == 'REGISTERED', 'Signed approval rejected')
            oid = approved['obligation_id']
        else:
            oid = previous['obligation_id']
        def create(op, route='B', revision=1):
            context = {'obligation_id': oid, 'operation_id': 'v2:'+op,
                       'route': route, 'approval_revision': revision}
            if route == 'C':
                # A system probe, not a third customer execution point.
                return c.create_attempt(oid, operation_id='v2:'+op, route=route, approval_revision=revision)
            result = hooks.invoke('original' if route == 'A' else 'replacement', context)
            if result['decision'] in {'HOLD', 'REFUSE'}:
                hooks.invoke('stop', context, result)
            return result
        def lookup_original():
            return hooks.invoke('recover', {'obligation_id': oid, 'operation_id': 'v2:original',
                                'recovery_action': 'LOOKUP_OPERATION'})
        def recover_attempt(aid):
            return hooks.invoke('recover', {'obligation_id': oid, 'attempt_id': aid,
                                'recovery_action': 'LOOKUP_ATTEMPT'})
        if stage == 'original':
            try:
                create('original', 'A')
                raise RuntimeError('Lost HTTP acknowledgement not exercised')
            except UncertainDispatch as exc:
                need(exc.operation_id == 'v2:original' and exc.recovery_action == 'LOOKUP_OPERATION', 'Wrong create recovery identity')
            found = lookup_original()
            need(found['redispatched'] is False, 'Lookup redispatched')
            aid = found['attempt_id']
            blocked = [create('unknown:'+r, r) for r in ['A', 'B', 'C']]
            need(all(r['decision'] == 'HOLD' for r in blocked), 'UNKNOWN released another route')
            need(c.obligation(oid)['available_principal_minor'] == 0, 'UNKNOWN released capacity')
            result = {'obligation_id': oid, 'attempt_id': aid, 'lookup_redispatched': False, 'unknown_routes': ['HOLD']*3}
        elif stage == 'restart':
            found = lookup_original()
            need(found['attempt_id'] == previous['attempt_id'] and found['redispatched'] is False, 'Restart changed the original')
            need(recover_attempt(found['attempt_id'])['state'] == 'PENDING', 'Restart did not observe original')
            need(create('after-restart')['decision'] == 'HOLD', 'Restart released the backup')
            need(c.obligation(oid)['available_principal_minor'] == 0, 'Restart released reserved principal')
            result = {**previous, 'restart_preserved_identity': True}
        elif stage == 'closure':
            aid = previous['attempt_id']
            try:
                c.cancel(aid)
                raise RuntimeError('Lost cancel acknowledgement not exercised')
            except UncertainDispatch as exc:
                need(exc.attempt_id == aid and exc.recovery_action == 'LOOKUP_ATTEMPT', 'Wrong cancel recovery identity')
            observed = recover_attempt(aid)
            need(observed['state'] == 'CLOSED', 'Exact closure not observed')
            need(create('old-approval')['decision'] == 'HOLD', 'Closure reused old approval')
            result = {**previous, 'closure_state': 'CLOSED', 'old_approval': 'HOLD'}
        elif stage == 'presigned':
            rejected = create('presigned', revision=2)
            need(rejected['reason'] == 'APPROVAL_MUST_BE_ISSUED_AFTER_CLOSURE', 'Presigned replacement admitted')
            result = {**previous, 'presigned_approval': 'HOLD'}
        elif stage == 'replacement':
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                contenders = list(pool.map(lambda n: create('race:'+str(n), revision=3), range(8)))
            winners = [r for r in contenders if r['decision'] == 'ACCEPT']
            need(len(winners) == 1 and all(r['decision'] in {'ACCEPT','HOLD'} for r in contenders), 'Race did not conserve authority')
            winner = winners[0]; aid = winner['attempt_id']
            need(winner['execution_outcome'] == 'UNKNOWN', 'Provider reply loss not exercised')
            need(recover_attempt(aid)['state'] == 'EXPOSED', 'Replacement original not recovered')
            try:
                c.resume(aid, approval_revision=3)
                raise RuntimeError('Lost resume acknowledgement not exercised')
            except UncertainDispatch as exc:
                need(exc.attempt_id == aid and exc.recovery_action == 'LOOKUP_ATTEMPT', 'Wrong resume recovery identity')
            need(recover_attempt(aid)['state'] == 'PENDING', 'Funded original not recovered')
            need(c.resume(aid, approval_revision=3)['decision'] == 'HOLD', 'Funding was repeated')
            need(create('third-unknown', 'C', 3)['decision'] == 'HOLD', 'Unknown successor released a third route')
            result = {**previous, 'replacement_attempt_id': aid, 'race_contenders': 8, 'race_winners': 1,
                      'replacement_unknown': True, 'funding_redispatched': False, 'third_route': 'HOLD'}
        elif stage == 'paid':
            need(recover_attempt(previous['replacement_attempt_id'])['state'] == 'PAID', 'Paid replacement not observed')
            decisions = [create('paid:'+r, r, 4)['decision'] for r in ['A','B','C']]
            need(decisions == ['REFUSE']*3, 'Paid history was reminted')
            result = {**previous, 'after_paid_routes': decisions}
        else:
            raise RuntimeError('Unknown stage')
        print(json.dumps({**result, 'adapter_kind': adapter.adapter_kind, 'hook_events': hooks.events}, sort_keys=True))
    finally:
        c.close()


if __name__ == '__main__':
    main()
