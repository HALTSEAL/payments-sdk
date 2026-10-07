import {newSession, execute, snapshot, strictJSON, OBLIGATION_ID, TTL_MS} from './fixture.mjs';

const keyPattern = /^hs_sandbox_[a-f0-9]{32}$/;
const apiPath = p => p.startsWith('/v1/') || ['/sandbox/session', '/sandbox/fixture', '/sandbox/report'].includes(p);
const MAX_BODY = 4096;
const LIMITER = 'sandbox-session-budget-v1';
function json(body, status = 200, requestId = crypto.randomUUID()) {
  return new Response(JSON.stringify(body), {status, headers: {
    'Content-Type': 'application/json', 'Cache-Control': 'no-store',
    'X-Request-ID': requestId, 'X-Content-Type-Options': 'nosniff',
    'X-Robots-Tag': 'noindex, nofollow', 'Referrer-Policy': 'no-referrer',
    'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'"}});
}
async function bodyOf(request) {
  if (request.method !== 'POST') return null;
  if ((request.headers.get('Content-Type') ?? '').split(';')[0].trim().toLowerCase() !== 'application/json') throw new Error('CONTENT_TYPE');
  const length = request.headers.get('Content-Length');
  if (length && (!/^[0-9]+$/.test(length) || Number(length) > MAX_BODY)) throw new Error('BODY_LIMIT');
  const reader = request.body?.getReader(); if (!reader) return null;
  const chunks = []; let size = 0;
  try {
    while (true) { const r = await reader.read(); if (r.done) break; size += r.value.byteLength;
      if (size > MAX_BODY) { await reader.cancel(); throw new Error('BODY_LIMIT'); } chunks.push(r.value); }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const c of chunks) { bytes.set(c, offset); offset += c.byteLength; }
  return strictJSON(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
}
async function digest(value) {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return [...new Uint8Array(bytes)].map(b => b.toString(16).padStart(2, '0')).join('');
}
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!apiPath(url.pathname)) return env.ASSETS.fetch(request);
    if (!env.SDK_SANDBOX) return json({error: 'SANDBOX_NOT_CONFIGURED'}, 503);
    if (url.search && url.pathname !== '/v1/payment-attempts/lookup') return json({error: 'INVALID_QUERY'}, 400);
    const origin = request.headers.get('Origin');
    if (origin && origin !== url.origin) return json({error: 'ORIGIN_NOT_ALLOWED'}, 403);
    if (!['GET', 'POST'].includes(request.method)) return json({error: 'METHOD_NOT_ALLOWED'}, 405);
    let body;
    try { body = await bodyOf(request); } catch (e) {
      return json({error: e.message === 'BODY_LIMIT' ? 'REQUEST_TOO_LARGE' : 'INVALID_JSON_REQUEST'}, e.message === 'BODY_LIMIT' ? 413 : 400);
    }
    if (url.pathname === '/sandbox/session') {
      if (request.method !== 'POST' || !body || typeof body !== 'object' || Array.isArray(body) || Object.keys(body).length) return json({error: 'EMPTY_SESSION_REQUEST_REQUIRED'}, 400);
      const now = Date.now();
      const ip = request.headers.get('CF-Connecting-IP') ?? 'unavailable';
      // Rotate the network identifier daily; retain no raw IP or visitor input.
      const identifier = await digest(Math.floor(now / 86400000) + ':' + ip);
      const budget = env.SDK_SANDBOX.get(env.SDK_SANDBOX.idFromName(LIMITER));
      const accepted = await budget.fetch(new Request('https://internal/budget', {method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({identifier, now})}));
      if (accepted.status !== 200) return accepted;
      const token = 'hs_sandbox_' + crypto.randomUUID().replaceAll('-', '');
      const stub = env.SDK_SANDBOX.get(env.SDK_SANDBOX.idFromName(token));
      const initialized = await stub.fetch(new Request('https://internal/create', {method: 'POST'}));
      if (!initialized.ok) return json({error: 'SANDBOX_START_FAILED'}, 503);
      const initializedRecord = await initialized.json();
      return json({api_origin: url.origin, api_key: token, obligation_id: OBLIGATION_ID,
        approval_revision: 1, expires_at: initializedRecord.expires_at,
        sandbox_profile: 'fixed-http-fixtures', production: 'NO_GO',
        scope: 'Synthetic HTTP fixtures only. No customer records, payment kernel or provider calls.'});
    }
    const token = (request.headers.get('Authorization') ?? '').replace(/^Bearer /, '');
    if (!keyPattern.test(token)) return json({error: 'SANDBOX_KEY_REQUIRED'}, 401);
    const stub = env.SDK_SANDBOX.get(env.SDK_SANDBOX.idFromName(token));
    // The object name identifies the session. No caller can initialize it via API.
    return stub.fetch(new Request('https://internal' + url.pathname + url.search, {
      method: request.method, headers: {'Content-Type': 'application/json'},
      ...(request.method === 'POST' ? {body: JSON.stringify(body)} : {})}));
  },
};

export class SdkSandbox {
  constructor(ctx) { this.ctx = ctx; }
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === '/budget') {
      const {identifier, now} = await request.json();
      const response = await this.ctx.storage.transaction(async tx => {
        let b = await tx.get('budget');
        if (!b || b.day !== Math.floor(now / 86400000)) b = {day: Math.floor(now / 86400000), total: 0, networks: {}};
        const bucket = b.networks[identifier] ?? {hour: Math.floor(now / 3600000), count: 0};
        if (bucket.hour !== Math.floor(now / 3600000)) { bucket.hour = Math.floor(now / 3600000); bucket.count = 0; }
        if (b.total >= 1000 || bucket.count >= 12) return json({error: 'SANDBOX_START_LIMIT'}, 429);
        bucket.count++; b.total++; b.networks[identifier] = bucket;
        await tx.put('budget', b);
        return json({allowed: true});
      });
      await this.ctx.storage.setAlarm((Math.floor(now / 86400000) + 1) * 86400000);
      return response;
    }
    if (url.pathname === '/create') {
      const response = await this.ctx.storage.transaction(async tx => {
        if (await tx.get('session')) return json({error: 'SESSION_EXISTS'}, 409);
        const s = newSession(); await tx.put('session', s);
        return json(snapshot(s));
      });
      if (response.ok) await this.ctx.storage.setAlarm(Date.parse((await response.clone().json()).expires_at));
      return response;
    }
    const body = request.method === 'POST' ? await request.json() : null;
    return this.ctx.storage.transaction(async tx => {
      const s = await tx.get('session'); if (!s) return json({error: 'SANDBOX_SESSION_NOT_FOUND'}, 401);
      const out = execute(s, request.method, url.pathname + url.search, body);
      await tx.put('session', s); return json(out.body, out.status);
    });
  }
  async alarm() {
    const now = Date.now(), s = await this.ctx.storage.get('session'), b = await this.ctx.storage.get('budget');
    // A delayed alarm must not delete a new day's session-start budget.
    const expiry = s?.expires_at ?? (b ? (b.day + 1) * 86400000 : 0);
    if (expiry > now) { await this.ctx.storage.setAlarm(expiry); return; }
    await this.ctx.storage.deleteAll();
  }
}
