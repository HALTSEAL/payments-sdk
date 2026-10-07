// Independent contract responses: valid records and deliberately corrupted echoes.
// This server is not a payment kernel and does not move funds.
import http from 'node:http';
import fs from 'node:fs';
const matrix = JSON.parse(fs.readFileSync(new URL('./response-cases.json', import.meta.url), 'utf8'));
const counts = {};
function expand(value, id) {
  if (value === '$case') return id;
  if (Array.isArray(value)) return value.map(v => expand(v, id));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k,v]) => [k,expand(v,id)]));
  return value;
}
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  if (url.pathname === '/__test__/stats') {
    res.writeHead(200, {'Content-Type':'application/json'});res.end(JSON.stringify(counts));return;
  }
  const chunks=[];for await(const c of req)chunks.push(c);
  let body;try{body=JSON.parse(Buffer.concat(chunks).toString());}catch{}
  const id=body?.operation_id??body?.test_case??url.searchParams.get('operation_id')??url.pathname.split('/')[3];
  counts[id]=(counts[id]??0)+1;
  const c=matrix.cases.find(c=>c.id===id);
  if(!c){res.writeHead(404,{'Content-Type':'application/json'});res.end('{"error":"UNKNOWN_TEST_CASE"}');return;}
  const data=expand(structuredClone(matrix.templates[c.template]),id);
  for(const mutation of c.mutations??[]) {
    let owner=data;for(const key of mutation.path.slice(0,-1))owner=owner[key];
    const key=mutation.path.at(-1);
    if(mutation.remove)delete owner[key];else owner[key]=expand(mutation.value,id);
  }
  res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(data));
});
server.listen(0,'127.0.0.1',()=>console.log('http://127.0.0.1:'+server.address().port));
process.on('SIGTERM',()=>server.close());
