'use strict';
(() => {
  const el = id => document.getElementById(id);
  const status = (msg, error = false) => {
    el('artworkStatus').textContent = msg;
    el('artworkStatus').className = error ? 'error' : 'ok';
  };
  let catalog = [], overrides = {}, defaults = {}, loading = false;
  let busy = false;
  const roles = ['fancy', 'hud'];
  const title = role => role === 'fancy' ? 'Fancy' : 'Hud';
  const identity = () => {
    const key = el('artworkItem').value;
    const match = /^(weapon|vehicle)-(WARSAW_ID_[A-Z0-9_]+)$/.exec(key);
    return match ? {key, kind:match[1], raw_key:match[2]} : null;
  };
  const params = (item, role) => new URLSearchParams({kind:item.kind,raw_key:item.raw_key,role});
  const fetchJSON = async (path, options = {}) => {
    const response = await fetch('/bf4ps-admin-api/' + path, {
      credentials:'same-origin',cache:'no-store',
      headers:{'Accept':'application/json',...(csrf ? {'X-CSRF-Token':csrf} : {}),...(options.headers || {})},
      ...options
    });
    const body = await response.json();
    if (!response.ok) throw Error(body.error || 'Request failed');
    return body;
  };
  async function loadDefaults() {
    // The shipped catalog is a JavaScript assignment, not JSON. Load it as a same-origin script.
    if (Object.keys(defaults).length) return;
    await new Promise((resolve,reject) => {
      const script=document.createElement('script');
      script.src='/equipment-artwork.js';
      script.onload=resolve;
      script.onerror=()=>reject(Error('Default artwork catalog unavailable'));
      document.head.append(script);
    });
    // The original catalog uses a top-level const, accessible by name in this script.
    if (typeof equipmentArtwork === 'undefined') throw Error('Default artwork catalog unavailable');
    defaults=equipmentArtwork;
  }
  const source = (item, role) => {
    const custom=overrides[item.key]?.[role]?.local;
    const original=defaults[item.key]?.[role]?.local;
    return {url:custom || original || '', custom:Boolean(custom)};
  };
  async function show() {
    const item=identity();
    for(const role of roles) {
      const name=title(role), img=el('artwork'+name);
      const info=el('artwork'+name+'Source');
      const restore=el('artwork'+name+'Restore');
      const publish=el('artwork'+name+'Publish');
      const history=el('artwork'+name+'History');
      img.removeAttribute('src');
      info.textContent='No equipment selected';
      history.replaceChildren();
      publish.disabled=!item || busy;
      restore.disabled=true;
      if(!item) continue;
      const current=source(item,role);
      if(current.url) img.src=current.url;
      info.textContent=current.custom?'Custom override active':current.url?'Default artwork':'No default artwork';
      restore.disabled=!current.custom || busy;
      try {
        const result=await fetchJSON('artwork/history?'+params(item,role));
        if(el('artworkItem').value!==item.key) return;
        const heading=document.createElement('p');
        heading.textContent='History: '+result.rows.length+' event(s)';
        history.append(heading);
        for(const entry of result.rows.slice(-5).reverse()) {
          const line=document.createElement('div');
          line.textContent=[entry.at,entry.action,entry.version||''].filter(Boolean).join(' · ');
          history.append(line);
        }
      } catch(err) { history.textContent='History unavailable: '+err.message; }
    }
  }
  async function load() {
    if(!csrf || loading) return;
    loading=true;
    try {
      status('Loading artwork catalog…');
      const data=await fetchJSON('artwork/catalog');
      catalog=data.keys;
      overrides=data.overrides;
      await loadDefaults();
      filter();
      status(catalog.length+' equipment entries available');
    } catch(err) {status(err.message,true);}
    finally {loading=false;}
  }
  function filter() {
    const q=el('artworkSearch').value.trim().toLowerCase();
    const select=el('artworkItem'), prior=select.value;
    select.replaceChildren();
    const empty=document.createElement('option');
    empty.value=''; empty.textContent='Select equipment'; select.append(empty);
    const matches=catalog.filter(key=>key.toLowerCase().includes(q));
    for(const key of matches) {
      const option=document.createElement('option');
      option.value=key; option.textContent=key.replace(/^(weapon|vehicle)-WARSAW_ID_/,'$1 · ').replaceAll('_',' ');
      select.append(option);
    }
    if(matches.includes(prior)) select.value=prior;
    void show();
  }
  async function act(role, restore) {
    const item=identity();
    if(!item || busy) return;
    const input=el('artwork'+title(role)+'File');
    const file=input.files?.[0];
    if(!restore && !file) return status('Choose an image before publishing',true);
    if(!restore && file.size>4*1024*1024) return status('Image exceeds 4 MiB upload limit',true);
    if(!restore && !['image/png','image/jpeg','image/webp'].includes(file.type)) return status('Use PNG, JPEG or WebP',true);
    const action=restore?'restore the default':'publish a new image';
    if(!confirm('Confirm: '+action+' for '+item.key+' ('+role+')?')) return;
    busy=true;
    try {
      status('Processing '+role+' artwork…');
      const path=restore?'artwork/restore':'artwork/publish?'+params(item,role);
      const result=await fetchJSON(path,{
        method:'POST',
        headers:restore?{'Content-Type':'application/json'}:{'Content-Type':file.type},
        body:restore?JSON.stringify({kind:item.kind,raw_key:item.raw_key,role}):file
      });
      if(!restore) input.value='';
      const refreshed=await fetchJSON('artwork/catalog');
      overrides=refreshed.overrides;
      status(restore?(result.changed?'Default restored':'Already using default'):'Artwork published');
    } catch(err) {status(err.message,true);}
    finally {busy=false;await show();}
  }
  el('artworkSearch').addEventListener('input',filter);
  el('artworkItem').addEventListener('change',()=>void show());
  el('artworkReload').addEventListener('click',()=>void load());
  for(const role of roles) {
    const input=el('artwork'+title(role)+'File');
    let previewURL=null;
    input.addEventListener('change',()=>{
      if(previewURL) URL.revokeObjectURL(previewURL);
      previewURL=null;
      const file=input.files?.[0];
      if(file && ['image/png','image/jpeg','image/webp'].includes(file.type) && file.size<=4*1024*1024) {
        previewURL=URL.createObjectURL(file);
        el('artwork'+title(role)).src=previewURL;
        el('artwork'+title(role)+'Source').textContent='Local preview only — not published';
      } else { void show(); }
    });
    el('artwork'+title(role)+'Publish').addEventListener('click',()=>void act(role,false));
    el('artwork'+title(role)+'Restore').addEventListener('click',()=>void act(role,true));
  }
  // Artwork is loaded only after the existing admin session is established.
  const observer=new MutationObserver(()=>{
    if(!el('app').classList.contains('hidden') && csrf && !catalog.length && !loading) void load();
    if(el('app').classList.contains('hidden')) catalog=[];
  });
  observer.observe(el('app'),{attributes:true,attributeFilter:['class']});
  if(!el('app').classList.contains('hidden') && csrf) void load();
})();
