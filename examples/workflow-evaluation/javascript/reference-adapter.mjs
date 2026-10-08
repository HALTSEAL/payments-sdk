// Synthetic kit wiring only. This never proves a customer installation.
export const adapterKind = 'reference-fixture';
export const mapReference = context => context.business_reference;
export const original = (client, context) => client.createAttempt(context.obligation_id, {
  operationId: context.operation_id, route: 'A', approvalRevision: context.approval_revision,
});
export const replacement = (client, context) => client.createAttempt(context.obligation_id, {
  operationId: context.operation_id, route: 'B', approvalRevision: context.approval_revision,
});
export const recover = (client, context) => context.recovery_action === 'LOOKUP_OPERATION'
  ? client.lookupOperation(context.operation_id, {obligationId: context.obligation_id})
  : client.recover(context.attempt_id);
export const stop = (client, context, result) => {
  if (!['HOLD', 'REFUSE'].includes(result.decision)) throw new Error('Expected a blocked execution');
  return 'STOP';
};
