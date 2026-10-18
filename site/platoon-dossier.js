(async()=>{
 const id=new URLSearchParams(location.search).get('id');if(!id||!/^[0-9]{1,18}$/.test(id))return;
 try{
  const [sr,pr]=await Promise.all([fetch('/bf4ps-api/soldier-detail?id='+encodeURIComponent(id)),fetch('/platoons-data.json',{cache:'no-store'})]);
  if(!sr.ok||!pr.ok)return;
  const soldier=(await sr.json()).soldier;if(!soldier)return;
  const data=await pr.json();const matches=[];
  for(const p of data.platoons||[])for(const m of p.members||[])for(const x of m.personas||[])if(String(x.persona_id)===String(soldier.persona_id)&&({pc:1,ps4:32,xboxone:64}[soldier.platform])===Number(x.platform_code))matches.push(p);
  const hero=document.querySelector('.hero');if(!hero)return;
  const section=document.createElement('section');section.className='panel';section.style.marginTop='14px';const heading=document.createElement('h2');heading.textContent='Known Platoons';section.append(heading);
  const note=document.createElement('p');note.className='muted';note.textContent='Battlelog roster account associations, not independently verified soldier memberships.';section.append(note);
  if(!matches.length){const empty=document.createElement('p');empty.className='muted';empty.textContent='No known roster association in the currently indexed platoons.';section.append(empty)}
  for(const p of matches){const a=document.createElement('a');a.href='/platoons.html?id='+encodeURIComponent(p.id);a.textContent='['+p.tag+'] '+p.name;a.style.cssText='display:inline-block;margin:4px 10px 4px 0;color:#f3a536';section.append(a)}
  hero.append(section);
 }catch(e){console.warn('Platoon associations unavailable',e)}
})();
