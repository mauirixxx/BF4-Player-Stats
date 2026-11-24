// Shared BF4PS operations navigation; canonical menu for both admin pages.
(function(){
 const links = [
  ["Collection Overview", "/admin-console.html#overview", "overview"],
  ["Operations Monitor", "/admin-console.html#operations", "operations"],
  ["Player Moderation", "/admin-console.html#moderation", "moderation"],
  ["Database Health", "/admin-console.html#database", "database"],
  ["Account Settings", "/admin-console.html#account", "account"],
  ["Error Logs", "/admin-console.html#errors", "errors"],
  ["Distributed Ranking Monitor", "/admin-ranking.html", "ranking"],
  ["General Ranking Monitor", "/admin-general-ranking.html", "general-ranking"]
 ];
 const nav=document.querySelector('[data-shared-admin-nav]');
 if(!nav)return;
 nav.replaceChildren();
 const ranking=location.pathname.endsWith('/admin-ranking.html');
 const generalRanking=location.pathname.endsWith('/admin-general-ranking.html');
 for(const [label,url,key] of links){
  const a=document.createElement('a');a.href=url;a.textContent=label;
  a.dataset.adminLink=key;
  const active=generalRanking?key==='general-ranking':ranking?key==='ranking':key===(location.hash.slice(1)||'overview');
  a.classList.toggle('current',active);a.classList.toggle('active',active);
  nav.append(a);
 }
 if(!ranking&&!generalRanking)window.addEventListener('hashchange',()=>{
  for(const a of nav.querySelectorAll('a')){
   const active=a.dataset.adminLink===(location.hash.slice(1)||'overview');
   a.classList.toggle('current',active);a.classList.toggle('active',active);
  }
 });
})();
