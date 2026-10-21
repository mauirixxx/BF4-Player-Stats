const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('site/homepage-paginated.js','utf8');
const calls=[];
const ctx={URLSearchParams,AbortSignal,Date,window:{},fetch:async(url,options)=>{
  calls.push({url,options});
  if(url.startsWith('/homepage-summary.json'))return {ok:true,json:async()=>({summary:{soldiers:209904,weapons:4462210,vehicles:2121094},detailed_soldiers:25786,full_soldiers:24849})};
  if(url.startsWith('/bf4ps-api/general-leaderboard'))return {ok:true,json:async()=>({population:25000,filtered_count:25000,rows:[{rank:51,soldier_id:123}]})};
  if(url.startsWith('/bf4ps-api/global-soldier-search'))return {ok:true,json:async()=>({rows:[{current_name:'FooeY',detailed_state:'never_attempted'}]})};
  throw Error('Unexpected endpoint '+url);
}};
vm.runInNewContext(source,ctx);
(async()=>{
 const api=ctx.window.BF4PSPaginated;
 const summary=await api.summary(ctx.fetch);assert.equal(summary.detailed_soldiers,25786);
 const ranking=await api.general({metric:'kills',platform:'pc',page:2,pageSize:50},ctx.fetch);
 assert.equal(ranking.rows[0].rank,51);
 assert.match(calls[1].url,/page=2/);
 assert.match(calls[1].url,/page_size=50/);
 const search=await api.search('FooeY',ctx.fetch);assert.equal(search.rows[0].detailed_state,'never_attempted');
 assert.equal((await api.search('x',ctx.fetch)).rows.length,0);
 assert.equal(calls.length,3);
 assert.throws(()=>api.generalUrl({metric:'kills;DROP TABLE soldiers'}));
 assert.throws(()=>api.generalUrl({pageSize:1000}));
 assert.equal(calls.some(c=>c.url.includes('temp-stats-data.json')),false);
 console.log('PASS: summary, paginated rankings, pending-soldier search, bounded requests and input validation');
})().catch(e=>{console.error(e);process.exitCode=1});
