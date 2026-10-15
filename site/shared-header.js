/* Shared BF4 Player Stats site header. Static UI; no submission endpoint. */
(function () {
  'use strict';
  const mount = document.getElementById('bf4ps-site-header');
  if (!mount) return;
  mount.className = 'top';
  mount.innerHTML = '<div class="wrap"><a class="brand brand-home" href="/index.html" aria-label="BF4 Player Stats home">BF4 <b>PLAYER STATS</b></a>' +
    '<div class="header-add"><label for="headerBattlelog">Not in the leaderboard yet? Add your Battlelog link below to manually add your stats!</label>' +
    '<div class="header-add-row"><input id="headerBattlelog" type="url" inputmode="url" autocomplete="off" spellcheck="false" placeholder="https://battlelog.battlefield.com/bf4/soldier/mauirixxx/stats/236753552/pc/" aria-label="Battlelog BF4 soldier stats URL">' +
    '<button id="headerAddStats" type="button" disabled title="Manual player submission is coming soon">Add Stats</button></div>' +
    '<span class="header-add-hint">Coming soon — preview only</span></div>' +
    '<nav class="topnav" aria-label="Main navigation"><a href="/index.html#leaderboards">LEADERBOARDS</a><a href="/equipment.html">EQUIPMENT VIEW</a><a href="/index.html#searchpanel">SOLDIERS</a></nav></div>';
})();
