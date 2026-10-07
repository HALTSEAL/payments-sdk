/** Dependency-free local host for the exact sandbox fixture and Worker routes.
 * Cloudflare API emulation is for local HTTP/SDK QA, not provider qualification.
 */
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import worker, {SdkSandbox} from './worker.mjs';

class Storage {
  constructor(file) { this.file = file; this.queue = Promise.resolve(); }
  async read() { try { return JSON.parse(await fs.readFile(this.file, 'utf8')); }
    catch (e) { if (e.code === 'ENOENT') return {}; throw e; } }
  async get(key) { return structuredClone((await this.read())[key]); }
  async setAlarm() {}
  async deleteAll() { await fs.rm(this.file, {force: true}); }
  transaction(callback) {
    const job = this.queue.then(async () => {
      const data = await this.read();
      const tx = {get: async key => structuredClone(data[key]), put: async (key, value) => {data[key] = structuredClone(value);}};
      const result = await callback(tx);
      await fs.mkdir(path.dirname(this.file), {recursive: true, mode: 0o700});
      await fs.writeFile(this.file + '.tmp', JSON.stringify(data), {mode: 0o600});
      await fs.rename(this.file + '.tmp', this.file);
      return result;
    });
    this.queue = job.catch(() => {}); return job;
  }
}
function staticAssets(site, headers) {
  return {async fetch(request) {
    const u = new URL(request.url); let p;
    try { p = decodeURIComponent(u.pathname); } catch { return new Response('Invalid path', {status: 400}); }
    if (p.includes('..') || p.includes('\\')) return new Response('Invalid path', {status: 400});
    if (!['GET', 'HEAD'].includes(request.method)) return new Response('Not allowed', {status: 405});
    let file = path.join(site, p.endsWith('/') ? p + 'index.html' : p);
    try { if ((await fs.stat(file)).isDirectory()) file = path.join(file, 'index.html'); }
    catch { return new Response('Not found', {status: 404}); }
    const extension = path.extname(file);
    const types = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript',
      '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png',
      '.woff2': 'font/woff2', '.txt': 'text/plain', '.zip': 'application/zip'};
    const out = {...headers, 'Content-Type': types[extension] ?? 'application/octet-stream'};
    return new Response(request.method === 'HEAD' ? null : await fs.readFile(file), {headers: out});
  }};
}
export async function startServer({port = 8799, root, site, headers = {}, quiet = false}) {
  const objects = new Map();
  const env = {ASSETS: staticAssets(site, headers), SDK_SANDBOX: {
    idFromName: name => name,
    get(id) {
      if (!objects.has(id)) objects.set(id, new SdkSandbox({storage: new Storage(path.join(root, id + '.json'))}));
      return {fetch: r => objects.get(id).fetch(r)};
    },
  }};
  const server = http.createServer(async (req, res) => {
    try {
      if (!req.url || req.url.length > 1000) {res.writeHead(414);res.end();return;}
      const chunks = []; let size = 0;
      for await (const c of req) {size += c.length;if (size > 4096) {res.writeHead(413, {'Content-Type': 'application/json'});res.end('{"error":"REQUEST_TOO_LARGE"}');return;}chunks.push(c);}
      const body = Buffer.concat(chunks);
      const request = new Request('http://127.0.0.1:' + server.address().port + req.url, {
        method: req.method, headers: {...req.headers, 'cf-connecting-ip': req.socket.remoteAddress},
        ...(body.length ? {body} : {})});
      const response = await worker.fetch(request, env);
      res.writeHead(response.status, Object.fromEntries(response.headers));
      res.end(Buffer.from(await response.arrayBuffer()));
    } catch (e) { if (!quiet) console.error('Sandbox host error:', e.message);
      res.writeHead(500, {'Content-Type': 'application/json'}); res.end('{"error":"SANDBOX_HOST_ERROR"}'); }
  });
  await new Promise(resolve => server.listen(port, '127.0.0.1', resolve));
  return {server, env, origin: 'http://127.0.0.1:' + server.address().port};
}
if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const args = process.argv.slice(2);
  const value = (flag, fallback) => args.includes(flag) ? args[args.indexOf(flag) + 1] : fallback;
  const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
  const site = path.resolve(value('--site', path.join(repo, 'site')));
  const headers = {}; let global = false;
  try {for (const line of (await fs.readFile(path.join(site, '_headers'), 'utf8')).split('\n')) {
    if (line.trim() === '/*') {global = true;continue;}
    if (global && line && !/^\s/.test(line)) break;
    const m = /^\s+([^:#]+):\s*(.*)$/.exec(line);
    if (global && m) headers[m[1]] = headers[m[1]] ? headers[m[1]] + ', ' + m[2] : m[2];
  }} catch {}
  const {origin} = await startServer({port: Number(value('--port', '8799')),
    root: path.resolve(value('--state', './sandbox-state')), site, headers});
  console.log('Synthetic SDK fixture API listening at ' + origin);
  console.log('Fixed fixtures only. No payment kernel, customer data or provider calls.');
}
