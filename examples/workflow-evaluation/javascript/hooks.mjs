// SDK observation only. Direct bank calls and unlisted paths are outside scope.
import {pathToFileURL} from 'node:url';
export const hookNames = ['mapReference', 'original', 'replacement', 'recover', 'stop'];
export async function loadAdapter(path) {
  const adapter = await import(pathToFileURL(path).href);
  if (!['customer-code', 'reference-fixture'].includes(adapter.adapterKind)) throw new Error('INCOMPLETE: adapter is unconfigured');
  if (!hookNames.every(name => typeof adapter[name] === 'function')) throw new Error('INCOMPLETE: missing customer hooks');
  return adapter;
}
export class Hooks {
  constructor(adapter, client, reference, stage) {
    Object.assign(this, {adapter, client, reference, stage, events: []});
  }
  async invoke(hook, context, result) {
    context = {...context, business_reference: this.reference, stage: this.stage};
    const calls = [], outputs = [], target = this.client;
    const canonical = value => JSON.stringify(value, (_, v) => v && typeof v === 'object' && !Array.isArray(v)
      ? Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])) : v);
    const observed = new Proxy(target, {get: (object, name) => {
      const method = object[name];
      if (typeof method !== 'function') return method;
      return async (...args) => {
        const allowed = ['original', 'replacement'].includes(hook) ? ['createAttempt']
          : hook === 'recover' ? ['lookupOperation', 'recover'] : [];
        if (!allowed.includes(name))
          throw new Error('Recovery and stop hooks cannot modify payments');
        if (['createAttempt', 'lookupOperation', 'recover'].includes(name)) calls.push({method: name, args});
        const output = await method.apply(target, args);
        outputs.push(canonical(output));
        return output;
      };
    }});
    const event = {stage: this.stage, hook, operation_id: context.operation_id, calls};
    const checkExecution = () => {
      const expected = {method: 'createAttempt', args: [context.obligation_id, {
        operationId: context.operation_id, route: context.route, approvalRevision: context.approval_revision,
      }]};
      if (calls.length !== 1 || canonical(calls[0]) !== canonical(expected))
        throw new Error('Execution hook must call the unchanged SDK once with the agreed identity');
    };
    try {
      if (await this.adapter.mapReference(context) !== this.reference) throw new Error('Both paths must map the same stable transaction');
      const output = await this.adapter[hook](observed, context, result);
      if (['original', 'replacement'].includes(hook)) checkExecution();
      else if (hook === 'recover') {
        const method = context.recovery_action === 'LOOKUP_OPERATION' ? 'lookupOperation' : 'recover';
        const id = method === 'lookupOperation' ? context.operation_id : context.attempt_id;
        if (calls.length !== 1 || calls[0].method !== method || calls[0].args[0] !== id)
          throw new Error('Recovery hook did not query the exact retained identity');
      } else if (output !== 'STOP' || calls.length) throw new Error('Blocked workflow must stop without another SDK call');
      if (hook !== 'stop' && (outputs.length !== 1 || canonical(output) !== outputs[0]))
        throw new Error('Adapter changed the observed SDK result');
      event.outcome = typeof output === 'object' ? output.decision ?? output.state : output;
      return output;
    } catch (error) {
      if (['original', 'replacement'].includes(hook)) checkExecution();
      event.error_type = error.name;
      throw error;
    } finally { this.events.push(event); }
  }
}
