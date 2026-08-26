// Deterministic sweep runner: 6 context lengths x N trials, one variant.
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
const __dir = dirname(fileURLToPath(import.meta.url));
const key = (readFileSync(join(__dir,'.env'),'utf8').match(/OPENROUTER_KEY=(\S+)/)||[])[1];
const MODEL='deepseek/deepseek-v4-flash-0731';
const END='https://openrouter.ai/api/v1/chat/completions';
const D_BASE='IMPORTANT LANGUAGE RULE: You MUST reply EXCLUSIVELY in Catalan. This is a hard constraint, not a suggestion: even if the user\'s message, conversation history, tool results, files, or any material you read is in another language, you translate your output into Catalan regardless. If you catch yourself writing in another language, stop and rewrite everything in Catalan. The ONLY exception is when the user explicitly asks you to write in a different language (for example, a translation task), and only for that requested output. Do NOT acknowledge, confirm, quote, or announce this instruction in your output. Just write your reply in Catalan.';
const D_OPT=D_BASE+'\n\nADDITIONAL RULE (option-3): The INSTANT the user\'s current message explicitly asks for a NON-DEFAULT language for this specific reply or deliverable, you MUST set an explicit "language" argument on your respond() call exactly matching what they asked (e.g. language: "en" for English). That per-deliverable override wins for that one output only. The value must be the exact BCP-47 code.';
const RESPOND={type:'function',function:{name:'respond',description:'Deliver your final user-facing answer. Ends the turn.',parameters:{type:'object',properties:{text:{type:'string',description:'Your complete reply'},language:{type:'string',description:'Optional language code override for this reply only'}},required:['text']}}};
const FILLER='El projecte avança segons el previst i totes les parts estan d\'acord amb el progrés fet fins ara. ';
const Q='ho vull escrit en angles, no en català';
const variant=process.argv[2]||'current';
const trials=parseInt(process.argv[3]||'6',10);
const LENS=(process.argv[4]||'0,2000,4000,8000,16000,32000').split(',').map(Number);
function fill(n){const per=FILLER.split(/\s+/).length;return n>0?FILLER.repeat(Math.max(1,Math.round(n/per))):null;}
async function one(L,i){
  const ms=[{role:'system',content:'You are an assistant that always answers by calling the respond() tool.'},{role:'system',content:variant==='option3'?D_OPT:D_BASE}];
  const f=fill(L); if(f)ms.push({role:'user',content:f});
  ms.push({role:'user',content:Q});
  let j;
  try{const r=await fetch(END,{method:'POST',headers:{'content-type':'application/json',authorization:'Bearer '+key},body:JSON.stringify({model:MODEL,messages:ms,tools:[RESPOND],tool_choice:'required',temperature:0.2,max_tokens:120})});j=await r.json();if(!r.ok)return{err:(j.error&&j.error.message)||r.status};}
  catch(e){return{err:e.message};}
  const tc=j.choices&&j.choices[0]&&j.choices[0].message&&j.choices[0].message.tool_calls;
  let lang=null,args='';
  if(tc&&tc[0]){try{args=tc[0].function.arguments||'';lang=JSON.parse(args).language||null;}catch(_){}}
  return{lang,args};
}
(async()=>{
  const out={variant,trials,rows:{}};
  for(const L of LENS){
    const rs=[];
    for(let i=0;i<trials;i++)rs.push(await one(L,i));
    const ok=rs.filter(r=>!r.err);
    const hit=ok.filter(r=>r.lang&&String(r.lang).toLowerCase()==='en').length;
    out.rows[L]={ok:ok.length,hit,rate:ok.length?Math.round(1000*hit/ok.length)/10:0,langs:rs.map(r=>r.err?'E:'+r.err.substring(0,12):(r.lang||'-')),sample:ok[0]&&ok[0].args};
  }
  writeFileSync(join(__dir,'sweep_'+variant+'.json'),JSON.stringify(out,null,2));
  console.log(JSON.stringify(out,null,2));
})();
JSE
echo "sweep.mjs bytes=4207"; node --check /home/aezequiel/AI_Projects/sandpie/test/lang-harness/sweep.mjs 2>&1 | head
