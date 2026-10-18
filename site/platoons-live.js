(async()=>{
 const root=document.querySelector('main.wrap');
 root.innerHTML='<div class="eyebrow">OFFICIAL BATTLELOG ROSTERS</div><h1>PLATOONS</h1><p>Confirmed account membership; associated BF4 soldiers are not independently verified platoon members.</p><div id="platoons-list"></div><section id="platoon-detail" class="panel" hidden></section>';
 const list=document.getElementById('platoons-list'),detail=document.getElementById('platoon-detail');
 const el=(tag,value)=>{const x=document.createElement(tag);x.textContent=value??'';return x};
 try{
  const response=await fetch('/platoons-data.json',{cache:'no-store'});
  if(!response.ok)throw Error('HTTP '+response.status);
  const {platoons}=await response.json();
  function showList(){detail.hidden=true;list.hidden=false;history.pushState(null,'','/platoons.html')}
  function show(p,change=true){list.hidden=true;detail.hidden=false;detail.replaceChildren();const back=el('button','← All platoons');back.onclick=showList;detail.append(back,el('h2','['+p.tag+'] '+p.name),el('p',p.official_member_count+' official roster accounts · Updated '+new Date(p.last_success_at).toLocaleString()));const search=el('input');search.placeholder='Search accounts and soldiers';search.style.cssText='padding:12px;background:#0b121b;color:white;border:1px solid #687b8b;width:100%;max-width:440px';detail.append(search);const table=el('div');detail.append(table);function render(){table.replaceChildren();const term=search.value.toLowerCase();for(const m of p.members.filter(x=>(x.account_name||'').toLowerCase().includes(term)||x.personas.some(y=>y.persona_name.toLowerCase().includes(term)))){const row=el('div');row.style.cssText='padding:12px 0;border-bottom:1px solid #425363';row.append(el('strong',(m.account_name||'Unknown account')+' · '+m.role),el('br'));for(const x of m.personas){const item=el(x.soldier_id?'a':'span',x.persona_name+' ('+({1:'PC',2:'Xbox 360',4:'PS3',32:'PS4',64:'Xbox One'}[x.platform_code]||x.platform)+')');item.style.cssText='display:inline-block;margin:5px 8px 0 0;color:#f3a536';if(x.soldier_id)item.href='/soldier.html?id='+encodeURIComponent(x.soldier_id);row.append(item)}table.append(row)}}search.oninput=render;render();if(change)history.pushState(null,'','/platoons.html?id='+p.id)}
  for(const p of platoons){const card=el('button','['+p.tag+'] '+p.name+' — '+p.official_member_count+' members');card.style.cssText='display:block;width:100%;text-align:left;padding:22px;background:#172635;color:#f3a536;border:1px solid #485d71;border-radius:8px;margin:12px 0;cursor:pointer;font-size:19px';card.onclick=()=>show(p);list.append(card)}
  const selected=new URLSearchParams(location.search).get('id');const match=platoons.find(x=>x.id===selected);if(match)show(match,false);
 }catch(e){list.textContent='Unable to load current platoon roster: '+e.message}
})();
