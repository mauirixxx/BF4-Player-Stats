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
    '<span class="header-add-hint">Paste a Battlelog BF4 soldier stats URL</span></div>' +
    '<nav class="topnav" aria-label="Main navigation"><a href="/index.html#leaderboards">LEADERBOARDS</a><a href="/equipment.html">EQUIPMENT VIEW</a><a href="/index.html#searchpanel">SOLDIERS</a></nav></div>';
  const btn=document.getElementById('headerAddStats'), field=document.getElementById('headerBattlelog'), hint=document.querySelector('.header-add-hint');
  btn.disabled=false;
  btn.addEventListener('click',async()=>{
    btn.disabled=true;hint.textContent='Submitting…';
    try {
      const tokenResponse=await fetch('/manual-gateway.php',{credentials:'same-origin',cache:'no-store'});
      if(!tokenResponse.ok)throw Error('Security token unavailable');
      const {csrf}=await tokenResponse.json();
      const response=await fetch('/manual-gateway.php',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-BF4PS-CSRF':csrf},body:JSON.stringify({url:field.value.trim(),kind:'add'})});
      const result=await response.json();
      if(!response.ok)throw Error(result.error||result.state||'Request failed');
      hint.textContent=({accepted:'Collection prioritized',verification_pending:'Soldier added; collection queued',cooldown:'Recently refreshed',up_to_date:'Stats already current'})[result.state]||result.state||'Submitted';
    } catch(err) {hint.textContent=err.message||'Submission failed';}
    finally {btn.disabled=false;}
  });
})();
