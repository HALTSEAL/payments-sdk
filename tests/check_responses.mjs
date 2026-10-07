import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {Client, TransportError, UncertainDispatch} from '@haltseal/payments';
const [origin,matrix,output]=process.argv.slice(2);
const {cases}=JSON.parse(await fs.readFile(matrix,'utf8'));
const records=[];
const before=await (await fetch(origin+'/__test__/stats')).json();
const client=new Client({baseUrl:origin,apiKey:'synthetic-response-key'});
try {
  for(const c of cases) {
    const kind=c.kind,value=c.id;let result;
    try {
      if(kind==='create')result=await client.createAttempt('test-obligation',{operationId:value,route:'A',approvalRevision:1});
      else if(kind==='lookup')result=await client.lookupOperation(value,c.bind_obligation?{obligationId:'test-obligation'}:{});
      else if(kind==='source')result=await client.approveSource(JSON.stringify({test_case:value}));
      else if(kind==='resume')result=await client.resume(value,{approvalRevision:1});
      else result=await client[kind](value);
      assert.ok(c.valid,'Accepted corrupt response: '+value);records.push({id:value,result});
    }catch(error){
      assert.ok(!c.valid,'Rejected valid response: '+value);
      const expected=['create','source','resume','recover','cancel'].includes(kind)?UncertainDispatch:TransportError;
      assert.equal(error.constructor,expected,value);assert.equal(error.code,'INVALID_RESPONSE_CONTRACT',value);
      records.push({id:value,error:error.constructor.name,recovery:error.recovery});
    }
  }
  const stats=await (await fetch(origin+'/__test__/stats')).json();
  assert.ok(cases.every(c=>(stats[c.id]??0)-(before[c.id]??0)===1),'Unexpected resend');
}finally{client.close();}
await fs.writeFile(output,JSON.stringify(records,null,2)+'\n');
console.log(`PASS: JavaScript ${cases.length} identity/record response cases.`);
