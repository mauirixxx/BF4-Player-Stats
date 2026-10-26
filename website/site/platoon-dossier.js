(async()=>{
 const id=new URLSearchParams(location.search).get('id');if(!id||!/^[0-9]{1,18}$/.test(id))return;
 try{
  const sr=await fetch('/bf4ps-api/soldier-detail?id='+encodeURIComponent(id));
  if(!sr.ok)return;
  const soldier=(await sr.json()).soldier;if(!soldier)return;
  const pr=await fetch('/bf4ps-api/soldier-platoons?'+new URLSearchParams({persona_id:String(soldier.persona_id),platform:soldier.platform}));if(!pr.ok)return;
  const data=await pr.json();const matches=data.platoons||[];
  const panels=document.getElementById('identity-panels');if(!panels)return;
  const section=document.createElement('section');section.className='panel';section.style.marginTop='0';const heading=document.createElement('h2');heading.textContent='Known Platoons';section.append(heading);
  const button=document.createElement('button');button.type='button';button.textContent='↻ Refresh Platoon';button.style.cssText='background:#225579;color:#f2f5f9;border:1px solid #536579;border-radius:4px;padding:10px 16px;font:600 14px Arial,sans-serif;cursor:pointer';
  const bar=document.createElement('div');bar.style.cssText='display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap';heading.style.margin='0';heading.replaceWith(bar);bar.append(heading,button);
  const feedback=document.createElement('div');feedback.className='muted';feedback.style.fontSize='12px';bar.after(feedback);
  button.onclick=async()=>{button.disabled=true;button.textContent='Requesting…';try{const token=await fetch('/platoon-refresh-gateway.php',{credentials:'same-origin',cache:'no-store'});if(!token.ok)throw Error('Security token unavailable');const {csrf}=await token.json();const response=await fetch('/platoon-refresh-gateway.php',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-BF4PS-CSRF':csrf},body:JSON.stringify({soldier_id:Number(id)})});const result=await response.json();if(!response.ok)throw Error(result.error||'Request failed');feedback.textContent=({queued:'Platoon inspection prioritized. Check back shortly.',already_queued:'Inspection already queued.',already_running:'Inspection already running.'})[result.state]||result.state;}catch(error){feedback.textContent=error.message||'Request failed'}finally{button.disabled=false;button.textContent='↻ Refresh Platoon'}};

  const note=document.createElement('p');note.className='muted';note.textContent='Battlelog roster account associations, not independently verified soldier memberships.';section.append(note);
  if(!matches.length){const empty=document.createElement('p');empty.className='muted';empty.textContent='No known roster association in the currently indexed platoons.';section.append(empty)}
  const observed=data.observed;
  const selected=matches.length>1&&observed?matches.find(p=>String(p.id)===String(observed.platoon_id)):null;
  for(const p of matches){const a=document.createElement('a');a.href='/platoons.html?id='+encodeURIComponent(p.id);a.textContent='['+p.tag+'] '+p.name;a.style.cssText='display:inline-block;background:#243546;border:1px solid #4a5e70;border-radius:5px;padding:4px 8px;font-size:12px;color:#f2f5f9;text-decoration:none;margin:4px 7px 4px 0';a.onmouseenter=()=>{a.style.borderColor='#f3a536';a.style.color='#f3a536'};a.onmouseleave=()=>{a.style.borderColor='#4a5e70';a.style.color='#f2f5f9'};if(selected&&String(p.id)===String(selected.id)){a.textContent+=' (active)';if(observed.observed_at)a.title='Active platoon last observed on soldier page: '+observed.observed_at}section.append(a)}
  panels.append(section);
 }catch(e){console.warn('Platoon associations unavailable',e)}
})();
