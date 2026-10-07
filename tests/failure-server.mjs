// Contract fault injection only. No payment kernel or provider implementation.
import http from 'node:http';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
const cases = JSON.parse(fs.readFileSync(new URL('./failure-cases.json', import.meta.url), 'utf8'));
const counts = {};
const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://127.0.0.1');
  if (u.pathname === '/__test__/stats') {
    res.writeHead(200, {'Content-Type': 'application/json'}); res.end(JSON.stringify(counts)); return;
  }
  const chunks = []; for await (const c of req) chunks.push(c);
  const body = Buffer.concat(chunks).toString();
  let parsed; try { parsed = JSON.parse(body); } catch {}
  const id = parsed?.operation_id ?? parsed?.test_case ?? u.searchParams.get('operation_id') ?? u.pathname.split('/')[3];
  counts[id ?? 'unexpected'] = (counts[id ?? 'unexpected'] ?? 0) + 1;
  const c = cases.find(c => c.id === id);
  if (!c) { res.writeHead(404, {'Content-Type': 'application/json'}); res.end('{"error":"UNKNOWN_TEST_CASE"}'); return; }
  if (c.disconnect) { req.socket.destroy(); return; }
  if (c.delay_ms) await new Promise(resolve => setTimeout(resolve, c.delay_ms));
  res.writeHead(c.status, {'Content-Type': 'application/json', 'X-Request-ID': 'fixture-' + id, ...c.headers});
  res.end(c.oversize ? 'x'.repeat(1_048_577) : c.raw ?? JSON.stringify(c.body));
});
server.listen(0, '127.0.0.1', () => console.log('http://127.0.0.1:' + server.address().port));
process.on('SIGTERM', () => server.close());
