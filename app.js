const APP_VERSION='20260828c';
const COLUMNS=['AssetTag','Name','Type','Serial','MacAddress','Location','Status','Manufacturer','Model','ReceivedBy','NotesReceived','Note','PurchaseDate','WarrantyMonths','Price','EmployeeID','RequestedBy'];
const LABELS={'AssetTag':'Asset ID','Name':'Asset Name','ReceivedBy':'Signed By','NotesReceived':'Signed Date','Note':'Note','WarrantyMonths':'Warranty','EmployeeID':'Employee Name','RequestedBy':'Requested By','Type':'Item Category','Price':'Price','MacAddress':'MAC Address','PurchaseDate':'Purchased Date'};

// --- currency: stored base = AED; display converts via rate and shows symbol ---
const MONEY={AED:{s:'AED',r:1},USD:{s:'$',r:0.272},EUR:{s:'€',r:0.25},INR:{s:'₹',r:22.7}};
let CURRENCY='AED';
function fmtMoney(v,cur){
  cur=cur||CURRENCY; const m=MONEY[cur]||MONEY.AED;
  const num=parseFloat(v||0)*m.r;
  return m.s+' '+num.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
}

// --- i18n: applied to [data-i18n] elements + document.dir for ar ---
const I18N={
  en:{Home:'Home',Assets:'Assets',AddAsset:'Add Asset',ImportExcel:'Import Excel',ExportExcel:'Export Excel',AuditLog:'Log',Tickets:'Tickets',Contracts:'Contracts',Locations:'Locations',Trash:'Trash',Customization:'Customization',NetworkScan:'Network Scan',Heartbeat:'Heartbeat',BackupRestore:'Backup / Restore',Settings:'Settings',System:'System',Employees:'Employees',Save:'Save',Add:'Add',Edit:'Edit',Delete:'Delete',Search:'Search',Dashboard:'IT Guy - The Assets Manager'},
  ar:{Home:'الرئيسية',Assets:'الأصول',AddAsset:'إضافة أصل',ImportExcel:'استيراد إكسل',ExportExcel:'تصدير إكسل',AuditLog:'سجل التدقيق',Tickets:'التذاكر',Contracts:'العقود',Locations:'المواقع',Trash:'السلة',Customization:'التخصيص',NetworkScan:'فحص الشبكة',Heartbeat:'مراقبة الأجهزة',BackupRestore:'النسخ الاحتياطي',Settings:'الإعدادات',System:'النظام',Employees:'الموظفون',Save:'حفظ',Add:'إضافة',Edit:'تعديل',Delete:'حذف',Search:'بحث',Dashboard:'IT Guy // مصفوفة الأصول'},
  ta:{Home:'முகப்பு',Assets:'சொத்துகள்',AddAsset:'சொத்து சேர்',ImportExcel:'எக்செல் இறக்குமதி',ExportExcel:'எக்செல் ஏற்றுமதி',AuditLog:'தணிக்கை பதிவு',Tickets:'டிக்கெட்டுகள்',Contracts:'ஒப்பந்தங்கள்',Locations:'இடங்கள்',Trash:'குப்பை',Customization:'தனிப்பயனாக்கம்',NetworkScan:'பிணைய ஸ்கேன்',Heartbeat:'கண்காணிப்பு',BackupRestore:'காப்புப்பு',Settings:'அமைப்புகள்',System:'கணினி',Employees:'ஊழியர்கள்',Save:'சேமி',Add:'சேர்',Edit:'திருத்து',Delete:'நீக்கு',Search:'தேடல்',Dashboard:'IT Guy // சொத்து மேட்ரிக்ஸ்'},
  fr:{Home:'Accueil',Assets:'Actifs',AddAsset:'Ajouter',ImportExcel:'Importer Excel',ExportExcel:'Exporter Excel',AuditLog:'Journal',Tickets:'Tickets',Contracts:'Contrats',Locations:'Emplacements',Trash:'Corbeille',Customization:'Personnalisation',NetworkScan:'Scan réseau',Heartbeat:'Supervision',BackupRestore:'Sauvegarde',Settings:'Paramètres',System:'Système',Employees:'Employés',Save:'Enregistrer',Add:'Ajouter',Edit:'Modifier',Delete:'Supprimer',Search:'Rechercher',Dashboard:'IT Guy // Matrice'}
};
// ---- column visibility (persisted) ----
// First-ever visit (nothing saved yet): show a concise, uncluttered default instead of
// every column — full detail is one click away via the Columns picker.
// Guard: if the stored value is invalid, fall back to ALL columns (full details).
// An empty array (e.g. from an old "NONE" click) must never blank the table.
const DEFAULT_VISIBLE_COLS=['AssetTag','Name','Type','Serial','Location','Status','EmployeeID'];
let VISIBLE_COLS = (()=>{
  try{
    const s=localStorage.getItem('itvault_cols');
    if(!s) return DEFAULT_VISIBLE_COLS;
    const v=JSON.parse(s);
    if(!Array.isArray(v) || v.length===0) return null;
    return v;
  }catch(e){ return null; }
})();
function visCols(){
  return (VISIBLE_COLS && VISIBLE_COLS.length) ? COLUMNS.filter(c=>VISIBLE_COLS.includes(c)) : COLUMNS.slice();
}
function saveVisCols(){
  try{ localStorage.setItem('itvault_cols', JSON.stringify(visCols())); }catch(e){}
}
function applyLanguage(lang){
  lang=lang||'en'; const d=I18N[lang]||I18N.en;
  document.documentElement.lang=lang;
  document.documentElement.dir=(lang==='ar')?'rtl':'ltr';
  document.querySelectorAll('[data-i18n]').forEach(el=>{
    const k=el.getAttribute('data-i18n'); if(!d[k])return;
    const icon=el.querySelector('.ni');
    if(icon){ let t=icon.nextSibling; if(t&&t.nodeType===3){t.textContent=d[k];}else{el.appendChild(document.createTextNode(d[k]));} }
    else { el.textContent=d[k]; }
  });
  document.title=d.Dashboard||document.title;
}
const STATUSES=['Available','Checked-Out','Under-Maintenance','Reserved','Retired','Lost/Stolen'];
{const _sf=document.getElementById('statusFilter'); if(_sf)_sf.innerHTML='<option value="">All statuses</option>'+STATUSES.map(s=>`<option>${s}</option>`).join('');}
const LABEL_FIELD_KEYS=['Name','Type','AssetID','Serial','Status','Location','ReceivedBy','ReceiverDate','EmployeeID','EmployeeName','Department','Warranty','PurchaseDate','Note'];
const ROLE_ADMIN='admin', ROLE_EDIT='read-write', ROLE_VIEW='read-only';
const ROLE_LABELS={'admin':'Admin','read-write':'Editor','read-only':'Read-only'};
const TICKET_STATUSES=['Open','In Progress','Pending','Resolved','Closed'];
const PRIORITIES=['Low','Normal','High','Urgent','Emergency'];
const TICKET_CATEGORIES=['Hardware','Software','Network','Access/Permissions','Email/Communication','Printer','CCTV/Security','Other'];
let assets=[],sortCol='',sortDir=1,groupBy='',expTimer=null,MY_ROLE=ROLE_VIEW;
// Per-module rights straight from /api/me. A custom role can grant tickets
// and nothing else, so the sidebar has to ask about the module rather than
// guess from the role name.
let MY_PERMS={};
// The individual permissions this role was granted (see FEATURE_GROUPS in
// app.py). Read through canDo() rather than directly.
let MY_FEATURES=[];
// Each settings section maps to one catalogue leaf, so a role can be given
// Branding and nothing else. My Account is everyone's -- it is where their own
// password and avatar live -- and the admin-only sections (Users, Database,
// Danger Zone) have no leaf on purpose: granting those is granting admin.
const SETTINGS_ALWAYS = ['account'];
const SETTINGS_FEATURE = {
  general: 'settings.general',
  branding: 'settings.branding',
  custom:   'settings.branding',
  notif:    'settings.email',
  sla:      'settings.sla',
  label:    'settings.labels',
  ldap:     'settings.ldap',
  unifi:    'settings.unifi',
};
function applySettingsPermissions(){
  const secOk = sec => SETTINGS_ALWAYS.indexOf(sec)>=0
    || (SETTINGS_FEATURE[sec] ? canDo(SETTINGS_FEATURE[sec]) : MY_ROLE===ROLE_ADMIN);
  const allowed = MY_ROLE===ROLE_ADMIN ? null
    : [...document.querySelectorAll('#cfgNav .cfgitem')].map(b=>b.dataset.sec).filter(secOk);
  document.querySelectorAll('#cfgNav .cfgitem').forEach(btn=>{
    const ok = !allowed || allowed.indexOf(btn.dataset.sec)>=0;
    btn.style.display = ok ? '' : 'none';
  });
  document.querySelectorAll('.cfg-sec').forEach(sec=>{
    if(allowed && allowed.indexOf(sec.dataset.sec)<0) sec.style.display='none';
  });
  // If the section on screen is now hidden, fall back to the first allowed one.
  if(allowed){
    const shown=[...document.querySelectorAll('.cfg-sec')]
      .find(s=>s.style.display!=='none' && allowed.indexOf(s.dataset.sec)>=0);
    if(!shown){
      const first=document.querySelector('#cfgNav .cfgitem[data-sec="account"]')
              || document.querySelector('#cfgNav .cfgitem:not([style*="none"])');
      if(first)first.click();
    }
  }
}

// Show only what this user can actually open. A role granted tickets and
// nothing else shouldn't see an Assets link that answers 403, and everyone
// keeps Settings because their own account lives in there.
function applyNavPermissions(){
  const show=(id,on)=>{const el=document.getElementById(id); if(el)el.style.display=on?'':'none';};

  // Main
  show('navAssets',    canSee('assets'));
  show('navContracts', canSee('contracts'));
  show('navTickets',   canSee('tickets'));

  // Records -- these are all views over assets/directory
  show('navDirectory', canSee('directory'));
  show('navAudit',     canDo('tools.audit'));

  // Tools
  show('navScan',      canDo('tools.scan'));
  show('navHeartbeat', canDo('tools.heartbeat'));
  show('navBackup',    canDo('tools.backup'));

  // Settings stays for everyone: My Account is in there. The page itself
  // hides the sections a user has no rights to.
  show('navSettings',  true);

  // Asset-page actions follow their own permission, so a role can be allowed
  // to add an asset without also being allowed to bulk-import or export one.
  show('navAdd',    canDo('assets.create'));
  show('navImport', canDo('assets.import'));
  show('navExport', canDo('assets.export'));
  show('navCatalog', canDo('assets.catalog'));
  show('navTrash',   canDo('assets.trash'));

  // Group headings are noise when everything under them is hidden.
  const groups=[
    ['Records', ['navDirectory','navCatalog','navTrash','navAudit']],
    ['Tools',   ['navScan','navHeartbeat','navBackup']],
  ];
  document.querySelectorAll('.nav-grp').forEach(g=>{
    const hit=groups.find(([name])=>g.textContent.trim()===name);
    if(!hit)return;
    const any=hit[1].some(id=>{const el=document.getElementById(id);return el&&el.style.display!=='none';});
    g.style.display=any?'':'none';
  });

  // If the landing page is one they can't see, move them somewhere they can.
  if(!canSee('assets')&&document.getElementById('page-assets')&&
     document.getElementById('page-assets').classList.contains('show')){
    if(canSee('tickets'))showPage('page-tickets'); else showPage('page-dashboard');
  }
}

function permOf(m){return (MY_PERMS&&MY_PERMS[m])||'none';}
function canSee(m){return MY_ROLE===ROLE_ADMIN||permOf(m)!=='none';}
function canWrite(m){return MY_ROLE===ROLE_ADMIN||permOf(m)==='write';}
// One catalogue leaf, e.g. canDo('tickets.delete'). The module helpers above
// answer "can they reach this area at all"; this answers "may they do this
// one thing", which is what a role built from individual permissions needs.
function canDo(f){return MY_ROLE===ROLE_ADMIN||MY_FEATURES.indexOf(f)>=0;}

const TIMEOUT_MS=5*60*1000;
let sessEnd=0;
function resetSessTimer(){ sessEnd=Date.now()+TIMEOUT_MS; }
function startSessBar(){
  clearInterval(expTimer);
  const bar=document.getElementById('sessBar');
  resetSessTimer();
  const tick=()=>{
    const left=sessEnd-Date.now();
    if(left<=0){location.href='/';return;}
    bar.style.width=(left/TIMEOUT_MS*100)+'%';
    bar.style.background = left<60000 ? 'linear-gradient(90deg,#ff3860,#ff2bd6)' : '';
  };
  tick(); expTimer=setInterval(tick,1000);
  // Any real interaction resets the idle clock, so an active user is never
  // logged out mid-task -- only genuine inactivity triggers the auto-logout.
  ['mousemove','keydown','click','scroll','touchstart'].forEach(ev=>
    document.addEventListener(ev, resetSessTimer, {passive:true})
  );
}

const cv=document.getElementById('bgCanvas'),ctx=cv.getContext('2d');let W,H,cols,drops;
function resize(){W=cv.width=innerWidth;H=cv.height=innerHeight;cols=Math.floor(W/18);drops=Array(cols).fill(0).map(()=>Math.random()*H);}
resize();addEventListener('resize',resize);
const glyphs="01ｱｲｳｴｵｶｷｸアイウ01ITGUY".split("");
let matrixOn=false;  /* matrix rain retired with the pro theme */
function drawMatrix(){
  if(!matrixOn){ctx.clearRect(0,0,W,H);return;}
  ctx.fillStyle="rgba(10,13,19,0.18)";ctx.fillRect(0,0,W,H);ctx.font="13px 'Share Tech Mono'";
  for(let i=0;i<cols;i++){const ch=glyphs[Math.floor(Math.random()*glyphs.length)],x=i*18,y=drops[i];
  ctx.fillStyle=Math.random()>.98?"rgba(124,92,255,.5)":"rgba(59,158,255,.35)";ctx.fillText(ch,x,y);drops[i]=y>H&&Math.random()>.975?0:y+18;}
}

function esc(v){return(v==null?'':String(v)).replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function statusClass(s){s=(s||'').toLowerCase();return s==='reserved'?'s-reserved':s==='retired'?'s-retired':s==='lost/stolen'?'s-lost':'s-default';}
function toast(m){const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),1800);}
// Every request in the app goes through here, which makes it the one place
// that can guarantee a failure is never silent. fetch() REJECTS on a dropped
// connection, a reset by a proxy or tunnel, or a mixed-content block -- and an
// async click handler that rejects shows the user absolutely nothing. That is
// what "I press save and nothing happens" was: not a server that refused the
// request, but a request whose failure had nowhere to go.
async function api(u,opt){
  let r;
  try{
    r=await fetch(u,opt);
  }catch(e){
    toast('✕ NO RESPONSE FROM SERVER — '+((e&&e.message)||'connection failed'));
    console.error('api() failed',u,e);
    return null;
  }
  if(r.status===401){location.href='/';return null;}
  return r;
}

// A failing response is not necessarily JSON. Anything in front of the app --
// a reverse proxy, a Cloudflare tunnel -- answers with HTML, and calling
// r.json() on that threw inside the very branch meant to report the error, so
// the user saw nothing. Falls back to the status line, which is always there.
async function apiError(r){
  if(!r) return 'no response';
  try{
    const j=await r.json();
    if(j && j.error) return j.error;
  }catch(e){}
  return ('HTTP '+r.status+' '+(r.statusText||'')).trim();
}
function canEdit(){return MY_ROLE===ROLE_ADMIN||MY_ROLE===ROLE_EDIT;}
function toggleSelectAll(checked){
  document.querySelectorAll('.row-chk').forEach(cb=>{cb.checked=checked;});
  updateSelBtns();
}
function updateSelBtns(){
  const n=document.querySelectorAll('.row-chk:checked').length;
  const dsb=document.getElementById('delSelBtn');
  if(dsb){ dsb.style.display = (n>0 && canEdit())?'inline-flex':'none'; dsb.textContent = `Delete selected (${n})`; }
}
let undoTimer=null, undoIds=[];
function showUndoBar(ids, label){
  const bar=document.getElementById('undoBar'); if(!bar) return;
  bar.innerHTML=`<span class="ub-msg">🗑 ${ids.length} asset${ids.length>1?'s':''} deleted${label?` (${label})`:''} — recoverable for 2 min</span><button class="ub-undo" id="undoBtn">↩ UNDO</button>`;
  bar.style.display='flex';
  document.getElementById('undoBtn').onclick=()=>undoDelete();
  if(undoTimer) clearTimeout(undoTimer);
  undoTimer=setTimeout(()=>{ undoIds=[]; bar.style.display='none'; }, 120000);
}
async function undoDelete(){
  if(!undoIds.length) return;
  for(const id of undoIds){ await api('/api/assets/'+id+'/restore',{method:'POST'}); }
  const n=undoIds.length; undoIds=[];
  if(undoTimer) clearTimeout(undoTimer);
  const bar=document.getElementById('undoBar'); if(bar) bar.style.display='none';
  toast('↩ RESTORED '+n+' asset'+(n>1?'s':''));
  load(); loadDashboard();
}
async function deleteSelected(){
  const ids=[...document.querySelectorAll('.row-chk:checked')].map(cb=>cb.dataset.id);
  if(!ids.length){ toast('No assets selected'); return; }
  if(!confirm(`Delete ${ids.length} selected asset(s)? They go to Trash (recoverable 2 min via UNDO).`)) return;
  let ok=0;
  for(const id of ids){ const r=await api('/api/assets/'+id,{method:'DELETE'}); if(r&&r.ok) ok++; }
  if(ok){ undoIds=ids.slice(); showUndoBar(ids); load(); loadDashboard(); }
  else toast('✕ delete failed');
}
// Shared print/PDF header: if a letterhead (PDF or image, normalized to
// /letterhead.png on upload) is configured in Branding, every printed sheet
// uses it as the header instead of the plain logo+name bar.
// Letterhead is a whole printed page (rasterized from the uploaded PDF's
// first page, or the image as-is), so it has to act as a full-page
// background -- position:fixed makes Chrome's print engine repeat it behind
// every printed page -- with real content pushed down below its header art,
// NOT stacked inline above the content (that was the "not aligned" bug:
// a full A4-shaped image at width:100% renders ~277mm tall inline, so it
// swallowed the whole first page on its own).
const LETTERHEAD_CLEARANCE_MM=38;
// Waits for the letterhead image specifically (not just window.onload, which
// can fire before a slow/remote-hosted image is actually painted -- that was
// the "letterhead pops in a few seconds after the print dialog" bug on a
// real deployment where images load slower than on localhost) before
// triggering print, so what's on screen when print fires already has it.
function printReadyScript(){
  if(window.HAS_LETTERHEAD){
    return `<script>(function(){
      var img=document.querySelector('img[src*="/letterhead.png"]');
      function go(){ setTimeout(function(){ window.print(); }, 30); }
      if(img && !img.complete){ img.addEventListener('load',go); img.addEventListener('error',go); }
      else { go(); }
    })();<\/script>`;
  }
  return `<script>setTimeout(function(){ window.print(); }, 100);<\/script>`;
}
function printHeaderHtml(title){
  if(window.HAS_LETTERHEAD){
    return `<img src="/letterhead.png?t=${Date.now()}" style="position:fixed;top:0;left:0;width:210mm;height:297mm;object-fit:fill;z-index:-1">`+
      (title?`<h2 style="margin:${LETTERHEAD_CLEARANCE_MM}mm 0 10px">${title}</h2>`:`<div style="margin-top:${LETTERHEAD_CLEARANCE_MM}mm"></div>`);
  }
  return `<div class="phead"><img src="/logo.png" onerror="this.style.display='none'"><h2 style="margin:0">${title}</h2></div>`;
}
function printSelected(){
  const ids=[...document.querySelectorAll('.row-chk:checked')].map(cb=>cb.dataset.id);
  if(!ids.length){toast('No assets selected');return;}
  const rows=ids.map(id=>assets.find(a=>a._id===id)).filter(Boolean);
  const win=window.open('','_blank');
  win.document.write(`<html><head><title>Print Assets</title><style>
    @page{size:A4;margin:${window.HAS_LETTERHEAD?'0':'14mm'}}
    body{font-family:Arial,sans-serif;padding:20px}
    .phead{display:flex;align-items:center;gap:12px;margin-bottom:6px}
    .phead img{height:36px}
    table{width:100%;border-collapse:collapse;margin-top:20px}
    th,td{text-align:left;padding:6px;border-bottom:1px solid #ddd}
    td:first-child{font-weight:800;font-family:ui-monospace,Consolas,monospace}
  </style></head><body>${printHeaderHtml((window.APP_NAME||'IT-Vault')+' — Selected Assets')}<table><thead><tr>${COLUMNS.map(c=>`<th>${LABELS[c]||c}</th>`).join('')}</tr></thead><tbody>${rows.map(a=>`<tr>${COLUMNS.map(c=>`<td>${esc(a[c])}</td>`).join('')}</tr>`).join('')}</tbody></table>${printReadyScript()}</body></html>`);
  win.document.close();
}
function printQRSelected(){
  const ids=[...document.querySelectorAll('.row-chk:checked')].map(cb=>cb.dataset.id);
  if(!ids.length){toast('No assets selected');return;}
  window.open('/labels?ids='+ids.map(encodeURIComponent).join(','),'_blank');
}
function printGroup(safeKey){
  if(!window.__groups)return;
  const k=window.__groupKeys.find(x=>x.replace(/[^a-zA-Z0-9_-]/g,'_')===safeKey);
  const rows=window.__groups[k]||[];
  const win=window.open('','_blank');
  win.document.write(`<html><head><title>Print Group - ${esc(k)}</title><style>
    @page{size:A4;margin:${window.HAS_LETTERHEAD?'0':'14mm'}}
    body{font-family:Arial,sans-serif;padding:20px}
    .phead{display:flex;align-items:center;gap:12px;margin-bottom:4px}
    .phead img{height:36px}
    h2{margin:0}
    .sub{color:#666;margin-bottom:14px;font-size:13px}
    table{width:100%;border-collapse:collapse;margin-top:10px}
    th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #ddd;font-size:13px}
    th{background:#f3f3f3}
    td:first-child{font-weight:800;font-family:ui-monospace,Consolas,monospace}
    @media print{body{padding:0}button{display:none}}
  </style></head><body>${printHeaderHtml('Asset Group: '+esc(LABELS[groupBy]||groupBy)+' — '+esc(k))}<div class="sub">${rows.length} asset${rows.length>1?'s':''} • generated ${new Date().toLocaleString()}</div><table><thead><tr>${COLUMNS.map(c=>`<th>${LABELS[c]||c}</th>`).join('')}</tr></thead><tbody>${rows.map(a=>`<tr>${COLUMNS.map(c=>`<td>${esc(a[c])}</td>`).join('')}</tr>`).join('')}</tbody></table><button onclick="window.print()">🖨 PRINT</button>${printReadyScript()}</body></html>`);
  win.document.close();
}
function warrantyEnd(a){
  if(!a.PurchaseDate)return null;
  const pd=new Date(a.PurchaseDate); if(isNaN(pd))return null;
  const wm=parseInt(a.WarrantyMonths||'12',10);
  const end=new Date(pd); end.setMonth(end.getMonth()+wm);
  const today=new Date(); today.setHours(0,0,0,0);
  const diff=Math.ceil((end-today)/(1000*60*60*24));
  return {end: end.toISOString().slice(0,10), expiring: diff>=0 && diff<=30};
}

