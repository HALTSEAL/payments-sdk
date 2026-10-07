import {Client, APIError, UncertainDispatch, type AttemptRecord, type Result,
  type RecoveryContext} from '@haltseal/payments';

async function integration(): Promise<Result> {
  const client = new Client({baseUrl: 'http://127.0.0.1:8799', apiKey: 'synthetic-type-key'});
  try {
    return await client.createAttempt('obligation', {operationId: 'retained-operation', route: 'A', approvalRevision: 1});
  } catch (error: unknown) {
    if (error instanceof UncertainDispatch) {
      const context: RecoveryContext = error.recovery;
      return client.lookupOperation(context.operation_id!, {obligationId: context.obligation_id!});
    }
    if (error instanceof APIError) console.log(error.code);
    throw error;
  } finally { client.close(); }
}

function completeRecord(attempt: AttemptRecord): [string, number, boolean] {
  return [attempt.product_instance_id, attempt.amount_minor, attempt.dispatch_intent_recorded];
}
void integration;
void completeRecord;
