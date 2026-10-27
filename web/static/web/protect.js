// Content protection for formula pages.
// IMPORTANT: browsers cannot truly block screenshots or copying. This script raises the effort
// (blocks copy/select/right-click/print/shortcuts, blurs the page when focus leaves it, clears the
// clipboard after PrintScreen) and adds a faint watermark with the viewer's name so a leaked
// screenshot can be traced. It is a deterrent, not a lock.
(()=>{
  const body=document.body;
  if(!body||body.dataset.protect!=='1')return;
  const okTarget=t=>t&&t.closest&&t.closest('input,textarea,select,[contenteditable="true"]');
  const stop=e=>{if(okTarget(e.target))return;e.preventDefault();e.stopPropagation()};

  ['contextmenu','copy','cut','dragstart','selectstart'].forEach(ev=>document.addEventListener(ev,stop,true));
  document.addEventListener('copy',e=>{if(okTarget(e.target))return;try{e.clipboardData.setData('text/plain','')}catch(_){}} ,true);

  // Shield: hides the page content (used when the tab loses focus, on print, on PrintScreen)
  let shieldTimer;
  const shield=(on,ms)=>{clearTimeout(shieldTimer);body.classList.toggle('shielded',on);
    if(on&&ms)shieldTimer=setTimeout(()=>body.classList.remove('shielded'),ms)};

  document.addEventListener('keydown',e=>{
    if(okTarget(e.target))return;
    const k=(e.key||'').toLowerCase(),mod=e.ctrlKey||e.metaKey;
    if(k==='printscreen'){shield(true,1500);try{navigator.clipboard.writeText('')}catch(_){};e.preventDefault();return}
    // Windows Snipping Tool (Win+Shift+S) and macOS capture (Cmd+Shift+3/4/5)
    if((e.metaKey&&e.shiftKey&&['s','3','4','5'].includes(k))){shield(true,2500);e.preventDefault();return}
    if(mod&&['c','x','a','s','p','u'].includes(k)){e.preventDefault();return}
    if(k==='f12'||(mod&&e.shiftKey&&['i','j','c'].includes(k))){e.preventDefault()}
  },true);
  document.addEventListener('keyup',e=>{if((e.key||'').toLowerCase()==='printscreen'){try{navigator.clipboard.writeText('')}catch(_){};shield(true,1500)}},true);

  // Hide content whenever the page is not the focused window (snipping overlays, screen-share pickers, tab switch)
  window.addEventListener('blur',()=>shield(true));
  window.addEventListener('focus',()=>shield(false));
  document.addEventListener('visibilitychange',()=>shield(document.hidden));
  window.addEventListener('beforeprint',()=>shield(true));
  window.addEventListener('afterprint',()=>shield(false));

  // Watermark: viewer name repeated across the page, very faint, so leaks are traceable
  const wm=body.dataset.wm;
  if(wm){
    const s=encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="260" height="170"><text x="20" y="100" transform="rotate(-24 130 85)" font-family="sans-serif" font-size="15" fill="#808080" fill-opacity="0.16">${wm.replace(/[<&>]/g,'')}</text></svg>`);
    const d=document.createElement('div');d.className='wm';d.setAttribute('aria-hidden','true');
    d.style.backgroundImage=`url("data:image/svg+xml,${s}")`;body.append(d);
  }
})();