/* ---------- employees ---------- */
let employees=[];
async function loadEmployees(){
  const r=await api('/api/employees'); employees=r?await r.json():[];
  const q=(document.getElementById('empSearch').value||'').trim().toLowerCase();
  const list=(employees||[]).filter(e=>[e.EmployeeName,e.EmployeeID,e.EmpCode,e.Department,e.Designation,e.Email].some(v=>(v||'').toLowerCase().includes(q)));
  renderEmployees(list);
}
function tempEmpId(e){
  // No real HR-assigned employee number is synced from AD (EmployeeID there is
  // just the AD username) -- derive a stable placeholder ID from the row's
  // internal _id so it stays put across searches/re-renders/sort order.
  const h=(e._id||'').replace(/-/g,'').slice(-6).toUpperCase()||'000000';
  return 'EMP-'+h;
}
function renderEmployees(list){
  const tbody=document.getElementById('empBody');
  document.getElementById('empEmpty').style.display=list.length?'none':'block';
  tbody.innerHTML=list.map(e=>`<tr>
    <td class="${e.EmpCode?'':'muted'} mono">${esc(e.EmpCode)||tempEmpId(e)}</td>
    <td>${esc(e.EmployeeID)}</td>
    <td>${esc(e.EmployeeName)}</td>
    <td>${esc(e.Department)}</td>
    <td>${esc(e.Designation)}</td>
    <td>${esc(e.Email)}</td>
    <td>${esc(e.source||'manual')}</td>
    <td><div class="row-actions">
      <button class="btn sm ghost" onclick="openEmpModal('${e._id}')">EDIT</button>
      <button class="btn sm danger" onclick="delEmployee('${e._id}')">DEL</button>
    </div></td>
  </tr>`).join('');
}
async function delEmployee(id){
  const e=employees.find(x=>x._id===id);
  if(!confirm('Delete employee "'+(e?e.EmployeeName||e.EmployeeID:'this employee')+'"? Any assets assigned to them will be unassigned.'))return;
  const r=await api('/api/employees/'+id,{method:'DELETE'});
  if(r&&r.ok){toast('✓ EMPLOYEE DELETED');loadEmployees();load();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}

let editingEmpId=null;
async function openEmpModal(id){
  editingEmpId=id; const e=(id?employees.find(x=>x._id===id):{})||{};
  document.getElementById('empModalTitle').textContent=id?'EDIT EMPLOYEE':'ADD EMPLOYEE';
  const empIdEl=document.getElementById('e_EmpCode');
  if(id){
    empIdEl.value=e.EmpCode||'';
    empIdEl.placeholder=e.EmpCode?'':('auto: '+tempEmpId(e));
  }else{
    empIdEl.value='';
    empIdEl.placeholder='…';
    const r=await api('/api/employees/next-code');
    if(r&&r.ok){ const j=await r.json(); empIdEl.value=j.code||''; }
  }
  document.getElementById('e_EmployeeID').value=e.EmployeeID||'';
  document.getElementById('e_EmployeeName').value=e.EmployeeName||'';
  document.getElementById('e_Email').value=e.Email||'';
  document.getElementById('empModal').classList.add('show');
  loadDepartmentOptions(e.Department||'');
  loadDesignationOptions(e.Designation||'');
}
// populate the Department <select> on the Employee form from the Departments
// reference table, auto-adding it if it's genuinely new (e.g. an existing
// employee's Department value from before this became a picker)
async function loadDepartmentOptions(selDept){
  const sel=document.getElementById('e_Department'); if(!sel)return;
  let deps=[];
  try{
    const r=await api('/api/departments'); deps=r?await r.json():[];
    if(selDept && !deps.some(d=>d.name===selDept)){
      const r2=await api('/api/departments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:selDept})});
      if(r2&&r2.ok){ const r3=await api('/api/departments'); deps=r3?await r3.json():deps; }
    }
  }catch(e){}
  sel.innerHTML='<option value="">-- select department --</option>'+deps.map(d=>`<option value="${esc(d.name)}" ${d.name===selDept?'selected':''}>${esc(d.name)}</option>`).join('')+'<option value="__new">＋ type new…</option>';
  sel.onchange=async()=>{
    if(sel.value==='__new'){const v=prompt('New department name:'); if(v&&v.trim()){const r=await api('/api/departments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:v.trim()})}); if(r&&r.ok){await loadDepartmentOptions(v.trim());}} else {sel.value=selDept;}}
  };
}
async function loadDesignationOptions(selDes){
  const sel=document.getElementById('e_Designation'); if(!sel)return;
  let dess=[];
  try{
    const r=await api('/api/designations'); dess=r?await r.json():[];
    if(selDes && !dess.some(d=>d.name===selDes)){
      const r2=await api('/api/designations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:selDes})});
      if(r2&&r2.ok){ const r3=await api('/api/designations'); dess=r3?await r3.json():dess; }
    }
  }catch(e){}
  sel.innerHTML='<option value="">-- select designation --</option>'+dess.map(d=>`<option value="${esc(d.name)}" ${d.name===selDes?'selected':''}>${esc(d.name)}</option>`).join('')+'<option value="__new">＋ type new…</option>';
  sel.onchange=async()=>{
    if(sel.value==='__new'){const v=prompt('New designation name:'); if(v&&v.trim()){const r=await api('/api/designations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:v.trim()})}); if(r&&r.ok){await loadDesignationOptions(v.trim());}} else {sel.value=selDes;}}
  };
}
async function saveEmployee(){
  const body={
    EmployeeID:document.getElementById('e_EmployeeID').value.trim(),
    EmpCode:document.getElementById('e_EmpCode').value.trim(),
    EmployeeName:document.getElementById('e_EmployeeName').value.trim(),
    Department:document.getElementById('e_Department').value.trim(),
    Designation:document.getElementById('e_Designation').value.trim(),
    Email:document.getElementById('e_Email').value.trim()
  };
  if(!body.EmployeeID&&!body.EmployeeName){toast('ID or Name required');return;}
  const r=editingEmpId
    ? await api('/api/employees/'+editingEmpId,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    : await api('/api/employees',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r&&r.ok){toast('✓ EMPLOYEE SAVED');document.getElementById('empModal').classList.remove('show');loadEmployees();load();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}

let ldapResults=[];
function openLdapImport(){
  ldapResults=[];
  const st=document.getElementById('ldapStatus'); if(st)st.textContent='';
  document.getElementById('ldapModal').classList.add('show');
}
async function doLdapSearch(){
  const q=document.getElementById('ldapQ').value.trim();
  if(!q){toast('Enter search term');return;}
  document.getElementById('ldapStatus').textContent='Searching LDAP…';
  const r=await api('/api/ldap/search?q='+encodeURIComponent(q));
  if(!r){document.getElementById('ldapStatus').textContent='failed';return;}
  const j=await r.json();
  ldapResults=j.results||[];
  document.getElementById('ldapStatus').textContent=`Found ${ldapResults.length}`;
}
async function doLdapImport(){
  await syncLdap();
}
async function syncLdap(){
  document.getElementById('ldapStatus').textContent='Syncing from Active Directory…';
  const r=await api('/api/employees/ldap-sync',{method:'POST'});
  if(r&&r.ok){const j=await r.json();document.getElementById('ldapStatus').textContent=`✓ Synced: ${j.added} added, ${j.updated} updated (${j.total} users)`;toast('✓ LDAP SYNCED');loadEmployees();}
  else if(r){const j=await r.json().catch(()=>({}));document.getElementById('ldapStatus').textContent='✕ '+(j.error||'failed');toast('✕ '+(j.error||'failed'));}
}

/* ---------- assets ---------- */
const DEBUG = (location.search.indexOf('debug=1')>=0) || (localStorage.getItem('itvault_debug')==='1');
if(location.search.indexOf('debug=1')>=0){ try{ localStorage.setItem('itvault_debug','1'); }catch(e){} }
function dbg(msg){ if(!DEBUG) return; let d=document.getElementById('dbgBox'); if(!d){d=document.createElement('div');d.id='dbgBox';d.style.cssText='position:fixed;left:8px;bottom:8px;z-index:99999;max-width:60vw;background:#101622;color:#7CFFB2;border:1px solid #2bd6a0;font:12px/1.4 monospace;padding:8px 10px;white-space:pre-wrap;border-radius:6px;opacity:.95';document.body.appendChild(d);} d.textContent='[DBG] '+msg+'\n'+d.textContent; }
function showAssetError(msg){ try{ const e=document.getElementById('empty'); if(e){ e.style.display='block'; e.style.color='#ff6b8a'; e.style.padding='20px'; e.textContent='⚠ ASSET LOAD FAILED: '+msg; } }catch(_){} }
function showCustomError(msg){ try{ const e=document.getElementById('cfgCustomSec'); if(e){ let b=document.getElementById('customErr'); if(!b){b=document.createElement('div');b.id='customErr';b.style.cssText='background:#2a0e16;color:#ff6b8a;border:1px solid #ff3860;padding:12px 14px;border-radius:8px;margin:12px 0;font:13px monospace';e.insertBefore(b,e.firstChild);} b.textContent='⚠ CUSTOMIZATION LOAD FAILED: '+msg; } }catch(_){} }
async function load(){
  console.log('[ITGUY] load start');
  dbg('load() called');
  let r;
  try{ r=await api('/api/assets'+location.search); }
  catch(e){ dbg('FETCH ERROR: '+e.message); showAssetError('network/fetch error: '+e.message); console.error(e); return; }
  if(!r){dbg('api() returned null (likely 401 -> redirected)');showAssetError('unauthorized (api returned null)');return;}
  dbg('api /api/assets status='+r.status);
  if(!r.ok){ dbg('api not ok: '+r.status); showAssetError('API HTTP '+r.status); return; }
  assets=await r.json();
  dbg('assets parsed: '+(Array.isArray(assets)?assets.length:'NOT ARRAY'));
  render();
}
// ---- row action overflow menu: every row action lives in one dropdown behind
// a single ⋮ button, so every row is pixel-identical regardless of asset state.
// Rendered into a single shared, fixed-position element (outside the scrolling
// table) so it can never get clipped by .tablewrap's overflow, and repositioned
// against whichever "⋮" button was clicked.
let rowMenuAssetId=null;
function toggleRowMenu(e,id){
  e.stopPropagation();
  const menu=document.getElementById('rowMenu');
  if(rowMenuAssetId===id && menu.style.display!=='none'){ menu.style.display='none'; rowMenuAssetId=null; return; }
  rowMenuAssetId=id;
  const a=assets.find(x=>x._id===id);
  // Checkout / Check-in and Maintenance now live inside the Edit form itself
  // (STATUS & ASSIGNMENT / MAINTENANCE sections), so the row menu only keeps
  // the one-click CHECK-IN shortcut -- everything else routes through EDIT.
  const checkoutItem=a&&a.Status==='Checked-Out'
    ?`<button onclick="closeRowMenu();checkinAsset('${id}')">CHECK-IN</button>`
    :'';
  menu.innerHTML=`
    <button onclick="closeRowMenu();editRow('${id}')">EDIT</button>
    ${checkoutItem}
    <button onclick="closeRowMenu();openSign('${id}')">SIGN</button>
    <button onclick="closeRowMenu();openQR('${id}')">QR</button>
    <button onclick="closeRowMenu();printAsset('${id}')">PRINT</button>
    <div class="row-menu-sep"></div>
    <button class="danger" onclick="closeRowMenu();delRow('${id}')">DELETE</button>`;
  const btn=e.currentTarget.getBoundingClientRect();
  menu.style.display='flex';
  const menuRect=menu.getBoundingClientRect();
  let left=btn.right-menuRect.width;
  if(left<8) left=8;
  let top=btn.bottom+4;
  if(top+menuRect.height>window.innerHeight-8) top=btn.top-menuRect.height-4;
  menu.style.left=left+'px'; menu.style.top=top+'px';
}
function closeRowMenu(){ const menu=document.getElementById('rowMenu'); if(menu){menu.style.display='none';} rowMenuAssetId=null; }
document.addEventListener('click',(e)=>{ const menu=document.getElementById('rowMenu'); if(menu && menu.style.display!=='none' && !menu.contains(e.target) && !e.target.classList.contains('row-more')) closeRowMenu(); });
window.toggleRowMenu=toggleRowMenu; window.closeRowMenu=closeRowMenu;
function render(){
  console.log('[ITGUY] render', assets.length, 'assets');
  const q=document.getElementById('search').value.trim().toLowerCase();
  const sf=document.getElementById('statusFilter').value;
  let rows=assets.filter(a=>{
    if(sf&&(a.Status||'')!==sf)return false;
    if(q){const hay=Object.values(a).join(' ');if(!hay.toLowerCase().includes(q))return false;}
    return true;
  });
  if(sortCol)rows.sort((a,b)=>{const x=(a[sortCol]||'').toString().toLowerCase(),y=(b[sortCol]||'').toString().toLowerCase();return(x<y?-1:x>y?1:0)*sortDir;});
  const head=document.getElementById('head'),body=document.getElementById('body');
  const VC=visCols();
  head.innerHTML='<th><input type="checkbox" id="chkAll"/></th>' + VC.map(c=>`<th data-c="${c}">${LABELS[c]||c}${sortCol===c?(sortDir>0?' ▲':' ▼'):''}</th>`).join('')+(canEdit()?'<th>ACTIONS</th>':'');
  document.getElementById('chkAll').addEventListener('change',e=>{toggleSelectAll(e.target.checked);});
  head.querySelectorAll('th[data-c]').forEach(th=>th.onclick=()=>{const c=th.dataset.c;if(sortCol===c)sortDir*=-1;else{sortCol=c;sortDir=1;}render();});
  const rowHtml=a=>`<tr data-id="${a._id}"><td><input type="checkbox" class="row-chk" data-id="${a._id}" onchange="updateSelBtns()"/></td>${
    VC.map(c=>{
      if(c==='AssetTag'){
        return `<td class="mono">${esc(a.AssetTag||a._id)}</td>`;
      }
      if(c==='Status'){
        const col=a.Status==='Available'?'var(--grn)':a.Status==='Checked-Out'?'var(--cyan)':a.Status==='Under-Maintenance'?'var(--amber)':a.Status==='Reserved'?'var(--muted)':'var(--red)';
        return `<td><span class="status ${statusClass(a.Status)}"><span class="sev" style="color:${col}"></span>${esc(a.Status||'')}</span></td>`;
      }
      if(c==='WarrantyMonths'){
        const w=warrantyEnd(a);
        return `<td>${a.WarrantyMonths||12} mo${w?`<br><small style="color:${w.expiring?'var(--amber)':'var(--muted)'}">${w.end}</small>`:''}</td>`;
      }
      if(c==='Price'){
        return `<td class="mono">${fmtMoney(a.Price||0, CURRENCY)}</td>`;
      }
      if(c==='EmployeeID'){
        const eid=a[c]||'';
        if(!eid) return `<td><span class="muted">—</span></td>`;
        const emp=employees.find(e=>e.EmployeeID===eid);
        return `<td>${emp?esc(emp.EmployeeName||eid):`<span class="mono">${esc(eid)}</span>`}</td>`;
      }
      return `<td>${esc(a[c])}</td>`;
    }).join('')
  }${(canEdit()?`<td><div class="row-actions">
        <button class="btn sm ghost row-more" onclick="toggleRowMenu(event,'${a._id}')" aria-label="Actions">⋮</button></td>`:(MY_ROLE===ROLE_VIEW?`<td><div class="row-actions"><button class="btn sm ghost" onclick="openQR('${a._id}')">QR</button><button class="btn sm ghost" onclick="printAsset('${a._id}')">PRINT</button></div></td>`:''))}</tr>`;
  if(groupBy){
    // group rows by the chosen column
    const groups={};
    rows.forEach(a=>{const k=(a[groupBy]||'—').toString();(groups[k]=groups[k]||[]).push(a);});
    const keys=Object.keys(groups).sort((x,y)=>x.toLowerCase()<y.toLowerCase()?-1:1);
    body.innerHTML=keys.map(k=>{
      const g=groups[k];
      const safe=k.replace(/[^a-zA-Z0-9_-]/g,'_');
      return `<tr class="group-head"><td colspan="${VC.length+2}"><span class="gh-label">▣ ${esc(LABELS[groupBy]||groupBy)}: ${esc(k)}</span><span class="gh-count">${g.length} asset${g.length>1?'s':''}</span><button class="btn sm ghost gh-print" data-g="${esc(safe)}" onclick="printGroup('${esc(safe)}')">🖨 PRINT GROUP</button></td></tr>`+g.map(rowHtml).join('');
    }).join('');
    // stash grouped data for print
    window.__groups=groups; window.__groupKeys=keys;
  } else {
    body.innerHTML=rows.map(rowHtml).join('');
    window.__groups=null;
  }
  document.getElementById('count').textContent=`${rows.length} of ${assets.length} assets`;
  document.getElementById('empty').style.display=assets.length?'none':'block';
  syncHScroll();
  document.getElementById('stTotal').textContent=assets.length;
  document.getElementById('addBtn2').style.display=canEdit()?'':'none';
  document.getElementById('importBtn2').style.display=canEdit()?'':'none';
  const na=document.getElementById('navAdd'); if(na) na.style.display=canEdit()?'':'none';
  const ni=document.getElementById('navImport'); if(ni) ni.style.display=canEdit()?'':'none';
  const pb=document.getElementById('printSelBtn'); if(pb) pb.onclick=printSelected;
  const qb=document.getElementById('qrSelBtn'); if(qb) qb.onclick=printQRSelected;
  const dsb=document.getElementById('delSelBtn'); if(dsb) dsb.onclick=deleteSelected;
  updateSelBtns();
  // ---- column visibility popover ----
  const colBtn=document.getElementById('colToggleBtn'), colPop=document.getElementById('colPop');
  if(colBtn && colPop){
    function buildColPop(){
      colPop.innerHTML='<div class="cp-title">Show columns</div>'+
        '<div class="cp-grid">'+COLUMNS.map(c=>`<label class="cp-item"><input type="checkbox" data-c="${c}" ${visCols().includes(c)?'checked':''}><span>${LABELS[c]||c}</span></label>`).join('')+'</div>'+
        '<div class="cp-actions"><button class="btn sm ghost" id="colAll">SHOW ALL</button><button class="btn sm ghost" id="colNone">RESET</button></div>';
      colPop.querySelectorAll('input[data-c]').forEach(ch=>ch.onchange=()=>{
        const sel=COLUMNS.filter(x=>colPop.querySelector(`input[data-c="${x}"]`).checked);
        VISIBLE_COLS=sel; saveVisCols(); render(); syncHScroll();
      });
      colPop.querySelector('#colAll').onclick=()=>{VISIBLE_COLS=null;saveVisCols();render();syncHScroll();buildColPop();};
      colPop.querySelector('#colNone').onclick=()=>{VISIBLE_COLS=DEFAULT_VISIBLE_COLS.slice();saveVisCols();render();syncHScroll();buildColPop();};
    }
    colBtn.onclick=(e)=>{e.stopPropagation(); const open=colPop.style.display!=='none'; if(open){colPop.style.display='none';}else{buildColPop();colPop.style.display='block';} };
    document.addEventListener('click',(e)=>{ if(colPop.style.display!=='none' && !colPop.contains(e.target) && e.target!==colBtn) colPop.style.display='none'; });
  }
  // ---- top horizontal scrollbar sync ----
  if(!window.__hscrollWired){
    const tw=document.getElementById('tablewrap'), hs=document.getElementById('hscroll');
    if(tw&&hs){
      hs.addEventListener('scroll',()=>{ document.getElementById('tablewrap').scrollLeft=hs.scrollLeft; });
      tw.addEventListener('scroll',()=>{ document.getElementById('hscroll').scrollLeft=tw.scrollLeft; });
      window.__hscrollWired=true;
    }
  }
}
function syncHScroll(){
  const tw=document.getElementById('tablewrap'), hs=document.getElementById('hscroll'), hsin=document.getElementById('hscrollIn');
  if(!tw||!hs||!hsin) return;
  hsin.style.width=tw.scrollWidth+'px';
  hs.scrollLeft=tw.scrollLeft;
}
  const gb=document.getElementById('groupBy'); if(gb){gb.value=groupBy; gb.onchange=()=>{groupBy=gb.value; render();};}
/* Fills BOTH the dashboard KPI row and the Assets-page stat cards from one
   payload, so the two screens can never disagree. Previously only kTotal..kWarr
   and stTotal were written -- stOut/stMaint/stDue/stWarr were never touched by
   any code and sat on their hardcoded 0 forever. */
function setKV(id,v){ const e=document.getElementById(id); if(e) e.textContent=v; }
async function loadStats(){
  const r=await api('/api/dashboard'); if(!r)return null; const d=await r.json();
  setKV('kTotal',d.total);  setKV('kOut',d.checked_out);  setKV('kMaint',d.maintenance);
  setKV('kDue',d.due_soon); setKV('kWarr',d.warranty_expiring);
  setKV('stTotal',d.total); setKV('stOut',d.checked_out); setKV('stMaint',d.maintenance);
  setKV('stDue',d.due_soon);setKV('stWarr',d.warranty_expiring);
  return d;
}
async function loadDashboard(){
  const d=await loadStats(); if(!d)return;
  renderBars('statusBars', d.by_status||{}, statusColor);
  renderBars('typeBars', d.by_type||{}, ()=> 'var(--accent)');
  renderBars('contractsBars', d.contracts_by_type||{}, ()=> 'var(--accent2)');
  const exp=d.expiring_contracts||[];
  const eb=document.getElementById('dashContractsExpBody');
  if(eb) eb.innerHTML=exp.map(c=>`<tr style="cursor:pointer" onclick="showPage('page-contracts');openContractModal(${c.id})"><td>${esc(c.name)}</td><td>${esc(c.vendor||'—')}</td><td>${esc(c.type||'—')}</td><td>${esc(c.end_date||'—')}</td><td>${c.days_left}d</td></tr>`).join('');
  const ee=document.getElementById('dashContractsExpEmpty'); if(ee) ee.style.display=exp.length?'none':'block';
  applyDashLayout();
  // the cached copy has already painted; this corrects it from the server
  syncDashLayout();
  loadDashHeartbeat();
  // widget bodies (recent assets / open tickets / activity) must refresh too --
  // previously these only reloaded when you navigated to the page
  loadDashboardPage();
}
function statusColor(s){
  return ({'Available':'var(--grn)','Checked-Out':'var(--cyan)','Under-Maintenance':'var(--amber)','Reserved':'var(--muted)','Retired':'var(--red)','Lost/Stolen':'var(--red)'})[s]||'var(--accent2)';
}
function renderBars(elId, obj, colorFn){
  const el=document.getElementById(elId); if(!el) return;
  const entries=Object.entries(obj).sort((a,b)=>b[1]-a[1]);
  const max=Math.max(1,...entries.map(e=>e[1]));
  if(!entries.length){ el.innerHTML='<div class="empty" style="padding:18px">No data yet.</div>'; return; }
  el.innerHTML=entries.map(([k,v])=>`<div class="bar"><div class="bar-top"><span>${esc(k)}</span><b>${v}</b></div><div class="bar-track"><div class="bar-fill" style="width:${Math.round(v/max*100)}%;background:${colorFn(k)}"></div></div></div>`).join('');
}
async function loadDashboardPage(){
  // recent assets
  try{
    const r=await api('/api/assets?order=recent'); if(r){ const list=await r.json(); const top=(list||[]).slice(0,12);
      const tb=document.getElementById('dashRecentBody');
      if(tb) tb.innerHTML=top.map(a=>`<tr><td>${esc(a.Name||'')}</td><td>${esc(a.Type||'')}</td><td class="mono">${esc(a.Serial||'')}</td><td>${esc(a.Status||'')}</td></tr>`).join('')||'';
      const emp=document.getElementById('dashRecentEmpty'); if(emp) emp.style.display=top.length?'none':'block';
    }
  }catch(e){}
  // open tickets
  try{
    const r=await api('/api/tickets'); if(r){ const list=await r.json(); const open=(list||[]).filter(t=>!['Resolved','Closed'].includes(t.status));
      const tb=document.getElementById('dashTicketsBody');
      if(tb) tb.innerHTML=open.slice(0,12).map(t=>`<tr style="cursor:pointer" onclick="openTicketById(${t.id})"><td class="mono">${esc(t.code||'')}</td><td>${esc(t.subject||'')}</td><td>${esc(t.status||'')}</td></tr>`).join('')||'';
      const emp=document.getElementById('dashTicketsEmpty'); if(emp) emp.style.display=open.length?'none':'block';
    }
  }catch(e){}
  // recent activity (audit)
  try{
    const r=await api('/api/audit'); if(r){ const list=await r.json(); const top=(list||[]).slice(0,10);
      const fb=document.getElementById('dashFeed');
      if(fb) fb.innerHTML=top.map(a=>`<div class="feed-item"><span class="fi-dot"></span><div class="fi-body"><div class="fi-text"><b>${esc(a.actor||'system')}</b> ${esc(a.action||'')} ${a.asset_id?('<span class=\"mono\">'+esc(a.asset_id)+'</span>'):''}</div><div class="fi-meta">${esc(a.ts||'')}</div></div></div>`).join('')||'';
      const emp=document.getElementById('dashFeedEmpty'); if(emp) emp.style.display=top.length?'none':'block';
    }
  }catch(e){}
  loadUnifiWidgets();
}
// UniFi Controller dashboard widgets (device list + active clients) --
// pass force=true to bypass the backend's short-lived cache (e.g. a manual refresh)
async function loadUnifiWidgets(force){
  const unifiEmptyMsg=(el,err,emptyText)=>{
    if(!el)return;
    if(err==='not_configured'){ el.textContent='UniFi Controller not configured — set it up in Settings ▸ UniFi Controller'; el.style.display='block'; }
    else if(err){ el.textContent='✕ '+err; el.style.display='block'; }
    else { el.textContent=emptyText; }
  };
  try{
    const r=await api('/api/unifi/devices'+(force?'?force=1':''));
    if(r){
      const j=await r.json(); const list=j.devices||[];
      const tb=document.getElementById('unifiDevicesBody');
      if(tb) tb.innerHTML=list.map(d=>`<tr><td>${esc(d.name)}</td><td>${esc(d.type)}</td><td class="mono">${esc(d.ip)}</td><td>${d.num_sta||0}</td><td>${d.online?'<span style="color:var(--grn)">● Online</span>':'<span style="color:var(--red)">● Offline</span>'}</td></tr>`).join('');
      const emp=document.getElementById('unifiDevicesEmpty');
      if(emp){ emp.style.display=(j.error||!list.length)?'block':'none'; unifiEmptyMsg(emp,j.error,'NO DEVICES'); }
    }
  }catch(e){}
  try{
    const r=await api('/api/unifi/clients'+(force?'?force=1':''));
    if(r){
      const j=await r.json(); const list=j.clients||[];
      const tb=document.getElementById('unifiClientsBody');
      if(tb) tb.innerHTML=list.map(c=>`<tr><td>${esc(c.hostname)}</td><td class="mono">${esc(c.ip)}</td><td>${esc(c.network||'—')}</td><td>${c.is_wired?'🔌 Wired':'📶 '+esc(c.essid||'Wi-Fi')}</td></tr>`).join('');
      const emp=document.getElementById('unifiClientsEmpty');
      if(emp){ emp.style.display=(j.error||!list.length)?'block':'none'; unifiEmptyMsg(emp,j.error,'NO ACTIVE CLIENTS'); }
    }
  }catch(e){}
}
let _unifiTimer=null;
function startUnifiAutoRefresh(){ stopUnifiAutoRefresh(); _unifiTimer=setInterval(()=>loadUnifiWidgets(), 30000); }
function stopUnifiAutoRefresh(){ if(_unifiTimer){ clearInterval(_unifiTimer); _unifiTimer=null; } }
const DASH_LAYOUT_KEY='itvault_dash_layout_v1';   // legacy: a bare order array
const DASH_LAYOUT_KEY2='itvault_dash_layout_v2';
/* The layout grew from "what order" into "what is shown, how wide, and which
   tiles the user invented". v1 stays on disk untouched and is migrated on
   read, so nothing is lost if someone rolls back. */
function blankLayout(){ return {v:2, cols:2, order:[], hidden:[], links:[]}; }
function getDashLayout(){
  try{
    const v2=localStorage.getItem(DASH_LAYOUT_KEY2);
    if(v2){ const o=JSON.parse(v2); return Object.assign(blankLayout(), o||{}); }
  }catch(e){}
  const L=blankLayout();
  try{
    const v1=JSON.parse(localStorage.getItem(DASH_LAYOUT_KEY)||'null');
    if(Array.isArray(v1)) L.order=v1;
  }catch(e){}
  return L;
}
/* Written to both: the server so it is the user's layout wherever they sign
   in (and so it lands in the backup, which is why it moved off the browser),
   and localStorage so the dashboard paints in the right shape on the next
   load without waiting for a round trip. */
function putDashLayout(L){
  try{ localStorage.setItem(DASH_LAYOUT_KEY2, JSON.stringify(L)); }catch(e){}
  api('/api/dash/layout', {method:'PUT', headers:{'Content-Type':'application/json'},
                           body:JSON.stringify({layout:L})})
    .then(async r=>{
      if(r&&r.ok) return;
      const j=r?await r.json().catch(()=>({})):{};
      // saved locally either way, so say what did not happen rather than
      // pretending the whole save failed
      toast('✕ Saved on this device only: '+((j&&j.error)||'server refused'));
    }).catch(()=>toast('✕ Saved on this device only — server unreachable'));
}

/* Pulls the stored layout once per dashboard visit. The cached copy has
   already painted by now, so this only corrects it -- and when it differs,
   re-applies rather than reloading the page. */
async function syncDashLayout(){
  try{
    const r=await api('/api/dash/layout');
    if(!r||!r.ok) return;
    const j=await r.json().catch(()=>null);
    if(!j||!j.layout) return;
    const server=JSON.stringify(Object.assign(blankLayout(), j.layout));
    if(server===JSON.stringify(getDashLayout())) return;
    try{ localStorage.setItem(DASH_LAYOUT_KEY2, server); }catch(e){}
    applyDashLayout();
  }catch(e){}
}
function dashCont(){ return document.getElementById('dashWidgets'); }

/* Built-in widgets are whatever the markup ships with; a title for the picker
   comes from the widget's own heading so the two can never disagree. */
function builtinWidgets(){
  const cont=dashCont(); if(!cont) return [];
  return [...cont.querySelectorAll('.widget[data-wkey]')]
    .filter(w=>!w.getAttribute('data-wkey').startsWith('link:'))
    .map(w=>({key:w.getAttribute('data-wkey'),
              title:(w.querySelector('.secthead')?.textContent||w.getAttribute('data-wkey')).trim()}));
}

function applyDashLayout(){
  const cont=dashCont(); if(!cont) return;
  const L=getDashLayout();
  cont.style.setProperty('--dashcols', String(L.cols||2));
  renderLinkWidgets(L);
  // order first, then visibility -- a hidden widget still has a place in the
  // order so unhiding it puts it back where it was, not at the end
  (L.order||[]).forEach(k=>{ const el=cont.querySelector('.widget[data-wkey="'+CSS.escape(k)+'"]'); if(el) cont.appendChild(el); });
  const hidden=new Set(L.hidden||[]);
  cont.querySelectorAll('.widget[data-wkey]').forEach(w=>{
    w.classList.toggle('w-hidden', hidden.has(w.getAttribute('data-wkey')));
  });
  const sel=document.getElementById('dashCols'); if(sel) sel.value=String(L.cols||2);
}

/* The user's own tiles. Rebuilt from the layout rather than mutated in place,
   so there is exactly one source of truth for what exists. */
function renderLinkWidgets(L){
  const cont=dashCont(); if(!cont) return;
  cont.querySelectorAll('.widget[data-wkey^="link:"]').forEach(w=>w.remove());
  (L.links||[]).forEach(t=>{
    const el=document.createElement('div');
    el.className='panel widget wlink';
    el.setAttribute('data-wkey', t.key);
    // _self is offered, but noopener stays on either way: a page opened from
    // here must never get a handle on this one.
    const tgt=(t.target==='_self')?'_self':'_blank';
    el.innerHTML=`<div class="secthead">${esc(t.title||'LINK')}</div>
      <a class="wlink-body" href="${esc(t.url)}" target="${tgt}" rel="noopener noreferrer">
        ${t.icon?`<img class="wlink-ico" src="${esc(t.icon)}" alt="">`:'<div class="wlink-ico wlink-ico-none">🔗</div>'}
        <div class="wlink-txt">
          <div class="wlink-host">${esc(t.desc||hostOf(t.url))}</div>
          <div class="wlink-sub">${esc(t.desc?hostOf(t.url):'')}</div>
          <div class="wlink-state" data-mon="${t.monitor||''}"></div>
        </div>
      </a>`;
    cont.appendChild(el);
  });
}
function hostOf(u){ try{ return new URL(u).host; }catch(e){ return String(u||''); } }

/* Heartbeat state is already fetched for the dashboard's own widget; the tiles
   read the same response rather than each polling for themselves. */
function paintLinkStates(monitors){
  const byId={}; (monitors||[]).forEach(m=>{ byId[String(m.id)]=m; });
  document.querySelectorAll('.wlink-state[data-mon]').forEach(el=>{
    const id=el.getAttribute('data-mon'); if(!id){ el.textContent=''; return; }
    const m=byId[id];
    if(!m){ el.innerHTML='<span class="muted">monitor gone</span>'; return; }
    const st=hbStatusOf(m);
    const ms=(m.last_ms!=null)?` · ${m.last_ms} ms`:'';
    el.innerHTML=`<span class="hbpill ${st==='disabled'?'paused':st}">${st==='disabled'?'paused':st}</span>${ms}`;
  });
}

function saveDashLayout(){
  const cont=dashCont(); if(!cont) return blankLayout();
  const L=getDashLayout();
  L.order=[...cont.querySelectorAll('.widget[data-wkey]')].map(w=>w.getAttribute('data-wkey'));
  L.hidden=[...cont.querySelectorAll('.widget.w-hidden[data-wkey]')].map(w=>w.getAttribute('data-wkey'));
  const sel=document.getElementById('dashCols');
  if(sel) L.cols=Math.max(1, Math.min(4, parseInt(sel.value,10)||2));
  return L;
}
function getDragAfterElement(container, y){
  const els=[...container.querySelectorAll('.widget:not(.dragging)')];
  let closest={offset:-Infinity, el:null};
  for(const el of els){
    const box=el.getBoundingClientRect();
    const offset=y - (box.top + box.height/2);
    if(offset < 0 && offset > closest.offset){ closest={offset, el}; }
  }
  return closest.el;
}
function initDashDrag(){
  const cont=document.getElementById('dashWidgets'); if(!cont) return;
  let dragEl=null;
  cont.querySelectorAll('.widget').forEach(w=>{ w.draggable=true; });
  cont.addEventListener('dragstart', e=>{
    const w=e.target.closest('.widget'); if(!w) return;
    dragEl=w;
    e.dataTransfer.effectAllowed='move';
    try{ e.dataTransfer.setData('text/plain', w.getAttribute('data-wkey')); }catch(_){}
    setTimeout(()=>w.classList.add('dragging'),0);
  });
  cont.addEventListener('dragend', e=>{
    const w=e.target.closest('.widget'); if(w) w.classList.remove('dragging');
    dragEl=null;
  });
  cont.addEventListener('dragover', e=>{
    e.preventDefault();
    if(!dragEl) return;
    const after=getDragAfterElement(cont, e.clientY);
    if(after==null){ cont.appendChild(dragEl); }
    else { cont.insertBefore(dragEl, after); }
  });
  cont.addEventListener('drop', e=>{ e.preventDefault(); });
}
function setEditLayout(on){
  document.body.classList.toggle('edit-layout', on);
  const show=(id,v)=>{ const el=document.getElementById(id); if(el) el.style.display=v?'':'none'; };
  show('dashSaveLayout', on); show('dashResetLayout', on);
  show('dashAddWidget', on); show('dashColsWrap', on);
  show('dashEditLayout', !on);
  document.getElementById('dashLayoutMsg').textContent=on
    ? 'Drag to reorder, ✕ to remove, + ADD WIDGET to bring one back — then SAVE'
    : '';
  decorateWidgets(on);
  if(on) initDashDrag();
  else { const cont=dashCont(); if(cont) cont.querySelectorAll('.widget').forEach(w=>w.draggable=false); }
}

/* One ✕ per widget, added only while editing so the chrome never shows in
   normal use. Removing a built-in hides it; removing a user tile deletes it,
   because nothing else refers to it. */
function decorateWidgets(on){
  const cont=dashCont(); if(!cont) return;
  cont.querySelectorAll('.wkill').forEach(b=>b.remove());
  if(!on) return;
  cont.querySelectorAll('.widget[data-wkey]').forEach(w=>{
    const key=w.getAttribute('data-wkey');
    const isLink=key.startsWith('link:');
    const bar=document.createElement('div');
    bar.className='wtools';
    // A tile you invented is a thing you got wrong the first time -- editing
    // it beats deleting it and retyping the address and re-fetching the icon.
    if(isLink){
      const pen=document.createElement('button');
      pen.type='button'; pen.className='wtool'; pen.title='Edit this tile';
      pen.textContent='✎';
      pen.onclick=(e)=>{ e.stopPropagation(); e.preventDefault(); openWidgetPicker(key); };
      bar.appendChild(pen);
    }
    const btn=document.createElement('button');
    btn.type='button'; btn.className='wtool wkill';
    btn.title=isLink?'Delete this tile':'Remove this widget';
    btn.textContent='✕';
    btn.onclick=(e)=>{
      e.stopPropagation(); e.preventDefault();
      const L=getDashLayout();
      if(isLink){
        L.links=(L.links||[]).filter(t=>t.key!==key);
        L.order=(L.order||[]).filter(k=>k!==key);
      }else{
        // Removed means gone from the page, not greyed out in place. It comes
        // back through + ADD WIDGET, which is where someone looks for it.
        L.hidden=Array.from(new Set((L.hidden||[]).concat([key])));
      }
      putDashLayout(L); applyDashLayout(); decorateWidgets(true); initDashDrag();
    };
    bar.appendChild(btn);
    w.appendChild(bar);
  });
}

/* ---------- widget picker ---------- */
let wmEditKey=null;
function openWidgetPicker(editKey){
  const L=getDashLayout();
  wmEditKey=editKey||null;
  const existing=wmEditKey?(L.links||[]).find(t=>t.key===wmEditKey):null;
  const hidden=new Set(L.hidden||[]);
  const list=document.getElementById('wmHidden');
  const items=builtinWidgets().filter(w=>hidden.has(w.key));
  list.innerHTML=items.length
    ? items.map(w=>`<button class="btn ghost sm wmadd" data-k="${esc(w.key)}">+ ${esc(w.title)}</button>`).join('')
    : '<span class="muted">Nothing is hidden — every built-in widget is already on the dashboard.</span>';
  list.querySelectorAll('.wmadd').forEach(b=>{
    b.onclick=()=>{
      const cont=dashCont();
      const el=cont?.querySelector('.widget[data-wkey="'+CSS.escape(b.getAttribute('data-k'))+'"]');
      if(el) el.classList.remove('w-hidden');
      openWidgetPicker();   // reflect that it is no longer hidden
      decorateWidgets(true); initDashDrag();
    };
  });
  // monitors to bind a tile to, if the user can see them at all
  const sel=document.getElementById('wmMonitor');
  sel.innerHTML='<option value="">— none —</option>';
  if(canDo('tools.heartbeat')){
    api('/api/heartbeat/state?hours=1').then(async r=>{
      if(!r||!r.ok) return;
      const j=await r.json().catch(()=>null);
      (j&&j.monitors||[]).forEach(m=>{
        const o=document.createElement('option');
        o.value=String(m.id); o.textContent=m.name||('monitor '+m.id);
        sel.appendChild(o);
      });
    });
  }
  wmIcon=existing?(existing.icon||''):''; renderWmIcon();
  document.getElementById('wmTitle').value=existing?(existing.title||''):'';
  document.getElementById('wmUrl').value=existing?(existing.url||''):'';
  document.getElementById('wmDesc').value=existing?(existing.desc||''):'';
  document.getElementById('wmTarget').value=(existing&&existing.target==='_self')?'_self':'_blank';
  document.getElementById('wmIconMsg').textContent='';
  // one dialog, two jobs -- say which one it is doing
  document.querySelector('#widgetModal h3').textContent=existing?'EDIT TILE':'ADD WIDGET';
  document.getElementById('wmAdd').textContent=existing?'💾 SAVE TILE':'+ ADD TILE';
  const hw=document.getElementById('wmHiddenWrap');
  if(hw) hw.style.display=existing?'none':'';
  // the monitor list is filled in asynchronously above; re-select once it is
  if(existing&&existing.monitor){
    const want=String(existing.monitor);
    const pick=()=>{ const m=document.getElementById('wmMonitor');
      if(!m) return; if([...m.options].some(o=>o.value===want)) m.value=want; else setTimeout(pick,150); };
    setTimeout(pick,150);
  }
  document.getElementById('widgetModal').classList.add('show');
}

let wmIcon='';
function renderWmIcon(){
  const img=document.getElementById('wmIconPrev');
  const clr=document.getElementById('wmClearIcon');
  if(!img) return;
  if(wmIcon){ img.src=wmIcon; img.style.display=''; if(clr) clr.style.display=''; }
  else { img.removeAttribute('src'); img.style.display='none'; if(clr) clr.style.display='none'; }
}

/* ---------- modal / crud ---------- */
let editingId=null;
async function openModal(id,prefill){
  editingId=id;const a=id?assets.find(x=>x._id===id):(prefill||{});
  document.getElementById('modalTitle').textContent=id?'Edit asset':'Add asset';
  const inv=a&&a.InvoiceFile?a.InvoiceFile:'';
  const renderField=c=>{
    const val=a?a[c]||'':'';
    if(c==='AssetTag')return`<div class="field2"><label>${LABELS[c]||c}</label><input id="f_${c}" class="mono" value="${esc(val)}" placeholder="${id?'':'(auto-generated if left blank, e.g. IT-1001)'}"></div>`;
    if(c==='Status')return`<div class="field2"><label>${c}</label><select id="f_${c}">${STATUSES.map(o=>`<option ${o===val?'selected':''}>${o}</option>`).join('')}</select></div>`;
    if(c==='EmployeeID')return`<div class="field2"><label>${LABELS[c]||c}</label><select id="f_EmployeeID"><option value="">-- select employee --</option></select></div>`;
    if(c==='RequestedBy')return`<div class="field2"><label>${LABELS[c]||c}</label><select id="f_RequestedBy"><option value="">-- select employee --</option></select></div>`;
    if(c==='Type')return`<div class="field2"><label>${LABELS[c]||c}</label><select id="f_Type"><option value="">-- select category --</option></select></div>`;
    if(c==='Location')return`<div class="field2"><label>${LABELS[c]||c}</label><select id="f_Location"><option value="">-- select location --</option></select></div>`;
    if(c==='NotesReceived')return`<div class="field2"><label>${LABELS[c]||c} <span class="muted" style="font-weight:400">(set automatically at Check Out)</span></label><input id="f_${c}" type="date" value="${esc(val)}" readonly disabled></div>`;
    if(c==='ReceivedBy')return`<div class="field2"><label>${LABELS[c]||c} <span class="muted" style="font-weight:400">(set automatically at Check Out)</span></label><input id="f_${c}" value="${esc(val)}" readonly disabled></div>`;
    if(c==='Price')return`<div class="field2"><label>${LABELS[c]||c} (${CURRENCY})</label><input id="f_${c}" type="number" step="0.01" min="0" value="${esc(val)}"></div>`;
    return`<div class="field2"><label>${LABELS[c]||c}</label><input id="f_${c}" value="${esc(val)}"></div>`;
  };
  const groups=[
    {label:'IDENTITY',cols:['AssetTag','Name','Type','Serial','MacAddress','Location']},
    {label:'PURCHASE &amp; WARRANTY',cols:['PurchaseDate','WarrantyMonths','Price']},
    {label:'STATUS &amp; ASSIGNMENT',cols:['Status','EmployeeID','RequestedBy','ReceivedBy','NotesReceived']},
  ];
  document.getElementById('formFields').innerHTML=
    `<div class="invbox">
      <label>IDENTITY</label>
      <div class="grid2">${groups[0].cols.map(renderField).join('')}</div>
    </div>`+
    `<div class="invbox refbox">
       <label>MANUFACTURER &amp; MODEL <a class="mlink" onclick="closeModal();showPage('page-catalog')">manage in Product Catalog ↗</a></label>
       <div class="ref2">
         <div><select id="f_Manufacturer"><option value="">-- choose manufacturer --</option></select></div>
         <div><select id="f_Model"><option value="">-- choose model --</option></select></div>
       </div>
     </div>`+
    groups.slice(1).map(g=>`<div class="invbox">
      <label>${g.label}</label>
      <div class="grid2">${g.cols.map(renderField).join('')}${g.label.indexOf('STATUS')===0?
        `<div class="field2"><label>Employee Department</label><input id="f_EmpDepartment" value="" readonly disabled></div>
         <div class="field2"><label>Employee Designation</label><input id="f_EmpDesignation" value="" readonly disabled></div>`:''}</div>
    </div>`).join('');
  document.getElementById('noteInvoiceWrap').innerHTML=
    `<div class="invbox">
      <label>NOTE (optional internal note)</label>
      <textarea id="f_Note" rows="3" placeholder="e.g. bought from X, handed to Y...">${esc(a?a.Note||'':'')}</textarea>
    </div>
    <div class="invbox">
      <label>INVOICE / PROOF (PDF or image)</label>
      <div class="invrow">
        <input type="file" id="f_InvoiceFile" accept=".pdf,.png,.jpg,.jpeg,.gif,.webp,.bmp">
        ${inv?`<a class="btn sm ghost" href="/invoice/${esc(inv)}" target="_blank">VIEW</a><button class="btn sm danger" type="button" onclick="delInvoice('${editingId}')">REMOVE</button>`:'<span class="muted">none yet</span>'}
      </div>
    </div>`;
  const histWrap=document.getElementById('histWrap');
  if(histWrap)histWrap.style.display=id?'':'none';
  document.getElementById('maintWrap').style.display=id?'':'none';
  if(id){ loadMaintInline(id); }
  document.getElementById('modal').classList.add('show');
  // The Employee/Manufacturer/Model/Category/Location dropdowns below are
  // populated asynchronously AFTER the modal is already visible and
  // clickable -- without this guard, hitting COMMIT during that brief
  // window (e.g. right after the modal auto-reopens from adding/deleting a
  // maintenance record) would submit those fields still on their empty
  // placeholder option, silently wiping the real Employee Name/Manufacturer/
  // etc. that was set before.
  const saveBtn=document.getElementById('saveBtn');
  if(saveBtn)saveBtn.disabled=true;
  try{
    if(!id && !(prefill&&prefill.AssetTag)){
      const tagEl=document.getElementById('f_AssetTag');
      if(tagEl){ const r=await api('/api/assets/next-tag'); if(r&&r.ok){ const j=await r.json(); tagEl.value=j.tag||''; } }
    }
    if(document.getElementById('f_EmployeeID')){
      await fetchEmployees(a?a.EmployeeID||'':'', a?a.RequestedBy||'':'');
    }
    // populate Manufacturer / Model / Category dropdowns from reference tables
    await loadMfrModelOptions(a?a.Manufacturer||'':'', a?a.Model||'':'');
    await loadCategoryOptions(a?a.Type||'':'');
    await loadLocationOptions(a?a.Location||'':'');
    if(id)loadAssetHistory(id);
  }finally{
    if(saveBtn)saveBtn.disabled=false;
  }
}

// populate Manufacturer + Model <select> dropdowns from backend reference data
async function loadMfrModelOptions(selMfr, selModel){
  try{
    const mf=await api('/api/manufacturers'); let mfrs=mf?await mf.json():[];
    const sel=document.getElementById('f_Manufacturer'); if(!sel)return;
    // e.g. pre-filled from a network-scan MAC vendor lookup -- add it to the
    // reference list if it's genuinely new, instead of silently dropping it
    if(selMfr && !mfrs.some(m=>m.name===selMfr)){
      const r=await api('/api/manufacturers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:selMfr})});
      if(r&&r.ok){ const mf2=await api('/api/manufacturers'); mfrs=mf2?await mf2.json():mfrs; }
    }
    sel.innerHTML='<option value="">-- choose manufacturer --</option>'+mfrs.map(m=>`<option value="${esc(m.name)}" ${m.name===selMfr?'selected':''}>${esc(m.name)}</option>`).join('')+'<option value="__new">＋ type new…</option>';
    sel.onchange=async()=>{
      if(sel.value==='__new'){const v=prompt('New manufacturer name:'); if(v&&v.trim()){const r=await api('/api/manufacturers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:v.trim()})}); if(r&&r.ok){await loadMfrModelOptions(v.trim(),'');}} else {sel.value=selMfr;}}
      else { await loadModelOptions('', sel.value, mfrs); }
    };
    await loadModelOptions(selModel, sel.value, mfrs);
  }catch(e){}
}
// Models are strictly scoped to a manufacturer -- can't pick or create one
// until a manufacturer is chosen/created above (was previously possible to
// silently create an orphan model with no manufacturer link).
async function loadModelOptions(selModel, mfrName, mfrs){
  const sel=document.getElementById('f_Model'); if(!sel)return;
  if(!mfrName){
    sel.innerHTML='<option value="">-- choose manufacturer first --</option>';
    sel.disabled=true;
    sel.onchange=null;
    return;
  }
  sel.disabled=false;
  const mfrObj=(mfrs||[]).find(m=>m.name===mfrName);
  const mfrId=mfrObj?mfrObj.id:null;
  let opts='<option value="">-- choose model --</option>';
  try{
    const md=await api('/api/models'); const models=md?await md.json():[];
    const filtered = models.filter(m=>m.manufacturer===mfrName);
    opts+=filtered.map(m=>`<option value="${esc(m.name)}" ${m.name===selModel?'selected':''}>${esc(m.name)}</option>`).join('')+'<option value="__new">＋ type new…</option>';
  }catch(e){}
  sel.innerHTML=opts;
  sel.onchange=async()=>{
    if(sel.value==='__new'){const v=prompt('New model name:'); if(v&&v.trim()){const r=await api('/api/models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:v.trim(),manufacturer_id:mfrId})}); if(r&&r.ok){await loadModelOptions(v.trim(), mfrName, mfrs);}} else {sel.value=selModel;}}
  };
}
// populate the Item Category <select> on the Add Asset form from the
// Categories reference table, auto-adding it if it's genuinely new (e.g. an
// existing asset's Type value from before this became a picker)
async function loadCategoryOptions(selCat){
  const sel=document.getElementById('f_Type'); if(!sel)return;
  let cats=[];
  try{
    const r=await api('/api/categories'); cats=r?await r.json():[];
    if(selCat && !cats.some(c=>c.name===selCat)){
      const r2=await api('/api/categories',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:selCat})});
      if(r2&&r2.ok){ const r3=await api('/api/categories'); cats=r3?await r3.json():cats; }
    }
  }catch(e){}
  sel.innerHTML='<option value="">-- select category --</option>'+cats.map(c=>`<option value="${esc(c.name)}" ${c.name===selCat?'selected':''}>${esc(c.name)}</option>`).join('')+'<option value="__new">＋ type new…</option>';
  sel.onchange=async()=>{
    if(sel.value==='__new'){const v=prompt('New category name:'); if(v&&v.trim()){const r=await api('/api/categories',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:v.trim()})}); if(r&&r.ok){await loadCategoryOptions(v.trim());}} else {sel.value=selCat;}}
  };
}
// populate the Location <select> on the Add Asset form from the Locations
// reference table (shared with the GLPI Location Tree page), auto-adding it
// if it's genuinely new (e.g. an existing asset's Location value from before
// this became a picker)
async function loadLocationOptions(selLoc){
  const sel=document.getElementById('f_Location'); if(!sel)return;
  let locs=[];
  try{
    const r=await api('/api/locations'); locs=r?await r.json():[];
    if(selLoc && !locs.some(l=>l.name===selLoc)){
      const r2=await api('/api/locations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:selLoc})});
      if(r2&&r2.ok){ const r3=await api('/api/locations'); locs=r3?await r3.json():locs; }
    }
  }catch(e){}
  sel.innerHTML='<option value="">-- select location --</option>'+locs.map(l=>`<option value="${esc(l.name)}" ${l.name===selLoc?'selected':''}>${esc(l.name)}</option>`).join('')+'<option value="__new">＋ type new…</option>';
  sel.onchange=async()=>{
    if(sel.value==='__new'){const v=prompt('New location name:'); if(v&&v.trim()){const r=await api('/api/locations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:v.trim()})}); if(r&&r.ok){await loadLocationOptions(v.trim());}} else {sel.value=selLoc;}}
  };
}
async function loadAssetHistory(id){
  const box=document.getElementById('histBox'); if(!box)return;
  const r=await api('/api/assets/'+id+'/history'); if(!r)return; const h=await r.json();
  box.innerHTML = h.length? h.map(e=>`<div class="hist"><span class="hfield">${esc(e.field)}</span> <span class="hold">${esc(e.old_val||'—')}</span> → <span class="hnew">${esc(e.new_val||'—')}</span> <span class="hmeta">${esc(e.user)} · ${esc(e.ts)}</span></div>`).join('') : '<div class="muted">No history yet.</div>';
}
// ---------- Camera scan (QR / barcode) -> Add Asset form ----------
let camScanStream=null, camScanLoopId=null, camScanDetector=null, camScanBusy=false;
async function getCamScanDetector(){
  if(camScanDetector) return camScanDetector;
  if(!('BarcodeDetector' in window)) return null;
  const formats=['qr_code','code_128','code_39','code_93','codabar','ean_13','ean_8','itf','upc_a','upc_e','data_matrix','pdf417'];
  try{ camScanDetector=new BarcodeDetector({formats}); }
  catch(e){ try{ camScanDetector=new BarcodeDetector({formats:['qr_code']}); }catch(e2){ return null; } }
  return camScanDetector;
}
async function openCamScan(){
  const status=document.getElementById('camScanStatus'); status.textContent='';
  document.getElementById('camScanModal').classList.add('show');
  const det=await getCamScanDetector();
  if(!det){
    status.textContent='✕ This browser doesn\'t support camera barcode scanning (try Chrome or Edge) -- use "Upload Photo Instead", or type the value in manually.';
    return;
  }
  try{
    camScanStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'}});
    const vid=document.getElementById('camScanVideo');
    vid.srcObject=camScanStream;
    status.textContent='Point the camera at a QR code or barcode…';
    const tick=async()=>{
      if(!camScanStream)return;
      if(!camScanBusy){
        camScanBusy=true;
        try{
          const codes=await det.detect(vid);
          if(codes && codes.length){ await onCamScanDecoded(codes[0].rawValue); return; }
        }catch(e){}
        camScanBusy=false;
      }
      camScanLoopId=requestAnimationFrame(tick);
    };
    camScanLoopId=requestAnimationFrame(tick);
  }catch(e){
    status.textContent='✕ Could not access the camera ('+(e.message||e.name||'permission denied')+') -- use "Upload Photo Instead".';
  }
}
function closeCamScan(){
  if(camScanLoopId){ cancelAnimationFrame(camScanLoopId); camScanLoopId=null; }
  if(camScanStream){ camScanStream.getTracks().forEach(t=>t.stop()); camScanStream=null; }
  camScanBusy=false;
  document.getElementById('camScanModal').classList.remove('show');
}
async function onCamScanDecoded(text){
  closeCamScan();
  const status=document.getElementById('camScanStatus');
  if(!text){ return; }
  // 1) this app's own printed asset QR (http://host/asset/<id>) -- open that
  //    existing asset for editing instead of prefilling a duplicate
  const m=text.match(/\/asset\/([a-f0-9]{8,40})\b/i);
  if(m && assets.some(a=>a._id===m[1])){
    toast('✓ SCANNED — opened existing asset');
    openModal(m[1]);
    return;
  }
  // 2) a QR payload that itself carries structured asset data as JSON
  let obj=null;
  try{ const p=JSON.parse(text); if(p && typeof p==='object') obj=p; }catch(e){}
  if(obj){
    await applyScannedFields(obj);
    toast('✓ SCANNED — form filled from QR data');
    return;
  }
  // 3) otherwise treat the raw decoded text as a serial number (the common
  //    case: a manufacturer's SN barcode/QR sticker)
  const f=document.getElementById('f_Serial');
  if(f){ f.value=text; toast('✓ SCANNED — Serial Number filled'); }
  else{ toast('✓ SCANNED: '+text); }
}
async function applyScannedFields(obj){
  const norm={}; Object.keys(obj).forEach(k=>norm[k.toLowerCase().replace(/[^a-z0-9]/g,'')]=obj[k]);
  const pick=(...keys)=>{ for(const k of keys){ if(norm[k]!=null && norm[k]!=='') return String(norm[k]); } return ''; };
  const name=pick('name','assetname','device','devicename');
  const serial=pick('serial','serialnumber','sn','serialno');
  const mac=pick('mac','macaddress');
  const type=pick('type','category','itemcategory');
  const mfr=pick('manufacturer','brand','make');
  const model=pick('model');
  const loc=pick('location','site');
  if(name && document.getElementById('f_Name')) document.getElementById('f_Name').value=name;
  if(serial && document.getElementById('f_Serial')) document.getElementById('f_Serial').value=serial;
  if(mac && document.getElementById('f_MacAddress')) document.getElementById('f_MacAddress').value=mac;
  if(type && document.getElementById('f_Type')) await loadCategoryOptions(type);
  if(loc && document.getElementById('f_Location')) await loadLocationOptions(loc);
  if(mfr || model) await loadMfrModelOptions(mfr, model);
}
async function camScanFromFile(file){
  const status=document.getElementById('camScanStatus');
  const det=await getCamScanDetector();
  if(!det){ status.textContent='✕ This browser doesn\'t support barcode scanning (try Chrome or Edge).'; return; }
  status.textContent='Reading photo…';
  try{
    const bmp=await createImageBitmap(file);
    const codes=await det.detect(bmp);
    if(codes && codes.length){ await onCamScanDecoded(codes[0].rawValue); }
    else { status.textContent='✕ No QR/barcode found in that photo -- try again or type the value manually.'; }
  }catch(e){
    status.textContent='✕ Could not read that photo ('+(e.message||e.name||'error')+').';
  }
}
document.getElementById('camScanBtn').onclick=openCamScan;
document.getElementById('camScanCancel').onclick=closeCamScan;
document.getElementById('camScanUploadBtn').onclick=()=>document.getElementById('camScanUploadFile').click();
document.getElementById('camScanUploadFile').onchange=(e)=>{
  const f=e.target.files[0]; e.target.value='';
  if(f) camScanFromFile(f);
};

// ---------- OCR (read a printed label's text -- S/N, Model, MAC -- not just QR/barcode) ----------
// Loaded on demand (only when the user actually taps "Scan Text") rather than
// on every page load, since it's a ~2MB library most visits never touch.
let _tesseractLoadPromise=null;
function loadTesseract(){
  if(window.Tesseract) return Promise.resolve();
  if(_tesseractLoadPromise) return _tesseractLoadPromise;
  _tesseractLoadPromise=new Promise((resolve,reject)=>{
    const s=document.createElement('script');
    s.src='https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js';
    s.onload=()=>resolve();
    s.onerror=()=>{ _tesseractLoadPromise=null; reject(new Error('could not load the text-recognition library (check your internet connection)')); };
    document.head.appendChild(s);
  });
  return _tesseractLoadPromise;
}
// Mirrors the Android app's OCR label parser: same-line "KEY: VALUE" lines,
// plus the common two-line layout (label alone on one line, value on the
// next) that's typical on printed asset stickers.
function ocrParseFields(text){
  const lines=text.split(/\r?\n/).map(l=>l.trim()).filter(Boolean);
  function findLabeled(aliasesLongestFirst){
    const escaped=aliasesLongestFirst.map(a=>a.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'));
    const sameLine=new RegExp('\\b('+escaped.join('|')+')\\b\\.?\\s*[:\\-]\\s*(.+)','i');
    for(const line of lines){
      const m=line.match(sameLine);
      if(m){ const v=(m[2]||'').trim(); if(v) return v; }
    }
    for(let i=0;i<lines.length;i++){
      const norm=lines[i].replace(/:$/,'').trim().toLowerCase();
      if(aliasesLongestFirst.some(a=>a.toLowerCase()===norm) && i+1<lines.length){
        const v=lines[i+1].trim(); if(v) return v;
      }
    }
    return '';
  }
  const serial=findLabeled(['serial number','serial no','serial#','s/n','sno','sn','serial']);
  const model=findLabeled(['model number','model no','model']);
  const manufacturer=findLabeled(['manufacturer','brand','make']);
  let mac=findLabeled(['mac address','mac id','mac']);
  if(!mac){ const mm=text.match(/([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}/); if(mm) mac=mm[0]; }
  return {serial, model, manufacturer, mac};
}
async function captureAndReadText(){
  const status=document.getElementById('camScanStatus');
  const vid=document.getElementById('camScanVideo');
  const btn=document.getElementById('camScanTextBtn');
  if(!camScanStream || !vid.videoWidth){ status.textContent='✕ Camera not ready yet -- wait a moment and try again.'; return; }
  btn.disabled=true;
  status.textContent='Loading text reader…';
  try{
    await loadTesseract();
    const canvas=document.getElementById('camScanCanvas');
    canvas.width=vid.videoWidth; canvas.height=vid.videoHeight;
    canvas.getContext('2d').drawImage(vid,0,0,canvas.width,canvas.height);
    status.textContent='Reading label…';
    const { data }=await Tesseract.recognize(canvas,'eng');
    const text=(data&&data.text)||'';
    if(!text.trim()){ status.textContent='✕ No text found on that label -- try getting closer or better lighting.'; return; }
    const f=ocrParseFields(text);
    const obj={};
    if(f.serial) obj.serial=f.serial;
    if(f.model) obj.model=f.model;
    if(f.manufacturer) obj.manufacturer=f.manufacturer;
    if(f.mac) obj.mac=f.mac;
    if(!Object.keys(obj).length){ status.textContent='✕ Couldn\'t recognize S/N, Model, or MAC on that label -- try getting closer or better lighting.'; return; }
    closeCamScan();
    await applyScannedFields(obj);
    toast('✓ Filled from label: '+Object.keys(obj).join(', '));
  }catch(e){
    status.textContent='✕ Text recognition failed: '+(e.message||e);
  }finally{
    btn.disabled=false;
  }
}
document.getElementById('camScanTextBtn').onclick=captureAndReadText;

async function fetchEmployees(selEmpId,selReqId){
  const r=await api('/api/employees');
  const list=r?await r.json():[];
  window.__employeesCache=list; // reused so Department/Designation can be pulled live without another API call
  const opts=list.map(e=>({id:e.EmployeeID,label:e.EmployeeName||e.EmployeeID}));
  const sel=document.getElementById('f_EmployeeID');
  if(sel){
    sel.innerHTML='<option value="">-- select employee --</option>'+opts.map(o=>`<option value="${esc(o.id)}" ${selEmpId&&o.id===selEmpId?'selected':''}>${esc(o.label)}</option>`).join('');
    sel.onchange=()=>fillEmpDeptDesig(sel.value);
  }
  const reqSel=document.getElementById('f_RequestedBy');
  if(reqSel)reqSel.innerHTML='<option value="">-- select employee --</option>'+opts.map(o=>`<option value="${esc(o.id)}" ${selReqId&&o.id===selReqId?'selected':''}>${esc(o.label)}</option>`).join('');
  fillEmpDeptDesig(selEmpId);
}
// Department/Designation are Employee-record fields, not Asset fields --
// pulled live from the Directory whenever Employee Name is set/changed on
// the asset form, so they're never stale or manually re-typed.
function fillEmpDeptDesig(empId){
  const dEl=document.getElementById('f_EmpDepartment'), sEl=document.getElementById('f_EmpDesignation');
  if(!dEl||!sEl)return;
  const emp=(window.__employeesCache||[]).find(e=>e.EmployeeID===empId);
  dEl.value=emp?(emp.Department||''):'';
  sEl.value=emp?(emp.Designation||''):'';
}

async function delInvoice(id){
  if(!confirm('Remove invoice file?'))return;
  const r=await api('/api/assets/'+id+'/invoice',{method:'DELETE'});
  if(r&&r.ok){toast('✕ INVOICE REMOVED');await openModal(id);}else if(r){toast('✕ '+await apiError(r));}
}
async function saveModal(){
  const row={};COLUMNS.forEach(c=>{const el=document.getElementById('f_'+c);row[c]=el?el.value.trim():'';});
  const fileEl=document.getElementById('f_InvoiceFile');
  if(editingId){
    await api('/api/assets/'+editingId,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(row)});
    if(fileEl&&fileEl.files&&fileEl.files[0]){
      const fd=new FormData();fd.append('file',fileEl.files[0]);
      const r=await api('/api/assets/'+editingId+'/invoice',{method:'POST',body:fd});
      if(r&&!r.ok){const j=await r.json().catch(()=>({}));toast('✕ invoice: '+(j.error||'upload failed'));}
      else if(r&&r.ok)toast('✓ INVOICE SAVED');
    }
    toast('✓ SAVED'); closeModal(); load(); loadDashboard();
  }else{
    const r=await api('/api/assets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(row)});
    if(r&&r.ok){
      const a=await r.json();
      if(fileEl&&fileEl.files&&fileEl.files[0]){
        const fd=new FormData();fd.append('file',fileEl.files[0]);
        const r2=await api('/api/assets/'+a._id+'/invoice',{method:'POST',body:fd});
        if(!r2||!r2.ok){const j=await r2.json().catch(()=>({}));toast('✕ invoice: '+(j.error||'upload failed'));}
      }
      toast('✓ ADDED');closeModal();load();loadDashboard();
    }else if(r){toast('✕ '+await apiError(r));}
  }
}
function closeModal(){document.getElementById('modal').classList.remove('show');editingId=null;closeCamScan();}

/* ---------- checkout / checkin / maint / qr ---------- */
async function doCheckout(){
  const user=document.getElementById('coUser').value;
  const signedDate=document.getElementById('coSignedDate').value;
  const expected=document.getElementById('coExpected').value;
  const note=document.getElementById('coNote').value.trim();
  if(!user){toast('Select user');return;}
  const r=await api('/api/assets/'+coAsset+'/checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:user,signed_date:signedDate,expected,note})});
  if(r&&r.ok){document.getElementById('checkoutModal').classList.remove('show');toast('✓ CHECKED OUT');load();loadDashboard();}else if(r){toast('✕ '+await apiError(r));}
}
async function checkinAsset(id){
  if(!confirm('CHECK IN this asset?'))return;
  const r=await api('/api/assets/'+id+'/checkin',{method:'POST'});
  if(r&&r.ok){toast('✓ CHECKED IN');load();loadDashboard();}else if(r){toast('✕ '+await apiError(r));}
}
let maintAsset=null;
async function openMaint(id){
  maintAsset=id; const r=await api('/api/assets/'+id+'/maintenance'); const list=r?await r.json():[];
  const tbody=document.getElementById('maintList');
  tbody.innerHTML=list.map(x=>`<tr><td>${esc(x.date||x.ts||'')}</td><td>${esc(x.mtype||x.type||'')}</td><td class="mono">${fmtMoney(x.cost||0, CURRENCY)}</td><td>${esc(x.note||x.detail||'')}</td><td><button class="btn sm ghost" onclick="delMaint('${x.id||x._id||''}')">DEL</button></td></tr>`).join('')||'<tr><td colspan=5 style="color:var(--muted)">no records</td></tr>';
  document.getElementById('maintModal').classList.add('show');
}
document.getElementById('mAdd').onclick=addMaint;
async function addMaint(){
  const body={mtype:document.getElementById('mType').value.trim(),cost:document.getElementById('mCost').value,note:document.getElementById('mNote').value.trim(),date:document.getElementById('mDate').value};
  if(!body.mtype){toast('Type required');return;}
  const r=await api('/api/assets/'+maintAsset+'/maintenance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r&&r.ok){toast('✓ LOGGED');openMaint(maintAsset);load();loadDashboard();}else if(r){toast('✕ '+await apiError(r));}
}
async function delMaint(mid){
  if(!mid)return;
  const r=await api('/api/assets/'+maintAsset+'/maintenance?id='+mid,{method:'DELETE'});
  if(r&&r.ok){toast('✓ REMOVED');openMaint(maintAsset);}else if(r){toast('✕ '+await apiError(r));}
}
function openQR(id){window.open('/label/'+id,'_blank');}

/* ---------- maintenance embedded directly in the Asset form ---------- */
// Checkout/check-in used to have their own inline section here, duplicating
// the Employee Name field above -- it's simpler now: Status is the single
// source of truth (switch it to/from "Checked-Out" and COMMIT), and the
// backend derives Signed By/Signed Date from Employee Name automatically.
async function loadMaintInline(id){
  maintAsset=id;
  const r=await api('/api/assets/'+id+'/maintenance'); const list=r?await r.json():[];
  const tbody=document.getElementById('maintListInline'); if(!tbody)return;
  tbody.innerHTML=list.map(x=>`<tr><td>${esc(x.date||x.ts||'')}</td><td>${esc(x.mtype||x.type||'')}</td><td class="mono">${fmtMoney(x.cost||0, CURRENCY)}</td><td>${esc(x.note||x.detail||'')}</td><td><button class="btn sm ghost" onclick="delMaintInline('${x.id||x._id||''}')">DEL</button></td></tr>`).join('')||'<tr><td colspan=5 style="color:var(--muted)">no records</td></tr>';
}
async function addMaintInline(){
  const body={mtype:document.getElementById('mType2').value.trim(),cost:document.getElementById('mCost2').value,note:document.getElementById('mNote2').value.trim(),date:document.getElementById('mDate2').value};
  if(!body.mtype){toast('Type required');return;}
  const r=await api('/api/assets/'+maintAsset+'/maintenance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r&&r.ok){toast('✓ LOGGED');await load();loadDashboard();await openModal(maintAsset);}else if(r){toast('✕ '+await apiError(r));}
}
async function delMaintInline(mid){
  if(!mid)return;
  const r=await api('/api/assets/'+maintAsset+'/maintenance?id='+mid,{method:'DELETE'});
  if(r&&r.ok){toast('✓ REMOVED');await load();loadDashboard();await openModal(maintAsset);}else if(r){toast('✕ '+await apiError(r));}
}
document.getElementById('mAdd2').onclick=addMaintInline;
async function printAsset(id){
  const w=window.open('','_blank');
  if(!w){toast('✕ Popup blocked — allow popups for this site');return;}
  const r=await api('/api/assets/'+id); if(!r){w.close();return;} const a=await r.json();
  if(a.error){w.close();toast('✕ '+a.error);return;}
  // EmployeeName/Designation/Department/Email were never real Asset columns
  // (only EmployeeID is) -- they always came back blank. Pulled live from
  // the assigned employee's Directory record instead, same as the sign
  // page / QR scan page / signed PDF. EmployeeID itself is dropped from the
  // generic field list below so "Employee Name" doesn't print twice.
  let emp=null;
  if(a.EmployeeID){
    const er=await api('/api/employees'); const elist=er?await er.json():[];
    emp=elist.find(e=>e.EmployeeID===a.EmployeeID)||null;
  }
  const fields=[...visCols(),'Price','WarrantyMonths','NotesReceived','Notes','ReceivedBy'].filter(f=>f!=='EmployeeID');
  const seen=new Set(); const rowsHtml=fields.filter(f=>!seen.has(f)&&seen.add(f)).map(f=>{
    let v=a[f]; if(f==='Price')v=fmtMoney(a.Price||0,CURRENCY); if(v==null||v==='')v='—';
    return `<tr><td class="k">${esc(LABELS[f]||f)}</td><td class="v">${esc(v)}</td></tr>`;
  }).join('') + (a.EmployeeID ? `
    <tr><td class="k">Employee Name</td><td class="v">${esc((emp&&emp.EmployeeName)||a.EmployeeID)}</td></tr>
    <tr><td class="k">Department</td><td class="v">${esc((emp&&emp.Department)||'—')}</td></tr>
    <tr><td class="k">Designation</td><td class="v">${esc((emp&&emp.Designation)||'—')}</td></tr>
    <tr><td class="k">Email</td><td class="v">${esc((emp&&emp.Email)||'—')}</td></tr>` : '');
  const sig=a.SignatureData?`<div class="sig-block"><div class="sig-title">SIGNATURE / ACKNOWLEDGEMENT</div><img src="${a.SignatureData}" style="max-width:340px;max-height:160px;border:1px solid #ccc;border-radius:6px;background:#fff"/></div>`:`<div class="sig-block muted">Not signed yet</div>`;
  w.document.write(`<!doctype html><html><head><title>Asset ${esc(a.AssetTag||'')} — ${esc(a.Name||'')}</title>
  <style>@page{size:A4;margin:${window.HAS_LETTERHEAD?'0':'14mm'}}body{font-family:'Segoe UI',Arial,sans-serif;color:#111;padding:0;margin:0}
  .card{border:1px solid #222;border-radius:8px;max-width:720px;margin:0 auto;overflow:hidden}
  .hd{background:#101622;color:#fff;padding:12px 16px;font-family:'Segoe UI',Arial,sans-serif;font-weight:600;letter-spacing:.2px;display:flex;justify-content:space-between;align-items:center}
  .hd .brand{display:flex;align-items:center;gap:10px} .hd img{height:26px}
  .idbar{background:#f4f6fa;border-bottom:2px solid #101622;padding:12px 16px;text-align:center}
  .idbar .tag{font-size:26px;font-weight:800;letter-spacing:1px;color:#101622;font-family:ui-monospace,Consolas,monospace}
  .idbar .nm{font-size:13px;color:#555;margin-top:2px}
  .bd{padding:14px 16px} table{width:100%;border-collapse:collapse} td.k{width:38%;padding:5px 8px;color:#555;font-weight:600;border-bottom:1px solid #eee;vertical-align:top} td.v{padding:5px 8px;border-bottom:1px solid #eee;word-break:break-word}
  .sig-block{margin-top:14px;padding:10px;border:1px dashed #999;border-radius:6px} .sig-title{font-weight:700;margin-bottom:6px;font-size:12px;letter-spacing:.5px} .muted{color:#999;font-style:italic}
  @media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact}.card{border-color:#222}}</style></head>
  <body>${window.HAS_LETTERHEAD?`<img src="/letterhead.png?t=${Date.now()}" style="position:fixed;top:0;left:0;width:210mm;height:297mm;object-fit:fill;z-index:-1">`:''}
  <div class="card" style="${window.HAS_LETTERHEAD?`margin-top:${LETTERHEAD_CLEARANCE_MM}mm`:''}">${window.HAS_LETTERHEAD?'':`<div class="hd"><div class="brand"><img src="/logo.png" onerror="this.style.display='none'"><span>${(window.APP_NAME||'IT-Vault')} — Asset record</span></div></div>`}
  <div class="idbar"><div class="tag">${esc(a.AssetTag||'—')}</div><div class="nm">${esc(a.Name||'')}</div></div>
  <div class="bd"><table>${rowsHtml}</table>${sig}</div></div>
  ${printReadyScript()}</body></html>`);
  w.document.close();
}


/* ---------- audit ---------- */
let _auditRows=[];
function renderAuditRows(){
  const q=(document.getElementById('auditSearch').value||'').trim().toLowerCase();
  const rows=q?_auditRows.filter(x=>[x.actor,x.action,x.detail].some(v=>(v||'').toLowerCase().includes(q))):_auditRows;
  document.getElementById('auditBody').innerHTML=rows.length?rows.map(x=>`<tr><td class="mono">${esc(x.ts)}</td><td>${esc(x.actor)}</td><td>${esc(x.action)}</td><td>${esc(x.detail||'')}</td></tr>`).join(''):`<tr><td colspan=4 style="color:var(--muted)">${q?'no matching entries':'no activity'}</td></tr>`;
  document.getElementById('auditCount').textContent=rows.length+' of '+_auditRows.length+' entries';
}
async function openAudit(){
  const r=await api('/api/audit'); _auditRows=r?await r.json():[];
  renderAuditRows();
  document.getElementById('auditModal').classList.add('show');
}
async function clearAuditLog(){
  if(!confirm('Clear the entire audit log? This cannot be undone.'))return;
  const r=await api('/api/audit',{method:'DELETE'});
  if(r&&r.ok){const j=await r.json();toast('🗑 LOG CLEARED ('+j.deleted+')');openAudit();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}

/* ---------- scan ---------- */
/* Results are held (persisted) until the next Scan -- opening the panel just
   shows whatever was last discovered, it doesn't silently re-scan. Scan
   itself always clears the old list first, so there's one button that does
   both "clear" and "rescan". */
const SCAN_LAST_KEY='itvault_scan_last';
function loadLastScan(){ try{ const s=localStorage.getItem(SCAN_LAST_KEY); const v=s?JSON.parse(s):[]; return Array.isArray(v)?v:[]; }catch(e){ return []; } }
function saveLastScan(devs){ try{ localStorage.setItem(SCAN_LAST_KEY, JSON.stringify(devs)); }catch(e){} }
let lastScan=loadLastScan();
function openScan(){
  document.getElementById('scanStatus').textContent='';
  document.getElementById('scanModal').classList.add('show');
  renderScan(lastScan);
}
async function doScan(){
  const prefix=document.getElementById('scanPrefix').value.trim();
  const deep=document.getElementById('scanDeep').checked;
  if(deep && !prefix){toast('✕ enter a subnet, e.g. 192.168.0.0/24');return;}
  lastScan=[];
  document.getElementById('scanBody').innerHTML='<tr><td colspan=6 style="color:var(--muted)">Clearing…</td></tr>';
  document.getElementById('scanStatus').textContent= deep?'Scanning subnet (larger ranges can take a while)…':'Reading ARP table…';
  const qs=(prefix?('?prefix='+encodeURIComponent(prefix)):'')+(deep?'&deep=1':'');
  const r=await api('/api/scan'+qs);
  const j=r?await r.json().catch(()=>null):null;
  document.getElementById('scanStatus').textContent='';
  if(!r||!r.ok){
    toast('✕ '+((j&&j.error)||'scan failed'));
    renderScan(lastScan);
    return;
  }
  lastScan=Array.isArray(j)?j:[];
  saveLastScan(lastScan);
  renderScan(lastScan);
  // An empty result is ambiguous -- a quiet network looks exactly like a
  // container that cannot see one. Ask the server which it was.
  if(!lastScan.length) explainEmptyScan();
}
async function explainEmptyScan(){
  const st=document.getElementById('scanStatus'); if(!st) return;
  const r=await api('/api/scan/capabilities');
  if(!r||!r.ok) return;
  const c=await r.json().catch(()=>null);
  if(c&&c.hint) st.innerHTML='&#9888; '+esc(c.hint);
}
function renderScan(devs){
  const nodes=devs.map((d,i)=>`<tr><td>${esc(d.ip||'')}</td><td>${esc(d.host||'')||'<span class="muted">—</span>'}</td><td>${esc(d.mac||d.hw||'')}</td><td>${esc(d.vendor||'')||'<span class="muted">—</span>'}</td><td>${esc(d.type||'LAN')}</td><td><button class="btn sm ghost" onclick="addScannedAsAsset('${i}')">Add as asset</button></td></tr>`).join('');
  document.getElementById('scanBody').innerHTML=nodes||'<tr><td colspan=6 style="color:var(--muted)">No results yet — press Scan to discover devices.</td></tr>';
}
function addScannedAsAsset(i){
  const dev=lastScan[Number(i)];
  if(!dev)return;
  document.getElementById('scanModal').classList.remove('show');
  // Pre-fill the real Add Asset form instead of inserting straight away, so
  // it can be reviewed/edited before anything is actually saved.
  openModal(null,{
    Name:dev.host||('Device '+dev.ip),
    Type:'Network Device',
    Serial:'',
    MacAddress:dev.mac||'',
    Manufacturer:dev.vendor||'',
    Location:'LAN',
    Status:'Available',
    Note:'Discovered via network scan ('+(dev.ip||'')+(dev.mac?', '+dev.mac:'')+')'
  });
}

/* ---------- version + update check ---------- */
// Shows the running version and, on demand, asks the server whether a newer
// release has been published. The check only ever runs on this click -- a
// self-hosted tool shouldn't reach out on its own -- and nothing is
// installed from here: a container install is told to pull a new image,
// a source install to git pull, because those upgrade differently.
const SPLIT_RE = new RegExp(String.fromCharCode(10) + String.fromCharCode(10));
function verTag(v){ return 'v'+String(v||'?').replace(/^v/i,''); }
async function wireUpdateCheck(){
  const cur=document.getElementById('verCurrent');
  const kind=document.getElementById('verInstallKind');
  const btn=document.getElementById('checkUpdateBtn');
  const out=document.getElementById('updateResult');
  const badge=document.getElementById('verBadge');
  if(!cur||!btn) return;
  let running='';
  try{
    const r=await api('/api/version');
    if(r&&r.ok){
      const j=await r.json();
      running=j.version||'';
      cur.textContent=verTag(j.version);
      kind.textContent = j.is_docker
        ? 'Running as a Docker container — updates arrive as a new image'
        : 'Running from source';
    }
  }catch(e){}

  /* Poll until the new version answers, then reload into it — so "update
     now" ends with the user looking at the new version instead of at a dead
     page they have to work out how to revive. */
  function waitForRestart(box, from){
    let tries=0;
    const tick=async()=>{
      tries++;
      try{
        const r=await fetch('/api/version',{cache:'no-store'});
        if(r&&r.ok){
          const j=await r.json().catch(()=>({}));
          if(j.version && j.version!==from){
            box.innerHTML=`<b style="color:var(--grn)">✓ Now running ${esc(verTag(j.version))} — reloading…</b>`;
            setTimeout(()=>location.reload(),1200);
            return;
          }
        }
      }catch(e){ /* expected while the server is down */ }
      if(tries>80){
        box.innerHTML='<span style="color:var(--amber)">Taking longer than expected. Reload the page in a minute — the update may still be finishing.</span>';
        return;
      }
      setTimeout(tick,3000);
    };
    setTimeout(tick,4000);
  }

  async function applyUpdate(nowBtn, live, from){
    nowBtn.disabled=true;
    const label=nowBtn.textContent;
    nowBtn.textContent='⏳ UPDATING…';
    live.innerHTML='<span class="muted">Pulling the new version — don\'t close this page.</span>';
    let j={};
    try{
      const r=await api('/api/update/apply',{method:'POST'});
      j=r?await r.json().catch(()=>({})):{};
    }catch(e){ j={ok:false,error:e.message}; }
    if(j.ok){
      live.innerHTML=`<b style="color:var(--grn)">${esc(j.message||'Update applied.')}</b>`;
      nowBtn.textContent='⏳ RESTARTING…';
      if(j.restarting) waitForRestart(live, from);
      return;
    }
    nowBtn.disabled=false; nowBtn.textContent=label;
    live.innerHTML=`<div class="updwarn">${esc(j.error||'Update failed.')}</div>`
      +(j.log?`<pre class="mono updlog">${esc(j.log)}</pre>`:'');
  }

  btn.onclick=async()=>{
    btn.disabled=true; out.innerHTML='<span class="muted">Checking for updates…</span>';
    if(badge) badge.classList.remove('has-update');
    try{
      const r=await api('/api/check-update',{method:'POST'});
      const j=r?await r.json().catch(()=>({})):{};
      if(!j.ok){
        out.innerHTML=`<div class="updwarn">${esc(j.error||'Update check failed.')}</div>`;
      }else if(j.update_available){
        const cmd=j.update_command||'';
        if(badge) badge.classList.add('has-update');
        out.innerHTML=`<div class="updcard">
            <div class="updhead">
              <div class="updring">⬆</div>
              <div>
                <div class="updver"><span class="muted">${esc(verTag(j.current))}</span> → <b>${esc(verTag(j.latest))}</b></div>
                <div class="muted">A new version of IT-Vault is ready to install.</div>
              </div>
            </div>
            <div class="m-actions updacts">
              <button class="btn mag" id="updNowBtn">⬆ UPDATE NOW</button>
              ${cmd?'<button class="btn ghost sm" id="updCopyBtn">⎘ COPY COMMAND</button>':''}
              ${j.release_url?`<a class="btn ghost sm" href="${esc(j.release_url)}" target="_blank" rel="noopener">RELEASE NOTES ↗</a>`:''}
            </div>
            <div class="updhint">${
              j.can_one_click
                ? (j.update_method==='watchtower'
                    ? 'One click pulls the new image and recreates the container. Your database, invoices and backups are on volumes and are untouched.'
                    : 'One click pulls the new code, installs any new requirements and restarts. Your database is untouched.')
                : 'One-click updating needs Watchtower running alongside IT-Vault — a container can\'t replace itself. Click UPDATE NOW for the exact steps, or copy the command and run it yourself.'
            }</div>
            ${cmd?`<pre class="mono updlog updcmd" id="updCmd" title="Click to copy">${esc(cmd)}</pre>`:''}
            <div id="updLive" style="margin-top:8px"></div>
          </div>`;
        const live=document.getElementById('updLive');
        const nowBtn=document.getElementById('updNowBtn');
        if(nowBtn) nowBtn.onclick=()=>applyUpdate(nowBtn, live, j.current);
        const copyCmd=async(el,done,back)=>{
          try{
            await navigator.clipboard.writeText(cmd);
            if(el){el.textContent=done;setTimeout(()=>{el.textContent=back;},1800);}
            else toast('✓ COPIED');
          }catch(e){ toast('✕ Copy failed — select and copy manually'); }
        };
        const pre=document.getElementById('updCmd');
        if(pre) pre.onclick=()=>copyCmd(null);
        const cp=document.getElementById('updCopyBtn');
        if(cp) cp.onclick=async()=>{
          try{
            await navigator.clipboard.writeText(cmd);
            cp.textContent='✓ COPIED';
            setTimeout(()=>{cp.textContent='⎘ COPY COMMAND';},1800);
          }catch(e){
            // the clipboard API needs a secure context; select the text so
            // the user can copy it by hand rather than getting nothing
            const pre=document.getElementById('updCmd');
            if(pre){ const rg=document.createRange(); rg.selectNodeContents(pre);
              const sel=window.getSelection(); sel.removeAllRanges(); sel.addRange(rg); }
            toast('Copy blocked by the browser — command selected instead');
          }
        };
      }else{
        out.innerHTML=`<span style="color:var(--grn)">✓ You're on the latest version${j.latest?' ('+esc(verTag(j.latest))+')':''}.</span>`
          +(j.note?`<div class="muted" style="margin-top:4px">${esc(j.note)}</div>`:'');
      }
    }catch(e){
      out.innerHTML=`<div class="updwarn">Update check failed: ${esc(e.message)}</div>`;
    }
    btn.disabled=false;
  };
}

/* ---------- backup ---------- */
function fmtBytes(n){
  n=Number(n)||0;
  if(n<1024) return n+' B';
  if(n<1024*1024) return (n/1024).toFixed(1)+' KB';
  return (n/(1024*1024)).toFixed(1)+' MB';
}
async function openBackup(){
  const r=await api('/api/backups'); const rows=r?await r.json():[];
  document.getElementById('bkList').innerHTML=rows.map(x=>`<tr><td class="mono">${esc(x.file)}</td><td>${esc(x.scope)}</td><td class="mono">${esc(x.created||'')}</td><td class="mono">${fmtBytes(x.size)}</td><td><div class="row-actions">
      <button class="btn sm ghost row-more" onclick="toggleBackupRowMenu(event,'${esc(x.file)}')" aria-label="Actions">⋮</button>
    </div></td></tr>`).join('')||'<tr><td colspan=5 style="color:var(--muted)">none</td></tr>';
  const sr=await api('/api/settings'); const s=sr?await sr.json():{};
  document.getElementById('bkSchedule').value=s.backup_schedule||'off';
  document.getElementById('bkScheduleScope').value=s.backup_scope||'all';
  document.getElementById('bkRetain').value=s.backup_retain||7;
  document.getElementById('bkScheduleHint').textContent = s.backup_last_run
    ? `Older backups beyond the keep-limit are deleted automatically, every time a backup runs. Last scheduled run: ${s.backup_last_run}.`
    : 'Older backups beyond the keep-limit are deleted automatically, every time a backup runs (scheduled or manual).';
  document.getElementById('backupModal').classList.add('show');
}
async function saveBackupSchedule(){
  const body={
    backup_schedule: document.getElementById('bkSchedule').value,
    backup_scope: document.getElementById('bkScheduleScope').value,
    backup_retain: parseInt(document.getElementById('bkRetain').value,10)||7
  };
  const r=await api('/api/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r&&r.ok){toast('✓ SCHEDULE SAVED');openBackup();}else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}
document.getElementById('bkScheduleSave').onclick=saveBackupSchedule;
function doBackup(){
  const scope=document.getElementById('bkScope').value;
  window.open('/api/backup?scope='+encodeURIComponent(scope),'_blank');
  toast('✓ BACKUP CREATED');
  setTimeout(openBackup,800);
}
async function delBackup(file){
  if(!confirm('Delete backup "'+file+'"? This cannot be undone.'))return;
  const r=await api('/api/backups/'+encodeURIComponent(file),{method:'DELETE'});
  if(r&&r.ok){toast('✓ BACKUP DELETED');openBackup();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}
async function doRestore(){
  const file=document.getElementById('bkFile').files[0];
  if(!file){toast('Select a backup file');return;}
  if(!confirm('Restore "'+file.name+'"? This replaces current data for everything in the backup and cannot be undone.'))return;
  const fd=new FormData();fd.append('file',file);
  const r=await api('/api/restore',{method:'POST',body:fd});
  if(r&&r.ok){toast('✓ RESTORED');load();loadDashboard();}else if(r){toast('✕ '+await apiError(r));}
}
async function restoreFromBackup(file){
  if(!confirm('Restore "'+file+'"? This replaces current data for everything in the backup and cannot be undone.'))return;
  const r=await api('/api/backups/'+encodeURIComponent(file)+'/restore',{method:'POST'});
  if(r&&r.ok){toast('✓ RESTORED');load();loadDashboard();}else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}
function toggleBackupRowMenu(e,file){
  e.stopPropagation();
  const menu=document.getElementById('rowMenu');
  const key='bk'+file;
  if(rowMenuAssetId===key && menu.style.display!=='none'){ menu.style.display='none'; rowMenuAssetId=null; return; }
  rowMenuAssetId=key;
  menu.innerHTML=`
    <button onclick="closeRowMenu();window.open('/api/backups/${encodeURIComponent(file)}/download','_blank')">⬇ DOWNLOAD</button>
    <button onclick="closeRowMenu();restoreFromBackup('${esc(file)}')">↺ RESTORE</button>
    <div class="row-menu-sep"></div>
    <button class="danger" onclick="closeRowMenu();delBackup('${esc(file)}')">DELETE</button>`;
  const btn=e.currentTarget.getBoundingClientRect();
  menu.style.display='flex';
  const menuRect=menu.getBoundingClientRect();
  let left=btn.right-menuRect.width;
  if(left<8) left=8;
  let top=btn.bottom+4;
  if(top+menuRect.height>window.innerHeight-8) top=btn.top-menuRect.height-4;
  menu.style.left=left+'px'; menu.style.top=top+'px';
}

/* ---------- signature ---------- */
let signAssetId=null;   // the asset the open signModal belongs to
async function openSign(id){
  const r=await api('/api/assets/'+id+'/sign/link');
  const j=r?await r.json():{};
  if(!j.ok){toast('✕ '+(j.error||'failed'));return;}
  signAssetId=id;
  showSignLink(j.url);
  showSignMailTarget(j);
}
function showSignLink(url){
  document.getElementById('signUrl').value=url;
  const shareBtn=document.getElementById('signShareBtn');
  if(shareBtn)shareBtn.style.display=(navigator.share)?'':'none';
  document.getElementById('signModal').classList.add('show');
}
// Say who the mail would go to, and when it can't go, say why -- an offer to
// email with no address on file is just a button that fails.
function showSignMailTarget(j){
  const row=document.getElementById('signMailRow');
  const who=document.getElementById('signMailWho');
  const btn=document.getElementById('signMailBtn');
  if(!row||!who||!btn)return;
  btn.disabled=!j.can_email;
  btn.textContent='📧 SEND LINK';
  if(j.can_email){
    who.innerHTML='Sends to <b>'+esc(j.assignee||'')+'</b> &lt;'+esc(j.assignee_email)+'&gt;';
  }else if(!j.assignee){
    who.textContent='Not assigned to anyone yet — assign the asset to email the link.';
  }else if(!j.assignee_email){
    who.innerHTML='No email on file for <b>'+esc(j.assignee)+'</b> — add one on the Employees page.';
  }else{
    who.textContent='Email is not set up — add an SMTP server under Settings.';
  }
}
async function emailSignLink(){
  const btn=document.getElementById('signMailBtn');
  if(!signAssetId||!btn||btn.disabled)return;
  const label=btn.textContent;
  btn.disabled=true; btn.textContent='SENDING…';
  try{
    const r=await api('/api/assets/'+signAssetId+'/sign/send',{method:'POST'});
    const j=r?await r.json():{};
    if(j&&j.ok){
      // each send issues a fresh link, so the box has to show the one that
      // was actually mailed -- otherwise a copied link is already dead
      if(j.url)document.getElementById('signUrl').value=j.url;
      toast('✓ SENT TO '+(j.sent_to||'employee'));
    }else{
      toast('✕ '+((j&&j.error)||'Could not send'));
    }
  }catch(e){ toast('✕ Could not send'); }
  btn.textContent=label; btn.disabled=false;
}
async function copySignLink(){
  const url=document.getElementById('signUrl').value;
  try{
    if(navigator.clipboard&&navigator.clipboard.writeText){await navigator.clipboard.writeText(url);}
    else{const el=document.getElementById('signUrl');el.select();document.execCommand('copy');}
    toast('✓ LINK COPIED');
  }catch(e){toast('✕ Copy failed — select and copy manually');}
}
async function shareSignLink(){
  const url=document.getElementById('signUrl').value;
  if(!navigator.share){toast('✕ Sharing not supported on this browser');return;}
  try{await navigator.share({title:'Asset acknowledgement', text:'Please review and sign this asset acknowledgement.', url});}
  catch(e){/* user cancelled the share sheet -- not an error */}
}
document.getElementById('signCopyBtn').onclick=copySignLink;
document.getElementById('signMailBtn').onclick=emailSignLink;
document.getElementById('signShareBtn').onclick=shareSignLink;

/* ---------- users ---------- */
let editingUser=null;
// custom roles (created on the Roles page) get appended to the built-in 3
// wherever a user's role is picked, so a "Manager" role shows up right
// alongside admin / read-write / read-only.
async function populateRoleSelect(selectedRole){
  const sel=document.getElementById('u_role'); if(!sel)return;
  const built='<option value="read-only">read-only</option><option value="read-write">read-write</option><option value="admin">admin</option>';
  let custom='';
  try{
    const r=await api('/api/roles'); const roles=r?await r.json():[];
    custom=roles.map(x=>`<option value="${esc(x.name)}">${esc(x.name)} (custom)</option>`).join('');
  }catch(e){}
  sel.innerHTML=built+custom;
  if(selectedRole)sel.value=selectedRole;
}
let userModalFromList=false; // true only if userModal was opened from the legacy usersModal list (Profile -> Users)
async function openUsers(){
  const r=await api('/api/users');if(!r)return; const us=await r.json();
  const tbody=document.getElementById('usersBody');
  tbody.innerHTML=us.map(u=>`<tr><td>${esc(u.username)}</td><td>${esc(u.role)}</td><td>${esc(u.display||'')}</td><td><button class="btn sm ghost" onclick="editUser('${u.username}')">EDIT</button><button class="btn sm danger" onclick="delUser('${u.username}')">DEL</button></td></tr>`).join('');
  document.getElementById('usersModal').classList.add('show');
}
function closeUsersReturnProfile(){
  document.getElementById('usersModal').classList.remove('show');
}
function editUser(un){
  editingUser=un;
  userModalFromList=document.getElementById('usersModal').classList.contains('show');
  document.getElementById('u_username').readOnly=true;
  document.getElementById('userModalTitle').textContent='Edit user';
  // minimal prefetch
  api('/api/users').then(r=>r.json()).then(async list=>{const u=list.find(x=>x.username===un)||{};document.getElementById('u_username').value=u.username||un;document.getElementById('u_display').value=u.display||'';document.getElementById('u_email').value=u.email||'';await populateRoleSelect(u.role||'read-only');document.getElementById('u_password').value='';document.getElementById('usersModal').classList.remove('show');document.getElementById('userModal').classList.add('show');});
}
async function saveUser(){
  const username=document.getElementById('u_username').value.trim();
  const pw=document.getElementById('u_password').value;
  const body={display:document.getElementById('u_display').value.trim(),email:document.getElementById('u_email').value.trim(),role:document.getElementById('u_role').value};
  if(pw)body.password=pw;
  let r;
  if(editingUser){
    r=await api('/api/users/'+encodeURIComponent(username),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  } else {
    // creating: POST /api/users, which needs username + password
    if(!username||!pw){toast('✕ Username and password are required');return;}
    body.username=username;
    r=await api('/api/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  }
  if(r&&r.ok){toast('✓ Saved');document.getElementById('userModal').classList.remove('show');
    if(window.loadCfgUsers)loadCfgUsers();
    if(userModalFromList)openUsers();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}
async function addUser(){
  editingUser=null;
  userModalFromList=document.getElementById('usersModal').classList.contains('show');
  document.getElementById('usersModal').classList.remove('show');
  document.getElementById('u_username').readOnly=false;
  document.getElementById('userModalTitle').textContent='Add user';
  document.getElementById('u_username').value='';
  document.getElementById('u_display').value='';
  document.getElementById('u_email').value='';
  await populateRoleSelect('read-only');
  document.getElementById('u_password').value='';
  document.getElementById('userModal').classList.add('show');
}
async function delUser(un){
  if(!confirm('DELETE USER?'))return;
  const r=await api('/api/users/'+encodeURIComponent(un),{method:'DELETE'});
  if(r&&r.ok){toast('✓ User deleted');if(window.loadCfgUsers)loadCfgUsers();if(document.getElementById('usersModal').classList.contains('show'))openUsers();}else if(r){toast('✕ '+await apiError(r));}
}

/* ---------- custom roles (Assets/Contracts/Directory/Tickets read/write) ---------- */
// Roles are built from individual permissions rather than one level per
// module, so an admin can grant exactly one thing -- "reply to tickets" and
// nothing else. The module columns the rest of the app checks are derived
// server-side from whatever is ticked here, so the two can't drift.
let FEATURE_CATALOGUE=[];
let editingRoleId=null;

async function loadFeatureCatalogue(){
  if(FEATURE_CATALOGUE.length)return FEATURE_CATALOGUE;
  const r=await api('/api/features');
  FEATURE_CATALOGUE=r?await r.json():[];
  return FEATURE_CATALOGUE;
}

function renderPermTree(granted){
  const have=new Set(granted||[]);
  document.getElementById('rl_tree').innerHTML=FEATURE_CATALOGUE.map(g=>`
    <div class="permgrp">
      <div class="permhead">
        <label class="chk"><input type="checkbox" class="permall" data-grp="${g.key}"
          ${g.items.every(i=>have.has(i.key))?'checked':''}><span>${esc(g.label)}</span></label>
        <span class="permcount" id="pc_${g.key}"></span>
      </div>
      <div class="permitems">
        ${g.items.map(i=>`<label class="chk permitem">
          <input type="checkbox" class="permleaf" data-grp="${g.key}" value="${i.key}"
            ${have.has(i.key)?'checked':''}>
          <span>${esc(i.label)}${i.level==='admin_only'?' <em class="permnote">extra</em>':''}</span>
        </label>`).join('')}
      </div>
    </div>`).join('');
  // group header toggles everything under it; leaves keep the header honest
  document.querySelectorAll('#rl_tree .permall').forEach(box=>{
    box.onchange=()=>{
      document.querySelectorAll(`#rl_tree .permleaf[data-grp="${box.dataset.grp}"]`)
        .forEach(l=>{l.checked=box.checked;});
      updatePermCounts();
    };
  });
  document.querySelectorAll('#rl_tree .permleaf').forEach(l=>{ l.onchange=updatePermCounts; });
  updatePermCounts();
}

function updatePermCounts(){
  FEATURE_CATALOGUE.forEach(g=>{
    const leaves=[...document.querySelectorAll(`#rl_tree .permleaf[data-grp="${g.key}"]`)];
    const on=leaves.filter(l=>l.checked).length;
    const el=document.getElementById('pc_'+g.key);
    if(el)el.textContent=on?`${on} of ${leaves.length}`:'no access';
    const all=document.querySelector(`#rl_tree .permall[data-grp="${g.key}"]`);
    if(all){all.checked=on===leaves.length; all.indeterminate=on>0&&on<leaves.length;}
  });
  const total=document.querySelectorAll('#rl_tree .permleaf:checked').length;
  const t=document.getElementById('rl_total');
  if(t)t.textContent=total?`${total} permission${total===1?'':'s'} selected`:'Nothing selected yet';
}

function checkedFeatures(){
  return [...document.querySelectorAll('#rl_tree .permleaf:checked')].map(l=>l.value);
}

function roleFormReset(){
  editingRoleId=null;
  const n=document.getElementById('rl_name');
  n.value=''; n.disabled=false;
  renderPermTree([]);
  document.getElementById('rl_save').textContent='+ ADD ROLE';
}

// A role's grants are the summary people actually want in the list: "6
// permissions" tells you more than five repetitions of "No access".
function roleSummary(x){
  const n=(x.features||[]).length;
  if(!n)return '<span class="muted">no access</span>';
  const byGrp={};
  (x.features||[]).forEach(f=>{const g=f.split('.')[0];byGrp[g]=(byGrp[g]||0)+1;});
  return Object.keys(byGrp).sort().map(g=>`<span class="permtag">${esc(g)} ${byGrp[g]}</span>`).join(' ');
}

async function loadRolesModal(){
  await loadFeatureCatalogue();
  const r=await api('/api/roles'); const roles=r?await r.json():[];
  document.getElementById('rolesBody').innerHTML=roles.map(x=>`<tr>
      <td>${esc(x.name)}</td>
      <td>${roleSummary(x)}</td>
      <td class="row-actions">
        <button class="btn sm ghost" onclick='editRoleForm(${JSON.stringify(x.id)},${JSON.stringify(x.name)},${JSON.stringify(x.features||[])})'>EDIT</button>
        <button class="btn sm danger" onclick="delRole(${x.id})">DEL</button>
      </td>
    </tr>`).join('')||'<tr><td colspan=3 style="color:var(--muted)">No custom roles yet</td></tr>';
  roleFormReset();
  document.getElementById('rolesModal').classList.add('show');
}

function editRoleForm(id,name,features){
  editingRoleId=id;
  const n=document.getElementById('rl_name');
  n.value=name; n.disabled=true;
  renderPermTree(features||[]);
  document.getElementById('rl_save').textContent='✓ UPDATE ROLE';
  document.getElementById('rl_name').scrollIntoView({behavior:'smooth',block:'nearest'});
}

async function saveRole(){
  const body={name:document.getElementById('rl_name').value.trim(), features:checkedFeatures()};
  if(!editingRoleId && !body.name){toast('✕ Role name required');return;}
  if(!body.features.length && !confirm('This role has no permissions at all. Save it anyway?'))return;
  const r=editingRoleId
    ? await api('/api/roles/'+editingRoleId,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    : await api('/api/roles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r&&r.ok){toast('✓ ROLE SAVED');loadRolesModal();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}

async function delRole(id){
  if(!confirm('Delete this custom role?'))return;
  const r=await api('/api/roles/'+id,{method:'DELETE'});
  if(r&&r.ok){toast('✓ ROLE DELETED');loadRolesModal();}else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}

document.getElementById('manageRolesBtn').onclick=loadRolesModal;
document.getElementById('rolesClose').onclick=()=>document.getElementById('rolesModal').classList.remove('show');
document.getElementById('rl_save').onclick=saveRole;
window.editRoleForm=editRoleForm;window.delRole=delRole;

async function delRow(id){
  if(!confirm('DELETE this asset permanently?'))return;
  const r=await api('/api/assets/'+id,{method:'DELETE'});
  if(r&&r.ok){toast('✕ ASSET DELETED');load();loadDashboard();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}

/* ---------- settings / profile ---------- */
async function loadSettings(){
  // /api/settings needs settings rights — a user without them gets {error:...} back here,
  // not a settings object. Skip populating these admin-only fields in that case instead of
  // blanking them out with garbage; loadProfile() (My Account) still runs for everyone below.
  const r=await api('/api/settings');
  if(r && r.ok){
    const s=await r.json();
    {const _mx=document.getElementById('matrixOn'); if(_mx)_mx.checked=s.matrix_on!==0;}
    document.getElementById('s_host').value=s.smtp_host||'';
    document.getElementById('s_port').value=s.smtp_port||'587';
    document.getElementById('s_from').value=s.smtp_from||'';
    document.getElementById('s_user').value=s.smtp_user||'';
    document.getElementById('s_pass').value=s.smtp_pass||'';
    document.getElementById('uNew').checked=s.notify_new!==0;
    document.getElementById('uDel').checked=s.notify_delete!==0;
    document.getElementById('b_name').value=s.app_name||'IT-Vault';
    document.getElementById('b_logoText').value=s.logo_text||'IT-Vault';
    document.getElementById('b_phone').value=s.company_phone||'';
    document.getElementById('b_address').value=s.company_address||'';
    {const _lp=document.getElementById('b_letterheadPrev'); if(_lp){_lp.style.display=s.has_letterhead?'block':'none'; _lp.src='/letterhead.png?t='+Date.now();}
     const _lr=document.getElementById('removeLetterheadBtn'); if(_lr)_lr.style.display=s.has_letterhead?'':'none';}
    if(document.getElementById('qr_size'))document.getElementById('qr_size').value=(s.qr_size||160).toString();
    if(document.getElementById('label_size'))document.getElementById('label_size').value=(s.label_size||'50x19');
    if(document.getElementById('label_logo'))document.getElementById('label_logo').checked=(s.label_logo!=0);
    const chosenFields=(s.qr_fields||'Name,AssetID,Type,Serial,Status,Location').split(',').map(f=>f.trim()).filter(Boolean);
    LABEL_FIELD_KEYS.forEach(k=>{ const cb=document.getElementById('lf_'+k); if(cb && !cb.disabled) cb.checked=chosenFields.includes(k); });
  }
  await loadProfile();
}
async function saveLdap(){
  const body={
    ldap_server:document.getElementById('ldap_server').value.trim(),
    ldap_domain:document.getElementById('ldap_domain').value.trim(),
    ldap_base_dn:document.getElementById('ldap_base_dn').value.trim(),
    ldap_bind_user:document.getElementById('ldap_bind_user').value.trim(),
    ldap_bind_pass:document.getElementById('ldap_bind_pass').value
  };
  const r=await api('/api/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r&&r.ok){toast('✓ LDAP SAVED');}
  else if(r){toast('✕ '+await apiError(r));}
}
async function testLdap(){
  const body={
    ldap_server:document.getElementById('ldap_server').value.trim(),
    ldap_base_dn:document.getElementById('ldap_base_dn').value.trim(),
    ldap_bind_user:document.getElementById('ldap_bind_user').value.trim(),
    ldap_bind_pass:document.getElementById('ldap_bind_pass').value
  };
  const _lts=document.getElementById('ldapTestStatus'); if(_lts)_lts.textContent='Testing…';
  const r=await api('/api/ldap/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r&&_lts){const j=await r.json();_lts.textContent=(j.ok?'✓ ':'✕ ')+(j.msg||j.error);}
}
function applyTheme(t){
  // Theme light/dark is now derived from the base background inside applyCustomVars.
  // We keep this for API compatibility (presets call applyTheme) but it just syncs
  // the body class; the actual palette lives on :root inline vars set by applyCustomVars.
  document.body.classList.toggle('light', t === 'light');
}
async function saveSettings(){
  const body={matrix_on:(document.getElementById('matrixOn')||{checked:false}).checked?1:0,smtp_host:document.getElementById('s_host').value.trim(),smtp_port:parseInt(document.getElementById('s_port').value||'587',10),smtp_from:document.getElementById('s_from').value.trim(),smtp_user:document.getElementById('s_user').value.trim(),smtp_pass:document.getElementById('s_pass').value,notify_new:document.getElementById('uNew').checked?1:0,notify_delete:document.getElementById('uDel').checked?1:0};
  const r=await api('/api/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r&&r.ok){toast('✓ SETTINGS SAVED');}
  else if(r){toast('✕ '+await apiError(r));}
}
async function saveProfile(){
  const body={display:document.getElementById('pDisplay').value.trim(),email:document.getElementById('p_email').value.trim()};
  const r=await api('/api/profile',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r&&r.ok){toast('✓ PROFILE SAVED');}
  else if(r){toast('✕ '+await apiError(r));}
}
async function saveBrand(){
  const fd=new FormData();fd.append('app_name',document.getElementById('b_name').value.trim());fd.append('logo_text',document.getElementById('b_logoText').value.trim());
  fd.append('company_phone',document.getElementById('b_phone').value.trim());fd.append('company_address',document.getElementById('b_address').value.trim());
  const logo=document.getElementById('b_logo').files[0]; if(logo)fd.append('logo',logo);
  const r=await api('/api/settings',{method:'PUT',body:fd});
  if(r&&r.ok){toast('✓ BRAND SAVED');document.getElementById('b_logo').value='';applyBranding();}
  else if(r){toast('✕ '+await apiError(r));}
}
async function saveLetterhead(){
  const f=document.getElementById('b_letterhead').files[0];
  if(!f){toast('✕ Choose a PDF or image first');return;}
  const fd=new FormData();fd.append('letterhead',f);
  const r=await api('/api/settings',{method:'PUT',body:fd});
  if(r&&r.ok){toast('✓ LETTERHEAD SAVED');document.getElementById('b_letterhead').value='';loadSettings();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}
async function removeLetterhead(){
  if(!confirm('Remove the letterhead? Prints/PDFs will go back to the plain logo header.'))return;
  const fd=new FormData();fd.append('remove_letterhead','1');
  const r=await api('/api/settings',{method:'PUT',body:fd});
  if(r&&r.ok){toast('✓ LETTERHEAD REMOVED');loadSettings();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}
async function removeLogo(){
  if(!confirm('Remove the current logo? This cannot be undone.'))return;
  const fd=new FormData();fd.append('app_name',document.getElementById('b_name').value.trim());fd.append('logo_text',document.getElementById('b_logoText').value.trim());fd.append('remove_logo','1');
  const r=await api('/api/settings',{method:'PUT',body:fd});
  if(r&&r.ok){toast('✓ LOGO REMOVED');document.getElementById('b_logo').value='';applyBranding();}
  else if(r){toast('✕ '+await apiError(r));}
}
async function applyBranding(){
  const me=await fetch('/api/me').then(r=>r.json());
  const nm=me.app_name||me.display||'IT-Vault';
  window.APP_NAME=nm;
  window.HAS_LETTERHEAD=!!me.has_letterhead;
  // The sidebar shows Logo Text, which is a separate setting from the
  // organisation name -- that is the whole point of having both, and the
  // field is even labelled "Logo Text (sidebar)". It was being ignored,
  // so the sidebar always read the company name.
  const sideText=(me.logo_text||'').trim()||nm;
  window.SIDE_TEXT=sideText;
  document.getElementById('sideName').textContent=sideText;
  document.title=nm+' // Assets Manager';
  const sideLogo=document.getElementById('sideLogo');
  if(sideLogo){
    // logo is served as a static file at /logo.png (cache-busted). Show it always.
    sideLogo.src='/logo.png?t='+Date.now();
    sideLogo.style.display='';
  }
  const loginLogo=document.getElementById('loginLogo');
  if(loginLogo){ loginLogo.src='/logo.png?t='+Date.now(); loginLogo.style.display=''; }
  const logoPrev=document.getElementById('b_logoPrev');
  if(logoPrev){ logoPrev.src='/logo.png?t='+Date.now(); }
  const st=document.getElementById('sideName'); if(st) st.textContent=sideText;
  // rebrand any static "IT GUY / ..." crumb text
  const crumbPrefix='IT GUY';
  document.querySelectorAll('.crumb').forEach(el=>{
    const t=el.textContent&&el.textContent.trim();
    if(t && t.startsWith(crumbPrefix)) el.textContent=nm+t.slice(crumbPrefix.length);
  });
}
async function saveLabel(){
  const fields=LABEL_FIELD_KEYS.filter(k=>{ const cb=document.getElementById('lf_'+k); return cb && cb.checked; });
  const body={
    qr_size: document.getElementById('qr_size').value,
    qr_fields: fields.join(','),
    label_size: document.getElementById('label_size').value.trim(),
    label_logo: document.getElementById('label_logo').checked ? 1 : 0
  };
  const r=await api('/api/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r&&r.ok){toast('✓ LABEL SETTINGS SAVED');}
  else if(r){toast('✕ '+await apiError(r));}
}

/* ---------- events ---------- */
window.addEventListener('error', (e) => console.error('[ITGUY] ERROR', e.message, 'at', e.filename, ':', e.lineno));
window.addEventListener('unhandledrejection', (e) => console.error('[ITGUY] UNHANDLED REJECTION', e.reason));
document.getElementById('saveBtn').onclick=saveModal;
document.getElementById('cancelBtn').onclick=closeModal;
const naTop=document.getElementById('navAdd'); if(naTop) naTop.onclick=()=>openModal();
document.getElementById('addBtn2').onclick=()=>openModal();
const ni2=document.getElementById('navImport'); if(ni2) ni2.onclick=()=>document.getElementById('file').click();
document.getElementById('importBtn2').onclick=()=>document.getElementById('file').click();
document.getElementById('exportBtn2').onclick=doExport;
document.getElementById('file').onchange=async()=>{
  const inp=document.getElementById('file');
  const file=inp.files[0]; if(!file)return;
  const fd=new FormData(); fd.append('file',file);
  const r=await api('/api/import',{method:'POST',body:fd});
  inp.value='';
  const j=r?await r.json().catch(()=>({})):{};
  if(r&&r.ok){ toast(`✓ imported: ${j.added||0} added, ${j.updated||0} updated`); load(); loadDashboard(); }
  else { toast('✕ '+(j.error||'import failed')); }
};
document.getElementById('ctImportBtn').onclick=()=>document.getElementById('ctFile').click();
document.getElementById('ctExportBtn').onclick=()=>window.location='/api/contracts/export';
document.getElementById('ctFile').onchange=async()=>{
  const inp=document.getElementById('ctFile');
  const file=inp.files[0]; if(!file)return;
  const fd=new FormData(); fd.append('file',file);
  const r=await api('/api/contracts/import',{method:'POST',body:fd});
  inp.value='';
  const j=r?await r.json().catch(()=>({})):{};
  if(r&&r.ok){ toast(`✓ imported: ${j.added||0} added`); loadContracts(); }
  else { toast('✕ '+(j.error||'import failed')); }
};
document.getElementById('addUserBtn').onclick=addUser;
document.getElementById('userSave').onclick=saveUser;
{const _uc=document.getElementById('userCancel'); if(_uc)_uc.onclick=()=>{document.getElementById('userModal').classList.remove('show'); if(userModalFromList)openUsers();};}
// usersModal close returns to Profile (since it's opened from Profile->Users tab)
(function(){
  const um=document.getElementById('usersModal');
  if(!um)return;
  const c=document.getElementById('usersClose');
  if(c)c.onclick=closeUsersReturnProfile;
  um.addEventListener('click',e=>{ if(e.target===um) closeUsersReturnProfile(); });
})();
document.getElementById('accSave').onclick=saveProfile;
document.getElementById('saveSettings').onclick=saveSettings;
document.getElementById('pm_saveBrand').onclick=saveBrand;
document.getElementById('removeLogoBtn').onclick=removeLogo;
document.getElementById('pm_saveLetterhead').onclick=saveLetterhead;
document.getElementById('removeLetterheadBtn').onclick=removeLetterhead;
document.getElementById('navAudit').onclick=openAudit;
document.getElementById('auditSearch').oninput=renderAuditRows;
document.getElementById('auditClearBtn').onclick=clearAuditLog;
document.getElementById('navScan').onclick=openScan;
document.getElementById('scanBtn').onclick=doScan;

// ---- Heartbeat: uptime monitoring ----
// The engine is server side: it probes each monitor on its own interval around
// the clock, keeps the history and sends the alert. This is the window onto it.
//
// Rows are ordered down first, then still-being-retried, then healthy, then
// paused. That is the order that matters when someone opens this in a hurry.
let HB={monitors:[],counts:{},channels:[],window_hours:24};
let hbTimer=null, hbEditId=null, hbDetailId=null, hbChanEditId=null;
const HB_RANK={down:0,pending:1,up:2,paused:3};
const HB_KIND_HINT={
  ping:'Ping is the right check for switches, access points, printers and cameras — anything that should simply be reachable.',
  http:'HTTP asks for the page and treats anything outside the accepted codes as down. Certificate trust is a separate question — the expiry is reported in its own column instead of failing the check.',
  keyword:'Fetches the page and looks for your text in the body. Catches the case a plain HTTP check misses: the server answers 200 while the application behind it is broken.',
  port:'Opens a TCP connection and closes it again. Use it for a service that answers on a port but not over HTTP — SQL on 3306, RDP on 3389, SMTP on 25.',
  dns:'Resolves the name and fails if it stops resolving. Worth having on anything whose DNS you depend on but do not control.'
};
const HB_CHAN_HINT={
  email:'Uses the SMTP server configured above. Leave Send to empty and it goes to every user with an email on their profile.',
  webhook:'Every alert is POSTed as JSON: event, monitor, target, status, error and the message text. Point it at whatever you already run.',
  slack:'Create an incoming webhook in Slack (Apps ▸ Incoming Webhooks) and paste the URL here.',
  telegram:'Talk to @BotFather to create a bot and get its token, then add the bot to the chat and use that chat id.'
};

function hbStatusOf(m){ return !m.enabled ? 'paused' : (m.status||'pending'); }
function hbRank(s){ return HB_RANK[s]===undefined ? 9 : HB_RANK[s]; }
function hbAgo(ts){
  if(!ts) return '—';
  const t=Date.parse(String(ts).replace(' ','T'));
  if(isNaN(t)) return '—';
  const s=Math.max(0,Math.round((Date.now()-t)/1000));
  if(s<60) return s+'s ago';
  if(s<3600) return Math.round(s/60)+'m ago';
  if(s<86400) return Math.round(s/3600)+'h ago';
  return Math.round(s/86400)+'d ago';
}

// ---- the ECG trace ----------------------------------------------------
// One heartbeat per recorded check, oldest on the left. An up check draws a
// full QRS complex; a failed check draws a flatline, which is the honest
// picture and reads instantly. The bright segment sweeping along the trace is
// the same idea as a bedside monitor -- it says the thing is still being
// watched right now, not that the data is moving.
function hbEcg(m, opts){
  opts=opts||{};
  const st=hbStatusOf(m);
  const beats=(m.bars||[]).slice(-(opts.beats||22));
  const W=opts.w||136, H=opts.h||30, mid=H/2;
  const ms=(m.series||[]).slice(-(opts.beats||22));
  const lo=Math.min.apply(null, ms.length?ms:[0]), hi=Math.max.apply(null, ms.length?ms:[1]);
  const span=(hi-lo)||1;
  let msi=0;
  let d='M0 '+mid.toFixed(1);
  if(!beats.length){
    // never checked yet: a bare baseline, still sweeping so it reads as armed
    d+=' L'+W+' '+mid.toFixed(1);
  } else {
    const seg=W/beats.length;
    beats.forEach((s,i)=>{
      const x=i*seg;
      const at=(f)=>(x+seg*f).toFixed(1);
      if(s==='up'){
        // a quicker response draws a taller spike, so the trace carries the
        // response shape as well as the up/down record
        const v=ms[msi++];
        const amp=(v===undefined) ? 10 : (7+6*(1-(v-lo)/span));
        d+=' L'+at(0.10)+' '+mid.toFixed(1)
         + ' Q'+at(0.17)+' '+(mid-2.5)+' '+at(0.24)+' '+mid.toFixed(1)
         + ' L'+at(0.32)+' '+(mid+1.8).toFixed(1)
         + ' L'+at(0.40)+' '+(mid-amp).toFixed(1)
         + ' L'+at(0.48)+' '+(mid+amp*0.42).toFixed(1)
         + ' L'+at(0.56)+' '+mid.toFixed(1)
         + ' Q'+at(0.72)+' '+(mid-3.2)+' '+at(0.86)+' '+mid.toFixed(1)
         + ' L'+at(1)+' '+mid.toFixed(1);
      } else if(s==='down'){
        d+=' L'+at(1)+' '+mid.toFixed(1);                 // flatline
      } else {
        d+=' L'+at(0.44)+' '+mid.toFixed(1)
         + ' L'+at(0.52)+' '+(mid-3.5).toFixed(1)
         + ' L'+at(0.60)+' '+mid.toFixed(1)
         + ' L'+at(1)+' '+mid.toFixed(1);
      }
    });
  }
  const cls='hbecg '+st+(beats.length?'':' idle');
  return `<svg class="${cls}" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}"
     preserveAspectRatio="none" role="img"
     aria-label="${beats.length} recent checks, ${beats.filter(b=>b==='up').length} up">
    <path class="hbecg-base" d="${d}" pathLength="1000"/>
    <path class="hbecg-live" d="${d}" pathLength="1000"/>
  </svg>`;
}

function hbAvgResponse(mons){
  const v=mons.filter(m=>m.enabled&&m.status==='up'&&m.last_ms!=null).map(m=>m.last_ms);
  if(!v.length) return '—';
  return Math.round(v.reduce((a,b)=>a+b,0)/v.length)+' ms';
}

async function loadHeartbeat(){
  const st=document.getElementById('hbStatus'); if(!st) return;
  const hrs=(document.getElementById('hbWindow')||{}).value||'24';
  const r=await api('/api/heartbeat/state?hours='+encodeURIComponent(hrs));
  if(!r) return;                                   // api() already reported it
  if(r.status===403){ st.textContent='No access to Heartbeat.'; return; }
  const j=await r.json().catch(()=>null);
  if(!j){ st.textContent='✕ could not read monitor status'; return; }
  HB=j; st.textContent='';
  renderHeartbeat();
  if(hbDetailId) loadHbDetail(hbDetailId, true);
}

function renderHeartbeat(){
  const body=document.getElementById('hbBody'); if(!body) return;
  const wrap=document.getElementById('hbTableWrap'), empty=document.getElementById('hbEmpty');
  const q=((document.getElementById('hbSearch')||{}).value||'').trim().toLowerCase();
  const f=(document.getElementById('hbFilter')||{}).value||'';
  const all=(HB.monitors||[]).slice().sort((a,b)=>
    (hbRank(hbStatusOf(a))-hbRank(hbStatusOf(b))) ||
    String(a.name||'').toLowerCase().localeCompare(String(b.name||'').toLowerCase()));
  const mons=all.filter(m=>{
    if(f && hbStatusOf(m)!==f) return false;
    if(!q) return true;
    return [m.name,m.kind,m.target,m.port,m.tag].some(x=>String(x||'').toLowerCase().includes(q));
  });

  const c=HB.counts||{};
  const set=(id,v)=>{const el=document.getElementById(id); if(el) el.textContent=v;};
  set('hbNDown',c.down||0); set('hbNPending',c.pending||0);
  set('hbNUp',c.up||0); set('hbNPaused',c.disabled||0);
  set('hbAvg',hbAvgResponse(all));
  set('hbMeta',all.length ? (mons.length===all.length
        ? all.length+' monitor'+(all.length===1?'':'s')+' · '+hbWindowLabel(HB.window_hours)
        : mons.length+' of '+all.length+' shown') : '');

  if(!all.length){
    wrap.style.display='none'; empty.style.display='block';
    empty.textContent='NO MONITORS YET — ADD ONE, OR RUN A NETWORK SCAN AND WATCH WHAT IT FINDS';
    return;
  }
  if(!mons.length){
    wrap.style.display='none'; empty.style.display='block';
    empty.textContent='NOTHING MATCHES THAT FILTER';
    return;
  }
  empty.style.display='none'; wrap.style.display='';
  body.innerHTML=mons.map(m=>{
    const st=hbStatusOf(m), paused=!m.enabled;
    const err=(m.last_error&&st!=='up'&&st!=='paused')
      ?`<div class="hberr" title="${esc(m.last_error)}">${esc(m.last_error)}</div>`:'';
    const mute=m.notify?'':'<span class="hbmute" title="alerts are off for this monitor">🔇</span>';
    const ud=m.upside_down?'<span class="hbtag" title="upside down: this should not respond">INVERTED</span>':'';
    const tag=m.tag?`<span class="hbtag">${esc(m.tag)}</span>`:'';
    const cert=(m.cert_days==null)?'<span class="muted">—</span>'
      :`<span class="${m.cert_days<14?'hbcert-bad':(m.cert_days<30?'hbcert-warn':'')}">${esc(String(m.cert_days))}d</span>`;
    return `<tr class="${st==='down'?'hb-down':''}">
      <td><span class="hbdot ${st}"></span>${st==='pending'?'CHECKING':st.toUpperCase()}</td>
      <td class="hblink" onclick="hbOpen(${m.id})"><b>${esc(m.name||'')}</b>${mute}${tag}${ud}${err}</td>
      <td>${esc((m.kind||'').toUpperCase())}</td>
      <td class="mono">${esc(m.target||'')}${m.port?':'+esc(String(m.port)):''}</td>
      <td>${m.last_ms==null?'<span class="muted">—</span>':esc(String(m.last_ms))+' ms'}</td>
      <td class="hbecg-cell">${hbEcg(m)}</td>
      <td>${m.uptime==null?'<span class="muted">—</span>':esc(String(m.uptime))+'%'}</td>
      <td>${cert}</td>
      <td class="muted">${esc(hbAgo(m.last_change))}</td>
      <td><div class="row-actions">
        <button class="btn sm ghost" onclick="hbToggle(${m.id})" title="${paused?'resume checking':'stop checking, keep the monitor'}">${paused?'▶':'❚❚'}</button>
        <button class="btn sm" onclick="hbEdit(${m.id})">EDIT</button>
        <button class="btn sm danger" onclick="hbDel(${m.id})">DEL</button>
      </div></td></tr>`;
  }).join('');
}

function hbWindowLabel(h){
  h=parseInt(h||24,10);
  if(h<=1) return '1h window';
  if(h<48) return h+'h window';
  if(h<720) return Math.round(h/24)+'d window';
  if(h<8760) return Math.round(h/24)+'d window';
  return '1y window';
}

async function hbCheckNow(){
  const b=document.getElementById('hbCheckBtn'); const old=b.textContent;
  b.disabled=true; b.textContent='CHECKING…';
  const r=await api('/api/heartbeat/check',{method:'POST'});
  b.disabled=false; b.textContent=old;
  if(!r) return;
  if(!r.ok){ toast('✕ '+await apiError(r)); return; }
  const j=await r.json().catch(()=>({}));
  toast('✓ CHECKED '+(j.checked||0)+' MONITOR'+((j.checked||0)===1?'':'S'));
  loadHeartbeat();
}

// ---- add / edit -------------------------------------------------------
function hbKindUI(){
  const k=document.getElementById('hb_kind').value;
  const show=(id,on)=>{const e=document.getElementById(id); if(e) e.style.display=on?'':'none';};
  const web=(k==='http'||k==='keyword');
  show('hb_portWrap', k==='port');
  show('hb_kwWrap', k==='keyword');
  show('hb_kwOpts', k==='keyword');
  show('hb_methodWrap', web);
  show('hb_codesWrap', web);
  show('hb_tlsOpts', web);
  document.getElementById('hb_targetLabel').textContent=
    web ? 'URL or host' : (k==='dns' ? 'Hostname to resolve' : 'IP or hostname');
  document.getElementById('hb_target').placeholder=
    web ? 'e.g. https://intranet.local/health'
        : (k==='dns' ? 'e.g. mail.company.com' : 'e.g. 192.168.0.1');
  document.getElementById('hb_kindHint').textContent=HB_KIND_HINT[k]||'';
  hbThreshHint();
}
// Spelling out when the alert actually arrives, because the retry count is
// the setting people get wrong -- too low and it cries wolf, too high and an
// outage sits unreported.
function hbThreshHint(){
  const el=document.getElementById('hb_thHint'); if(!el) return;
  const iv=parseInt(document.getElementById('hb_interval').value||'60',10);
  const th=parseInt(document.getElementById('hb_thresh').value||'2',10);
  const rs=parseInt(document.getElementById('hb_resend').value||'0',10);
  if(!iv||!th){ el.textContent=''; return; }
  const secs=iv*th, mins=Math.round(secs/60);
  const when=secs<60?(secs+' seconds'):(mins+' minute'+(mins===1?'':'s'));
  let s='You will hear about an outage roughly '+when+' after it starts — '+th+
        ' failed check'+(th===1?'':'s')+' at '+iv+'s apart — and once more when it recovers.';
  s+= rs>0 ? (' While it stays down you get a reminder every '+rs+' further failed check'+(rs===1?'':'s')+'.')
           : ' Nothing in between.';
  el.textContent=s;
}
function hbChanChecklist(selected){
  const box=document.getElementById('hb_chanBox');
  const list=document.getElementById('hb_chanList');
  const chans=(HB.channels||[]);
  if(!chans.length){
    box.style.display=(MY_ROLE===ROLE_ADMIN)?'':'none';
    // channels are configured in one place now, so point at it rather than
    // opening a second copy of the same form from here
    list.innerHTML='<p class="muted" style="margin:0">No channels set up yet. '
      +'<a class="mlink" onclick="goToNotificationSettings()">'
      +'Set them up in Settings ▸ Notifications ↗</a>, or leave this alone and '
      +'alerts go to everyone with an email on their profile.</p>';
    return;
  }
  box.style.display='';
  const want=new Set(String(selected||'').split(',').filter(Boolean));
  list.innerHTML=chans.map(ch=>`<label class="permitem"><input type="checkbox" class="hb-chan-chk"
      value="${ch.id}"${want.has(String(ch.id))?' checked':''}${ch.enabled?'':' disabled'}>
      <span>${esc(ch.name)} <span class="permtag">${esc(ch.kind)}</span>${ch.enabled?'':' <span class="muted">(inactive)</span>'}</span></label>`).join('');
}
async function openHbModal(id){
  hbEditId=id||null;
  const m=id?(HB.monitors||[]).find(x=>x.id===id):null;
  const set=(el,v)=>{const e=document.getElementById(el); if(e) e.value=v;};
  const chk=(el,v)=>{const e=document.getElementById(el); if(e) e.checked=!!v;};
  document.getElementById('hbModalTitle').textContent=m?'EDIT MONITOR':'ADD MONITOR';
  set('hb_name',m?(m.name||''):'');
  set('hb_kind',m?(m.kind||'ping'):'ping');
  set('hb_target',m?(m.target||''):'');
  set('hb_port',(m&&m.port)?m.port:'');
  set('hb_keyword',m?(m.keyword||''):'');
  set('hb_method',m?(m.http_method||'GET'):'GET');
  set('hb_codes',m?(m.accepted_codes||'200-299'):'200-299');
  set('hb_tag',m?(m.tag||''):'');
  set('hb_note',m?(m.note||''):'');
  set('hb_interval',m?(m.interval_s||60):60);
  set('hb_thresh',m?(m.fail_threshold||2):2);
  set('hb_timeout',m?(m.timeout_s||8):8);
  set('hb_retryEvery',m?(m.retry_interval_s||0):0);
  set('hb_resend',m?(m.resend_every||0):0);
  chk('hb_notify',m?m.notify:true);
  chk('hb_enabled',m?m.enabled:true);
  chk('hb_upside',m?m.upside_down:false);
  chk('hb_kwInvert',m?m.keyword_invert:false);
  chk('hb_ignoreTls',m?m.ignore_tls:true);
  document.getElementById('hbDelete').style.display=m?'':'none';
  hbKindUI();
  hbChanChecklist(m?m.channels:'');
  // the asset list is only needed while the form is open, so fetch it here
  const sel=document.getElementById('hb_asset');
  sel.innerHTML='<option value="">-- none --</option>';
  try{
    const r=await api('/api/assets');
    if(r&&r.ok){
      const list=await r.json();
      sel.innerHTML='<option value="">-- none --</option>'+(list||[]).map(a=>
        `<option value="${esc(a._id)}">${esc(a.Name||a.AssetTag||a._id)}${a.AssetTag?' ('+esc(a.AssetTag)+')':''}</option>`).join('');
    }
  }catch(e){}
  sel.value=(m&&m.asset_id)?m.asset_id:'';
  document.getElementById('hbModal').classList.add('show');
  document.getElementById('hb_name').focus();
}
async function saveHbMonitor(){
  const g=(id)=>document.getElementById(id);
  const kind=g('hb_kind').value;
  const target=g('hb_target').value.trim();
  if(!target){ toast('✕ enter an IP, hostname or URL'); return; }
  const port=g('hb_port').value.trim();
  if(kind==='port' && !port){ toast('✕ a port check needs a port number'); return; }
  if(kind==='keyword' && !g('hb_keyword').value.trim()){ toast('✕ enter the keyword to look for'); return; }
  const body={
    name:g('hb_name').value.trim()||target,
    kind, target, port:port?parseInt(port,10):null,
    keyword:g('hb_keyword').value.trim(),
    keyword_invert:g('hb_kwInvert').checked,
    http_method:g('hb_method').value,
    accepted_codes:g('hb_codes').value.trim()||'200-299',
    ignore_tls:g('hb_ignoreTls').checked,
    tag:g('hb_tag').value.trim(),
    note:g('hb_note').value.trim(),
    interval_s:parseInt(g('hb_interval').value||'60',10),
    fail_threshold:parseInt(g('hb_thresh').value||'2',10),
    timeout_s:parseInt(g('hb_timeout').value||'8',10),
    retry_interval_s:parseInt(g('hb_retryEvery').value||'0',10),
    resend_every:parseInt(g('hb_resend').value||'0',10),
    notify:g('hb_notify').checked,
    enabled:g('hb_enabled').checked,
    upside_down:g('hb_upside').checked,
    channels:[...document.querySelectorAll('.hb-chan-chk:checked')].map(c=>c.value),
    asset_id:g('hb_asset').value||''
  };
  const editing=hbEditId;
  const r=await api(editing?('/api/heartbeat/monitors/'+editing):'/api/heartbeat/monitors',
    {method:editing?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!r) return;
  if(!r.ok){ toast('✕ '+await apiError(r)); return; }
  const j=await r.json().catch(()=>({}));
  document.getElementById('hbModal').classList.remove('show');
  toast(editing?'✓ MONITOR UPDATED':'✓ MONITOR ADDED');
  hbEditId=null;
  // probe it straight away rather than leaving the row blank until the tick
  const id=editing||j.id;
  if(id) await api('/api/heartbeat/monitors/'+id+'/check',{method:'POST'});
  loadHeartbeat();
}
window.hbEdit=(id)=>openHbModal(id);
window.hbDel=async(id)=>{
  const m=(HB.monitors||[]).find(x=>x.id===id);
  if(!confirm('Delete monitor "'+((m&&m.name)||id)+'" and its history?')) return;
  const r=await api('/api/heartbeat/monitors/'+id,{method:'DELETE'});
  if(r&&r.ok){
    toast('✓ MONITOR DELETED');
    if(hbDetailId===id){ document.getElementById('hbDetailModal').classList.remove('show'); hbDetailId=null; }
    loadHeartbeat();
  } else if(r){ toast('✕ '+await apiError(r)); }
};
window.hbToggle=async(id)=>{
  const m=(HB.monitors||[]).find(x=>x.id===id); if(!m) return;
  const r=await api('/api/heartbeat/monitors/'+id,{method:'PUT',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({kind:m.kind,target:m.target,port:m.port,keyword:m.keyword,enabled:!m.enabled})});
  if(r&&r.ok){ toast(m.enabled?'❚❚ PAUSED':'▶ RESUMED'); loadHeartbeat(); }
  else if(r){ toast('✕ '+await apiError(r)); }
};

// ---- detail view ------------------------------------------------------
window.hbOpen=(id)=>{ hbDetailId=id; document.getElementById('hbDetailModal').classList.add('show'); loadHbDetail(id); };
async function loadHbDetail(id, quiet){
  const hrs=(document.getElementById('hbdWindow')||{}).value||'24';
  const r=await api('/api/heartbeat/monitors/'+id+'/detail?hours='+encodeURIComponent(hrs));
  if(!r||!r.ok) return;
  const j=await r.json().catch(()=>null); if(!j) return;
  const m=j.monitor||{}, st=hbStatusOf(m);
  document.getElementById('hbdTitle').textContent=(m.name||'MONITOR').toUpperCase();
  document.getElementById('hbdDot').className='hbdot '+st;
  document.getElementById('hbdStatus').textContent=
    (st==='pending'?'CHECKING':st.toUpperCase())+(m.last_change?(' · since '+hbAgo(m.last_change)):'');
  document.getElementById('hbdTarget').textContent=
    (m.kind||'').toUpperCase()+' · '+(m.target||'')+(m.port?(':'+m.port):'')
    +' · every '+(m.interval_s||60)+'s'+(m.note?(' · '+m.note):'');
  const w=j.windows||{};
  // 100% in the default accent read as an alarm; uptime is a verdict, so it
  // gets a verdict colour
  const put=(id,v)=>{
    const el=document.getElementById(id);
    el.textContent = v==null ? '—' : (v+'%');
    el.className='kpi-v '+(v==null?'none':(v>=99.5?'ok':(v>=95?'warn':'bad')));
  };
  put('hbdU24',(w['24h']||{}).uptime);
  put('hbdU7',(w['7d']||{}).uptime);
  put('hbdU30',(w['30d']||{}).uptime);
  put('hbdU1y',(w['1y']||{}).uptime);
  const avg=(w['24h']||{}).avg_ms;
  document.getElementById('hbdAvg').textContent=avg==null?'—':(avg+' ms');
  // the ECG for the detail view uses the same generator, just wider
  const bars=(j.series||[]).map(p=>p.status==='mixed'?'pending':p.status);
  const msv=(j.series||[]).filter(p=>p.ms!=null).map(p=>p.ms);
  document.getElementById('hbdEcg').innerHTML=hbEcg({bars, series:msv, enabled:m.enabled, status:m.status},
                                                    {w:760,h:64,beats:40});
  document.getElementById('hbdChart').innerHTML=hbSparkChart(j.series||[]);
  document.getElementById('hbdChartHint').textContent=
    (j.series||[]).length ? ((j.window_hours<=48)
      ? (j.series.length+' checks in the last '+hbWindowLabel(j.window_hours).replace(' window',''))
      : ('hourly averages over the last '+hbWindowLabel(j.window_hours).replace(' window','')))
    : 'No checks recorded in this window yet.';
  const evb=document.getElementById('hbdEvents');
  const evs=j.events||[];
  evb.innerHTML=evs.map(e=>`<tr>
      <td class="mono">${esc(e.t||'')}</td>
      <td><span class="hbdot ${e.kind==='up'?'up':(e.kind==='down'?'down':'paused')}"></span>${esc((e.kind||'').toUpperCase())}</td>
      <td>${esc(e.message||'')}</td></tr>`).join('');
  document.getElementById('hbdEventsEmpty').style.display=evs.length?'none':'block';
  const pb=document.getElementById('hbdPause');
  pb.textContent=m.enabled?'❚❚ PAUSE':'▶ RESUME';
  if(!quiet) document.getElementById('hbdWindow').focus();
}
// A plain inline chart -- no library, so it cannot fail to load and cannot
// drift out of step with the theme.
function hbSparkChart(series){
  const pts=series.filter(p=>p.ms!=null);
  if(!pts.length) return '<div class="empty" style="padding:16px">NO RESPONSE DATA IN THIS WINDOW</div>';
  const W=760, H=120, pad=18;
  const hi=Math.max.apply(null,pts.map(p=>p.ms)), lo=0;
  const span=(hi-lo)||1;
  const step=pts.length>1?(W-pad*2)/(pts.length-1):0;
  const xy=(p,i)=>[(pad+i*step).toFixed(1), (H-pad-((p.ms-lo)/span)*(H-pad*2)).toFixed(1)];
  const line=pts.map((p,i)=>xy(p,i).join(',')).join(' ');
  const area=`${pad},${H-pad} ${line} ${(pad+(pts.length-1)*step).toFixed(1)},${H-pad}`;
  const downs=series.map((p,i)=>({p,i})).filter(x=>x.p.status==='down');
  const allStep=series.length>1?(W-pad*2)/(series.length-1):0;
  const bands=downs.map(x=>`<rect class="hbc-down" x="${(pad+x.i*allStep-1).toFixed(1)}" y="${pad}"
      width="${Math.max(2,allStep).toFixed(1)}" height="${H-pad*2}"/>`).join('');
  return `<svg class="hbchart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img"
      aria-label="response time, peak ${hi} ms">
    <line class="hbc-axis" x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${H-pad}"/>
    <line class="hbc-axis" x1="${pad}" y1="${pad}" x2="${W-pad}" y2="${pad}"/>
    ${bands}
    <polygon class="hbc-area" points="${area}"/>
    <polyline class="hbc-line" points="${line}"/>
    <text class="hbc-lbl" x="${pad}" y="${pad-5}">${hi} ms</text>
    <text class="hbc-lbl" x="${pad}" y="${H-pad+13}">0</text>
  </svg>`;
}

// ---- alert channels ---------------------------------------------------
// One hop from wherever notifications are mentioned to the page that owns
// them, so nothing has to reproduce the navigation inline.
window.goToNotificationSettings=()=>{
  showPage('page-usettings');
  // click the real nav item rather than toggling display directly, so the
  // sidebar highlight follows too
  const item=document.querySelector('.cfgitem[data-sec="notif"]');
  if(item) item.click();
  const sec=document.querySelector('.cfg-sec[data-sec="notif"]');
  if(sec) sec.scrollIntoView({behavior:'smooth', block:'start'});
};

// The channel list lives in Settings > Notifications now rather than behind a
// button on the Heartbeat page: one page that owns every notification, instead
// of alerts being configured somewhere separate from everything else.
window.openHbChannels=async()=>{
  hbcReset();
  await loadHbChannels();
};
async function loadHbChannels(){
  const body=document.getElementById('hbChanBody'); if(!body) return;
  const r=await api('/api/heartbeat/channels');
  if(!r) return;
  if(!r.ok){ toast('✕ '+await apiError(r)); return; }
  const list=await r.json().catch(()=>[]);
  HB.channels=list.map(c=>({id:c.id,name:c.name,kind:c.kind,enabled:c.enabled}));
  window.HB_CHAN_FULL=list;
  body.innerHTML=list.map(c=>{
    const cfg=c.config||{};
    const where=c.kind==='email' ? 'Settings ▸ Notifications'
      : (c.kind==='telegram' ? ('chat '+esc(cfg.chat_id||'—')) : esc(cfg.url||'—'));
    return `<tr>
      <td><b>${esc(c.name)}</b></td>
      <td>${esc((c.kind||'').toUpperCase())}</td>
      <td class="mono" style="max-width:260px;overflow-wrap:anywhere">${where}</td>
      <td>${c.enabled?'<span class="hbpill up">ACTIVE</span>':'<span class="hbpill paused">OFF</span>'}</td>
      <td><div class="row-actions">
        <button class="btn sm ghost" onclick="hbcTest(${c.id})">TEST</button>
        <button class="btn sm" onclick="hbcEdit(${c.id})">EDIT</button>
        <button class="btn sm danger" onclick="hbcDel(${c.id})">DEL</button>
      </div></td></tr>`;
  }).join('');
  document.getElementById('hbChanEmpty').style.display=list.length?'none':'block';
}
function hbcKindUI(){
  const k=document.getElementById('hbc_kind').value;
  const show=(id,on)=>{document.getElementById(id).style.display=on?'':'none';};
  show('hbc_toWrap', k==='email');
  show('hbc_urlWrap', k==='webhook'||k==='slack');
  show('hbc_tokenWrap', k==='telegram');
  show('hbc_chatWrap', k==='telegram');
  document.getElementById('hbc_urlLabel').textContent=k==='slack'?'Slack webhook URL':'Webhook URL';
  document.getElementById('hbc_hint').textContent=HB_CHAN_HINT[k]||'';
}
function hbcReset(){
  hbChanEditId=null;
  document.getElementById('hbChanFormTitle').textContent='ADD A CHANNEL';
  ['hbc_name','hbc_to','hbc_url','hbc_token','hbc_chat'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('hbc_kind').value='email';
  document.getElementById('hbc_enabled').checked=true;
  document.getElementById('hbcReset').style.display='none';
  document.getElementById('hbcSave').textContent='SAVE CHANNEL';
  hbcKindUI();
}
window.hbcEdit=(id)=>{
  const c=(window.HB_CHAN_FULL||[]).find(x=>x.id===id); if(!c) return;
  hbChanEditId=id;
  const cfg=c.config||{};
  document.getElementById('hbChanFormTitle').textContent='EDIT CHANNEL';
  document.getElementById('hbc_name').value=c.name||'';
  document.getElementById('hbc_kind').value=c.kind||'email';
  document.getElementById('hbc_to').value=cfg.to||'';
  document.getElementById('hbc_url').value=cfg.url||'';
  document.getElementById('hbc_chat').value=cfg.chat_id||'';
  document.getElementById('hbc_token').value='';
  document.getElementById('hbc_token').placeholder=cfg.token_set?'leave blank to keep current':'123456:ABC-DEF...';
  document.getElementById('hbc_enabled').checked=!!c.enabled;
  document.getElementById('hbcReset').style.display='';
  document.getElementById('hbcSave').textContent='UPDATE CHANNEL';
  hbcKindUI();
};
async function saveHbChannel(){
  const g=(id)=>document.getElementById(id);
  const kind=g('hbc_kind').value;
  const cfg={};
  // blank means "everyone with an email on their profile", which is what an
  // email channel did before there was anywhere to type an address
  if(kind==='email') cfg.to=g('hbc_to').value.trim();
  if(kind==='webhook'||kind==='slack') cfg.url=g('hbc_url').value.trim();
  if(kind==='telegram'){ cfg.token=g('hbc_token').value.trim(); cfg.chat_id=g('hbc_chat').value.trim(); }
  const body={name:g('hbc_name').value.trim()||kind, kind, config:cfg, enabled:g('hbc_enabled').checked};
  const editing=hbChanEditId;
  const r=await api(editing?('/api/heartbeat/channels/'+editing):'/api/heartbeat/channels',
    {method:editing?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!r) return;
  if(!r.ok){ toast('✕ '+await apiError(r)); return; }
  toast(editing?'✓ CHANNEL UPDATED':'✓ CHANNEL ADDED');
  hbcReset();
  await loadHbChannels();
}
window.hbcTest=async(id)=>{
  const r=await api('/api/heartbeat/channels/'+id+'/test',{method:'POST'});
  if(!r) return;
  const j=await r.json().catch(()=>({}));
  toast(r.ok ? ('✓ '+(j.message||'sent')) : ('✕ '+(j.error||'failed')));
};
window.hbcDel=async(id)=>{
  const c=(window.HB_CHAN_FULL||[]).find(x=>x.id===id);
  if(!confirm('Delete channel "'+((c&&c.name)||id)+'"? Monitors using only this channel fall back to the notification address.')) return;
  const r=await api('/api/heartbeat/channels/'+id,{method:'DELETE'});
  if(r&&r.ok){ toast('✓ CHANNEL DELETED'); hbcReset(); loadHbChannels(); loadHeartbeat(); }
  else if(r){ toast('✕ '+await apiError(r)); }
};

// ---- auto-refresh, only while the page is actually on screen ----------
function startHbAuto(){
  stopHbAuto();
  if(!(document.getElementById('hbAuto')||{}).checked) return;
  hbTimer=setInterval(()=>{
    const p=document.getElementById('page-heartbeat');
    if(!p||p.style.display==='none'){ stopHbAuto(); return; }
    loadHeartbeat();
  },30000);
}
function stopHbAuto(){ if(hbTimer){ clearInterval(hbTimer); hbTimer=null; } }

// ---- dashboard widget -------------------------------------------------
async function loadDashHeartbeat(){
  const body=document.getElementById('dashHbBody'); if(!body) return;
  const widget=document.querySelector('.widget[data-wkey="heartbeat"]');
  const hide=()=>{ if(widget) widget.style.display='none'; };
  if(!canDo('tools.heartbeat')){ hide(); paintLinkStates([]); return; }
  const r=await api('/api/heartbeat/state?hours=24');
  if(!r||!r.ok){ hide(); return; }
  const j=await r.json().catch(()=>null);
  if(!j){ hide(); return; }
  if(widget) widget.style.display='';
  // user tiles bound to a monitor read this same response rather than each
  // polling on its own timer
  paintLinkStates(j.monitors);
  const c=j.counts||{};
  const label=(k)=>k==='pending'?'checking':(k==='disabled'?'paused':k);
  const cn=document.getElementById('dashHbCounts');
  if(cn) cn.innerHTML=['down','pending','up','disabled'].filter(k=>c[k])
    .map(k=>`<span class="hbpill ${k==='disabled'?'paused':k}">${c[k]} ${label(k)}</span>`).join(' ')
    || '<span class="muted">no monitors yet</span>';
  // worst first, and only enough rows to notice something is wrong
  const mons=(j.monitors||[]).slice().sort((a,b)=>
    (hbRank(hbStatusOf(a))-hbRank(hbStatusOf(b))) ||
    String(a.name||'').toLowerCase().localeCompare(String(b.name||'').toLowerCase())).slice(0,12);
  body.innerHTML=mons.map(m=>{
    const st=hbStatusOf(m);
    return `<tr style="cursor:pointer" onclick="showPage('page-heartbeat')">
      <td><span class="hbdot ${st}"></span>${st==='pending'?'CHECKING':st.toUpperCase()}</td>
      <td>${esc(m.name||'')}</td>
      <td class="hbecg-cell">${hbEcg(m,{w:96,h:22,beats:14})}</td>
      <td>${m.last_ms==null?'—':esc(String(m.last_ms))+' ms'}</td>
      <td>${m.uptime==null?'—':esc(String(m.uptime))+'%'}</td></tr>`;
  }).join('');
  const emp=document.getElementById('dashHbEmpty');
  if(emp) emp.style.display=mons.length?'none':'block';
}

document.getElementById('navHeartbeat').onclick=()=>showPage('page-heartbeat');
document.getElementById('hbAddBtn').onclick=()=>openHbModal(null);
document.getElementById('hbCheckBtn').onclick=hbCheckNow;
// loaded with the Settings page it now lives on
if(document.getElementById('hbChanBody')) openHbChannels();
document.getElementById('hbSearch').oninput=renderHeartbeat;
document.getElementById('hbFilter').onchange=renderHeartbeat;
document.getElementById('hbWindow').onchange=loadHeartbeat;
document.getElementById('hbAuto').onchange=startHbAuto;
document.getElementById('hb_kind').onchange=hbKindUI;
['hb_interval','hb_thresh','hb_resend'].forEach(id=>{
  document.getElementById(id).oninput=hbThreshHint;
});
document.getElementById('hbCancel').onclick=()=>{document.getElementById('hbModal').classList.remove('show');hbEditId=null;};
document.getElementById('hbSave').onclick=saveHbMonitor;
document.getElementById('hbDelete').onclick=()=>{
  if(!hbEditId) return;
  const id=hbEditId;
  document.getElementById('hbModal').classList.remove('show');
  hbEditId=null;
  window.hbDel(id);
};
document.getElementById('hbdClose').onclick=()=>{
  document.getElementById('hbDetailModal').classList.remove('show'); hbDetailId=null;
};
document.getElementById('hbdWindow').onchange=()=>{ if(hbDetailId) loadHbDetail(hbDetailId,true); };
document.getElementById('hbdCheck').onclick=async()=>{
  if(!hbDetailId) return;
  const b=document.getElementById('hbdCheck'); b.disabled=true;
  await api('/api/heartbeat/monitors/'+hbDetailId+'/check',{method:'POST'});
  b.disabled=false;
  loadHbDetail(hbDetailId,true); loadHeartbeat();
};
document.getElementById('hbdPause').onclick=async()=>{
  if(!hbDetailId) return;
  await window.hbToggle(hbDetailId);
  loadHbDetail(hbDetailId,true);
};
document.getElementById('hbdEdit').onclick=()=>{
  if(!hbDetailId) return;
  document.getElementById('hbDetailModal').classList.remove('show');
  const id=hbDetailId; hbDetailId=null;
  openHbModal(id);
};
document.getElementById('hbChanClose').onclick=()=>{
  // nothing to close -- the list is part of the page
  loadHeartbeat();
};
document.getElementById('hbc_kind').onchange=hbcKindUI;
document.getElementById('hbcSave').onclick=saveHbChannel;
document.getElementById('hbcReset').onclick=hbcReset;
window.loadHeartbeat=loadHeartbeat;
window.loadDashHeartbeat=loadDashHeartbeat;
document.getElementById('scanDeep').onchange=e=>{
  const row=document.getElementById('scanPrefixRow');
  row.style.display=e.target.checked?'':'none';
  if(e.target.checked) document.getElementById('scanPrefix').focus();
};
document.getElementById('navBackup').onclick=openBackup;
document.getElementById('bkDownload').onclick=doBackup;
document.getElementById('bkFile').onchange=doRestore;
document.getElementById('trashRestoreSelBtn').onclick=restoreSelectedTrash;
document.getElementById('trashDelSelBtn').onclick=deleteSelectedTrash;
document.getElementById('trashEmptyBtn').onclick=emptyTrash;
document.getElementById('ctTrashRestoreSelBtn').onclick=restoreSelectedContractsTrash;
document.getElementById('ctTrashDelSelBtn').onclick=deleteSelectedContractsTrash;
document.getElementById('ctTrashEmptyBtn').onclick=emptyContractsTrash;
document.getElementById('addEmpBtn').onclick=()=>openEmpModal('');
document.getElementById('importLdapBtn').onclick=openLdapImport;
document.getElementById('empSearch').oninput=loadEmployees;
document.getElementById('empCancel').onclick=()=>document.getElementById('empModal').classList.remove('show');
document.getElementById('empSave').onclick=saveEmployee;
const _ldapSyncBtn=document.getElementById('ldapSyncBtn'); if(_ldapSyncBtn)_ldapSyncBtn.onclick=syncLdap;
document.getElementById('navTrash').onclick=()=>showPage('page-trash');
document.getElementById('navTickets').onclick=()=>showPage('page-tickets');
document.getElementById('newTicketBtn').onclick=openNewTicket;
document.getElementById('tkFormCancel').onclick=()=>document.getElementById('tkFormModal').classList.remove('show');
document.getElementById('tkFormSave').onclick=saveNewTicket;
document.getElementById('tkSearch').oninput=loadTickets;
document.getElementById('tkStatus').onchange=loadTickets;
document.getElementById('tkReplyBtn').onclick=sendReply;

document.getElementById('openMonitorBtn').onclick=()=>window.open('/monitor','_blank');
document.getElementById('sharePortalBtn').onclick=async()=>{
  const r=await api('/api/portal/link'); if(!r){toast('✕ error');return;} const j=await r.json();
  try{ await navigator.clipboard.writeText(j.url); toast('🔗 LINK COPIED: '+j.url); }
  catch(e){ window.prompt('Copy portal link:', j.url); }
};
document.getElementById('tkModalClose').onclick=()=>document.getElementById('tkModal').classList.remove('show');
document.getElementById('tkSaveBtn').onclick=saveTicketEdits;
document.getElementById('tkDeleteBtn').onclick=deleteTicket;
document.getElementById('navContracts').onclick=()=>showPage('page-contracts');
document.getElementById('newContractBtn').onclick=()=>openContractModal(null);
document.getElementById('ctSearch').oninput=renderContracts;
document.getElementById('ctTypeFilter').onchange=renderContracts;
document.getElementById('ctGroupBy').onchange=(e)=>{ctGroupBy=e.target.value;renderContracts();};
document.getElementById('ctPrintSelBtn').onclick=printContractsSelected;
document.getElementById('ctDelSelBtn').onclick=deleteContractsSelected;
document.getElementById('navCatalog').onclick=()=>showPage('page-catalog');
document.getElementById('ldapCancel').onclick=()=>document.getElementById('ldapModal').classList.remove('show');
document.getElementById('coSave').onclick=doCheckout;
window.loadCfgUsers=window.loadCfgUsers||function(){};window.editRow=openModal;window.delRow=delRow;window.editUser=editUser;window.delUser=delUser;window.delInvoice=delInvoice;
window.openSign=openSign;window.openCheckout=(id)=>{coAsset=id;Promise.all([api('/api/users'),api('/api/employees')]).then(async ([ru,re])=>{const us=ru?await ru.json():[];const emps=re?await re.json():[];const opts=us.map(u=>`<option value="${u.username}">${u.display||u.username} (user)</option>`).concat(emps.map(e=>`<option value="${e.EmployeeID}">${e.EmployeeName||e.EmployeeID} (${e.EmployeeID})</option>`));const sel=document.getElementById('coUser');sel.innerHTML=opts.join('');document.getElementById('coSignedDate').value=new Date().toISOString().slice(0,10);document.getElementById('coExpected').value='';document.getElementById('coNote').value='';document.getElementById('checkoutModal').classList.add('show');});};
window.checkinAsset=checkinAsset;window.openMaint=openMaint;window.openQR=openQR;window.doCheckout=doCheckout;window.addMaint=addMaint;window.delMaint=delMaint;
window.openAudit=openAudit;window.openScan=openScan;window.doScan=doScan;window.addScannedAsAsset=addScannedAsAsset;
window.openBackup=openBackup;window.doBackup=doBackup;window.doRestore=doRestore;window.delBackup=delBackup;
window.openEmpModal=openEmpModal;window.openLdapImport=openLdapImport;

function showPage(id){
  const PAGES=['page-dashboard','page-assets','page-employees','page-trash','page-tickets','page-contracts','page-catalog','page-usettings','page-scan','page-heartbeat','page-audit','page-import','page-export'];
  PAGES.forEach(p=>{const el=document.getElementById(p);if(el)el.style.display=(p===id?'block':'none');});
  document.querySelectorAll('.nav a').forEach(a=>a.classList.remove('active'));
  const map={  'page-dashboard':'navHome','page-employees':'navDirectory','page-trash':'navTrash','page-tickets':'navTickets',
    'page-contracts':'navContracts','page-catalog':'navCatalog',
    'page-usettings':'navSettings','page-scan':'navScan','page-heartbeat':'navHeartbeat',
    'page-audit':'navAudit','page-import':'navImport','page-export':'navExport','page-assets':'navAssets'};
  const n=map[id]?document.getElementById(map[id]):null;
  if(n)n.classList.add('active');
  if(id==='page-dashboard')startUnifiAutoRefresh(); else stopUnifiAutoRefresh();
  if(id!=='page-heartbeat') stopHbAuto();
  if(id==='page-dashboard'){ loadDashboard(); }   // loadDashboard() chains loadDashboardPage() + applyDashLayout()
  else if(id==='page-assets'){ load(); loadStats(); }
  else if(id==='page-employees')loadDirectory();
  else if(id==='page-trash'){loadTrash();loadContractsTrash();}
  else if(id==='page-tickets')loadTickets();
  else if(id==='page-contracts')loadContracts();
  else if(id==='page-catalog')loadCatalog();
  else if(id==='page-usettings'){loadUserSettings();loadSettings();loadCustom();}
  else if(id==='page-scan')openScan();
  else if(id==='page-heartbeat'){loadHeartbeat();startHbAuto();}
  else if(id==='page-audit')openAudit();
}
window.showPage=showPage;

async function loadTrash(){
  const r=await api('/api/assets/trash'); if(!r)return; const list=await r.json();
  const tb=document.getElementById('trashBody');
  tb.innerHTML=list.map(a=>`<tr><td><input type="checkbox" class="trash-chk" data-id="${a._id}" onchange="updateTrashSelBtns()"/></td><td class="mono">${esc(a.AssetTag||a._id)}</td><td>${esc(a.Name||'')}</td><td>${esc(a.Type||'')}</td><td class="mono">${esc(a.Serial||'')}</td><td>${esc(a.Location||'')}</td><td>${esc(a.Status||'')}</td><td><div class="row-actions"><button class="btn sm" onclick="restoreAsset('${a._id}')">♻ RESTORE</button><button class="btn sm danger" onclick="permaDeleteAsset('${a._id}')">DEL</button></div></td></tr>`).join('');
  document.getElementById('trashEmpty').style.display=list.length?'none':'block';
  const chkAll=document.getElementById('trashChkAll');
  if(chkAll){ chkAll.checked=false; chkAll.onchange=()=>{ document.querySelectorAll('.trash-chk').forEach(c=>c.checked=chkAll.checked); updateTrashSelBtns(); }; }
  updateTrashSelBtns();
}
function updateTrashSelBtns(){
  const n=document.querySelectorAll('.trash-chk:checked').length;
  const rb=document.getElementById('trashRestoreSelBtn'), db=document.getElementById('trashDelSelBtn');
  if(rb) rb.disabled = n===0;
  if(db) db.disabled = n===0;
}
window.restoreAsset=async(id)=>{
  const r=await api('/api/assets/'+id+'/restore',{method:'POST'});
  if(r&&r.ok){toast('♻ RESTORED');loadTrash();load();}else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'restore failed'));}
};
window.permaDeleteAsset=async(id)=>{
  if(!confirm('Permanently delete this asset? This cannot be undone.'))return;
  const r=await api('/api/assets/'+id+'/permanent',{method:'DELETE'});
  if(r&&r.ok){toast('🗑 DELETED PERMANENTLY');loadTrash();}else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'delete failed'));}
};
async function restoreSelectedTrash(){
  const ids=[...document.querySelectorAll('.trash-chk:checked')].map(c=>c.dataset.id);
  if(!ids.length)return;
  if(!confirm(`Restore ${ids.length} asset(s)?`))return;
  await Promise.all(ids.map(id=>api('/api/assets/'+id+'/restore',{method:'POST'})));
  toast('♻ '+ids.length+' RESTORED');
  loadTrash(); load();
}
async function deleteSelectedTrash(){
  const ids=[...document.querySelectorAll('.trash-chk:checked')].map(c=>c.dataset.id);
  if(!ids.length)return;
  if(!confirm(`Permanently delete ${ids.length} asset(s)? This cannot be undone.`))return;
  await Promise.all(ids.map(id=>api('/api/assets/'+id+'/permanent',{method:'DELETE'})));
  toast('🗑 '+ids.length+' DELETED PERMANENTLY');
  loadTrash();
}
async function emptyTrash(){
  if(!confirm('Permanently delete ALL items in Trash? This cannot be undone.'))return;
  const r=await api('/api/assets/trash/empty',{method:'POST'});
  if(r&&r.ok){const j=await r.json();toast('🗑 TRASH EMPTIED ('+j.deleted+')');loadTrash();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}
async function loadContractsTrash(){
  const r=await api('/api/contracts/trash'); if(!r)return; const list=await r.json();
  const tb=document.getElementById('ctTrashBody');
  tb.innerHTML=list.map(c=>`<tr><td><input type="checkbox" class="ct-trash-chk" data-id="${c.id}" onchange="updateContractTrashSelBtns()"/></td><td class="mono">${esc(contractIdFor(c))}</td><td>${esc(c.name||'')}</td><td>${esc(c.type||'')}</td><td>${esc(c.vendor||'')}</td><td>${esc(c.end_date||'')}</td><td class="mono">${fmtMoney(c.cost||0,CURRENCY)}</td><td><div class="row-actions"><button class="btn sm" onclick="restoreContract(${c.id})">♻ RESTORE</button><button class="btn sm danger" onclick="permaDeleteContract(${c.id})">DEL</button></div></td></tr>`).join('');
  document.getElementById('ctTrashEmpty').style.display=list.length?'none':'block';
  const chkAll=document.getElementById('ctTrashChkAll');
  if(chkAll){ chkAll.checked=false; chkAll.onchange=()=>{ document.querySelectorAll('.ct-trash-chk').forEach(c=>c.checked=chkAll.checked); updateContractTrashSelBtns(); }; }
  updateContractTrashSelBtns();
}
function updateContractTrashSelBtns(){
  const n=document.querySelectorAll('.ct-trash-chk:checked').length;
  const rb=document.getElementById('ctTrashRestoreSelBtn'), db=document.getElementById('ctTrashDelSelBtn');
  if(rb) rb.disabled = n===0;
  if(db) db.disabled = n===0;
}
window.restoreContract=async(id)=>{
  const r=await api('/api/contracts/'+id+'/restore',{method:'POST'});
  if(r&&r.ok){toast('♻ RESTORED');loadContractsTrash();loadContracts();}else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'restore failed'));}
};
window.permaDeleteContract=async(id)=>{
  if(!confirm('Permanently delete this contract? This cannot be undone.'))return;
  const r=await api('/api/contracts/'+id+'/permanent',{method:'DELETE'});
  if(r&&r.ok){toast('🗑 DELETED PERMANENTLY');loadContractsTrash();}else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'delete failed'));}
};
async function restoreSelectedContractsTrash(){
  const ids=[...document.querySelectorAll('.ct-trash-chk:checked')].map(c=>parseInt(c.dataset.id));
  if(!ids.length)return;
  if(!confirm(`Restore ${ids.length} contract(s)?`))return;
  await Promise.all(ids.map(id=>api('/api/contracts/'+id+'/restore',{method:'POST'})));
  toast('♻ '+ids.length+' RESTORED');
  loadContractsTrash(); loadContracts();
}
async function deleteSelectedContractsTrash(){
  const ids=[...document.querySelectorAll('.ct-trash-chk:checked')].map(c=>parseInt(c.dataset.id));
  if(!ids.length)return;
  if(!confirm(`Permanently delete ${ids.length} contract(s)? This cannot be undone.`))return;
  await Promise.all(ids.map(id=>api('/api/contracts/'+id+'/permanent',{method:'DELETE'})));
  toast('🗑 '+ids.length+' DELETED PERMANENTLY');
  loadContractsTrash();
}
async function emptyContractsTrash(){
  if(!confirm('Permanently delete ALL contracts in Trash? This cannot be undone.'))return;
  const r=await api('/api/contracts/trash/empty',{method:'POST'});
  if(r&&r.ok){const j=await r.json();toast('🗑 TRASH EMPTIED ('+j.deleted+')');loadContractsTrash();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}

// ---------- Product Catalog page: Categories / Manufacturers / Models ----------
async function loadCatalog(){
  await Promise.all([loadCatCategories(), loadCatManufacturers(), loadCatModels(), loadCatContractTypes()]);
}
async function loadCatContractTypes(){
  const r=await api('/api/contract-types'); const list=r?await r.json():[];
  document.getElementById('ctTypeCatBody').innerHTML=list.map(t=>`<tr><td>${esc(t.name)}</td><td class="col-del"><button class="btn sm danger" onclick="delCatalogItem('contract-types','${t.id}')">DEL</button></td></tr>`).join('')||'<tr><td colspan=2 class="muted">none yet</td></tr>';
  document.getElementById('ctTypeCatCount').textContent=list.length?`(${list.length})`:'';
}
async function loadCatCategories(){
  const r=await api('/api/categories'); const list=r?await r.json():[];
  document.getElementById('catBody').innerHTML=list.map(c=>`<tr><td>${esc(c.name)}</td><td class="col-del"><button class="btn sm danger" onclick="delCatalogItem('categories','${c.id}')">DEL</button></td></tr>`).join('')||'<tr><td colspan=2 class="muted">none yet</td></tr>';
  document.getElementById('catCount').textContent=list.length?`(${list.length})`:'';
}
async function loadCatManufacturers(){
  const r=await api('/api/manufacturers'); const list=r?await r.json():[];
  document.getElementById('mfrCatBody').innerHTML=list.map(m=>`<tr><td>${esc(m.name)}</td><td class="col-del"><button class="btn sm danger" onclick="delCatalogItem('manufacturers','${m.id}')">DEL</button></td></tr>`).join('')||'<tr><td colspan=2 class="muted">none yet</td></tr>';
  document.getElementById('mfrCatCount').textContent=list.length?`(${list.length})`:'';
  const sel=document.getElementById('modMfrSelect');
  const cur=sel.value;
  sel.innerHTML='<option value="">-- choose manufacturer --</option>'+list.map(m=>`<option value="${m.id}" ${String(m.id)===cur?'selected':''}>${esc(m.name)}</option>`).join('');
}
async function loadCatModels(){
  const r=await api('/api/models'); const list=r?await r.json():[];
  document.getElementById('modCatBody').innerHTML=list.map(m=>`<tr><td>${esc(m.name)}</td><td>${esc(m.manufacturer||'—')}</td><td class="col-del"><button class="btn sm danger" onclick="delCatalogItem('models','${m.id}')">DEL</button></td></tr>`).join('')||'<tr><td colspan=3 class="muted">none yet</td></tr>';
  document.getElementById('modCatCount').textContent=list.length?`(${list.length})`:'';
}
async function delCatalogItem(kind,id){
  if(!confirm('Delete this '+kind.slice(0,-1)+'? Assets already using it keep their saved value.'))return;
  const r=await api('/api/'+kind,{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
  if(r&&r.ok){toast('🗑 DELETED');loadCatalog();}else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}
window.delCatalogItem=delCatalogItem;
document.getElementById('catAdd').onclick=async()=>{
  const el=document.getElementById('catInput'); const n=el.value.trim(); if(!n)return;
  const r=await api('/api/categories',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n})});
  if(r&&r.ok){el.value='';loadCatCategories();}
};
document.getElementById('mfrCatAdd').onclick=async()=>{
  const el=document.getElementById('mfrCatInput'); const n=el.value.trim(); if(!n)return;
  const r=await api('/api/manufacturers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n})});
  if(r&&r.ok){el.value='';loadCatManufacturers();}
};
document.getElementById('ctTypeCatAdd').onclick=async()=>{
  const el=document.getElementById('ctTypeCatInput'); const n=el.value.trim(); if(!n)return;
  const r=await api('/api/contract-types',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n})});
  if(r&&r.ok){el.value='';loadCatContractTypes();}
};
document.getElementById('modCatAdd').onclick=async()=>{
  const mid=document.getElementById('modMfrSelect').value;
  const el=document.getElementById('modCatInput'); const n=el.value.trim();
  if(!mid){toast('✕ choose a manufacturer first');return;}
  if(!n)return;
  const r=await api('/api/models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n,manufacturer_id:mid})});
  if(r&&r.ok){el.value='';loadCatModels();}
};
document.getElementById('catImportBtn').onclick=()=>document.getElementById('catImportFile').click();
document.getElementById('catImportFile').onchange=async()=>{
  const inp=document.getElementById('catImportFile');
  const file=inp.files[0]; if(!file)return;
  const fd=new FormData(); fd.append('file',file);
  const r=await api('/api/catalog/import',{method:'POST',body:fd});
  inp.value='';
  const j=r?await r.json().catch(()=>({})):{};
  if(r&&r.ok){
    toast(`✓ imported: ${j.categories||0} categories, ${j.manufacturers||0} manufacturers, ${j.models||0} models`);
    loadCatalog();
  } else {
    toast('✕ '+(j.error||'import failed'));
  }
};

// ---------- Directory page: Employees + Departments / Locations / Designations ----------
async function loadDirectory(){
  await Promise.all([loadEmployees(), loadDirDepartments(), loadDirLocations(), loadDirDesignations()]);
}
async function loadDirDepartments(){
  const r=await api('/api/departments'); const list=r?await r.json():[];
  document.getElementById('depBody').innerHTML=list.map(d=>`<tr><td>${esc(d.name)}</td><td class="col-del"><button class="btn sm danger" onclick="delDirItem('departments','${d.id}')">DEL</button></td></tr>`).join('')||'<tr><td colspan=2 class="muted">none yet</td></tr>';
  document.getElementById('depCount').textContent=list.length?`(${list.length})`:'';
}
async function loadDirLocations(){
  const r=await api('/api/locations'); const list=r?await r.json():[];
  document.getElementById('dirLocBody').innerHTML=list.map(l=>`<tr><td>${esc(l.name)}</td><td class="col-del"><button class="btn sm danger" onclick="delDirItem('locations','${l.id}')">DEL</button></td></tr>`).join('')||'<tr><td colspan=2 class="muted">none yet</td></tr>';
  document.getElementById('dirLocCount').textContent=list.length?`(${list.length})`:'';
}
async function loadDirDesignations(){
  const r=await api('/api/designations'); const list=r?await r.json():[];
  document.getElementById('desBody').innerHTML=list.map(d=>`<tr><td>${esc(d.name)}</td><td class="col-del"><button class="btn sm danger" onclick="delDirItem('designations','${d.id}')">DEL</button></td></tr>`).join('')||'<tr><td colspan=2 class="muted">none yet</td></tr>';
  document.getElementById('desCount').textContent=list.length?`(${list.length})`:'';
}
async function delDirItem(kind,id){
  if(!confirm('Delete this '+kind.slice(0,-1)+'? Employees/assets already using it keep their saved value.'))return;
  const r=await api('/api/'+kind,{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
  if(r&&r.ok){toast('🗑 DELETED');loadDirectory();}else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}
window.delDirItem=delDirItem;
document.getElementById('depAdd').onclick=async()=>{
  const el=document.getElementById('depInput'); const n=el.value.trim(); if(!n)return;
  const r=await api('/api/departments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n})});
  if(r&&r.ok){el.value='';loadDirDepartments();}
};
document.getElementById('dirLocAdd').onclick=async()=>{
  const el=document.getElementById('dirLocInput'); const n=el.value.trim(); if(!n)return;
  const r=await api('/api/locations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n})});
  if(r&&r.ok){el.value='';loadDirLocations();}
};
document.getElementById('desAdd').onclick=async()=>{
  const el=document.getElementById('desInput'); const n=el.value.trim(); if(!n)return;
  const r=await api('/api/designations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n})});
  if(r&&r.ok){el.value='';loadDirDesignations();}
};
document.getElementById('dirImportBtn').onclick=()=>document.getElementById('dirImportFile').click();
document.getElementById('dirImportFile').onchange=async()=>{
  const inp=document.getElementById('dirImportFile');
  const file=inp.files[0]; if(!file)return;
  const fd=new FormData(); fd.append('file',file);
  const r=await api('/api/directory/import',{method:'POST',body:fd});
  inp.value='';
  const j=r?await r.json().catch(()=>({})):{};
  if(r&&r.ok){
    toast(`✓ imported: ${j.departments||0} departments, ${j.locations||0} locations, ${j.designations||0} designations`);
    loadDirectory();
  } else {
    toast('✕ '+(j.error||'import failed'));
  }
};

// ---------- Tickets (osTicket-style) ----------
let _usersCache=null;
async function getUsersCached(){
  if(_usersCache) return _usersCache;
  // /api/users is admin-only; everyone else gets a 403 {error:"No access"} here,
  // not an array — never trust the shape without checking r.ok and Array.isArray first.
  try{
    const r=await api('/api/users');
    const j=(r&&r.ok)?await r.json():[];
    _usersCache=Array.isArray(j)?j:[];
  }catch(e){ _usersCache=[]; }
  return _usersCache;
}
async function assignTicketFromRow(id, val){
  const r=await api('/api/tickets/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({assignee:val})});
  if(r&&r.ok){ toast('✓ ASSIGNED'+(val?' to '+val:'')); await loadTickets(); }
  else toast('✕ assign failed');
}
function copyTicketCode(e, code){
  e.stopPropagation();
  navigator.clipboard.writeText(code).then(()=>toast('✓ COPIED '+code)).catch(()=>toast('✕ copy failed'));
}
window.copyTicketCode=copyTicketCode;
async function loadTickets(){
  const q=document.getElementById('tkSearch').value.trim();
  const st=document.getElementById('tkStatus').value;
  const users=await getUsersCached();
  const assignOpts=(sel)=>'<option value="">— Unassigned —</option>'+users.map(u=>`<option ${u.username===sel?'selected':''}>${esc(u.username)}</option>`).join('');
  const r=await api('/api/tickets?status='+encodeURIComponent(st)+'&q='+encodeURIComponent(q)); if(!r)return;
  const list=await r.json();
  const now=new Date();
  const rowHtml=t=>{
    let dueStr=t.due_date||'—';
    let slaClass='';
    if(t.due_date && t.status!=='Resolved' && t.status!=='Closed'){
      const due=new Date(t.due_date.replace(' ','T'));
      if(due<now){dueStr='<span style="color:#ff5d6c;font-weight:700">⚠ '+dueStr+'</span>';slaClass=' style="border-left:3px solid #ff5d6c"';}
      else if(due-now<1000*60*60*4){dueStr='<span style="color:#ffb84d">'+dueStr+'</span>';}
    }
    return `<tr onclick="openTicket(${t.id})" style="cursor:pointer"${slaClass}>
    <td class="mono tk-code" title="Click to copy" onclick="copyTicketCode(event,'${esc(t.code)}')">${esc(t.code)} <span class="tk-copy-ico">⧉</span></td><td>${esc(t.subject)}</td>
    <td><span class="prio ${t.priority}">${esc(t.priority)}</span></td>
    <td><span class="status s_${t.status.replace(' ','')}">${esc(t.status)}</span></td>
    <td>${esc(t.category||'—')}</td>
    <td>${esc(t.requester||'—')}</td><td><select class="rowassign" data-id="${t.id}" onclick="event.stopPropagation()" onchange="assignTicketFromRow(${t.id}, this.value)">${assignOpts(t.assignee)}</select></td>
    <td>${dueStr}</td><td>${t.reply_count||0}</td></tr>`;
  };
  const active=list.filter(t=>t.status!=='Resolved' && t.status!=='Closed');
  const closed=list.filter(t=>t.status==='Resolved' || t.status==='Closed');
  document.getElementById('tkBody').innerHTML=active.map(rowHtml).join('');
  document.getElementById('tkEmpty').style.display=active.length?'none':'block';
  document.getElementById('tkActiveCount').textContent=active.length?`(${active.length})`:'';
  document.getElementById('tkBodyClosed').innerHTML=closed.map(rowHtml).join('');
  document.getElementById('tkEmptyClosed').style.display=closed.length?'none':'block';
  document.getElementById('tkClosedCount').textContent=closed.length?`(${closed.length})`:'';
}
let curTicketId=null;
async function openTicket(id){
  curTicketId=id;
  const r=await api('/api/tickets/'+id); if(!r)return; const d=await r.json();
  const t=d.ticket, reps=d.replies||[], atts=d.attachments||[];
  document.getElementById('tkModalTitle').textContent=t.code+' · '+t.subject;
  const catList=TICKET_CATEGORIES.slice();
  const curCat=(t.category||'').trim();
  const catKnown=!curCat||catList.indexOf(curCat)>=0;
  const isAdmin=canDo('tickets.edit');   // may change the ticket's details
  const mayQueue=canDo('tickets.queue'); // status / priority / assignee
  const ro=(label,value,extra='')=>`<div class="field2" ${extra}><label>${label}</label><input value="${esc(value==null?'':String(value))}" readonly disabled></div>`;
  // Laid out with the same invbox / grid2 / field2 blocks as the asset form,
  // so a ticket reads like every other record in the app. Nothing appears
  // twice: whoever may change a field gets the input, everyone else the
  // read-only copy of it.
  document.getElementById('tkDetail').innerHTML=`
    ${mayQueue?`
    <div class="invbox">
      <label>QUEUE</label>
      <div class="grid2">
        <div class="field2"><label>Status</label>
          <select id="tkStatusUpd">${TICKET_STATUSES.map(s=>`<option ${s===t.status?'selected':''}>${s}</option>`).join('')}</select>
        </div>
        <div class="field2"><label>Priority</label>
          <select id="tkPrioUpd">${PRIORITIES.map(s=>`<option ${s===t.priority?'selected':''}>${s}</option>`).join('')}</select>
        </div>
        <div class="field2" style="grid-column:1/-1"><label>Assigned to</label>
          <select id="tkAssignee"><option value="">-- unassigned --</option></select>
        </div>
      </div>
    </div>`:''}

    <div class="invbox">
      <label>TICKET DETAILS${isAdmin?'':' <span class="muted" style="font-weight:400">(you cannot change these)</span>'}</label>
      <div class="grid2">
        ${isAdmin?`
        <div class="field2" style="grid-column:1/-1"><label>Subject</label>
          <input id="tkeSubject" value="${esc(t.subject||'')}">
        </div>
        <div class="field2"><label>Category</label>
          <select id="tkeCategorySel">
            <option value="">-- none --</option>
            ${catList.map(c=>`<option value="${esc(c)}" ${c===curCat?'selected':''}>${esc(c)}</option>`).join('')}
            <option value="__custom" ${catKnown?'':'selected'}>+ type another...</option>
          </select>
        </div>
        <div class="field2" id="tkeCategoryWrap" ${catKnown?'style="display:none"':''}><label>Category (typed)</label>
          <input id="tkeCategory" value="${catKnown?'':esc(curCat)}" placeholder="e.g. Telephony">
        </div>
        <div class="field2"><label>Requester</label><input id="tkeRequester" value="${esc(t.requester||'')}"></div>
        <div class="field2"><label>Requester Email</label><input id="tkeRequesterEmail" type="email" value="${esc(t.requester_email||'')}"></div>
        <div class="field2"><label>Asset ID</label><input id="tkeAssetId" value="${esc(t.asset_id||'')}"></div>
        <div class="field2"><label>Due Date</label><input id="tkeDueDate" type="date" value="${esc((t.due_date||'').toString().slice(0,10))}"></div>
        <div class="field2"><label>SLA Hours</label><input id="tkeSlaHours" type="number" min="1" value="${esc(String(t.sla_hours||''))}"></div>`:`
        ${ro('Subject',t.subject||'-','style="grid-column:1/-1"')}
        ${mayQueue?'':ro('Status',t.status||'-')}
        ${mayQueue?'':ro('Priority',t.priority||'-')}
        ${ro('Category',curCat||'-')}
        ${ro('Requester',t.requester||'-')}
        ${ro('Requester Email',t.requester_email||'-')}
        ${ro('Asset ID',t.asset_id||'-')}
        ${ro('Due Date',(t.due_date||'').toString().slice(0,10)||'-')}
        ${ro('SLA Hours',t.sla_hours||'-')}`}
        <div class="field2"><label>Source</label><input value="${esc(t.source||'Web')}" readonly disabled></div>
      </div>
    </div>

    <div class="invbox">
      <label>DESCRIPTION</label>
      ${isAdmin?`<textarea id="tkeDescription" rows="4">${esc(t.description||'')}</textarea>`
               :`<textarea rows="4" readonly disabled>${esc(t.description||'')}</textarea>`}
    </div>

    ${ticketPhotosHtml(atts,id)}

    <div class="invbox">
      <label>REPLIES</label>
      <div class="tkreplies">${reps.map(rp=>`<div class="rep ${rp.author_role}"><div class="repmeta"><b>${esc(rp.author)}</b> &middot; ${esc(rp.author_role)} &middot; ${esc(rp.created_at)}</div><div>${esc(rp.body)}</div></div>`).join('')||'<div class="muted">No replies yet.</div>'}</div>
    </div>`;
  loadTicketHistory(id);
  // the assignee select is rendered as part of the panel, so it is filled
  // after the markup exists rather than before it
  const asel=document.getElementById('tkAssignee');
  if(asel){
    try{
      const users=await getUsersCached();
      asel.innerHTML='<option value="">-- unassigned --</option>'+
        users.map(u=>`<option ${u.username===t.assignee?'selected':''}>${esc(u.username)}</option>`).join('');
    }catch(e){}
  }
  const photoIn=document.getElementById('tkPhotoInput');
  if(photoIn)photoIn.onchange=()=>{uploadTicketPhotos(photoIn.files);};
  // "type another..." reveals a text box rather than throwing a prompt() at
  // the user, so the typed value is visible before it is saved.
  const catSel=document.getElementById('tkeCategorySel');
  if(catSel){
    catSel.onchange=()=>{
      const wrap=document.getElementById('tkeCategoryWrap');
      const custom=catSel.value==='__custom';
      if(wrap)wrap.style.display=custom?'':'none';
      if(custom){const i=document.getElementById('tkeCategory'); if(i)i.focus();}
    };
  }
  const delBtn=document.getElementById('tkDeleteBtn');
  if(delBtn)delBtn.style.display=canDo('tickets.delete')?'':'none';
  // Read-write on tickets may move the queue, so they need SAVE CHANGES too.
  const saveBtn=document.getElementById('tkSaveBtn');
  if(saveBtn)saveBtn.style.display=mayQueue?'':'none';
  document.getElementById('tkModal').classList.add('show');
}
window.openTicketById=(id)=>openTicket(id);
// Photos a requester attached from the portal, plus a way for whoever is
// working the ticket to add their own (the repair, the replaced part). The
// bytes are fetched one at a time by their own route, so a ticket with four
// photos doesn't bloat the detail response.
async function uploadTicketPhotos(files){
  if(!curTicketId||!files||!files.length)return;
  const fd=new FormData();
  Array.prototype.forEach.call(files,f=>fd.append('photos',f,f.name));
  const r=await api('/api/tickets/'+curTicketId+'/attachments',{method:'POST',body:fd});
  if(!r){toast('✕ upload failed');return;}
  const j=await r.json().catch(()=>({}));
  if(!r.ok){toast('✕ '+(j.error||'upload failed'));return;}
  if(j.warnings&&j.warnings.length)toast('⚠ '+j.warnings.join('; '));
  else toast('✓ '+j.saved+' PHOTO'+(j.saved===1?'':'S')+' ADDED');
  openTicket(curTicketId);
}

async function deleteTicketPhoto(attId){
  if(!curTicketId)return;
  if(!confirm('Delete this photo? It cannot be recovered.'))return;
  const r=await api('/api/tickets/'+curTicketId+'/attachments/'+attId,{method:'DELETE'});
  if(r&&r.ok){toast('✓ PHOTO DELETED');openTicket(curTicketId);}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'delete failed'));}
}

// Rendered as a block of thumbnails; clicking one opens the full-size image
// in a new tab rather than building a lightbox nobody asked for.
function ticketPhotosHtml(atts,ticketId){
  const mayDelete=canDo('tickets.delete');
  const canAdd=canDo('tickets.photos');
  if(!atts.length&&!canAdd)return '';
  const kb=n=>n>=1048576?((n/1048576).toFixed(1)+' MB'):(Math.max(1,Math.round(n/1024))+' KB');
  const thumbs=atts.map(a=>{
    const u='/api/tickets/'+ticketId+'/attachments/'+a.id;
    return `<div class="shot">
      <a href="${u}" target="_blank" rel="noopener" title="${esc(a.filename)} &middot; ${kb(a.size)} &middot; ${esc(a.uploaded_by)}">
        <img src="${u}" alt="${esc(a.filename)}" loading="lazy">
      </a>
      ${mayDelete?`<button type="button" class="x" title="Delete photo" onclick="deleteTicketPhoto(${a.id})">&times;</button>`:''}
      <div class="nm">${esc(a.filename)}</div>
    </div>`;
  }).join('');
  return `
    <div class="invbox">
      <label>PHOTOS${atts.length?` <span class="muted" style="font-weight:400">(${atts.length})</span>`:''}</label>
      ${atts.length?`<div class="shots">${thumbs}</div>`:'<p class="muted" style="margin:0">No photos attached.</p>'}
      ${canAdd?`<div style="margin-top:12px">
        <input type="file" id="tkPhotoInput" accept="image/*" multiple style="display:none">
        <button type="button" class="btn sm ghost" onclick="document.getElementById('tkPhotoInput').click()">+ ADD PHOTO</button>
        <span class="muted" style="margin-left:8px;font-size:11.5px">JPEG, PNG, GIF, WebP or HEIC &middot; up to 4MB each &middot; 4 per ticket</span>
      </div>`:''}
    </div>`;
}

// Field-change trail for a ticket, rendered like an asset's history: who
// changed what, from what, when. Loaded after the panel renders so a slow
// query never holds up the rest of the view.
async function loadTicketHistory(id){
  const box=document.getElementById('tkHistory');
  if(!box)return;
  box.innerHTML='<div class="muted">Loading…</div>';
  const r=await api('/api/tickets/'+id+'/history');
  if(!r||!r.ok){box.innerHTML='<div class="muted">History unavailable.</div>';return;}
  const rows=await r.json();
  if(!rows.length){box.innerHTML='<div class="muted">No changes recorded yet.</div>';return;}
  // Same markup and classes as the asset history block, so the two read
  // identically instead of inventing a second style for the same idea.
  box.innerHTML=rows.map(e=>`<div class="hist"><span class="hfield">${esc(e.field)}</span> <span class="hold">${esc(e.old_val||'—')}</span> → <span class="hnew">${esc(e.new_val||'—')}</span> <span class="hmeta">${esc(e.user)} · ${esc(e.ts)}</span></div>`).join('');
}
// Full ticket edit. The API already accepts every one of these fields on PUT;
// the UI simply never offered them, so only status/priority could be changed.
async function saveTicketEdits(){
  if(!curTicketId){return;}
  const val=id=>{const el=document.getElementById(id);return el?el.value.trim():undefined;};
  const payload={};
  const map={tkeSubject:'subject',tkeDescription:'description',
             tkeRequester:'requester',tkeRequesterEmail:'requester_email',
             tkeAssetId:'asset_id',tkeDueDate:'due_date'};
  for(const [el,field] of Object.entries(map)){const v=val(el);if(v!==undefined)payload[field]=v;}
  // category: the dropdown, or the typed box when "type another..." is picked
  const catSel=document.getElementById('tkeCategorySel');
  if(catSel)payload.category=(catSel.value==='__custom')?(val('tkeCategory')||''):catSel.value;
  const sla=val('tkeSlaHours'); if(sla)payload.sla_hours=parseInt(sla,10);
  const st=document.getElementById('tkStatusUpd'), pr=document.getElementById('tkPrioUpd');
  const as=document.getElementById('tkAssignee');
  if(st)payload.status=st.value; if(pr)payload.priority=pr.value;
  // assignee travels with the rest: the standalone ASSIGN button and its
  // separate request are gone, so one save does the whole queue.
  if(as)payload.assignee=as.value;
  // The subject box only exists for an admin; a tickets-write user is saving
  // status and priority on their own, so don't demand a field they can't see.
  if(document.getElementById('tkeSubject')&&!payload.subject){toast('✕ SUBJECT REQUIRED');return;}
  if(!Object.keys(payload).length){toast('✕ NOTHING TO SAVE');return;}
  const r=await api('/api/tickets/'+curTicketId,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(r&&r.ok){toast('✓ TICKET SAVED');openTicket(curTicketId);await loadTickets();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'save failed'));}
}
// Deletion is admin-only and enforced server-side too -- this just hides the
// button for everyone else rather than letting them discover a 403.
async function deleteTicket(){
  if(!curTicketId)return;
  if(MY_ROLE!==ROLE_ADMIN){toast('✕ ADMIN ONLY');return;}
  if(!confirm('Delete this ticket and its entire reply history? This cannot be undone.'))return;
  const r=await api('/api/tickets/'+curTicketId,{method:'DELETE'});
  if(r&&r.ok){document.getElementById('tkModal').classList.remove('show');curTicketId=null;toast('✓ TICKET DELETED');await loadTickets();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'delete failed'));}
}
async function sendReply(){
  if(!curTicketId)return;
  const body=document.getElementById('tkReply').value.trim(); if(!body){toast('✕ empty');return;}
  const r=await api('/api/tickets/'+curTicketId+'/reply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({body})});
  // Only editors get the status/priority controls, so a read-only replier
  // shouldn't hit a null here -- and shouldn't send an empty update either.
  const stEl=document.getElementById('tkStatusUpd'), prEl=document.getElementById('tkPrioUpd');
  if(stEl&&prEl){
    await api('/api/tickets/'+curTicketId,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:stEl.value,priority:prEl.value})});
  }
  if(r&&r.ok){document.getElementById('tkReply').value='';openTicket(curTicketId);await loadTickets();toast('✓ REPLY SENT');}
}
async function openNewTicket(){
  document.getElementById('tkFormFields').innerHTML=
    `<div class="grid2">
       <div class="field2"><label>SUBJECT</label><input id="t_subject" placeholder="e.g. Laptop won't boot"></div>
       <div class="field2"><label>REQUESTER</label><input id="t_requester" value="${window.sessionUser||''}" placeholder="Name"></div>
       <div class="field2"><label>PRIORITY</label><select id="t_priority">${PRIORITIES.map(s=>`<option ${s==='Normal'?'selected':''}>${s}</option>`).join('')}</select></div>
       <div class="field2"><label>CATEGORY</label><select id="t_category">${TICKET_CATEGORIES.map(c=>`<option>${c}</option>`).join('')}</select></div>
       <div class="field2"><label>ASSIGNEE</label><input id="t_assignee" placeholder="leave blank = auto-assign"></div>
       <div class="field2"><label>SLA (hours) <span style="color:var(--mut);font-weight:400">(auto from priority)</span></label><input id="t_sla" type="number" value="24" min="0"></div>
     </div>
     <div class="invbox"><label>DESCRIPTION</label><textarea id="t_desc" rows="4" placeholder="Describe the issue..."></textarea></div>
     <div class="invbox"><label>LINKED ASSET ID (optional)</label><input id="t_asset" placeholder="e.g. a1b2c3... (leave blank if none)"></div>`;
  document.getElementById('tkFormModal').classList.add('show');
}
let savingTicket=false;
async function saveNewTicket(){
  if(savingTicket)return;
  const subject=document.getElementById('t_subject').value.trim();
  if(!subject){toast('✕ subject required');return;}
  const btn=document.getElementById('tkFormSave');
  savingTicket=true; if(btn){btn.disabled=true;btn.textContent='CREATING…';}
  const body={
    subject,
    description:document.getElementById('t_desc').value.trim(),
    priority:document.getElementById('t_priority').value,
    category:document.getElementById('t_category').value,
    requester:document.getElementById('t_requester').value.trim()||(window.sessionUser||'Unknown'),
    assignee:document.getElementById('t_assignee').value.trim()||null,
    sla_hours:parseInt(document.getElementById('t_sla').value||'24',10),
    asset_id:document.getElementById('t_asset').value.trim()||null,
    source:'Web'
  };
  try{
    const r=await api('/api/tickets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(r&&r.ok){document.getElementById('tkFormModal').classList.remove('show');toast('✓ TICKET CREATED');loadTickets();}
    else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
  } finally {
    savingTicket=false; if(btn){btn.disabled=false;btn.textContent='CREATE TICKET';}
  }
}
window.openNewTicket=openNewTicket;
window.openTicket=openTicket;

// ---------- Contracts / AMC / Licenses / Subscriptions ----------
let contracts=[];
let editingContractId=null;
let ctGroupBy='';
function contractIdLabel(id){
  return 'CT-'+String(id).padStart(4,'0');
}
// Prefer the user-editable contract_tag (like Assets' AssetTag) -- falls
// back to the auto CT-0001 format derived from the row id for contracts
// created before contract_tag existed, or left blank.
function contractIdFor(c){
  return (c&&c.contract_tag)?c.contract_tag:contractIdLabel(c?c.id:'');
}
function assetLabelFor(id){
  if(!id)return'';
  const a=assets.find(x=>x._id===id);
  return a?`${a.AssetTag||a._id} — ${a.Name} (${a.Serial||'no S/N'})`:'';
}
async function loadContracts(){
  const r=await api('/api/contracts'); if(!r)return; contracts=await r.json();
  renderContractStats();
  renderContracts();
}
function renderContracts(){
  const q=(document.getElementById('ctSearch').value||'').trim().toLowerCase();
  const tf=document.getElementById('ctTypeFilter').value;
  let rows=contracts.filter(c=>{
    if(tf && (c.type||'')!==tf) return false;
    if(q){ const hay=[c.name,c.vendor,c.type,c.note].join(' ').toLowerCase(); if(!hay.includes(q)) return false; }
    return true;
  });
  const tb=document.getElementById('ctBody');
  const rowHtml=c=>`<tr data-id="${c.id}"><td><input type="checkbox" class="ct-row-chk" data-id="${c.id}" onchange="updateContractSelBtns()"/></td><td class="mono" style="cursor:pointer" onclick="openContractModal(${c.id})">${esc(contractIdFor(c))}</td><td style="cursor:pointer" onclick="openContractModal(${c.id})">${esc(c.name)}</td><td>${esc(c.type||'—')}</td><td>${esc(c.vendor||'—')}</td><td>${esc(c.start_date||'—')}</td><td>${esc(c.end_date||'—')}</td><td class="mono">${fmtMoney(c.cost||0, CURRENCY)}</td><td>${esc(c.billing_period||'One-Time')}</td><td class="mono">${esc(c.license_key||'—')}</td><td>${esc(assetLabelFor(c.asset_id)||'—')}</td><td><div class="row-actions"><button class="btn sm ghost row-more" onclick="toggleContractRowMenu(event,${c.id})" aria-label="Actions">⋮</button></div></td></tr>`;
  if(ctGroupBy){
    const groups={};
    rows.forEach(c=>{const k=(c[ctGroupBy]||'—').toString();(groups[k]=groups[k]||[]).push(c);});
    const keys=Object.keys(groups).sort((x,y)=>x.toLowerCase()<y.toLowerCase()?-1:1);
    tb.innerHTML=keys.map(k=>{
      const g=groups[k];
      return `<tr class="group-head"><td colspan="12"><span class="gh-label">▣ ${esc(ctGroupBy==='type'?'Type':'Vendor')}: ${esc(k)}</span><span class="gh-count">${g.length} contract${g.length>1?'s':''}</span></td></tr>`+g.map(rowHtml).join('');
    }).join('');
  } else {
    tb.innerHTML=rows.map(rowHtml).join('');
  }
  document.getElementById('ctCount').textContent=`${rows.length} of ${contracts.length} contracts`;
  document.getElementById('ctEmpty').style.display=contracts.length?'none':'block';
  const chkAll=document.getElementById('ctChkAll');
  if(chkAll){ chkAll.checked=false; chkAll.onchange=()=>{ document.querySelectorAll('.ct-row-chk').forEach(c=>c.checked=chkAll.checked); updateContractSelBtns(); }; }
  updateContractSelBtns();
}
function updateContractSelBtns(){
  const n=document.querySelectorAll('.ct-row-chk:checked').length;
  const dsb=document.getElementById('ctDelSelBtn');
  if(dsb){ dsb.style.display = n>0 ? 'inline-flex' : 'none'; dsb.textContent = `Delete selected (${n})`; }
}
async function deleteContractsSelected(){
  const ids=[...document.querySelectorAll('.ct-row-chk:checked')].map(c=>parseInt(c.dataset.id));
  if(!ids.length){toast('No contracts selected');return;}
  if(!confirm(`Move ${ids.length} contract(s) to trash?`))return;
  await Promise.all(ids.map(id=>api('/api/contracts',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})})));
  toast('🗑 '+ids.length+' MOVED TO TRASH');
  loadContracts();
}
function printContractsSelected(){
  const ids=[...document.querySelectorAll('.ct-row-chk:checked')].map(c=>parseInt(c.dataset.id));
  if(!ids.length){toast('No contracts selected');return;}
  const list=contracts.filter(c=>ids.includes(c.id));
  const w=window.open('','_blank');
  if(!w){toast('✕ Popup blocked — allow popups for this site');return;}
  const rowsHtml=list.map(c=>`<tr><td class="mono">${esc(contractIdFor(c))}</td><td>${esc(c.name)}</td><td>${esc(c.type||'—')}</td><td>${esc(c.vendor||'—')}</td><td>${esc(c.start_date||'—')}</td><td>${esc(c.end_date||'—')}</td><td>${fmtMoney(c.cost||0,CURRENCY)}</td><td>${esc(c.billing_period||'One-Time')}</td><td>${esc(c.license_key||'—')}</td><td>${esc(assetLabelFor(c.asset_id)||'—')}</td></tr>`).join('');
  w.document.write(`<!doctype html><html><head><title>Contracts</title>
  <style>@page{size:A4;margin:${window.HAS_LETTERHEAD?'0':'14mm'}}body{font-family:'Segoe UI',Arial,sans-serif;color:#111}
  .phead{display:flex;align-items:center;gap:12px;margin-bottom:4px} .phead img{height:36px} .phead h2{margin:0}
  table{width:100%;border-collapse:collapse;margin-top:10px}th,td{padding:6px 8px;border-bottom:1px solid #ddd;font-size:12px;text-align:left}th{background:#101622;color:#fff}
  </style></head><body>${printHeaderHtml((window.APP_NAME||'IT-Vault')+' — Contracts')}<div>${list.length} contract${list.length>1?'s':''} • generated ${new Date().toLocaleString()}</div>
  <table><thead><tr><th>Contract ID</th><th>Name</th><th>Type</th><th>Vendor</th><th>Start</th><th>End</th><th>Cost</th><th>Plan</th><th>License Key</th><th>Linked Asset</th></tr></thead><tbody>${rowsHtml}</tbody></table>
  ${printReadyScript()}
  </body></html>`);
  w.document.close();
}
function renderContractStats(){
  const today=new Date();
  const in30=new Date(today.getTime()+30*86400000);
  const count=t=>contracts.filter(c=>(c.type||'')===t).length;
  const expiring=contracts.filter(c=>{
    if(!c.end_date)return false;
    const d=new Date(c.end_date);
    return d>=today && d<=in30;
  }).length;
  const setKV=(id,v)=>{ const el=document.getElementById(id); if(el)el.textContent=v; };
  setKV('ctTotal',contracts.length);
  setKV('ctAmc',count('AMC'));
  setKV('ctLicense',count('License'));
  setKV('ctSub',count('Subscription'));
  setKV('ctExpiring',expiring);
}
// per-row "⋮" actions menu -- same shared #rowMenu component the Assets table uses
function toggleContractRowMenu(e,id){
  e.stopPropagation();
  const menu=document.getElementById('rowMenu');
  if(rowMenuAssetId===('ct'+id) && menu.style.display!=='none'){ menu.style.display='none'; rowMenuAssetId=null; return; }
  rowMenuAssetId='ct'+id;
  menu.innerHTML=`
    <button onclick="closeRowMenu();openContractModal(${id})">EDIT</button>
    <button onclick="closeRowMenu();printContract(${id})">PRINT</button>
    <div class="row-menu-sep"></div>
    <button class="danger" onclick="closeRowMenu();deleteContractRow(${id})">DELETE</button>`;
  const btn=e.currentTarget.getBoundingClientRect();
  menu.style.display='flex';
  const menuRect=menu.getBoundingClientRect();
  let left=btn.right-menuRect.width;
  if(left<8) left=8;
  let top=btn.bottom+4;
  if(top+menuRect.height>window.innerHeight-8) top=btn.top-menuRect.height-4;
  menu.style.left=left+'px'; menu.style.top=top+'px';
}
window.toggleContractRowMenu=toggleContractRowMenu;
function printContract(id){
  const c=contracts.find(x=>x.id===id); if(!c)return;
  const w=window.open('','_blank');
  if(!w){toast('✕ Popup blocked — allow popups for this site');return;}
  const rows=[
    ['Name',c.name],['Type',c.type||'—'],['Vendor / Company',c.vendor||'—'],
    ['Cost',fmtMoney(c.cost||0,CURRENCY)],['Payment Plan',c.billing_period||'One-Time'],['Start Date',c.start_date||'—'],['End / Renewal Date',c.end_date||'—'],
    ['Linked Asset',assetLabelFor(c.asset_id)||'—']
  ];
  if(c.type==='License' && c.license_key) rows.push(['License Key',c.license_key]);
  rows.push(['Note',c.note||'—']);
  const rowsHtml=rows.map(([k,v])=>`<tr><td class="k">${esc(k)}</td><td class="v">${esc(v)}</td></tr>`).join('');
  w.document.write(`<!doctype html><html><head><title>Contract — ${esc(c.name||'')}</title>
  <style>@page{size:A4;margin:${window.HAS_LETTERHEAD?'0':'14mm'}}body{font-family:'Segoe UI',Arial,sans-serif;color:#111;padding:0;margin:0}
  .card{border:1px solid #222;border-radius:8px;max-width:720px;margin:0 auto;overflow:hidden}
  .hd{background:#101622;color:#fff;padding:12px 16px;font-family:'Segoe UI',Arial,sans-serif;font-weight:600;letter-spacing:.2px;display:flex;justify-content:space-between;align-items:center}
  .hd .brand{display:flex;align-items:center;gap:10px} .hd img{height:26px}
  .hd .id{font-size:11px;opacity:.7} .bd{padding:14px 16px} table{width:100%;border-collapse:collapse} td.k{width:38%;padding:5px 8px;color:#555;font-weight:600;border-bottom:1px solid #eee;vertical-align:top} td.v{padding:5px 8px;border-bottom:1px solid #eee;word-break:break-word}
  @media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact}.card{border-color:#222}}</style></head>
  <body>${window.HAS_LETTERHEAD?`<img src="/letterhead.png?t=${Date.now()}" style="position:fixed;top:0;left:0;width:210mm;height:297mm;object-fit:fill;z-index:-1">`:''}
  <div class="card" style="${window.HAS_LETTERHEAD?`margin-top:${LETTERHEAD_CLEARANCE_MM}mm`:''}">${window.HAS_LETTERHEAD?'':`<div class="hd"><div class="brand"><img src="/logo.png" onerror="this.style.display='none'"><span>${(window.APP_NAME||'IT-Vault')} — Contract record</span></div><span class="id">${contractIdFor(c)}</span></div>`}
  <div class="bd"><table>${rowsHtml}</table></div></div>
  ${printReadyScript()}
  </body></html>`);
  w.document.close();
}
window.printContract=printContract;
async function deleteContractRow(id){
  if(!confirm('Move this contract to trash?'))return;
  const r=await api('/api/contracts',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
  if(r&&r.ok){toast('🗑 MOVED TO TRASH');loadContracts();}else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}
window.deleteContractRow=deleteContractRow;
function populateContractAssetSelect(sel){
  const selEl=document.getElementById('ct_asset');
  selEl.innerHTML='<option value="">-- none --</option>'+assets.map(a=>`<option value="${a._id}" ${a._id===sel?'selected':''}>${esc(a.AssetTag||a._id)} — ${esc(a.Name)} (${esc(a.Serial||'no S/N')})</option>`).join('');
}
async function populateContractEmployeeSelect(sel){
  const selEl=document.getElementById('ct_employee'); if(!selEl)return;
  const r=await api('/api/employees'); const list=r?await r.json():[];
  selEl.innerHTML='<option value="">-- none --</option>'+list.map(e=>`<option value="${esc(e.EmployeeID)}" ${e.EmployeeID===sel?'selected':''}>${esc(e.EmployeeName||e.EmployeeID)}</option>`).join('');
}
async function populateContractLocationSelect(sel){
  const selEl=document.getElementById('ct_location'); if(!selEl)return;
  const r=await api('/api/locations'); const list=r?await r.json():[];
  selEl.innerHTML='<option value="">-- none --</option>'+list.map(l=>`<option value="${esc(l.name)}" ${l.name===sel?'selected':''}>${esc(l.name)}</option>`).join('');
}
async function populateContractDepartmentSelect(sel){
  const selEl=document.getElementById('ct_department'); if(!selEl)return;
  const r=await api('/api/departments'); const list=r?await r.json():[];
  selEl.innerHTML='<option value="">-- none --</option>'+list.map(d=>`<option value="${esc(d.name)}" ${d.name===sel?'selected':''}>${esc(d.name)}</option>`).join('');
}
async function loadContractTypeOptions(selType){
  const sel=document.getElementById('ct_type'); if(!sel)return;
  const r=await api('/api/contract-types'); const list=r?await r.json():[];
  sel.innerHTML='<option value="">-- select type --</option>'+list.map(t=>`<option value="${esc(t.name)}" ${t.name===selType?'selected':''}>${esc(t.name)}</option>`).join('')+'<option value="__new">＋ type new…</option>';
  sel.onchange=async()=>{
    if(sel.value==='__new'){
      const v=prompt('New contract type:');
      if(v&&v.trim()){
        const r2=await api('/api/contract-types',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:v.trim()})});
        if(r2&&r2.ok){await loadContractTypeOptions(v.trim());}
      } else { sel.value=selType; }
    }
    toggleContractLicenseKeyField();
  };
  toggleContractLicenseKeyField();
}
function toggleContractLicenseKeyField(){
  const sel=document.getElementById('ct_type'); const wrap=document.getElementById('ct_license_key_wrap');
  if(!sel||!wrap)return;
  wrap.style.display=sel.value==='License'?'':'none';
}
async function openContractModal(id){
  editingContractId=id||null;
  const c=id?(contracts.find(x=>x.id===id)||{}):{};
  document.getElementById('contractModalTitle').textContent=id?'EDIT CONTRACT':'ADD CONTRACT';
  document.getElementById('ctCurLabel').textContent=CURRENCY;
  if(id){
    document.getElementById('ct_idDisplay').value=contractIdFor(c);
  }else{
    document.getElementById('ct_idDisplay').value='';
    const r=await api('/api/contracts/next-tag'); if(r&&r.ok){ const j=await r.json(); document.getElementById('ct_idDisplay').value=j.tag||''; }
  }
  document.getElementById('ct_name').value=c.name||'';
  document.getElementById('ct_vendor').value=c.vendor||'';
  document.getElementById('ct_vendor_email').value=c.vendor_email||'';
  document.getElementById('ct_cost').value=c.cost||'';
  document.getElementById('ct_billing').value=c.billing_period||'One-Time';
  document.getElementById('ct_start').value=c.start_date||'';
  document.getElementById('ct_end').value=c.end_date||'';
  document.getElementById('ct_license_key').value=c.license_key||'';
  document.getElementById('ct_note').value=c.note||'';
  populateContractAssetSelect(c.asset_id||'');
  await Promise.all([
    loadContractTypeOptions(c.type||'AMC'),
    populateContractEmployeeSelect(c.employee_id||''),
    populateContractLocationSelect(c.location||''),
    populateContractDepartmentSelect(c.department||'')
  ]);
  document.getElementById('ctDelete').style.display=id?'':'none';
  document.getElementById('contractModal').classList.add('show');
}
window.openContractModal=openContractModal;
// Picking a recurring Payment Plan (or changing the Start Date once one's
// picked) auto-fills End/Renewal Date to match -- still a plain editable
// date input, so a manual override afterward just sticks. One-Time has no
// cadence to compute from, so it's left alone.
function calcContractEndDate(startStr, period){
  const months={Monthly:1, Quarterly:3, 'Semi-Annually':6, Annually:12}[period];
  if(!startStr || !months) return '';
  const d=new Date(startStr+'T00:00:00');
  if(isNaN(d)) return '';
  const day=d.getDate();
  d.setMonth(d.getMonth()+months);
  if(d.getDate()!==day) d.setDate(0); // month overflowed (e.g. Jan 31 +1mo) -- clamp to that month's last day
  // build the string from local date parts, not toISOString() -- that
  // converts to UTC and can shift the date by a day either way depending
  // on the browser's timezone offset from a plain local midnight Date.
  const y=d.getFullYear(), m=String(d.getMonth()+1).padStart(2,'0'), dd=String(d.getDate()).padStart(2,'0');
  return `${y}-${m}-${dd}`;
}
function autoFillContractEnd(){
  const end=calcContractEndDate(document.getElementById('ct_start').value, document.getElementById('ct_billing').value);
  if(end) document.getElementById('ct_end').value=end;
}
document.getElementById('ct_billing').onchange=autoFillContractEnd;
document.getElementById('ct_start').onchange=autoFillContractEnd;
async function saveContract(){
  const body={
    contract_tag: document.getElementById('ct_idDisplay').value.trim(),
    name: document.getElementById('ct_name').value.trim(),
    type: document.getElementById('ct_type').value,
    vendor: document.getElementById('ct_vendor').value.trim(),
    vendor_email: document.getElementById('ct_vendor_email').value.trim(),
    cost: parseFloat(document.getElementById('ct_cost').value)||0,
    billing_period: document.getElementById('ct_billing').value,
    start_date: document.getElementById('ct_start').value,
    end_date: document.getElementById('ct_end').value,
    asset_id: document.getElementById('ct_asset').value||null,
    employee_id: document.getElementById('ct_employee').value||'',
    location: document.getElementById('ct_location').value||'',
    department: document.getElementById('ct_department').value||'',
    license_key: document.getElementById('ct_license_key').value.trim(),
    note: document.getElementById('ct_note').value.trim()
  };
  if(!body.name){toast('✕ Name required');return;}
  if(body.type==='__new'){toast('✕ Pick a contract type');return;}
  const r=editingContractId
    ? await api('/api/contracts',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,id:editingContractId})})
    : await api('/api/contracts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r&&r.ok){toast('✓ CONTRACT SAVED');document.getElementById('contractModal').classList.remove('show');loadContracts();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}
async function deleteContract(){
  if(!editingContractId)return;
  if(!confirm('Move this contract to trash?'))return;
  const r=await api('/api/contracts',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:editingContractId})});
  if(r&&r.ok){toast('🗑 MOVED TO TRASH');document.getElementById('contractModal').classList.remove('show');loadContracts();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}
document.getElementById('ctCancel').onclick=()=>document.getElementById('contractModal').classList.remove('show');
document.getElementById('ctSave').onclick=saveContract;
document.getElementById('ctDelete').onclick=deleteContract;
window.loadTickets=loadTickets;window.openNewTicket=openNewTicket;window.sendReply=sendReply;
window.loadContracts=loadContracts;


document.getElementById('navDirectory').onclick=()=>showPage('page-employees');
document.getElementById('navTrash').onclick=()=>showPage('page-trash');
document.getElementById('navTickets').onclick=()=>showPage('page-tickets');
document.getElementById('navContracts').onclick=()=>showPage('page-contracts');
document.getElementById('logoutBtn').onclick=async()=>{ try{ await api('/api/logout',{method:'POST'}); }catch(e){} location.href='/'; };
document.getElementById('navSettings').onclick=()=>showPage('page-usettings');
document.getElementById('navBackup').onclick=()=>openBackup();
const ni3=document.getElementById('navImport'); if(ni3) ni3.onclick=()=>showPage('page-import');
const ne=document.getElementById('navExport'); if(ne) ne.onclick=()=>window.location='/api/export';
const na2=document.getElementById('navAdd'); if(na2) na2.onclick=()=>openModal();
document.getElementById('navHome').onclick=()=>showPage('page-dashboard');
document.getElementById('dashEditLayout').onclick=()=>setEditLayout(true);
document.getElementById('dashSaveLayout').onclick=()=>{
  putDashLayout(saveDashLayout());
  applyDashLayout();
  setEditLayout(false);
  document.getElementById('dashLayoutMsg').textContent='✓ Layout saved';
};
document.getElementById('dashResetLayout').onclick=()=>{
  // both keys: leaving v1 behind would have it migrated straight back in
  try{ localStorage.removeItem(DASH_LAYOUT_KEY2); localStorage.removeItem(DASH_LAYOUT_KEY); }catch(e){}
  document.getElementById('dashLayoutMsg').textContent='↺ Reset to default';
  location.reload();
};
document.getElementById('dashAddWidget').onclick=openWidgetPicker;

/* Type-to-find, matching a widget's heading and a tile's title/address.
   Purely visual -- it never touches the saved layout. */
const dashFilterEl=document.getElementById('dashFilter');
if(dashFilterEl) dashFilterEl.oninput=()=>{
  const q=dashFilterEl.value.trim().toLowerCase();
  const cont=dashCont(); if(!cont) return;
  cont.classList.toggle('filtering', !!q);
  cont.querySelectorAll('.widget[data-wkey]').forEach(w=>{
    if(!q){ w.classList.remove('w-nomatch'); return; }
    const hay=[w.querySelector('.secthead')?.textContent,
               w.querySelector('.wlink-host')?.textContent,
               w.querySelector('.wlink-sub')?.textContent,
               w.querySelector('.wlink-body')?.getAttribute('href')]
              .join(' ').toLowerCase();
    w.classList.toggle('w-nomatch', !hay.includes(q));
  });
};

document.getElementById('dashCols').onchange=(e)=>{
  const n=Math.max(1, Math.min(4, parseInt(e.target.value,10)||2));
  dashCont()?.style.setProperty('--dashcols', String(n));
};
document.getElementById('wmFetchIcon').onclick=async()=>{
  const url=document.getElementById('wmUrl').value.trim();
  const msg=document.getElementById('wmIconMsg');
  if(!url){ msg.textContent='Enter the address first'; return; }
  msg.textContent='Looking…';
  const r=await api('/api/widget/icon?url='+encodeURIComponent(url));
  const j=r?await r.json().catch(()=>({})):{};
  if(j&&j.icon){ wmIcon=j.icon; renderWmIcon(); msg.textContent='Found it'; }
  else { msg.textContent=(j&&j.error)||'No icon found at that address'; }
};
document.getElementById('wmIconFile').onchange=(e)=>{
  const f=e.target.files&&e.target.files[0]; if(!f) return;
  const msg=document.getElementById('wmIconMsg');
  // the tile is stored in localStorage, so the icon has to stay small
  if(f.size > 512*1024){ msg.textContent='That image is over 512KB — use a smaller one'; return; }
  const fr=new FileReader();
  fr.onload=()=>{ wmIcon=String(fr.result||''); renderWmIcon(); msg.textContent='Uploaded'; };
  fr.onerror=()=>{ msg.textContent='Could not read that file'; };
  fr.readAsDataURL(f);
};
document.getElementById('wmClearIcon').onclick=()=>{ wmIcon=''; renderWmIcon(); };
document.getElementById('wmAdd').onclick=()=>{
  const title=document.getElementById('wmTitle').value.trim();
  const url=document.getElementById('wmUrl').value.trim();
  const mon=document.getElementById('wmMonitor').value;
  const msg=document.getElementById('wmIconMsg');
  if(!title||!url){ msg.textContent='A title and an address are both needed'; return; }
  // only ever a link the browser will actually open
  let safe=url; if(!/^https?:\/\//i.test(safe)) safe='http://'+safe;
  try{ new URL(safe); }catch(e){ msg.textContent='That address is not valid'; return; }
  const L=getDashLayout();
  const desc=document.getElementById('wmDesc').value.trim();
  const target=document.getElementById('wmTarget').value==='_self'?'_self':'_blank';
  const key=wmEditKey||('link:'+Math.random().toString(36).slice(2,10));
  const tile={key, title, url:safe, icon:wmIcon||'',
              monitor:mon?Number(mon):null, desc, target};
  if(wmEditKey){
    // replaced in place, so an edited tile keeps its spot on the grid
    L.links=(L.links||[]).map(t=>t.key===wmEditKey?tile:t);
  }else{
    L.links=(L.links||[]).concat([tile]);
    L.order=(L.order||[]).concat([key]);
  }
  putDashLayout(L);
  applyDashLayout();
  decorateWidgets(document.body.classList.contains('edit-layout'));
  initDashDrag();
  document.getElementById('widgetModal').classList.remove('show');
  toast(wmEditKey?'✓ TILE UPDATED':'✓ TILE ADDED');
  wmEditKey=null;
};
document.getElementById('navAssets').onclick=()=>showPage('page-assets');

function showFatal(msg){
  let b=document.getElementById('fatalBanner');
  if(!b){b=document.createElement('div');b.id='fatalBanner';b.style.cssText='position:fixed;top:0;left:0;right:0;z-index:9999;background:#ff3860;color:#fff;font-family:monospace;padding:10px 14px;font-size:13px;white-space:pre-wrap';document.body.appendChild(b);}
  b.textContent='[ITGUY STARTUP ERROR] '+msg;
  console.error('[ITGUY] FATAL',msg);
}
window.addEventListener('error',e=>showFatal(e.message+' ('+e.filename+':'+e.lineno+')'));
window.addEventListener('unhandledrejection',e=>showFatal('Promise: '+(e.reason&&e.reason.message||e.reason)));
/* Ensure dashboard widgets/tools are correctly nested inside #page-dashboard.
   Some browsers auto-eject them if the HTML parser closes #page-dashboard early
   (e.g. due to an edge-case in the KPI markup). This repairs the DOM so that
   hiding #page-dashboard also hides its widgets — keeping pages independent. */
function repairDashStructure(){
  try{
    const pd=document.getElementById('page-dashboard');
    const dw=document.getElementById('dashWidgets');
    const dt=document.getElementById('dashTools');
    if(!pd||!dw) return;
    if(!pd.contains(dw)){
      // place tools then widgets at the end of page-dashboard
      if(dt && !pd.contains(dt)) pd.appendChild(dt);
      pd.appendChild(dw);
    }
  }catch(e){ console.warn('repairDashStructure skipped', e); }
}
window.repairDashStructure=repairDashStructure;

// Self-heal: clear any stale/corrupt itvault_* localStorage from older builds so an
// old empty-column or bad-layout selection can't blank the UI for returning users.
(function healStorage(){
  try{
    const KEEP=new Set(['itvault_dash_layout_v1','itvault_dash_layout_v2','itvault_cols','itvault_sess','itvault_scan_last']);
    const bad=[];
    for(let i=localStorage.length-1;i>=0;i--){
      const k=localStorage.key(i);
      if(k && k.indexOf('itvault_')===0 && !KEEP.has(k)) bad.push(k);
    }
    bad.forEach(k=>localStorage.removeItem(k));
    // also repair itvault_cols if it's empty/invalid
    try{
      const c=localStorage.getItem('itvault_cols');
      if(c){ const v=JSON.parse(c); if(!Array.isArray(v)||v.length===0) localStorage.removeItem('itvault_cols'); }
    }catch(e){ localStorage.removeItem('itvault_cols'); }
    if(bad.length) console.log('[ITGUY] healed stale storage keys:', bad);
  }catch(e){}
})();

(async()=>{
 try{
  const me=await fetch('/api/me').then(r=>r.json());
  if(!me.user){location.href='/'+(location.search||'');return;}
  MY_ROLE=me.role;
  MY_PERMS=me.perms||{};
  MY_FEATURES=me.features||[];
  applyNavPermissions();
  applySettingsPermissions();
  window.sessionUser=me.user;
  {const dz=document.getElementById('navDangerZone'); if(dz)dz.style.display=(MY_ROLE===ROLE_ADMIN)?'':'none';}
  applyTheme(me.theme||'dark');
  try{applyCustomVars(me);}catch(e){console.warn('theme vars skipped',e);}
  CURRENCY=me.currency||'AED';
  applyLanguage(me.language||'en');
  document.getElementById('uname').textContent=me.user;
  renderSidebarAvatar(me);
  document.getElementById('roleBadge').textContent=(me.role||'').toUpperCase();
  // sidebar visibility by role
  const navShow = {
    navAudit: true,
    navScan: me.role===ROLE_ADMIN || me.role===ROLE_EDIT,
    navHeartbeat: me.role===ROLE_ADMIN || me.role===ROLE_EDIT,
    navDirectory: me.role===ROLE_ADMIN || me.role===ROLE_EDIT,
    navContracts: me.role===ROLE_ADMIN || me.role===ROLE_EDIT,
    navTrash: me.role===ROLE_ADMIN || me.role===ROLE_EDIT,
    navCatalog: me.role===ROLE_ADMIN || me.role===ROLE_EDIT,
    navBackup: me.role===ROLE_ADMIN
  };
  Object.entries(navShow).forEach(([id,show])=>{ const el=document.getElementById(id); if(el) el.style.display = show ? 'flex' : 'none'; });
  // guarantee app is visible even if later calls fail
  document.getElementById('app').style.display='flex';
  try{await applyBranding();}catch(e){console.warn('branding skipped',e);}
  wireModalClose();
  startSessBar();
  repairDashStructure();
  // run data loads independently so one failure can't blank the rest
  load().catch(e=>showFatal('load(): '+e.message));
  loadDashboard().catch(e=>showFatal('loadDashboard(): '+e.message));
  loadEmployees().catch(e=>console.warn('employees skipped',e));
  showPage('page-dashboard');
  try{ var av=document.getElementById('appVer'); if(av) av.textContent=APP_VERSION; }catch(e){}
}catch(e){showFatal(e.message+' @ startup');}
})();

function wireModalClose(){
  document.querySelectorAll('.modal').forEach(m=>{
    if(m.id==='usersModal')return; // handled by closeUsersReturnProfile (returns to Profile)
    if(!m.dataset._wired){
      // Only close on a genuine click on the backdrop -- mousedown AND
      // mouseup both landing on the backdrop itself. Checking the click
      // target alone was the bug: dragging to select text (e.g. copying the
      // sign link) that drifts past the dialog's edge for even a moment
      // still fires a "click" on the backdrop when the mouse comes up out
      // there, closing the modal mid-selection.
      let downOnBackdrop=false;
      m.addEventListener('mousedown',e=>{ downOnBackdrop=(e.target===m); });
      m.addEventListener('click',e=>{ if(downOnBackdrop && e.target===m) m.classList.remove('show'); downOnBackdrop=false; });
      new MutationObserver(mo=>{
        if(m.classList.contains('show')) bringToFront(m);
      }).observe(m,{attributes:true,attributeFilter:['class']});
      m.dataset._wired='1';
    }
  });
}
function bringToFront(m){
  // keep explicitly-stacked modals (profile/users) above the generic base
  const fixed={usersModal:210};
  document.querySelectorAll('.modal.show').forEach(el=>{
    if(fixed[el.id]) el.style.zIndex=fixed[el.id];
    else el.style.zIndex=100;
  });
  const box=m.querySelector('.modal-box');
  if(box) box.style.zIndex=200;
}
function doExport(){window.location='/api/export';}

/* =========================================================================
   THEME ENGINE + CUSTOMIZATION / PROFILE / USER SETTINGS PAGES
   ========================================================================= */
const api_json = async (p, o) => { const r = await api(p, o); if (!r) return {}; try { return await r.json(); } catch (e) { return {}; } };

/* Backend PUT /api/settings rewrites the whole Settings row and falls back to
   defaults for any key it does not receive. So every save must send a FULL
   body: read the current settings, merge the patch, then PUT. */
const SETTINGS_KEYS = ['theme','smtp_host','smtp_port','smtp_user','smtp_from','notify_new','notify_delete',
  'app_name','logo_text','matrix_on','ldap_server','ldap_domain','ldap_bind_user','ldap_base_dn',
  'qr_size','qr_fields','label_size','label_logo','theme_preset','bg_type','bg','comp_bg','radius',
  'font','accent','accent2','language','currency','region'];
async function putSettingsMerged(patch){
  const cur = await api_json('/api/settings');
  const body = {};
  SETTINGS_KEYS.forEach(k => { if (cur[k] !== undefined && cur[k] !== null) body[k] = cur[k]; });
  Object.keys(patch || {}).forEach(k => { body[k] = patch[k]; });
  return api('/api/settings', { method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
}

const THEME_PRESETS = {
  deepdark:   { label:'Deep Dark',   bg_type:'solid', bg:'#000000', comp_bg:'#000000', accent:'#ff3b30', accent2:'#c0392b', radius:12, font:'Inter',           theme:'dark'  },
  cleanlight: { label:'Clean Light', bg_type:'solid', bg:'#eef1f6', comp_bg:'#ffffff', accent:'#ff3b30', accent2:'#c0392b', radius:10, font:'Inter',           theme:'light' },
  graphite:   { label:'Graphite',    bg_type:'solid', bg:'#16181d', comp_bg:'#1e2127', accent:'#ff6b57', accent2:'#a56b6b', radius:8,  font:'Inter',           theme:'dark'  },
  /* legacy key kept so a saved 'cyberpunk' setting still resolves */
  cyberpunk:  { label:'Graphite',    bg_type:'solid', bg:'#16181d', comp_bg:'#1e2127', accent:'#ff6b57', accent2:'#a56b6b', radius:8,  font:'Inter',           theme:'dark'  },
  minimalist: { label:'Minimalist',  bg_type:'solid', bg:'#f7f7f8', comp_bg:'#ffffff', accent:'#111111', accent2:'#888888', radius:2,  font:'Inter',           theme:'light' }
};
const EMOJI_FALLBACK = ",'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji'";
const FONT_STACKS = {
  'Inter':"'Inter','Segoe UI',system-ui,-apple-system,sans-serif"+EMOJI_FALLBACK,
  'Segoe UI':"'Segoe UI',system-ui,-apple-system,sans-serif"+EMOJI_FALLBACK,
  'System':"system-ui,-apple-system,'Segoe UI',sans-serif"+EMOJI_FALLBACK
};

function hex6(v, fb){
  const s = String(v == null ? '' : v).trim();
  if (/^#[0-9a-fA-F]{6}$/.test(s)) return s.toLowerCase();
  if (/^#[0-9a-fA-F]{3}$/.test(s)) return ('#' + s[1]+s[1] + s[2]+s[2] + s[3]+s[3]).toLowerCase();
  return fb;
}
function hexRgb(h){ const s = hex6(h, '#000000'); return [parseInt(s.slice(1,3),16), parseInt(s.slice(3,5),16), parseInt(s.slice(5,7),16)]; }
function rgba(h, a){ const c = hexRgb(h); return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a + ')'; }
function shade(h, amt){
  const c = hexRgb(h);
  const f = n => { const v = Math.max(0, Math.min(255, Math.round(n + 255 * amt))); return v.toString(16).padStart(2, '0'); };
  return '#' + f(c[0]) + f(c[1]) + f(c[2]);
}
function isLightHex(h){ const c = hexRgb(h); return (c[0]*0.299 + c[1]*0.587 + c[2]*0.114) > 150; }
/* Picks a readable foreground for a given background hex */
function onBg(bgHex){
  return isLightHex(bgHex) ? '#16202e' : '#e6edf6';
}
// For button text ON TOP OF an accent color, a simple light/dark luminance
// split (like onBg) is too blunt -- a saturated color like the default red
// accent reads as "dark" by that formula even though the dark navy text
// (#04121f) the app has always used actually contrasts better against it
// than light text would. Pick whichever of the two candidate text colors
// gives the higher WCAG contrast ratio against this specific accent, so
// every existing preset keeps its current look and only a genuinely bad
// pairing (e.g. Minimalist's near-black accent) actually changes.
function bestTextOn(bgHex){
  const dark = '#04121f', light = '#e6edf6';
  return contrastRatio(bgHex, dark) >= contrastRatio(bgHex, light) ? dark : light;
}
function muteFor(bgHex, k){
  // k: 'muted' (secondary text) or 'muted2' (tertiary)
  const light = isLightHex(bgHex);
  if (light){
    return k === 'muted' ? '#5d6b82' : '#8595ad';
  }
  return k === 'muted' ? '#8a98b0' : '#5d6b82';
}
/* W3C contrast ratio between two hex colors */
function contrastRatio(a, b){
  const L = h => { const [r,g,bl] = hexRgb(h).map(v => { v/=255; return v<=0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055,2.4); }); return 0.2126*r+0.7152*g+0.0722*bl; };
  const la = L(a), lb = L(b);
  const hi = Math.max(la,lb), lo = Math.min(la,lb);
  return (hi+0.05)/(lo+0.05);
}
/* Ensure an accent is visible on a surface: if contrast < 2.2, mix toward surface */
function ensureAccentVisible(accent, surface){
  if (contrastRatio(accent, surface) >= 2.2) return accent;
  // blend 35% toward surface
  const a = hexRgb(accent), s = hexRgb(surface);
  const mix = a.map((v,i)=> Math.round(v*0.65 + s[i]*0.35));
  return '#' + mix.map(v=>v.toString(16).padStart(2,'0')).join('');
}

/* Normalizes any settings-ish object (from /api/me or /api/settings) into theme fields */
function normCustom(s){
  s = s || {};
  const bgRaw = String(s.bg == null ? '' : s.bg).trim();
  const isGrad = String(s.bg_type || 'solid') === 'gradient';
  let bgA = '#0a0d13', bgB = '#121826';
  if (isGrad){
    const found = bgRaw.match(/#[0-9a-fA-F]{3,6}/g) || [];
    bgA = hex6(s.bgA || found[0] || '#0a0d13', '#0a0d13');
    bgB = hex6(s.bgB || found[1] || '#121826', '#121826');
  }
  const font = FONT_STACKS[s.font] ? s.font : 'Inter';
  let radius = parseInt(s.radius, 10); if (!isFinite(radius)) radius = 12;
  radius = Math.max(0, Math.min(24, radius));
  // derive light/dark from base background (single source of truth)
  const baseHex = isGrad ? bgA : hex6(bgRaw, '#000000');
  const theme = isLightHex(baseHex) ? 'light' : 'dark';
  return {
    theme_preset: String(s.theme_preset || 'deepdark'),
    theme: theme,
    bg_type: isGrad ? 'gradient' : 'solid',
    bg: hex6(isGrad ? bgA : bgRaw, '#000000'),
    bgA: bgA, bgB: bgB,
    comp_bg: hex6(s.comp_bg, '#000000'),
    accent: hex6(s.accent, '#ff3b30'),
    accent2: hex6(s.accent2, '#c0392b'),
    radius: radius,
    font: font
  };
}

/* Applies CSS variables live. SINGLE SOURCE OF TRUTH for theming.
   Derives a full, contrast-correct palette from base bg + accents so the UI
   is always readable regardless of which preset or custom colors are chosen. */
function applyCustomVars(s){
  const c = normCustom(s);
  const st = document.documentElement.style;
  const bgValue = c.bg_type === 'gradient'
    ? 'linear-gradient(135deg, ' + c.bgA + ', ' + c.bgB + ')'
    : c.bg;
  const baseHex = c.bg_type === 'gradient' ? c.bgA : c.bg;
  const light = isLightHex(baseHex);

  // Keep the light/dark class in sync (used only for matrix + scrollbar tweaks now)
  document.body.classList.toggle('light', light);

  // Surface / component background
  const surface = c.comp_bg;
  const surfaceLight = isLightHex(surface);

  // Accents guaranteed visible on surface
  const accent = ensureAccentVisible(c.accent, surface);
  const accent2 = ensureAccentVisible(c.accent2, surface);

  // Foreground text derived from base bg (not from a competing CSS block)
  const txt = onBg(baseHex);
  const muted = muteFor(baseHex, 'muted');
  const muted2 = muteFor(baseHex, 'muted2');

  st.setProperty('--bg', bgValue);
  st.setProperty('--bg1', light ? shade(baseHex, -0.04) : shade(baseHex, 0.03));
  st.setProperty('--surface', surface);
  st.setProperty('--surface2', surfaceLight ? shade(surface, -0.04) : shade(surface, -0.02));
  st.setProperty('--line', surfaceLight ? shade(surface, -0.14) : shade(surface, 0.10));
  st.setProperty('--line2', surfaceLight ? shade(surface, -0.22) : shade(surface, 0.16));
  st.setProperty('--txt', txt);
  st.setProperty('--muted', muted);
  st.setProperty('--muted2', muted2);
  st.setProperty('--accent', accent);
  st.setProperty('--accent2', accent2);
  st.setProperty('--accent-soft', rgba(accent, 0.14));
  // Primary buttons paint text on top of --accent -- a fixed dark text color
  // (the old behavior) goes invisible on presets like Minimalist whose
  // accent is itself near-black. Derive readable button text from the
  // accent's own lightness instead, same as --txt is derived from the page
  // background.
  st.setProperty('--btn-text', bestTextOn(accent));
  st.setProperty('--btn-mag-text', bestTextOn(accent2));
  st.setProperty('--radius', c.radius + 'px');
  const fontStack = FONT_STACKS[c.font] || FONT_STACKS['Inter'];
  st.setProperty('--font', fontStack);
  document.body.style.fontFamily = fontStack;

  window.__customTheme = c;
  return c;
}
window.applyCustomVars = applyCustomVars;

/* ---------- CUSTOMIZATION PAGE ---------- */
function customGradToggle(){
  const grad = document.getElementById('bgType').value === 'gradient';
  const a = document.getElementById('bgGradWrapA'), b = document.getElementById('bgGradWrapB');
  if (a) a.style.display = grad ? 'flex' : 'none';
  if (b) b.style.display = grad ? 'flex' : 'none';
  const solid = document.getElementById('bg').closest('.field2');
  if (solid) solid.style.display = grad ? 'none' : 'flex';
}
function readCustomForm(){
  const g = id => document.getElementById(id);
  const bgType = g('bgType').value === 'gradient' ? 'gradient' : 'solid';
  const bgA = hex6(g('bgA').value, '#0a0d13'), bgB = hex6(g('bgB').value, '#121826');
  return {
    theme_preset: (window.__customTheme && window.__customTheme.theme_preset) || 'deepdark',
    bg_type: bgType,
    bg: bgType === 'gradient' ? (bgA + '|' + bgB) : hex6(g('bg').value, '#0a0d13'),
    bgA: bgA, bgB: bgB,
    comp_bg: hex6(g('compBg').value, '#121826'),
    radius: Math.max(0, Math.min(24, parseInt(g('radius').value, 10) || 0)),
    font: FONT_STACKS[g('font').value] ? g('font').value : 'Inter',
    accent: hex6(g('accent').value, '#ff3b30'),
    accent2: hex6(g('accent2').value, '#c0392b')
  };
}
function fillCustomForm(c){
  const g = id => document.getElementById(id);
  g('bgType').value = c.bg_type;
  g('bg').value = c.bg_type === 'gradient' ? c.bgA : c.bg;
  g('bgA').value = c.bgA; g('bgB').value = c.bgB;
  g('compBg').value = c.comp_bg;
  g('radius').value = String(c.radius);
  const rv = g('radiusVal'); if (rv) rv.textContent = String(c.radius);
  g('font').value = c.font;
  g('accent').value = c.accent;
  g('accent2').value = c.accent2;
  customGradToggle();
  markPreset(c.theme_preset);
}
function markPreset(name){
  document.querySelectorAll('#presetGrid .preset-card').forEach(el => {
    el.classList.toggle('active', el.dataset.preset === name);
  });
}
function applyFormLive(){
  const c = readCustomForm();
  applyCustomVars(c);
  const rv = document.getElementById('radiusVal');
  if (rv) rv.textContent = String(c.radius);
}
async function loadCustom(){
  dbg('loadCustom() called');
  let s;
  try{ s = await api_json('/api/settings'); }
  catch(e){ dbg('loadCustom FETCH ERROR: '+e.message); showCustomError('network/fetch error: '+e.message); console.error(e); return; }
  if(!s){ dbg('loadCustom settings NULL (unauthorized)'); showCustomError('unauthorized (settings returned null)'); return; }
  // /api/settings needs settings rights: a user without them gets back
  // {error:"No access"},
  // not a settings object. Applying that would reset everyone's live theme to hardcoded
  // defaults just from opening Settings — bail out instead and leave the theme untouched.
  if(s.error || s.bg===undefined){ dbg('loadCustom: not a settings object (no access) — leaving theme untouched'); showCustomError('No access — appearance settings need the Branding permission.'); return; }
  dbg('loadCustom settings: '+(s?('keys='+Object.keys(s).length):'NULL'));
  const c = applyCustomVars(s);
  fillCustomForm(c);

  if (!document.getElementById('cfgCustomSec').dataset._wired){
    ['bgType','bg','bgA','bgB','compBg','font','accent','accent2'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.oninput = () => { customGradToggle(); applyFormLive(); };
    });
    const rad = document.getElementById('radius');
    if (rad) rad.oninput = applyFormLive;

    document.querySelectorAll('#presetGrid .preset-card').forEach(card => {
      card.onclick = () => {
        const key = card.dataset.preset;
        const p = THEME_PRESETS[key];
        if (!p) return;
        const c2 = normCustom(Object.assign({}, p, { theme_preset: key }));
        c2.theme_preset = key;
        applyCustomVars(c2);
        window.__customTheme.theme_preset = key;
        if (p.theme) applyTheme(p.theme);
        fillCustomForm(c2);
        toast('◆ ' + p.label.toUpperCase());
      };
    });

    const sv = document.getElementById('saveCustomBtn'); if (sv) sv.onclick = saveCustom;
    const rs = document.getElementById('resetCustomBtn');
    if (rs) rs.onclick = () => {
      const c3 = normCustom(Object.assign({}, THEME_PRESETS.deepdark, { theme_preset:'deepdark' }));
      c3.theme_preset = 'deepdark';
      applyCustomVars(c3); applyTheme('dark'); fillCustomForm(c3);
      toast('↺ RESET TO DEEP DARK');
    };
    document.getElementById('cfgCustomSec').dataset._wired = '1';
  }
}
async function saveCustom(){
  const c = readCustomForm();
  const body = {
    theme_preset: c.theme_preset,
    bg_type: c.bg_type,
    bg: c.bg,
    comp_bg: c.comp_bg,
    radius: c.radius,
    font: c.font,
    accent: c.accent,
    accent2: c.accent2,
    theme: document.body.classList.contains('light') ? 'light' : 'dark'
  };
  const r = await putSettingsMerged(body);
  if (r && r.ok){ applyCustomVars(c); toast('✓ SAVED'); }
  else if (r){ const j = await r.json().catch(() => ({})); toast('✕ ' + (j.error || 'save failed')); }
}
window.loadCustom = loadCustom; window.saveCustom = saveCustom;

/* ---------- PROFILE PAGE ---------- */
// Sidebar avatar (bottom-left, next to Logout) — shared by boot() and by the
// avatar upload flow below, so a freshly-uploaded photo shows immediately
// instead of only after the next full page reload.
function renderSidebarAvatar(p){
  const avEl=document.getElementById('av');
  if(!avEl) return;
  const avSrc=String(p.avatar||'').trim();
  if(avSrc){
    const src=avSrc.startsWith('data:')?avSrc:('data:image/png;base64,'+avSrc);
    avEl.innerHTML='<img src="'+esc(src)+'" alt="me" style="width:100%;height:100%;border-radius:inherit;object-fit:cover">';
  } else {
    avEl.textContent=((p.user||p.display||'A')[0]||'A').toUpperCase();
  }
}
function renderAvatarPreview(p){
  const box = document.getElementById('avatarPrev');
  if (!box) return;
  const av = String(p.avatar || '').trim();
  if (av){
    const src = av.startsWith('data:') ? av : ('data:image/png;base64,' + av);
    box.innerHTML = '<img src="' + esc(src) + '" alt="avatar">';
    box.classList.add('has-img');
  } else {
    const name = String(p.display || p.user || 'A').trim();
    const parts = name.split(/\s+/).filter(Boolean);
    const ini = ((parts[0] || 'A')[0] + (parts[1] ? parts[1][0] : '')).toUpperCase();
    box.textContent = ini;
    box.classList.remove('has-img');
  }
}
async function loadProfile(){
  const p = await api_json('/api/profile');
  const g = id => document.getElementById(id);
  if (g('pDisplay')) g('pDisplay').value = p.display || '';
  if (g('p_email')) g('p_email').value = p.email || '';
  if (g('pApiKey')) g('pApiKey').value = p.api_key || '';
  if (g('avatarPrev')) renderAvatarPreview(p);
  renderSidebarAvatar(p);

  const ul = g('pSessions');
  if (ul){
    const items = [];
    items.push('<li><span class="sl-k">CURRENT SESSION</span><span class="sl-v">' + esc(p.user || '') + ' • active now</span></li>');
    items.push('<li><span class="sl-k">LAST LOGIN</span><span class="sl-v">' + esc(p.last_login || '—') + '</span></li>');
    items.push('<li><span class="sl-k">ROLE</span><span class="sl-v">' + esc((p.role || '').toUpperCase() || '—') + '</span></li>');
    items.push('<li><span class="sl-k">USER AGENT</span><span class="sl-v">' + esc(navigator.userAgent.slice(0, 90)) + '</span></li>');
    ul.innerHTML = items.join('');
  }

  const file = g('avatarFile');
  if (file) file.onchange = () => {
    const f = file.files && file.files[0];
    if (!f) return;
    const rd = new FileReader();
    rd.onload = () => renderAvatarPreview({ avatar: String(rd.result), display: g('pDisplay').value });
    rd.readAsDataURL(f);
  };
  const asave = g('avatarSave');
  if (asave) asave.onclick = async () => {
    const f = file && file.files && file.files[0];
    if (!f){ toast('✕ Choose an image first'); return; }
    const fd = new FormData(); fd.append('avatar', f);
    const r = await api('/api/profile/avatar', { method:'POST', body: fd });
    if (r && r.ok){ toast('✓ AVATAR UPDATED'); loadProfile(); }
    else if (r){ const j = await r.json().catch(() => ({})); toast('✕ ' + (j.error || 'upload failed')); }
  };
  const regen = g('regenKey');
  if (regen) regen.onclick = async () => {
    if (!confirm('Regenerate API key? The old key stops working immediately.')) return;
    const j = await api_json('/api/profile/apikey', { method:'POST' });
    if (j && j.api_key){ g('pApiKey').value = j.api_key; toast('✓ NEW API KEY'); }
    else { toast('✕ ' + ((j && j.error) || 'failed')); }
  };
  const copy = g('copyKey');
  if (copy) copy.onclick = async () => {
    const v = g('pApiKey').value;
    if (!v){ toast('✕ No key to copy'); return; }
    try { await navigator.clipboard.writeText(v); }
    catch (e) { g('pApiKey').select(); document.execCommand('copy'); }
    toast('⧉ COPIED');
  };
  const ps = g('pPassSave');
  if (ps) ps.onclick = async () => {
    const oldp = g('p_old').value, np = g('p_new').value, np2 = g('p_new2').value;
    if (!oldp || !np){ toast('✕ Fill current and new password'); return; }
    if (np !== np2){ toast('✕ New passwords do not match'); return; }
    if (np.length < 4){ toast('✕ Password too short'); return; }
    const r = await api('/api/profile', { method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ old: oldp, new: np }) });
    if (r && r.ok){ toast('✓ PASSWORD UPDATED'); g('p_old').value = ''; g('p_new').value = ''; g('p_new2').value = ''; }
    else if (r){ const j = await r.json().catch(() => ({})); toast('✕ ' + (j.error || 'failed')); }
  };
  load2faStatus();
}
window.loadProfile = loadProfile;

/* ---------- two-factor auth (self-service, Settings > My Account) ---------- */
async function load2faStatus(){
  const g = id => document.getElementById(id);
  if (!g('totpStatusText')) return;
  const s = await api_json('/api/2fa/status');
  if (!s) return;
  g('totpStatusText').textContent = s.totp_enabled ? 'Enabled ✓' : 'Not enabled';
  g('totpEnableBtn').style.display = s.totp_enabled ? 'none' : '';
  g('totpDisableBtn').style.display = s.totp_enabled ? '' : 'none';
  g('emailOtpStatusText').textContent = s.email_otp_enabled ? `Enabled ✓ (${esc(s.email)})` : (s.email ? 'Not enabled' : 'Not enabled — set an email above first');
  g('emailOtpEnableBtn').style.display = s.email_otp_enabled ? 'none' : '';
  g('emailOtpEnableBtn').disabled = !s.email || !s.smtp_configured;
  g('emailOtpDisableBtn').style.display = s.email_otp_enabled ? '' : 'none';
}
{
  const g = id => document.getElementById(id);
  const totpEnableBtn = g('totpEnableBtn');
  if (totpEnableBtn) totpEnableBtn.onclick = async () => {
    const j = await api_json('/api/2fa/totp/setup', { method:'POST' });
    if (!j || !j.secret){ toast('✕ Could not start setup'); return; }
    g('totpQr').innerHTML = j.qr_svg;
    g('totpSecretText').value = j.secret;
    g('totpConfirmCode').value = '';
    g('totpSetupMsg').textContent = '';
    g('totpSetupBox').style.display = '';
  };
  const totpCancelBtn = g('totpCancelBtn');
  if (totpCancelBtn) totpCancelBtn.onclick = () => { g('totpSetupBox').style.display = 'none'; };
  const totpConfirmBtn = g('totpConfirmBtn');
  if (totpConfirmBtn) totpConfirmBtn.onclick = async () => {
    const code = g('totpConfirmCode').value.trim();
    if (!code){ g('totpSetupMsg').textContent = 'Enter the code from your app.'; return; }
    const r = await api('/api/2fa/totp/confirm', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ code }) });
    if (r && r.ok){ toast('✓ AUTHENTICATOR ENABLED'); g('totpSetupBox').style.display = 'none'; load2faStatus(); }
    else if (r){ const d = await r.json().catch(()=>({})); g('totpSetupMsg').textContent = d.error || 'Invalid code'; }
  };
  const totpDisableBtn = g('totpDisableBtn');
  if (totpDisableBtn) totpDisableBtn.onclick = async () => {
    if (!confirm('Disable the authenticator app for your account?')) return;
    const r = await api('/api/2fa/totp/disable', { method:'POST' });
    if (r && r.ok){ toast('✓ DISABLED'); load2faStatus(); }
  };
  const emailOtpEnableBtn = g('emailOtpEnableBtn');
  if (emailOtpEnableBtn) emailOtpEnableBtn.onclick = async () => {
    const r = await api('/api/2fa/email-otp/enable', { method:'POST' });
    const d = r ? await r.json().catch(()=>({})) : {};
    if (r && r.ok){
      g('emailOtpConfirmCode').value = '';
      g('emailOtpSetupMsg').textContent = 'Code sent to ' + (d.sent_to || 'your email') + '.';
      g('emailOtpSetupBox').style.display = '';
    } else { toast('✕ ' + (d.error || 'failed')); }
  };
  const emailOtpCancelBtn = g('emailOtpCancelBtn');
  if (emailOtpCancelBtn) emailOtpCancelBtn.onclick = () => { g('emailOtpSetupBox').style.display = 'none'; };
  const emailOtpConfirmBtn = g('emailOtpConfirmBtn');
  if (emailOtpConfirmBtn) emailOtpConfirmBtn.onclick = async () => {
    const code = g('emailOtpConfirmCode').value.trim();
    if (!code){ g('emailOtpSetupMsg').textContent = 'Enter the code we emailed you.'; return; }
    const r = await api('/api/2fa/email-otp/confirm', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ code }) });
    if (r && r.ok){ toast('✓ EMAIL CODES ENABLED'); g('emailOtpSetupBox').style.display = 'none'; load2faStatus(); }
    else if (r){ const d = await r.json().catch(()=>({})); g('emailOtpSetupMsg').textContent = d.error || 'Invalid code'; }
  };
  const emailOtpDisableBtn = g('emailOtpDisableBtn');
  if (emailOtpDisableBtn) emailOtpDisableBtn.onclick = async () => {
    if (!confirm('Disable email sign-in codes for your account?')) return;
    const r = await api('/api/2fa/email-otp/disable', { method:'POST' });
    if (r && r.ok){ toast('✓ DISABLED'); load2faStatus(); }
  };
}

/* ---------- USER SETTINGS PAGE (system-wide) ---------- */
async function loadUserSettings(){
  const s = await api_json('/api/settings');
  const g = id => document.getElementById(id);
  const setSel = (el, v, fb) => {
    if (!el) return;
    const val = String(v == null || v === '' ? fb : v);
    const has = Array.prototype.some.call(el.options, o => o.value === val);
    if (!has){ const o = document.createElement('option'); o.value = val; o.textContent = val; el.appendChild(o); }
    el.value = val;
    if (el.selectedIndex < 0) el.value = fb;
  };
  setSel(g('uLang'), s.language, 'en');
  setSel(g('uCur'), s.currency, 'AED');
  setSel(g('uRegion'), s.region, 'UAE');
  if (g('uNew')) g('uNew').checked = (s.notify_new != 0);
  if (g('uDel')) g('uDel').checked = (s.notify_delete != 0);
  if (g('uMatrix')) g('uMatrix').checked = (s.matrix_on != 0);
  // DB + LDAP config fields
  if (g('db_host')) g('db_host').value = s.db_host || '127.0.0.1';
  if (g('db_port')) g('db_port').value = s.db_port || 3306;
  if (g('db_name')) g('db_name').value = s.db_name || 'itguy_assets';
  if (g('db_user')) g('db_user').value = s.db_user || 'itguy';
  if (g('db_pass')) g('db_pass').value = '';
  if (g('ldap_server')) g('ldap_server').value = s.ldap_server || '';
  if (g('ldap_domain')) g('ldap_domain').value = s.ldap_domain || '';
  if (g('ldap_bind_user')) g('ldap_bind_user').value = s.ldap_bind_user || '';
  if (g('ldap_bind_pass')) g('ldap_bind_pass').value = '';
  if (g('ldap_base_dn')) g('ldap_base_dn').value = s.ldap_base_dn || '';
  // UniFi Controller fields
  if (g('unifi_enabled')) g('unifi_enabled').checked = !!s.unifi_enabled;
  if (g('unifi_host')) g('unifi_host').value = s.unifi_host || '';
  if (g('unifi_port')) g('unifi_port').value = s.unifi_port || 443;
  if (g('unifi_site')) g('unifi_site').value = s.unifi_site || 'default';
  if (g('unifi_user')) g('unifi_user').value = s.unifi_user || '';
  if (g('unifi_pass')) g('unifi_pass').value = '';
  if (g('unifi_is_os')) g('unifi_is_os').checked = (s.unifi_is_os == null ? true : !!s.unifi_is_os);
  if (g('unifi_verify_ssl')) g('unifi_verify_ssl').checked = !!s.unifi_verify_ssl;
  // SLA policy fields
  if (g('sla_low')) g('sla_low').value = s.sla_low || 72;
  if (g('sla_normal')) g('sla_normal').value = s.sla_normal || 24;
  if (g('sla_high')) g('sla_high').value = s.sla_high || 8;
  if (g('sla_urgent')) g('sla_urgent').value = s.sla_urgent || 4;
  if (g('sla_breach_notify')) g('sla_breach_notify').checked = (s.sla_breach_notify != 0);
  if (g('auto_assign_roundrobin')) g('auto_assign_roundrobin').checked = (s.auto_assign_roundrobin != 0);
  // Notification toggles
  if (g('notify_on_create')) g('notify_on_create').checked = (s.notify_on_create != 0);
  if (g('notify_on_resolve')) g('notify_on_resolve').checked = (s.notify_on_resolve != 0);
  if (g('notify_on_reply')) g('notify_on_reply').checked = (s.notify_on_reply != 0);

  const page = document.getElementById('page-usettings');
  if (page.dataset._wired) return;
  const mx = g('uMatrix');
  if (mx) mx.onchange = () => { matrixOn = mx.checked; };
  wireUpdateCheck();
  const sv = g('saveUsetBtn');
  if (sv) sv.onclick = async () => {
    const body = {
      language: g('uLang').value, currency: g('uCur').value, region: g('uRegion').value,
      db_host: g('db_host').value.trim(), db_port: g('db_port').value || 3306,
      db_name: g('db_name').value.trim(), db_user: g('db_user').value.trim(),
      ldap_server: g('ldap_server').value.trim(), ldap_domain: g('ldap_domain').value.trim(),
      ldap_bind_user: g('ldap_bind_user').value.trim(), ldap_base_dn: g('ldap_base_dn').value.trim()
    };
    if (g('db_pass').value) body.db_pass = g('db_pass').value;
    if (g('ldap_bind_pass').value) body.ldap_bind_pass = g('ldap_bind_pass').value;
    const r = await api('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    if (r && r.ok){ CURRENCY = body.currency; applyLanguage(body.language); toast('✓ SAVED — DB config applied'); if(typeof renderAssets==='function')renderAssets(); if(document.getElementById('ctBody'))loadContracts(); }
    else if (r){ const j = await r.json().catch(() => ({})); toast('✕ ' + (j.error || 'save failed')); }
  };
  const dt = g('dbTestBtn');
  if (dt) dt.onclick = async () => {
    const m = g('dbTestMsg'); m.textContent = 'testing…';
    const body = {db_host:g('db_host').value.trim(), db_port:g('db_port').value||3306,
        db_name:g('db_name').value.trim(), db_user:g('db_user').value.trim()};
    if (g('db_pass').value) body.db_pass = g('db_pass').value;
    const r = await api('/api/test-db', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body)});
    const j = r ? await r.json().catch(()=>({})) : {};
    m.textContent = (j.ok? '✓ ' : '✕ ') + (j.msg||''); m.style.color = j.ok? 'var(--grn)':'var(--red)';
  };
  const lt = g('ldapTestBtn2');
  if (lt) lt.onclick = async () => {
    const m = g('ldapTestMsg2'); m.textContent = 'testing…';
    const r = await api('/api/test-ldap', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ldap_server:g('ldap_server').value.trim(), ldap_domain:g('ldap_domain').value.trim(),
        ldap_bind_user:g('ldap_bind_user').value.trim(), ldap_bind_pass:g('ldap_bind_pass').value,
        ldap_base_dn:g('ldap_base_dn').value.trim()})});
    const j = r ? await r.json().catch(()=>({})) : {};
    m.textContent = (j.ok? '✓ ' : '✕ ') + (j.msg||''); m.style.color = j.ok? 'var(--grn)':'var(--red)';
  };
  const ls = g('ldapSyncBtn2');
  if (ls) ls.onclick = async () => {
  const m = g('ldapTestMsg2'); m.textContent = 'syncing…';
  const r = await api('/api/employees/ldap-sync', {method:'POST'});
  const j = r ? await r.json().catch(()=>({})) : {};
  m.textContent = (r&&r.ok? '✓ ' : '✕ ') + (j.msg||j.error||''); m.style.color = (r&&r.ok)? 'var(--grn)':'var(--red)';
  if(r&&r.ok) loadEmployees();
  };
  // System Config sub-nav: toggle section panels
  const nav = document.getElementById('cfgNav');
  applySettingsPermissions();
  if (nav) {
  nav.querySelectorAll('.cfgitem').forEach(btn => {
    btn.onclick = () => {
      nav.querySelectorAll('.cfgitem').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const sec = btn.dataset.sec;
      document.querySelectorAll('.cfg-sec').forEach(s => s.style.display = (s.dataset.sec === sec) ? 'block' : 'none');
    };
  });
  }
  // Users table: load + add user
  const addUserBtn = g('cfgAddUser');
  if (addUserBtn) addUserBtn.onclick = () => {
  if(typeof addUser === 'function') addUser();
  else {
    toast('✕ User management not available yet');
  }
  };
  // Custom roles were only reachable from the legacy Profile -> Users modal,
  // so per-module access looked like it didn't exist from Settings -> Users
  // (which is where you'd go looking for it). Same modal, surfaced here too.
  const rolesBtn = g('cfgManageRoles');
  if (rolesBtn) rolesBtn.onclick = () => {
    if (typeof loadRolesModal === 'function') loadRolesModal();
    else toast('✕ Role management not available yet');
  };
  // System users table — login accounts from the Users table (NOT the employee directory)
  window.loadCfgUsers = async function(){
    const body = document.getElementById('cfgUsersBody');
    if (!body) return;
    try {
      const r = await api('/api/users');
      if (!r) return;
      const list = await r.json();
      const tfaLabel = u => { const m=[]; if(u.totp_enabled)m.push('Authenticator'); if(u.email_otp_enabled)m.push('Email'); return m.length?m.join(' + '):'—'; };
      body.innerHTML = (list || []).map(u => `<tr>`
        + `<td>${esc(u.username||'')}</td>`
        + `<td>${esc(ROLE_LABELS[u.role] || u.role || '')}</td>`
        + `<td>${esc(u.display||'')}</td>`
        + `<td>${esc(u.email||'')}</td>`
        + `<td>${esc(tfaLabel(u))}</td>`
        + `<td class="row-actions"><button class="btn sm ghost" onclick="editUser('${esc(u.username)}')">Edit</button>`
        + ((u.totp_enabled||u.email_otp_enabled)?`<button class="btn sm ghost" onclick="adminReset2fa('${esc(u.username)}')">Reset 2FA</button>`:'')
        + `<button class="btn sm danger" onclick="delUser('${esc(u.username)}')">Delete</button></td>`
        + `</tr>`).join('')
        || '<tr><td colspan="6" class="empty">No system users yet.</td></tr>';
    } catch(e) {}
  };
  loadCfgUsers();
  window.adminReset2fa = async function(un){
    if (!confirm(`Reset 2FA for "${un}"? They will be able to sign in with just their password again.`)) return;
    const r = await api(`/api/users/${encodeURIComponent(un)}/2fa/disable`, { method:'POST' });
    if (r && r.ok){ toast('✓ 2FA RESET'); loadCfgUsers(); }
    else if (r){ const j = await r.json().catch(()=>({})); toast('✕ ' + (j.error || 'failed')); }
  };
  // SMTP test + save (Notifications section)
  const st = g('smtpTestBtn');
  if (st) st.onclick = async () => {
  const m = g('smtpTestMsg'); m.textContent = 'testing…';
  const r = await api('/api/settings/smtp-test', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      smtp_host: g('s_host').value.trim(),
      smtp_port: parseInt(g('s_port').value||'587', 10),
      smtp_user: g('s_user').value.trim(),
      smtp_pass: g('s_pass').value,
      smtp_from: g('s_from').value.trim()
    })
  });
  const j = r ? await r.json().catch(()=>({})) : {};
  m.textContent = (j.ok? '✓ ' : '✕ ') + (j.msg||''); m.style.color = j.ok? 'var(--grn)':'var(--red)';
  };
  const sn = g('saveNotifBtn');
  if (sn) sn.onclick = async () => {
  const body = {
    smtp_host: g('s_host').value.trim(),
    smtp_port: parseInt(g('s_port').value||'587', 10),
    smtp_user: g('s_user').value.trim(),
    smtp_pass: g('s_pass').value,
    smtp_from: g('s_from').value.trim(),
    notify_on_create: g('notify_on_create').checked,
    notify_on_resolve: g('notify_on_resolve').checked,
    notify_on_reply: g('notify_on_reply').checked,
    notify_new: g('uNew').checked ? 1 : 0,
    notify_delete: g('uDel').checked ? 1 : 0
  };
  const r = await api('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (r && r.ok){ toast('✓ NOTIFICATIONS SAVED'); }
  else if (r){ const j = await r.json().catch(()=>({})); toast('✕ ' + (j.error || 'save failed')); }
  };
  // DB save button (Database section)
  const sd = g('saveDbBtn');
  if (sd) sd.onclick = async () => {
  const body = {
    db_host: g('db_host').value.trim(), db_port: g('db_port').value || 3306,
    db_name: g('db_name').value.trim(), db_user: g('db_user').value.trim()
  };
  if (g('db_pass').value) body.db_pass = g('db_pass').value;
  const r = await api('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (r && r.ok){ toast('✓ DATABASE SAVED — config will apply to new connections'); }
  else if (r){ const j = await r.json().catch(()=>({})); toast('✕ ' + (j.error || 'save failed')); }
  };
  // LDAP save button (LDAP section)
  const sl = g('saveLdapBtn');
  if (sl) sl.onclick = async () => {
  const body = {
    ldap_server: g('ldap_server').value.trim(), ldap_domain: g('ldap_domain').value.trim(),
    ldap_bind_user: g('ldap_bind_user').value.trim(), ldap_base_dn: g('ldap_base_dn').value.trim()
  };
  if (g('ldap_bind_pass').value) body.ldap_bind_pass = g('ldap_bind_pass').value;
  const r = await api('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (r && r.ok){ toast('✓ LDAP SAVED'); }
  else if (r){ const j = await r.json().catch(()=>({})); toast('✕ ' + (j.error || 'save failed')); }
  };
  // UniFi test + save (UniFi Controller section)
  const ut = g('unifiTestBtn');
  if (ut) ut.onclick = async () => {
  const m = g('unifiTestMsg'); m.textContent = 'testing…';
  const body = {
    unifi_host: g('unifi_host').value.trim(), unifi_port: parseInt(g('unifi_port').value||'443', 10),
    unifi_site: g('unifi_site').value.trim(), unifi_user: g('unifi_user').value.trim(),
    unifi_is_os: g('unifi_is_os').checked, unifi_verify_ssl: g('unifi_verify_ssl').checked
  };
  if (g('unifi_pass').value) body.unifi_pass = g('unifi_pass').value;
  const r = await api('/api/test-unifi', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const j = r ? await r.json().catch(()=>({})) : {};
  m.textContent = (j.ok? '✓ ' : '✕ ') + (j.msg||''); m.style.color = j.ok? 'var(--grn)':'var(--red)';
  };
  const su = g('saveUnifiBtn');
  if (su) su.onclick = async () => {
  const body = {
    unifi_enabled: g('unifi_enabled').checked,
    unifi_host: g('unifi_host').value.trim(), unifi_port: parseInt(g('unifi_port').value||'443', 10),
    unifi_site: g('unifi_site').value.trim(), unifi_user: g('unifi_user').value.trim(),
    unifi_is_os: g('unifi_is_os').checked, unifi_verify_ssl: g('unifi_verify_ssl').checked
  };
  if (g('unifi_pass').value) body.unifi_pass = g('unifi_pass').value;
  const r = await api('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (r && r.ok){ toast('✓ INTEGRATIONS SAVED'); loadUnifiWidgets(true); }
  else if (r){ const j = await r.json().catch(()=>({})); toast('✕ ' + (j.error || 'save failed')); }
  };
  // Asset Label save button
  const slb = g('saveLabelBtn');
  if (slb) slb.onclick = saveLabel;
  // SLA policy save button
  const slsa = g('saveSlaBtn');
  if (slsa) slsa.onclick = async () => {
  const body = {
    sla_low: parseInt(g('sla_low').value||'72', 10),
    sla_normal: parseInt(g('sla_normal').value||'24', 10),
    sla_high: parseInt(g('sla_high').value||'8', 10),
    sla_urgent: parseInt(g('sla_urgent').value||'4', 10),
    sla_breach_notify: g('sla_breach_notify').checked,
    auto_assign_roundrobin: g('auto_assign_roundrobin').checked
  };
  const r = await api('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (r && r.ok){ toast('✓ SLA SETTINGS SAVED'); }
  else if (r){ const j = await r.json().catch(()=>({})); toast('✕ ' + (j.error || 'save failed')); }
  };
  page.dataset._wired = '1';
}
window.loadUserSettings = loadUserSettings;

/* ---------- Danger Zone: factory reset ---------- */
(function(){
  const openBtn=document.getElementById('openWipeBtn');
  const modal=document.getElementById('wipeModal');
  const pwEl=document.getElementById('wipePassword');
  const confirmEl=document.getElementById('wipeConfirmText');
  const goBtn=document.getElementById('wipeConfirmBtn');
  const cancelBtn=document.getElementById('wipeCancelBtn');
  const errEl=document.getElementById('wipeErr');
  if(!openBtn||!modal)return;
  function resetForm(){
    pwEl.value=''; confirmEl.value=''; errEl.textContent=''; goBtn.disabled=true;
  }
  function checkReady(){
    goBtn.disabled=!(pwEl.value && confirmEl.value.trim().toUpperCase()==='WIPE EVERYTHING');
  }
  openBtn.onclick=()=>{ resetForm(); modal.classList.add('show'); pwEl.focus(); };
  cancelBtn.onclick=()=>{ modal.classList.remove('show'); };
  pwEl.addEventListener('input',checkReady);
  confirmEl.addEventListener('input',checkReady);
  goBtn.onclick=async()=>{
    errEl.textContent='';
    goBtn.disabled=true; const label=goBtn.textContent; goBtn.textContent='WIPING…';
    try{
      const r=await api('/api/admin/wipe',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({password:pwEl.value,confirm:confirmEl.value.trim()})});
      const j=r?await r.json().catch(()=>({})):{};
      if(r&&r.ok){
        toast('💀 EVERYTHING WIPED — backup: '+(j.backup_file||''));
        modal.classList.remove('show');
        // the schema and every account are gone, so there's nothing to
        // reload into -- go straight to the first-run wizard
        setTimeout(()=>{ window.location.href = j.setup_required ? '/setup' : '/'; }, 1400);
      }else{
        errEl.textContent=j.error||'Wipe failed.';
        goBtn.disabled=false;
      }
    }catch(e){
      errEl.textContent='Cannot reach the server.';
      goBtn.disabled=false;
    }finally{
      goBtn.textContent=label;
    }
  };
})();
