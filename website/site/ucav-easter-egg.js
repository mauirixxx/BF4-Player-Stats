// BF4PS UCAV Easter egg
'use strict';
(()=>{
const search=document.getElementById('soldier');
const kind=document.getElementById('kind');
const equipment=document.getElementById('equipment');
const hero=document.getElementById('heroIcon');
const platforms=document.getElementById('platforms');
const names=['ah1z','mi28','z10w','ah6','z11','ka60','venom'];
let last='',timer=0;
function check(){
 clearTimeout(timer);
 timer=setTimeout(()=>{
  const pc=platforms.querySelector('[data-platform="pc"].active');
  const ps=platforms.querySelector('[data-platform="ps4"].active');
  const player=search.value.trim().toLowerCase();
  const valid=kind.value==='vehicle'&&((pc&&player==='mauirixxx')||(ps&&player==='raad_iq9'));
  const stage=hero.closest('.stage');
  if(!valid){last='';stage?.querySelector('.ucav-easter-frame')?.remove();return;}
  const src=hero.querySelector('img')?.getAttribute('src')||'';
  const name=names.find(n=>src.includes('/'+n+'_fancy.'));
  if(!name)return;
  const key=name+'-'+equipment.value;
  if(last===key)return;
  last=key;
  if(!stage)return;
  stage.style.position='relative';
  stage.querySelector('.ucav-easter-frame')?.remove();
  const frame=document.createElement('iframe');
  frame.className='ucav-easter-frame';
  frame.title='UCAV animation';
  frame.style.cssText='position:absolute;inset:0;width:100%;height:100%;border:0;z-index:10;pointer-events:none';
  frame.src='/ucav-helicopter-tests.html?embed=1&aircraft='+name;
  stage.appendChild(frame);
  setTimeout(()=>{if(frame.isConnected)frame.remove()},4200);
 },450);
}
search.addEventListener('input',check);
kind.addEventListener('change',check);
equipment.addEventListener('change',check);
platforms.addEventListener('click',check);
new MutationObserver(check).observe(hero,{childList:true});
check();
})();
