// Theme: light / dark / match device, plus an accent colour. Kept in this browser (localStorage).
(()=>{const root=document.documentElement,mq=matchMedia('(prefers-color-scheme: dark)');
const get=k=>{try{return localStorage.getItem(k)}catch(e){return null}};
const put=(k,v)=>{try{v?localStorage.setItem(k,v):localStorage.removeItem(k)}catch(e){}};
const apply=()=>{const m=get('fs-theme')||'system',a=get('fs-accent');
 root.dataset.theme=(m==='dark'||(m==='system'&&mq.matches))?'dark':'light';
 if(a)root.dataset.accent=a;else delete root.dataset.accent;
 document.querySelectorAll('input[name=fs-mode]').forEach(i=>{i.checked=i.value===m});
 document.querySelectorAll('[data-accent-pick]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.accentPick===(a||'indigo'))));
 const t=document.getElementById('theme-toggle');t&&t.setAttribute('aria-pressed',String(root.dataset.theme==='dark'))};
const t=document.getElementById('theme-toggle');
t&&t.addEventListener('click',()=>{put('fs-theme',root.dataset.theme==='dark'?'light':'dark');apply()});
document.querySelectorAll('input[name=fs-mode]').forEach(i=>i.addEventListener('change',()=>{put('fs-theme',i.value);apply()}));
document.querySelectorAll('[data-accent-pick]').forEach(b=>b.addEventListener('click',()=>{put('fs-accent',b.dataset.accentPick==='indigo'?'':b.dataset.accentPick);apply()}));
const r=document.getElementById('theme-reset');r&&r.addEventListener('click',()=>{put('fs-theme','');put('fs-accent','');apply()});
mq.addEventListener&&mq.addEventListener('change',apply);apply()})();
document.querySelectorAll('[data-math]').forEach(el=>{
  try{katex.render(el.dataset.math,el,{displayMode:el.dataset.display==='1',throwOnError:false,trust:false,maxExpand:200,maxSize:20})}
  catch(e){el.textContent=el.dataset.math}
});
const t=document.querySelector('.menu-toggle');
t&&t.addEventListener('click',()=>{const n=document.getElementById('nav');const o=n.classList.toggle('open');t.setAttribute('aria-expanded',o)});
function toast(m){const d=document.createElement('div');d.className='toast';d.setAttribute('role','status');d.textContent=m;document.body.append(d);setTimeout(()=>d.remove(),2200)}
document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',async()=>{
  try{await navigator.clipboard.writeText(b.dataset.copy);toast('Copied')}catch(e){toast('Copy failed. Select the text manually.')}}));
const si=document.getElementById('q'),sl=document.getElementById('suggest');let timer;
si&&si.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(async()=>{
  if(si.value.trim().length<2){sl.hidden=true;return}
  try{const r=await fetch('/api/suggest/?q='+encodeURIComponent(si.value));const d=await r.json();
    sl.replaceChildren(...d.results.map(x=>{const li=document.createElement('li'),a=document.createElement('a');a.href='/formulas/'+x.slug+'/';a.textContent=x.title;li.append(a);return li}));
    sl.hidden=!d.results.length}catch(e){sl.hidden=true}},200)});
// Sign-up: the grade list only appears for account types that ask for it (for example Student).
(()=>{const t=document.getElementById('account_type'),b=document.getElementById('grade_box'),g=document.getElementById('grade');
if(!t||!b||!g)return;
const sync=()=>{const o=t.options[t.selectedIndex],show=!!o&&o.dataset.asksGrade==='1';b.hidden=!show;g.required=show;if(!show)g.value=''};
t.addEventListener('change',sync);sync()})();
