/* Shared BF4 Player Stats site header. Static UI; no submission endpoint. */
(function () {
  'use strict';
  const mount = document.getElementById('bf4ps-site-header');
  if (!mount) return;
  mount.className = 'top';
  mount.innerHTML = '<div class="wrap"><a class="brand brand-home" href="/index.html" aria-label="BF4 Player Stats home">BF4 <b>PLAYER STATS</b></a>' +
    '<div class="header-add"><label for="headerBattlelog">Not in the leaderboard yet? Add your Battlelog link below to manually add your stats!</label>' +
    '<div class="header-add-row"><input id="headerBattlelog" type="url" inputmode="url" autocomplete="off" spellcheck="false" placeholder="https://battlelog.battlefield.com/bf4/soldier/mauirixxx/stats/236753552/pc/" aria-label="Battlelog BF4 soldier stats URL">' +
    '<button id="headerAddStats" type="button" title="Submit a BF4 soldier">Add Stats</button></div>' +
    '<span class="header-add-hint" role="status" aria-live="polite">Paste a Battlelog BF4 soldier stats URL</span></div>' +
    '<div class="topnav-stack"><nav class="topnav" aria-label="Main navigation"><a href="/index.html#leaderboards">LEADERBOARDS</a><a href="/equipment.html">EQUIPMENT VIEW</a><a href="/admin-console.html">ADMIN</a></nav><nav class="topnav-sub" aria-label="Secondary navigation"><a href="/index.html#searchpanel">SOLDIERS</a><a href="/platoons.html">PLATOONS</a><a href="/community.html">COMMUNITY STATS</a></nav></div></div>';
  const platoonPage=location.pathname.replace(/\/$/,'').endsWith('/platoons.html');
  if(platoonPage){
    const area=mount.querySelector('.header-add');
    area.innerHTML='<label for="headerPlatoon">Have an official Battlelog platoon? Add your platoon!</label>'+
      '<div class="header-add-row"><input id="headerPlatoon" type="url" inputmode="url" autocomplete="off" spellcheck="false" placeholder="https://battlelog.battlefield.com/bf4/platoons/members/754443074295858477/" aria-label="Official Battlelog platoon URL">'+
      '<button id="headerAddPlatoon" type="button" title="Queue an official Battlelog platoon">Add Platoon</button></div>'+
      '<span class="header-add-hint" role="status">Paste an official Battlelog platoon URL to queue collection.</span>';
    const button=document.getElementById('headerAddPlatoon'),input=document.getElementById('headerPlatoon'),hint=area.querySelector('.header-add-hint');
    button.addEventListener('click',async()=>{
      if(!input.value.trim()){hint.textContent='Paste an official Battlelog platoon URL first';return}
      button.disabled=true;hint.textContent='Submitting platoon…';
      try{
        const token=await fetch('/platoon-gateway.php',{credentials:'same-origin',cache:'no-store'});
        if(!token.ok)throw Error('Unable to get security token');
        const {csrf}=await token.json();
        const response=await fetch('/platoon-gateway.php',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-BF4PS-CSRF':csrf},body:JSON.stringify({url:input.value.trim()})});
        const result=await response.json();
        if(!response.ok)throw Error(result.error||'Submission failed');
        hint.textContent=({queued:'Platoon queued for collection!',already_queued:'This platoon is already queued.',already_collected:'This platoon is already in our database.'})[result.state]||result.state;
        if(result.state==='already_collected')location.href='/platoons.html?id='+encodeURIComponent(result.platoon_id);
        if(result.state==='queued')input.value='';
      }catch(err){hint.textContent=err.message||'Submission failed'}finally{button.disabled=false}
    });
    return;
  }
  const btn=document.getElementById('headerAddStats'), field=document.getElementById('headerBattlelog'), hint=document.querySelector('.header-add-hint');
  // Acknowledge successful submissions without making bulk entry cumbersome.
  const dialog=document.createElement('dialog');
  dialog.className='bf4ps-add-confirmation';
  dialog.setAttribute('aria-labelledby','bf4ps-add-confirmation-title');
  dialog.innerHTML='<h2 id="bf4ps-add-confirmation-title">Stats request accepted</h2>'+
    '<p id="bf4ps-add-confirmation-message"></p>'+
    '<form method="dialog"><button type="submit" autofocus>OK</button></form>';
  document.body.appendChild(dialog);
  const confirmationMessage=dialog.querySelector('#bf4ps-add-confirmation-message');
  function resetForNextLink(){
    field.value='';
    hint.textContent='Paste a Battlelog BF4 soldier stats URL';
    field.focus();
  }
  dialog.addEventListener('close',resetForNextLink);
  btn.disabled=false;
  btn.addEventListener('click',async()=>{
    if(!field.value.trim()){hint.textContent='Paste a Battlelog BF4 soldier stats URL first';field.focus();return;}

    btn.disabled=true;hint.textContent='Submitting…';
    try {
      const tokenResponse=await fetch('/manual-gateway.php',{credentials:'same-origin',cache:'no-store'});
      if(!tokenResponse.ok)throw Error('Security token unavailable');
      const {csrf}=await tokenResponse.json();
      const response=await fetch('/manual-gateway.php',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-BF4PS-CSRF':csrf},body:JSON.stringify({url:field.value.trim(),kind:'add'})});
      const result=await response.json();
      if(!response.ok)throw Error(result.error||result.state||'Request failed');
      const messages={accepted:'Your Battlelog link was accepted. Stats collection has been prioritized.',verification_pending:'Soldier added; stats collection queued.',cooldown:'This soldier was recently requested. The existing cooldown is still active.',up_to_date:'This soldier’s statistics are already current.'};
      hint.textContent=({accepted:'Collection prioritized',verification_pending:'Soldier added; collection queued',cooldown:'Recently refreshed',up_to_date:'Stats already current'})[result.state]||result.state||'Submitted';
      confirmationMessage.textContent=messages[result.state]||'Your request was processed.';
      if(typeof dialog.showModal==='function')dialog.showModal();
      else {window.alert(confirmationMessage.textContent);resetForNextLink();}
    } catch(err) {hint.textContent=err.message||'Submission failed';}
    finally {btn.disabled=false;}
  });
})();
