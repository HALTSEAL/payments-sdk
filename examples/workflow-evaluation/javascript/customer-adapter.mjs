// Copy outside Git and connect permitted nonproduction application code.
export const adapterKind = 'unconfigured';
const missing = name => { throw new Error('INCOMPLETE: connect '+name); };
export const mapReference = context => missing('shared transaction mapping');
export const original = (client, context) => missing('original execution point');
export const replacement = (client, context) => missing('replacement execution point');
export const recover = (client, context) => missing('exact-original recovery');
export const stop = (client, context, result) => missing('application stop branch');
