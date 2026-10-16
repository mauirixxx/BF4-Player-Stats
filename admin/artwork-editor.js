'use strict';
(async()=>{
const $=id=>document.getElementById(id),q=new URLSearchParams(location.search);
const kind=q.get('kind'),raw_key=q.get('raw_key'),platform=q.get('platform'),item=q.get('item');
const valid=(kind==='weapon'||kind==='vehicle')&&/^WARSAW_ID_[A-Z0-9_]{3,160}$/.test(raw_key||'')&&['pc','ps4','xboxone'].includes(platform)&&/^\d+$/.test(item||'');
const key=kind+'-'+raw_key;
const back=new URL('/equipment.html',location.origin);
if(valid){back.searchParams.set('kind',kind);back.searchParams.set('platform',platform);back.searchParams.set('item',item);}
$('back').href=back.pathname+back.search;$('cancel').href=$('back').href;
const status=(msg,bad=false)=>{$('status').textContent=msg;$('status').className=bad?'error':'ok';};
if(!valid){status('Invalid equipment selection',true);return;}
let csrf='',historyState={},addedArt={};const previewUrls={};
const api=async(path,options={})=>{
  const r=await fetch('/bf4ps-admin-api/'+path,{credentials:'same-origin',cache:'no-store',...options,
    headers:{Accept:'application/json',...(csrf?{'X-CSRF-Token':csrf}:{}),...(options.headers||{})}});
  const body=await r.json();if(!r.ok)throw Error(body.error||'Request failed');return body;
};
const params=role=>new URLSearchParams({kind,raw_key,role});
const defaultArt=equipmentArtwork[key]||{};
function paint(role){
  const source=addedArt[role]?.local||defaultArt[role]?.local;
  const img=$(role+'Image');img.removeAttribute('src');if(source)img.src=source+'?v='+Date.now();
  $(role+'Info').textContent=historyState[role]?'Updated artwork':source?'Current artwork':'No default image available';
  $(role+'Restore').disabled=!historyState[role];
}
async function refresh(){
  const data=await api('artwork/catalog');
  if(!data.keys.includes(key))throw Error('Equipment is not in the approved artwork catalog');
  addedArt=data.overrides?.[key]||{};
  for(const role of ['fancy','hud']){const history=await api('artwork/history?'+params(role));historyState[role]=history.rows?.at(-1)?.action==='publish';paint(role);}
}
for(const role of ['fancy','hud']){
  $(role+'File').addEventListener('change',()=>{
    if(previewUrls[role])URL.revokeObjectURL(previewUrls[role]);
    const file=$(role+'File').files[0];if(!file){paint(role);return;}
    if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>4*1024*1024){status('Choose a PNG, JPEG or WebP image up to 4 MiB',true);$(role+'File').value='';paint(role);return;}
    previewUrls[role]=URL.createObjectURL(file);$(role+'Image').src=previewUrls[role];$(role+'Info').textContent='Local preview (not published)';
  });
  $(role+'Restore').addEventListener('click',async()=>{
    if(!confirm('Restore original or remove newly added '+role+' image for '+raw_key+'?'))return;
    try{status('Restoring '+role+'…');await api('artwork/restore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,raw_key,role})});await refresh();status('Default restored');}
    catch(e){status(e.message,true);}
  });
}
$('publish').addEventListener('click',async()=>{
  const files=['fancy','hud'].filter(role=>$(role+'File').files.length);
  if(!files.length){status('Select at least one replacement image',true);return;}
  if(files.some(role=>{const f=$(role+'File').files[0];return !['image/png','image/jpeg','image/webp'].includes(f.type)||f.size>4*1024*1024;})){status('Invalid replacement image',true);return;}
  if(!confirm('Publish '+files.join(' and ')+' artwork for '+raw_key+'?'))return;
  $('publish').disabled=true;
  for(const role of ['fancy','hud'])$(role+'Restore').disabled=true;
  try{
    for(const role of files){
      status('Publishing '+role+'…');
      const file=$(role+'File').files[0];
      await api('artwork/publish?'+params(role),{method:'POST',headers:{'Content-Type':file.type},body:file});
    }
    status('Published successfully. Returning to equipment…');
    location.assign(back.pathname+back.search);
  }catch(e){status('Publication stopped: '+e.message+'. Any earlier successful image may already be live.',true);$('publish').disabled=false;await refresh().catch(()=>{});}
});
try{
  const session=await api('session');csrf=session.csrf;
  await refresh();$('title').textContent='Update artwork · '+raw_key;$('editor').hidden=false;status('Administrator authenticated');
}catch(e){status('Admin login required or artwork unavailable: '+e.message+'. Sign in via the admin console first.',true);}
})();
