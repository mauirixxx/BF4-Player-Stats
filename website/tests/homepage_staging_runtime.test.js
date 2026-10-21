// Execute the real staging homepage scripts against a small DOM and HTTP stub.
// This is an integration smoke test, not a substitute for a visual browser test.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('site/index-paginated-staging.html','utf8');
const adapter=fs.readFileSync('site/homepage-paginated.js','utf8');
const inline=html.match(/<script>\s*([\s\S]*?)<\/script>/g).at(-1).replace(/^<script>/,'').replace(/<\/script>$/,'');
const elements=new Map();
function el(id){if(!elements.has(id))elements.set(id,{
 id,value:'',innerHTML:'',textContent:'',disabled:false,style:{},dataset:{},
 classList:{toggle(){}},addEventListener(){},insertAdjacentHTML(){},querySelector(){return null}
});return elements.get(id)}
el('metric').value='kills';el('divisionFilter').value='';
const requests=[];
const ctx={console,URL,URLSearchParams,AbortSignal,Date,Number,String,Math,encodeURIComponent,
 setInterval(){},setTimeout(fn){fn();return 1},clearTimeout(){},
 location:{search:'',origin:'https://www.bf4playerstats.com'},window:{location:{href:''}},
 document:{hidden:false,getElementById:el,querySelectorAll(){return []},addEventListener(){}},
 fetch:async(url)=>{requests.push(String(url));const path=String(url);
  let result;
  if(path.includes('/health'))result={status:'ok'};
  else if(path.includes('homepage-summary.json'))result={summary:{soldiers:209904,weapons:4000000,vehicles:2000000},detailed_soldiers:26500,full_soldiers:25000};
  else if(path.includes('/general-leaderboard'))result={population:26500,filtered_count:26500,total_pages:530,rows:[{soldier_id:42,current_name:'TestSoldier',persona_id:12345,platform:'pc',value:99,rank:1,position:1,top_pct:0.01,division:1}]};
  else if(path.includes('/global-soldier-search'))result={rows:[{soldier_id:42,current_name:'TestSoldier',platform:'pc',persona_id:12345,rank:1,kills:99,detailed_state:'success'}]};
  else throw Error('Unexpected request '+path);
  return {ok:true,status:200,json:async()=>result};
 }};
ctx.window.window=ctx.window;
vm.createContext(ctx);
vm.runInContext(adapter,ctx);
ctx.BF4PSPaginated=ctx.window.BF4PSPaginated;
vm.runInContext(inline,ctx);
(async()=>{
 await new Promise(resolve=>setTimeout(resolve,10));
 assert.equal(el('soldierCount').textContent,'209,904');
 assert.match(el('leaderRows').innerHTML,/TestSoldier/);
 assert.equal(el('nextPage').disabled,false);
 el('nextPage').onclick();await new Promise(resolve=>setTimeout(resolve,10));
 assert(requests.some(x=>x.includes('page=2')));
 el('globalSearch').value='Test';
 await vm.runInContext('updateAliasSearch()',ctx);
 assert.match(el('searchRows').innerHTML,/TestSoldier/);
 assert(!requests.some(x=>x.includes('temp-stats-data.json')));
 console.log('PASS: staging startup, summary, leaderboard rendering, page navigation, global search, no bulk JSON');
})().catch(e=>{console.error(e);process.exitCode=1});
