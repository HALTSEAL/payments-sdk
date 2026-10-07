import {createHash} from 'node:crypto';
import {isIP} from 'node:net';

const MAX_RESPONSE = 1_048_576;
const MAX_REQUEST = 16_384;
// $ also matches before a trailing newline; assert the absolute end.
const ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}(?![\s\S])/;
const STATES = new Set(['PREPARED','EXPOSED','PENDING','IN_TRANSIT','PAID','CLOSED','FAILED_REVIEW','NEVER_DISPATCHED']);
const DECISIONS = new Set(['ACCEPT','HOLD','REFUSE','REGISTERED','REVOKED','OBSERVED']);
const object = x => x !== null && typeof x === 'object' && !Array.isArray(x);

export class ValidationError extends TypeError {}
export class APIError extends Error {
  constructor(code, status, recovery, requestId) {
    super(code); this.name='APIError'; this.code=code; this.status=status;
    this.recovery=recovery; this.requestId=requestId;
  }
}
export class TransportError extends Error {
  constructor(code, recovery, status, requestId) {
    super('Response unavailable or invalid; follow the retained recovery context. No automatic retry.');
    this.name='TransportError'; this.code=code; this.recovery=recovery;
    this.status=status; this.requestId=requestId;
    this.operationId=recovery.operation_id; this.attemptId=recovery.attempt_id;
    this.obligationId=recovery.obligation_id; this.recoveryAction=recovery.action;
    this.identityKind=recovery.identity_kind; this.identityValue=recovery.identity_value;
    this.requestFingerprint=recovery.request_fingerprint;
  }
}
export class UncertainDispatch extends TransportError {
  constructor(...args) { super(...args); this.name='UncertainDispatch'; }
}
function identifier(value) {
  if(typeof value!=='string' || !ID.test(value)) throw new ValidationError('Identifier must contain 1-128 ASCII identifier characters');
  return value;
}
function revision(value) {
  if(!Number.isSafeInteger(value) || value<1) throw new ValidationError('approvalRevision must be a positive safe integer');
  return value;
}
// Scan key tokens before JSON.parse, including escaped spellings of the same key.
// Original signed source text is never reconstructed from parsed JS numbers.
function strictJSON(raw) {
  const stack=[];
  for(const token of raw.matchAll(/"(?:\\.|[^"\\])*"|[{}\[\],:]/gs)) {
    const t=token[0], top=stack.at(-1);
    if(t[0]==='"' && top?.key) {
      const key=JSON.parse(t);
      if(top.keys.has(key)) throw new Error('Duplicate JSON key');
      top.keys.add(key); top.key=false;
    } else if(t==='{') stack.push({keys:new Set(),key:true});
    else if(t==='[') stack.push({key:false});
    else if(t==='}' || t===']') stack.pop();
    else if(t===',' && top?.keys) top.key=true;
  }
  return JSON.parse(raw,(_key,value)=>{
    if(typeof value==='number' && !Number.isFinite(value)) throw new Error('Nonfinite JSON value');
    return value;
  });
}
function validResult(data, ctx) {
  if(!object(data) || data.mode!=='local-evaluation' || data.production!=='NO_GO') return false;
  for(const key of ['attempt_id','obligation_id']) if(key in data && (typeof data[key]!=='string' || !ID.test(data[key]))) return false;
  if(ctx.obligation_id && 'obligation_id' in data && data.obligation_id!==ctx.obligation_id) return false;
  if(ctx.attempt_id && 'attempt_id' in data && data.attempt_id!==ctx.attempt_id) return false;
  for(const key of ['historical_decision','redispatched','ever_paid','dispatch_intent_recorded'])
    if(key in data && typeof data[key]!=='boolean') return false;
  if(['create_attempt','lookup_operation'].includes(ctx.request_kind) && data.historical_decision===true && data.redispatched!==false) return false;
  for(const key of ['amount_minor','maximum_source_debit_minor','available_principal_minor','approval_revision'])
    if(key in data && (!Number.isSafeInteger(data[key]) || data[key]<0 || key==='approval_revision' && data[key]<1)) return false;
  if('decision' in data && !DECISIONS.has(data.decision)) return false;
  if('state' in data && !STATES.has(data.state)) return false;
  if('execution_outcome' in data && !['UNKNOWN','PREPARED_BLOCKED'].includes(data.execution_outcome) && !STATES.has(data.execution_outcome)) return false;
  if('reason' in data && typeof data.reason!=='string') return false;
  const validAttempt=a=>object(a) && typeof a.attempt_id==='string' && ID.test(a.attempt_id) &&
    typeof a.obligation_id==='string' && ID.test(a.obligation_id) &&
    (!ctx.obligation_id || a.obligation_id===ctx.obligation_id) && STATES.has(a.state) &&
    validResult({...a,mode:'local-evaluation',production:'NO_GO'},
      {...ctx,request_kind:'attempt',attempt_id:a.attempt_id,obligation_id:null});
  switch(ctx.request_kind) {
    case 'approve_source': return ['REGISTERED','REVOKED','HOLD','REFUSE'].includes(data.decision) &&
      (!['REGISTERED','REVOKED'].includes(data.decision) || typeof data.obligation_id==='string');
    case 'obligation': return data.obligation_id===ctx.obligation_id && Array.isArray(data.attempts) && data.attempts.every(validAttempt);
    case 'attempt': return data.attempt_id===ctx.attempt_id && STATES.has(data.state);
    case 'lookup_operation': return data.historical_decision===true && data.redispatched===false &&
      ['ACCEPT','HOLD','REFUSE'].includes(data.decision) && (data.decision!=='ACCEPT' || 'attempt_id' in data) && (!data.attempt_id ||
      validAttempt(data.attempt) && data.attempt.attempt_id===data.attempt_id);
    case 'create_attempt': return ['ACCEPT','HOLD','REFUSE'].includes(data.decision) &&
      (data.decision!=='ACCEPT' || typeof data.attempt_id==='string' && 'execution_outcome' in data);
    default: return ['recover','cancel','resume'].includes(ctx.request_kind) &&
      ['HOLD','REFUSE','OBSERVED'].includes(data.decision) &&
      (data.decision!=='OBSERVED' || data.attempt_id===ctx.attempt_id && STATES.has(data.state));
  }
}
function withAbort(promise, signal) {
  return new Promise((resolve,reject)=>{
    const abort=()=>reject(new Error('Deadline exceeded'));
    if(signal.aborted) return abort();
    signal.addEventListener('abort',abort,{once:true});
    Promise.resolve(promise).then(resolve,reject).finally(()=>signal.removeEventListener('abort',abort));
  });
}
function cancelBody(body) {
  // Transport cleanup must never replace a verdict or retained recovery error.
  try { Promise.resolve(body.cancel()).catch(()=>{}); } catch {}
}
async function boundedBody(response, signal) {
  const length=response.headers.get('content-length');
  if(length!==null && (!/^[0-9]+$/.test(length) || Number(length)>MAX_RESPONSE)) throw new Error('Invalid or oversized response length');
  if(!response.body || typeof response.body.getReader!=='function') throw new Error('Readable response body required');
  const reader=response.body.getReader(), chunks=[]; let size=0;
  try {
    while(true) {
      const {done,value}=await withAbort(reader.read(),signal);
      if(done) break;
      size+=value.byteLength;
      if(size>MAX_RESPONSE) throw new Error('Oversized response');
      chunks.push(value);
    }
    if(length!==null && size!==Number(length)) throw new Error('Incomplete response');
    const bytes=new Uint8Array(size); let offset=0;
    for(const chunk of chunks) { bytes.set(chunk,offset); offset+=chunk.byteLength; }
    return new TextDecoder('utf-8',{fatal:true}).decode(bytes);
  } catch(error) {
    cancelBody(reader);
    throw error;
  } finally { try { reader.releaseLock(); } catch {} }
}
export class Client {
  constructor({baseUrl,apiKey,timeoutMs=30000,fetchImpl=globalThis.fetch,onEvent}) {
    if(typeof baseUrl!=='string' || !/^https?:\/\//i.test(baseUrl) || /[\u0000-\u0020\\?#]/.test(baseUrl) ||
      !baseUrl.match(/^https?:\/\/([^/?#]+)/i) ||
      baseUrl.match(/^https?:\/\/([^/?#]*)/i)?.[1].includes('@')) throw new ValidationError('A complete origin without credentials is required');
    let u;
    try { u=new URL(baseUrl); } catch { throw new ValidationError('Invalid origin'); }
    const authority=baseUrl.match(/^https?:\/\/([^/?#]*)/i)[1];
    const literalHost=authority.startsWith('[')?authority.slice(1,authority.indexOf(']')):authority.split(':',1)[0];
    const loopback=isIP(literalHost)===6?u.hostname==='[::1]':isIP(literalHost)===4 && literalHost.split('.')[0]==='127';
    if(!['http:','https:'].includes(u.protocol) || (u.protocol==='http:' && !loopback) ||
      u.username || u.password || u.search || u.hash || u.pathname!=='/' || u.port==='0') throw new ValidationError('Use an HTTPS origin or literal loopback HTTP origin without credentials or a path');
    if(typeof apiKey!=='string' || !apiKey || /[^\x21-\x7e]/.test(apiKey)) throw new ValidationError('A nonempty ASCII API key without whitespace is required');
    if(!Number.isSafeInteger(timeoutMs) || timeoutMs<1 || timeoutMs>2_147_483_647) throw new ValidationError('timeoutMs must be a positive integer within timer limits');
    if(typeof fetchImpl!=='function' || (onEvent!==undefined && typeof onEvent!=='function')) throw new ValidationError('Invalid transport or event callback');
    this.baseUrl=u.origin; this.apiKey=apiKey; this.timeoutMs=timeoutMs;
    this.fetchImpl=fetchImpl; this.onEvent=onEvent; this.closed=false;
  }
  close() { this.closed=true; }
  async request(method,path,body,kind,identity={}) {
    if(this.closed) throw new ValidationError('Client is closed');
    const serialized=body===undefined?undefined:typeof body==='string'?body:JSON.stringify(body,Object.keys(body).sort());
    if(serialized!==undefined && Buffer.byteLength(serialized)>MAX_REQUEST) throw new ValidationError('Request exceeds the API 16 KiB limit');
    const fingerprint=createHash('sha256').update(method+'\n'+path+'\n'+(serialized||'')).digest('hex');
    const op=identity.operation_id, aid=identity.attempt_id, oid=identity.obligation_id;
    const ctx=Object.freeze({api_origin:this.baseUrl,request_kind:kind,
      action:method==='GET'?'REPEAT_READ':op?'LOOKUP_OPERATION':aid?'LOOKUP_ATTEMPT':'REVIEW_SOURCE',
      identity_kind:op?'OPERATION_ID':aid?'ATTEMPT_ID':oid?'OBLIGATION_ID':'SOURCE_APPROVAL',
      identity_value:op||aid||oid||null,request_fingerprint:fingerprint,
      operation_id:op||null,attempt_id:aid||null,obligation_id:oid||null,
      approval_revision:identity.approval_revision??null,request_may_have_executed:method==='POST'});
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),this.timeoutMs);
    const started=performance.now(); let status=null, requestId=null, resultKind='unknown', response;
    const failure=code=>new (method==='POST'?UncertainDispatch:TransportError)(code,ctx,status,requestId);
    try {
      response=await withAbort(this.fetchImpl(this.baseUrl+path,{method,redirect:'manual',signal:controller.signal,
        headers:{Authorization:'Bearer '+this.apiKey,Accept:'application/json','Content-Type':'application/json'},
        body:serialized}),controller.signal);
      status=response.status;
      const trace=response.headers.get('x-request-id');
      requestId=trace && /^[A-Za-z0-9_.:-]{1,128}$/.test(trace)?trace:null;
      if(response.redirected || (response.url && response.url!==this.baseUrl+path) || status>=300 && status<400) {
        if(method==='POST') throw failure('REDIRECT_REFUSED');
        throw new APIError('REDIRECT_REFUSED',status,ctx,requestId);
      }
      if(status>=500 || [408,429].includes(status)) throw failure('HTTP_'+status);
      if(response.headers.get('content-type')?.split(';',1)[0].trim().toLowerCase()!=='application/json') throw failure('INVALID_CONTENT_TYPE');
      const data=strictJSON(await boundedBody(response,controller.signal));
      if(status>=400) {
        if(!object(data) || typeof data.error!=='string' || !/^[A-Z0-9_]{1,128}$/.test(data.error)) throw failure('INVALID_ERROR_RESPONSE');
        throw new APIError(data.error,status,ctx,requestId);
      }
      if(status!==200 || !validResult(data,ctx)) throw failure('INVALID_RESPONSE_CONTRACT');
      resultKind='response'; return data;
    } catch(error) {
      if(error instanceof APIError && error.recovery===ctx) { resultKind='api_error'; throw error; }
      if(error instanceof TransportError && error.recovery===ctx) throw error;
      throw failure('TRANSPORT_OR_RESPONSE_UNCERTAIN');
    } finally {
      clearTimeout(timer);
      try {
        if(response?.body && !response.body.locked) cancelBody(response.body);
      } catch {}
      if(this.onEvent) {
        const event=Object.freeze({request_kind:kind,request_fingerprint:fingerprint,request_id:requestId,
          status,result:resultKind,duration_ms:Math.round((performance.now()-started)*1000)/1000});
        try { Promise.resolve(this.onEvent(event)).catch(()=>{}); } catch {}
      }
    }
  }
  approveSource(signedSourceJson) {
    if(typeof signedSourceJson!=='string') throw new ValidationError('Original signed source JSON string required');
    let parsed;
    try { parsed=strictJSON(signedSourceJson); } catch { throw new ValidationError('Original signed source JSON required'); }
    if(!object(parsed)) throw new ValidationError('Signed source envelope object required');
    return this.request('POST','/v1/payment-obligations',signedSourceJson,'approve_source');
  }
  obligation(id) { identifier(id); return this.request('GET','/v1/payment-obligations/'+encodeURIComponent(id),undefined,'obligation',{obligation_id:id}); }
  createAttempt(id,{operationId,route,approvalRevision}) {
    identifier(id); identifier(operationId); identifier(route); revision(approvalRevision);
    if(!['A','B','C'].includes(route)) throw new ValidationError('route must be A, B or C in this evaluation profile');
    return this.request('POST','/v1/payment-obligations/'+encodeURIComponent(id)+'/attempts',
      {operation_id:operationId,route,approval_revision:approvalRevision},'create_attempt',
      {operation_id:operationId,obligation_id:id,approval_revision:approvalRevision});
  }
  lookupOperation(id) { identifier(id); return this.request('GET','/v1/payment-attempts/lookup?operation_id='+encodeURIComponent(id),undefined,'lookup_operation',{operation_id:id}); }
  attempt(id) { identifier(id); return this.request('GET','/v1/payment-attempts/'+encodeURIComponent(id),undefined,'attempt',{attempt_id:id}); }
  recover(id) { return this.action('recover',id); }
  cancel(id) { return this.action('cancel',id); }
  resume(id,{approvalRevision}) { return this.action('resume',id,revision(approvalRevision)); }
  action(kind,id,rev) {
    identifier(id);
    return this.request('POST','/v1/payment-attempts/'+encodeURIComponent(id)+'/'+kind,
      kind==='resume'?{approval_revision:rev}:{},kind,{attempt_id:id,approval_revision:rev});
  }
}
