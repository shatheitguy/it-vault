const APP_VERSION='20260828c';
const COLUMNS=['Name','Type','Serial','MacAddress','Location','Status','Manufacturer','Model','ReceivedBy','NotesReceived','Note','PurchaseDate','WarrantyMonths','Price','EmployeeID'];
const LABELS={'ReceivedBy':'Received By','NotesReceived':'Receiver Date','Note':'Note','WarrantyMonths':'Warranty','EmployeeID':'Employee ID','Type':'Item Category','Price':'Price','MacAddress':'MAC Address'};

// --- currency: stored base = AED; display converts via rate and shows symbol ---
const MONEY={AED:{s:'﷼',r:1},USD:{s:'$',r:0.272},EUR:{s:'€',r:0.25},INR:{s:'₹',r:22.7}};
let CURRENCY='AED';
function fmtMoney(v,cur){
  cur=cur||CURRENCY; const m=MONEY[cur]||MONEY.AED;
  const num=parseFloat(v||0)*m.r;
  return m.s+' '+num.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
}

// --- i18n: applied to [data-i18n] elements + document.dir for ar ---
const I18N={
  en:{Home:'Home',Assets:'Assets',AddAsset:'Add Asset',ImportExcel:'Import Excel',ExportExcel:'Export Excel',AuditLog:'Audit Log',Tickets:'Tickets',Contracts:'Contracts',Locations:'Locations',Trash:'Trash',Customization:'Customization',NetworkScan:'Network Scan',BackupRestore:'Backup / Restore',Settings:'Settings',System:'System',Employees:'Employees',Save:'Save',Add:'Add',Edit:'Edit',Delete:'Delete',Search:'Search',Dashboard:'IT Guy - The Assets Manager'},
  ar:{Home:'الرئيسية',Assets:'الأصول',AddAsset:'إضافة أصل',ImportExcel:'استيراد إكسل',ExportExcel:'تصدير إكسل',AuditLog:'سجل التدقيق',Tickets:'التذاكر',Contracts:'العقود',Locations:'المواقع',Trash:'السلة',Customization:'التخصيص',NetworkScan:'فحص الشبكة',BackupRestore:'النسخ الاحتياطي',Settings:'الإعدادات',System:'النظام',Employees:'الموظفون',Save:'حفظ',Add:'إضافة',Edit:'تعديل',Delete:'حذف',Search:'بحث',Dashboard:'IT Guy // مصفوفة الأصول'},
  ta:{Home:'முகப்பு',Assets:'சொத்துகள்',AddAsset:'சொத்து சேர்',ImportExcel:'எக்செல் இறக்குமதி',ExportExcel:'எக்செல் ஏற்றுமதி',AuditLog:'தணிக்கை பதிவு',Tickets:'டிக்கெட்டுகள்',Contracts:'ஒப்பந்தங்கள்',Locations:'இடங்கள்',Trash:'குப்பை',Customization:'தனிப்பயனாக்கம்',NetworkScan:'பிணைய ஸ்கேன்',BackupRestore:'காப்புப்பு',Settings:'அமைப்புகள்',System:'கணினி',Employees:'ஊழியர்கள்',Save:'சேமி',Add:'சேர்',Edit:'திருத்து',Delete:'நீக்கு',Search:'தேடல்',Dashboard:'IT Guy // சொத்து மேட்ரிக்ஸ்'},
  fr:{Home:'Accueil',Assets:'Actifs',AddAsset:'Ajouter',ImportExcel:'Importer Excel',ExportExcel:'Exporter Excel',AuditLog:'Journal',Tickets:'Tickets',Contracts:'Contrats',Locations:'Emplacements',Trash:'Corbeille',Customization:'Personnalisation',NetworkScan:'Scan réseau',BackupRestore:'Sauvegarde',Settings:'Paramètres',System:'Système',Employees:'Employés',Save:'Enregistrer',Add:'Ajouter',Edit:'Modifier',Delete:'Supprimer',Search:'Rechercher',Dashboard:'IT Guy // Matrice'}
};
// ---- column visibility (persisted) ----
// First-ever visit (nothing saved yet): show a concise, uncluttered default instead of
// every column — full detail is one click away via the Columns picker.
// Guard: if the stored value is invalid, fall back to ALL columns (full details).
// An empty array (e.g. from an old "NONE" click) must never blank the table.
const DEFAULT_VISIBLE_COLS=['Name','Type','Serial','Location','Status'];
let VISIBLE_COLS = (()=>{
  try{
    const s=localStorage.getItem('nexus_cols');
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
  try{ localStorage.setItem('nexus_cols', JSON.stringify(visCols())); }catch(e){}
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
const STATUSES=['New','Active','In Use','Available','Checked-Out','Under-Maintenance','Storage','Worn','Retired','Out of Service'];
const LABEL_FIELD_KEYS=['Name','Type','AssetID','Serial','Status','Location','ReceivedBy','ReceiverDate','EmployeeID','Department','Warranty','PurchaseDate','Note'];
const ROLE_ADMIN='admin', ROLE_EDIT='read-write', ROLE_VIEW='read-only';
const ROLE_LABELS={'admin':'Admin','read-write':'Editor','read-only':'Read-only'};
const TICKET_STATUSES=['Open','In Progress','Pending','Resolved','Closed'];
const PRIORITIES=['Low','Normal','High','Urgent','Emergency'];
const TICKET_CATEGORIES=['Hardware','Software','Network','Access/Permissions','Email/Communication','Printer','CCTV/Security','Other'];
let assets=[],sortCol='',sortDir=1,groupBy='',expTimer=null,MY_ROLE=ROLE_VIEW;

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
function statusClass(s){s=(s||'').toLowerCase();return s==='active'?'s-active':s==='storage'?'s-storage':s==='retired'?'s-retired':'s-default';}
function toast(m){const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),1800);}
async function api(u,opt){const r=await fetch(u,opt);if(r.status===401){location.href='/';return null;}return r;}
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
function printSelected(){
  const ids=[...document.querySelectorAll('.row-chk:checked')].map(cb=>cb.dataset.id);
  if(!ids.length){toast('No assets selected');return;}
  const rows=ids.map(id=>assets.find(a=>a._id===id)).filter(Boolean);
  const win=window.open('','_blank');
  win.document.write(`<html><head><title>Print Assets</title><style>
    body{font-family:Arial,sans-serif;padding:20px}
    table{width:100%;border-collapse:collapse;margin-top:20px}
    th,td{text-align:left;padding:6px;border-bottom:1px solid #ddd}
  </style></head><body><h2>Selected Assets</h2><table><thead><tr>${COLUMNS.map(c=>`<th>${LABELS[c]||c}</th>`).join('')}</tr></thead><tbody>${rows.map(a=>`<tr>${COLUMNS.map(c=>`<td>${esc(a[c])}</td>`).join('')}</tr>`).join('')}</tbody></table></body></html>`);
  win.document.close(); win.print();
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
    body{font-family:Arial,sans-serif;padding:20px}
    h2{margin-bottom:4px}
    .sub{color:#666;margin-bottom:14px;font-size:13px}
    table{width:100%;border-collapse:collapse;margin-top:10px}
    th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #ddd;font-size:13px}
    th{background:#f3f3f3}
    @media print{body{padding:0}button{display:none}}
  </style></head><body><h2>Asset Group: ${esc(LABELS[groupBy]||groupBy)} — ${esc(k)}</h2><div class="sub">${rows.length} asset${rows.length>1?'s':''} • generated ${new Date().toLocaleString()}</div><table><thead><tr>${COLUMNS.map(c=>`<th>${LABELS[c]||c}</th>`).join('')}</tr></thead><tbody>${rows.map(a=>`<tr>${COLUMNS.map(c=>`<td>${esc(a[c])}</td>`).join('')}</tr>`).join('')}</tbody></table><button onclick="window.print()">🖨 PRINT</button></body></html>`);
  win.document.close(); win.print();
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
function openEmpModal(id){
  editingEmpId=id; const e=(id?employees.find(x=>x._id===id):{})||{};
  document.getElementById('empModalTitle').textContent=id?'EDIT EMPLOYEE':'ADD EMPLOYEE';
  const empIdEl=document.getElementById('e_EmpCode');
  empIdEl.value=e.EmpCode||'';
  empIdEl.placeholder=id?('auto: '+tempEmpId(e)):'auto-generated if left blank';
  document.getElementById('e_EmployeeID').value=e.EmployeeID||'';
  document.getElementById('e_EmployeeName').value=e.EmployeeName||'';
  document.getElementById('e_Department').value=e.Department||'';
  document.getElementById('e_Designation').value=e.Designation||'';
  document.getElementById('e_Email').value=e.Email||'';
  document.getElementById('empModal').classList.add('show');
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
const DEBUG = (location.search.indexOf('debug=1')>=0) || (localStorage.getItem('nexus_debug')==='1');
if(location.search.indexOf('debug=1')>=0){ try{ localStorage.setItem('nexus_debug','1'); }catch(e){} }
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
  const checkoutItem=a&&a.Status==='Checked-Out'
    ?`<button onclick="closeRowMenu();checkinAsset('${id}')">CHECK-IN</button>`
    :`<button onclick="closeRowMenu();openCheckout('${id}')">CHECKOUT</button>`;
  menu.innerHTML=`
    <button onclick="closeRowMenu();editRow('${id}')">EDIT</button>
    ${checkoutItem}
    <button onclick="closeRowMenu();openSign('${id}')">SIGN</button>
    <button onclick="closeRowMenu();openMaint('${id}')">MAINT</button>
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
      if(c==='Status'){
        const col=a.Status==='Available'?'var(--grn)':a.Status==='Checked-Out'?'var(--cyan)':a.Status==='Under-Maintenance'?'var(--amber)':a.Status==='Storage'?'var(--muted)':'var(--red)';
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
        return `<td><span class="mono">${esc(a[c]||'')}</span></td>`;
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
  applyDashLayout();
  // widget bodies (recent assets / open tickets / activity) must refresh too --
  // previously these only reloaded when you navigated to the page
  loadDashboardPage();
}
function statusColor(s){
  return ({'Available':'var(--grn)','Checked-Out':'var(--cyan)','Under-Maintenance':'var(--amber)','Storage':'var(--muted)','Retired':'var(--red)'})[s]||'var(--accent2)';
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
}
const DASH_LAYOUT_KEY='nexus_dash_layout_v1';
function getDashLayout(){ try{ const v=localStorage.getItem(DASH_LAYOUT_KEY); return v?JSON.parse(v):null; }catch(e){ return null; } }
function applyDashLayout(){
  const order=getDashLayout(); if(!order||!order.length) return;
  const cont=document.getElementById('dashWidgets'); if(!cont) return;
  order.forEach(k=>{ const el=cont.querySelector('.widget[data-wkey="'+k+'"]'); if(el) cont.appendChild(el); });
}
function saveDashLayout(){ const cont=document.getElementById('dashWidgets'); if(!cont) return [];
  return [...cont.querySelectorAll('.widget')].map(w=>w.getAttribute('data-wkey')); }
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
  document.getElementById('dashSaveLayout').style.display=on?'':'none';
  document.getElementById('dashResetLayout').style.display=on?'':'none';
  document.getElementById('dashEditLayout').style.display=on?'none':'';
  document.getElementById('dashLayoutMsg').textContent=on?'Drag widgets to any position, then SAVE':'';
  if(on) initDashDrag();
  else { const cont=document.getElementById('dashWidgets'); if(cont) cont.querySelectorAll('.widget').forEach(w=>w.draggable=false); }
}

/* ---------- modal / crud ---------- */
let editingId=null;
async function openModal(id,prefill){
  editingId=id;const a=id?assets.find(x=>x._id===id):(prefill||{});
  document.getElementById('modalTitle').textContent=id?'Edit asset':'Add asset';
  const inv=a&&a.InvoiceFile?a.InvoiceFile:'';
  const renderField=c=>{
    const val=a?a[c]||'':'';
    if(c==='Status')return`<div class="field2"><label>${c}</label><select id="f_${c}">${STATUSES.map(o=>`<option ${o===val?'selected':''}>${o}</option>`).join('')}</select></div>`;
    if(c==='EmployeeID')return`<div class="field2"><label>${LABELS[c]||c}</label><select id="f_EmployeeID"><option value="">-- select employee --</option></select></div>`;
    if(c==='NotesReceived')return`<div class="field2"><label>${LABELS[c]||c}</label><input id="f_${c}" type="date" value="${esc(val)}"></div>`;
    if(c==='Price')return`<div class="field2"><label>${LABELS[c]||c} (${CURRENCY})</label><input id="f_${c}" type="number" step="0.01" min="0" value="${esc(val)}"></div>`;
    return`<div class="field2"><label>${LABELS[c]||c}</label><input id="f_${c}" value="${esc(val)}"></div>`;
  };
  const groups=[
    {label:'IDENTITY',cols:['Name','Type','Serial','MacAddress','Location']},
    {label:'STATUS &amp; ASSIGNMENT',cols:['Status','ReceivedBy','NotesReceived','EmployeeID']},
    {label:'PURCHASE &amp; WARRANTY',cols:['PurchaseDate','WarrantyMonths','Price']},
  ];
  document.getElementById('formFields').innerHTML=
    groups.map(g=>`<div class="invbox">
      <label>${g.label}</label>
      <div class="grid2">${g.cols.map(renderField).join('')}</div>
    </div>`).join('')+
    `<div class="invbox refbox">
       <label>MANUFACTURER &amp; MODEL <a class="mlink" onclick="openRef()">manage ↗</a></label>
       <div class="ref2">
         <div><select id="f_Manufacturer"><option value="">-- choose manufacturer --</option></select></div>
         <div><select id="f_Model"><option value="">-- choose model --</option></select></div>
       </div>
     </div>`+
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
  document.getElementById('modal').classList.add('show');
  if(document.getElementById('f_EmployeeID')){fetchEmployees();}
  // populate Manufacturer / Model dropdowns from reference tables
  await loadMfrModelOptions(a?a.Manufacturer||'':'', a?a.Model||'':'');
  if(id)loadAssetHistory(id);
}

// populate Manufacturer + Model <select> dropdowns from backend reference data
async function loadMfrModelOptions(selMfr, selModel){
  try{
    const mf=await api('/api/manufacturers'); const mfrs=mf?await mf.json():[];
    const sel=document.getElementById('f_Manufacturer'); if(!sel)return;
    sel.innerHTML='<option value="">-- choose manufacturer --</option>'+mfrs.map(m=>`<option value="${esc(m.name)}" ${m.name===selMfr?'selected':''}>${esc(m.name)}</option>`).join('')+'<option value="__new">＋ type new…</option>';
    sel.onchange=async()=>{
      if(sel.value==='__new'){const v=prompt('New manufacturer name:'); if(v&&v.trim()){const r=await api('/api/manufacturers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:v.trim()})}); if(r&&r.ok){await loadMfrModelOptions(v.trim(),'');}} else {sel.value=selMfr;}}
      else { await loadModelOptions('', sel.value); }
    };
    await loadModelOptions(selModel, sel.value);
  }catch(e){}
}
async function loadModelOptions(selModel, mfr){
  const sel=document.getElementById('f_Model'); if(!sel)return;
  let opts='<option value="">-- choose model --</option>';
  try{
    const md=await api('/api/models'); const models=md?await md.json():[];
    const filtered = mfr ? models.filter(m=>m.manufacturer===mfr) : models;
    opts+=filtered.map(m=>`<option value="${esc(m.name)}" ${m.name===selModel?'selected':''}>${esc(m.name)}</option>`).join('')+'<option value="__new">＋ type new…</option>';
  }catch(e){}
  sel.innerHTML=opts;
  sel.onchange=async()=>{
    if(sel.value==='__new'){const v=prompt('New model name:'); if(v&&v.trim()){const r=await api('/api/models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:v.trim(),manufacturer:mfr||undefined})}); if(r&&r.ok){await loadModelOptions(v.trim(), mfr);}} else {sel.value=selModel;}}
  };
}
async function loadAssetHistory(id){
  const box=document.getElementById('histBox'); if(!box)return;
  const r=await api('/api/assets/'+id+'/history'); if(!r)return; const h=await r.json();
  box.innerHTML = h.length? h.map(e=>`<div class="hist"><span class="hfield">${esc(e.field)}</span> <span class="hold">${esc(e.old_val||'—')}</span> → <span class="hnew">${esc(e.new_val||'—')}</span> <span class="hmeta">${esc(e.user)} · ${esc(e.ts)}</span></div>`).join('') : '<div class="muted">No history yet.</div>';
}
async function fetchEmployees(){
  const r=await api('/api/employees');
  const list=r?await r.json():[];
  const sel=document.getElementById('f_EmployeeID');
  if(!sel)return;
  sel.innerHTML='<option value="">-- select employee --</option>'+(list||[]).map(e=>`<option value="${esc(e.EmployeeID)}">${esc(e.EmployeeName||e.EmployeeID)}</option>`).join('');
}

async function delInvoice(id){
  if(!confirm('Remove invoice file?'))return;
  const r=await api('/api/assets/'+id+'/invoice',{method:'DELETE'});
  if(r&&r.ok){toast('✕ INVOICE REMOVED');openModal(id);}else if(r){const j=await r.json();toast('✕ '+(j.error||'failed'));}
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
    }else if(r){const j=await r.json();toast('✕ '+(j.error||'failed'));}
  }
}
function closeModal(){document.getElementById('modal').classList.remove('show');editingId=null;}

/* ---------- checkout / checkin / maint / qr ---------- */
async function doCheckout(){
  const user=document.getElementById('coUser').value;
  const expected=document.getElementById('coExpected').value;
  const note=document.getElementById('coNote').value.trim();
  if(!user){toast('Select user');return;}
  const r=await api('/api/assets/'+coAsset+'/checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:user,expected,note})});
  if(r&&r.ok){document.getElementById('checkoutModal').classList.remove('show');toast('✓ CHECKED OUT');load();loadDashboard();}else if(r){const j=await r.json();toast('✕ '+(j.error||'failed'));}
}
async function checkinAsset(id){
  if(!confirm('CHECK IN this asset?'))return;
  const r=await api('/api/assets/'+id+'/checkin',{method:'POST'});
  if(r&&r.ok){toast('✓ CHECKED IN');load();loadDashboard();}else if(r){const j=await r.json();toast('✕ '+(j.error||'failed'));}
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
  if(r&&r.ok){toast('✓ LOGGED');openMaint(maintAsset);load();loadDashboard();}else if(r){const j=await r.json();toast('✕ '+(j.error||'failed'));}
}
async function delMaint(mid){
  if(!mid)return;
  const r=await api('/api/assets/'+maintAsset+'/maintenance?id='+mid,{method:'DELETE'});
  if(r&&r.ok){toast('✓ REMOVED');openMaint(maintAsset);}else if(r){const j=await r.json();toast('✕ '+(j.error||'failed'));}
}
function openQR(id){window.open('/label/'+id,'_blank');}
async function printAsset(id){
  const w=window.open('','_blank');
  if(!w){toast('✕ Popup blocked — allow popups for this site');return;}
  const r=await api('/api/assets/'+id); if(!r){w.close();return;} const a=await r.json();
  if(a.error){w.close();toast('✕ '+a.error);return;}
  const fields=[...visCols(),'Price','WarrantyMonths','NotesReceived','Notes','ReceivedBy','EmployeeName','EmployeeID','Designation','Department','Email'];
  const seen=new Set(); const rowsHtml=fields.filter(f=>!seen.has(f)&&seen.add(f)).map(f=>{
    let v=a[f]; if(f==='Price')v=fmtMoney(a.Price||0,CURRENCY); if(v==null||v==='')v='—';
    return `<tr><td class="k">${esc(LABELS[f]||f)}</td><td class="v">${esc(v)}</td></tr>`;
  }).join('');
  const sig=a.SignatureData?`<div class="sig-block"><div class="sig-title">SIGNATURE / ACKNOWLEDGEMENT</div><img src="${a.SignatureData}" style="max-width:340px;max-height:160px;border:1px solid #ccc;border-radius:6px;background:#fff"/></div>`:`<div class="sig-block muted">Not signed yet</div>`;
  w.document.write(`<!doctype html><html><head><title>Asset — ${esc(a.Name||'')}</title>
  <style>@page{margin:14mm}body{font-family:'Segoe UI',Arial,sans-serif;color:#111;padding:0;margin:0}
  .card{border:1px solid #222;border-radius:8px;max-width:720px;margin:0 auto;overflow:hidden}
  .hd{background:#101622;color:#fff;padding:12px 16px;font-family:'Segoe UI',Arial,sans-serif;font-weight:600;letter-spacing:.2px;display:flex;justify-content:space-between;align-items:center}
  .hd .id{font-size:11px;opacity:.7} .bd{padding:14px 16px} table{width:100%;border-collapse:collapse} td.k{width:38%;padding:5px 8px;color:#555;font-weight:600;border-bottom:1px solid #eee;vertical-align:top} td.v{padding:5px 8px;border-bottom:1px solid #eee;word-break:break-word}
  .sig-block{margin-top:14px;padding:10px;border:1px dashed #999;border-radius:6px} .sig-title{font-weight:700;margin-bottom:6px;font-size:12px;letter-spacing:.5px} .muted{color:#999;font-style:italic}
  @media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact}.card{border-color:#222}}</style></head>
  <body><div class="card"><div class="hd"><span>${(window.APP_NAME||'Sha The IT Guy')} — Asset record</span><span class="id">${esc(a._id||'')}</span></div>
  <div class="bd"><table>${rowsHtml}</table>${sig}</div></div>
  <script>setTimeout(()=>{window.print();},250);<\/script></body></html>`);
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
let lastScan=[];
/* A cleared scan list must STAY cleared -- opening the panel used to silently
   re-read the ARP table and repopulate it. The flag is remembered so the list
   also stays empty across a page reload, until you press Scan again. */
const SCAN_CLEARED_KEY='nexus_scan_cleared';
function scanIsCleared(){ try{ return localStorage.getItem(SCAN_CLEARED_KEY)==='1'; }catch(e){ return false; } }
function setScanCleared(v){ try{ if(v) localStorage.setItem(SCAN_CLEARED_KEY,'1'); else localStorage.removeItem(SCAN_CLEARED_KEY); }catch(e){} }
function renderScanCleared(){
  document.getElementById('scanBody').innerHTML='<tr><td colspan=5 style="color:var(--muted)">List cleared — press Scan to discover devices again.</td></tr>';
}
async function openScan(){
  document.getElementById('scanStatus').textContent='';
  document.getElementById('scanModal').classList.add('show');
  if(scanIsCleared()){ lastScan=[]; renderScanCleared(); return; }
  document.getElementById('scanBody').innerHTML='';
  const r=await api('/api/scan'); lastScan=r?await r.json():[];
  renderScan(lastScan);
}
async function doScan(){
  setScanCleared(false);
  const prefix=document.getElementById('scanPrefix').value.trim();
  const deep=document.getElementById('scanDeep').checked;
  if(deep && !prefix){toast('✕ enter subnet prefix');return;}
  document.getElementById('scanStatus').textContent= deep?'Scanning /24 (this can take ~30s)…':'Reading ARP table…';
  const qs=(prefix?('?prefix='+encodeURIComponent(prefix)):'')+(deep?'&deep=1':'');
  const r=await api('/api/scan'+qs); lastScan=r?await r.json():[];
  renderScan(lastScan);
}
function renderScan(devs){
  const nodes=devs.map((d,i)=>`<tr><td>${esc(d.ip||'')}</td><td>${esc(d.host||'')||'<span class="muted">—</span>'}</td><td>${esc(d.mac||d.hw||'')}</td><td>${esc(d.type||'LAN')}</td><td><button class="btn sm ghost" onclick="addScannedAsAsset('${i}')">Add as asset</button></td></tr>`).join('');
  document.getElementById('scanBody').innerHTML=nodes||'<tr><td colspan=5 style="color:var(--muted)">No devices found on the local network.</td></tr>';
}
function clearScan(){
  lastScan=[];
  setScanCleared(true);
  renderScanCleared();
  document.getElementById('scanStatus').textContent='';
}
async function cleanRescan(){
  // wipe current results, then re-run scan with current options
  lastScan=[];
  document.getElementById('scanBody').innerHTML='<tr><td colspan=5 style="color:var(--muted)">Clearing…</td></tr>';
  await doScan();
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
    Location:'LAN',
    Status:'Available',
    Note:'Discovered via network scan ('+(dev.ip||'')+(dev.mac?', '+dev.mac:'')+')'
  });
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
  document.getElementById('bkList').innerHTML=rows.map(x=>`<tr><td class="mono">${esc(x.file)}</td><td>${esc(x.scope)}</td><td>${esc(x.created||'')}</td><td class="mono">${fmtBytes(x.size)}</td><td><div class="row-actions">
      <button class="btn sm ghost" onclick="window.open('/api/backups/${encodeURIComponent(x.file)}/download','_blank')">⬇ DOWNLOAD</button>
      <button class="btn sm danger" onclick="delBackup('${esc(x.file)}')">DEL</button>
    </div></td></tr>`).join('')||'<tr><td colspan=5 style="color:var(--muted)">none</td></tr>';
  document.getElementById('backupModal').classList.add('show');
}
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
  if(!file){toast('Select a .sql backup');return;}
  const fd=new FormData();fd.append('file',file);
  const r=await api('/api/restore',{method:'POST',body:fd});
  if(r&&r.ok){toast('✓ RESTORED');load();loadDashboard();}else if(r){const j=await r.json();toast('✕ '+(j.error||'failed'));}
}

/* ---------- signature ---------- */
async function openSign(id){
  const r=await api('/api/assets/'+id+'/sign/link');
  const j=r?await r.json():{};
  if(!j.ok){toast('✕ '+(j.error||'failed'));return;}
  const url=j.url;
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(url).then(()=>toast('✓ LINK COPIED')).catch(()=>showSignLink(url));
  }else{showSignLink(url);}
}
function showSignLink(url){
  document.getElementById('signUrl').value=url;
  document.getElementById('signModal').classList.add('show');
}

/* ---------- users ---------- */
let editingUser=null;
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
  document.getElementById('u_username').readOnly=true;
  document.getElementById('userModalTitle').textContent='Edit user';
  // minimal prefetch
  api('/api/users').then(r=>r.json()).then(list=>{const u=list.find(x=>x.username===un)||{};document.getElementById('u_username').value=u.username||un;document.getElementById('u_display').value=u.display||'';document.getElementById('u_email').value=u.email||'';document.getElementById('u_role').value=u.role||'read-only';document.getElementById('u_password').value='';document.getElementById('usersModal').classList.remove('show');document.getElementById('userModal').classList.add('show');});
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
    if(document.getElementById('usersModal').classList.contains('show'))openUsers();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}
async function addUser(){
  editingUser=null;
  document.getElementById('usersModal').classList.remove('show');
  document.getElementById('u_username').readOnly=false;
  document.getElementById('userModalTitle').textContent='Add user';
  document.getElementById('u_username').value='';
  document.getElementById('u_display').value='';
  document.getElementById('u_email').value='';
  document.getElementById('u_role').value='read-only';
  document.getElementById('u_password').value='';
  document.getElementById('userModal').classList.add('show');
}
async function delUser(un){
  if(!confirm('DELETE USER?'))return;
  const r=await api('/api/users/'+encodeURIComponent(un),{method:'DELETE'});
  if(r&&r.ok){toast('✓ User deleted');if(window.loadCfgUsers)loadCfgUsers();if(document.getElementById('usersModal').classList.contains('show'))openUsers();}else if(r){const j=await r.json();toast('✕ '+(j.error||'failed'));}
}

async function delRow(id){
  if(!confirm('DELETE this asset permanently?'))return;
  const r=await api('/api/assets/'+id,{method:'DELETE'});
  if(r&&r.ok){toast('✕ ASSET DELETED');load();loadDashboard();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}

/* ---------- settings / profile ---------- */
async function loadSettings(){
  // /api/settings is admin-only — a read-only/read-write user gets {error:...} back here,
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
    document.getElementById('b_name').value=s.app_name||'Sha The IT Guy';
    document.getElementById('b_logoText').value=s.logo_text||'Sha';
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
  else if(r){const j=await r.json();toast('✕ '+(j.error||'failed'));}
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
  else if(r){const j=await r.json();toast('✕ '+(j.error||'failed'));}
}
async function saveProfile(){
  const body={display:document.getElementById('pDisplay').value.trim(),email:document.getElementById('p_email').value.trim()};
  const r=await api('/api/profile',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r&&r.ok){toast('✓ PROFILE SAVED');}
  else if(r){const j=await r.json();toast('✕ '+(j.error||'failed'));}
}
async function saveBrand(){
  const fd=new FormData();fd.append('app_name',document.getElementById('b_name').value.trim());fd.append('logo_text',document.getElementById('b_logoText').value.trim());
  const logo=document.getElementById('b_logo').files[0]; if(logo)fd.append('logo',logo);
  const r=await api('/api/settings',{method:'PUT',body:fd});
  if(r&&r.ok){toast('✓ BRAND SAVED');document.getElementById('b_logo').value='';applyBranding();}
  else if(r){const j=await r.json();toast('✕ '+(j.error||'failed'));}
}
async function removeLogo(){
  if(!confirm('Remove the current logo? This cannot be undone.'))return;
  const fd=new FormData();fd.append('app_name',document.getElementById('b_name').value.trim());fd.append('logo_text',document.getElementById('b_logoText').value.trim());fd.append('remove_logo','1');
  const r=await api('/api/settings',{method:'PUT',body:fd});
  if(r&&r.ok){toast('✓ LOGO REMOVED');document.getElementById('b_logo').value='';applyBranding();}
  else if(r){const j=await r.json();toast('✕ '+(j.error||'failed'));}
}
async function applyBranding(){
  const me=await fetch('/api/me').then(r=>r.json());
  const nm=me.app_name||me.display||'Sha The IT Guy';
  window.APP_NAME=nm;
  document.getElementById('sideName').textContent=nm;
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
  const st=document.getElementById('sideName'); if(st) st.textContent=nm;
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
  else if(r){const j=await r.json();toast('✕ '+(j.error||'failed'));}
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
document.getElementById('addUserBtn').onclick=addUser;
document.getElementById('userSave').onclick=saveUser;
{const _uc=document.getElementById('userCancel'); if(_uc)_uc.onclick=()=>{document.getElementById('userModal').classList.remove('show');openUsers();};}
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
document.getElementById('openRefBtn').onclick=openRef;
document.getElementById('navAudit').onclick=openAudit;
document.getElementById('auditSearch').oninput=renderAuditRows;
document.getElementById('auditClearBtn').onclick=clearAuditLog;
document.getElementById('navScan').onclick=openScan;
document.getElementById('scanBtn').onclick=doScan;
document.getElementById('navBackup').onclick=openBackup;
document.getElementById('bkDownload').onclick=doBackup;
document.getElementById('bkFile').onchange=doRestore;
document.getElementById('trashRestoreSelBtn').onclick=restoreSelectedTrash;
document.getElementById('trashDelSelBtn').onclick=deleteSelectedTrash;
document.getElementById('trashEmptyBtn').onclick=emptyTrash;
document.getElementById('addEmpBtn').onclick=()=>openEmpModal('');
document.getElementById('importLdapBtn').onclick=openLdapImport;
document.getElementById('empSearch').oninput=loadEmployees;
document.getElementById('empCancel').onclick=()=>document.getElementById('empModal').classList.remove('show');
document.getElementById('empSave').onclick=saveEmployee;
const _ldapSyncBtn=document.getElementById('ldapSyncBtn'); if(_ldapSyncBtn)_ldapSyncBtn.onclick=syncLdap;
document.getElementById('navTrash').onclick=()=>showPage('page-trash');
document.getElementById('navTrash').style.display=MY_ROLE!==ROLE_VIEW?'':'none';
document.getElementById('navTickets').onclick=()=>showPage('page-tickets');
document.getElementById('newTicketBtn').onclick=openNewTicket;
document.getElementById('tkFormCancel').onclick=()=>document.getElementById('tkFormModal').classList.remove('show');
document.getElementById('tkFormSave').onclick=saveNewTicket;
document.getElementById('tkSearch').oninput=loadTickets;
document.getElementById('tkStatus').onchange=loadTickets;
document.getElementById('tkReplyBtn').onclick=sendReply;
document.getElementById('tkAssignBtn').onclick=async()=>{
  if(!curTicketId)return;
  const a=document.getElementById('tkAssignee').value;
  const m=document.getElementById('tkAssignMsg'); m.textContent='saving…';
  const r=await api('/api/tickets/'+curTicketId,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({assignee:a})});
  if(r&&r.ok){ m.textContent='✓ assigned'+(a?' → '+a:''); m.style.color='var(--grn)'; openTicket(curTicketId); await loadTickets(); toast('✓ ASSIGNED'+(a?' to '+a:'')); }
  else { m.textContent='✕ failed'; m.style.color='var(--red)'; }
};
document.getElementById('openMonitorBtn').onclick=()=>window.open('/monitor','_blank');
document.getElementById('sharePortalBtn').onclick=async()=>{
  const r=await api('/api/portal/link'); if(!r){toast('✕ error');return;} const j=await r.json();
  try{ await navigator.clipboard.writeText(j.url); toast('🔗 LINK COPIED: '+j.url); }
  catch(e){ window.prompt('Copy portal link:', j.url); }
};
document.getElementById('tkModalClose').onclick=()=>document.getElementById('tkModal').classList.remove('show');
document.getElementById('navContracts').onclick=()=>showPage('page-contracts');
document.getElementById('navContracts').style.display=MY_ROLE!==ROLE_VIEW?'':'none';
document.getElementById('newContractBtn').onclick=newContract;
document.getElementById('navLocations').onclick=()=>showPage('page-locations');
document.getElementById('navLocations').style.display=MY_ROLE!==ROLE_VIEW?'':'none';
document.getElementById('newLocBtn').onclick=addLoc;
document.getElementById('refClose').onclick=()=>document.getElementById('refModal').classList.remove('show');
document.getElementById('mfrList').onchange=e=>loadModels(e.target.value);
document.getElementById('mfrAdd').onclick=async()=>{const n=document.getElementById('mfrInput').value.trim();if(!n)return;const r=await api('/api/manufacturers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n})});if(r&&r.ok){document.getElementById('mfrInput').value='';loadRef();}};
document.getElementById('modAdd').onclick=async()=>{const mi=document.getElementById('mfrList').value;const n=document.getElementById('modInput').value.trim();if(!mi||!n)return;const r=await api('/api/models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n,manufacturer_id:mi})});if(r&&r.ok){document.getElementById('modInput').value='';loadModels(mi);}};
document.getElementById('ldapCancel').onclick=()=>document.getElementById('ldapModal').classList.remove('show');
document.getElementById('coSave').onclick=doCheckout;
window.loadCfgUsers=window.loadCfgUsers||function(){};window.editRow=openModal;window.delRow=delRow;window.editUser=editUser;window.delUser=delUser;window.delInvoice=delInvoice;
window.openSign=openSign;window.openCheckout=(id)=>{coAsset=id;Promise.all([api('/api/users'),api('/api/employees')]).then(async ([ru,re])=>{const us=ru?await ru.json():[];const emps=re?await re.json():[];const opts=us.map(u=>`<option value="${u.username}">${u.display||u.username} (user)</option>`).concat(emps.map(e=>`<option value="${e.EmployeeID}">${e.EmployeeName||e.EmployeeID} (${e.EmployeeID})</option>`));const sel=document.getElementById('coUser');sel.innerHTML=opts.join('');document.getElementById('checkoutModal').classList.add('show');});};
window.checkinAsset=checkinAsset;window.openMaint=openMaint;window.openQR=openQR;window.doCheckout=doCheckout;window.addMaint=addMaint;window.delMaint=delMaint;
window.openAudit=openAudit;window.openScan=openScan;window.doScan=doScan;window.addScannedAsAsset=addScannedAsAsset;
window.openBackup=openBackup;window.doBackup=doBackup;window.doRestore=doRestore;window.delBackup=delBackup;
window.openEmpModal=openEmpModal;window.openLdapImport=openLdapImport;

function showPage(id){
  const PAGES=['page-dashboard','page-assets','page-employees','page-trash','page-tickets','page-contracts','page-locations','page-usettings','page-scan','page-audit','page-import','page-export'];
  PAGES.forEach(p=>{const el=document.getElementById(p);if(el)el.style.display=(p===id?'block':'none');});
  document.querySelectorAll('.nav a').forEach(a=>a.classList.remove('active'));
  const map={  'page-dashboard':'navHome','page-employees':'navEmployees','page-trash':'navTrash','page-tickets':'navTickets',
    'page-contracts':'navContracts','page-locations':'navLocations',
    'page-usettings':'navSettings','page-scan':'navScan',
    'page-audit':'navAudit','page-import':'navImport','page-export':'navExport','page-assets':'navAssets'};
  const n=map[id]?document.getElementById(map[id]):null;
  if(n)n.classList.add('active');
  if(id==='page-dashboard'){ loadDashboard(); }   // loadDashboard() chains loadDashboardPage() + applyDashLayout()
  else if(id==='page-assets'){ load(); loadStats(); }
  else if(id==='page-employees')loadEmployees();
  else if(id==='page-trash')loadTrash();
  else if(id==='page-tickets')loadTickets();
  else if(id==='page-contracts')loadContracts();
  else if(id==='page-locations')loadLocations();
  else if(id==='page-usettings'){loadUserSettings();loadSettings();loadCustom();}
  else if(id==='page-scan')openScan();
  else if(id==='page-audit')openAudit();
}
window.showPage=showPage;

async function loadTrash(){
  const r=await api('/api/assets/trash'); if(!r)return; const list=await r.json();
  const tb=document.getElementById('trashBody');
  tb.innerHTML=list.map(a=>`<tr><td><input type="checkbox" class="trash-chk" data-id="${a._id}" onchange="updateTrashSelBtns()"/></td><td>${esc(a.Name||'')}</td><td>${esc(a.Type||'')}</td><td class="mono">${esc(a.Serial||'')}</td><td>${esc(a.Status||'')}</td><td><div class="row-actions"><button class="btn sm" onclick="restoreAsset('${a._id}')">♻ RESTORE</button><button class="btn sm danger" onclick="permaDeleteAsset('${a._id}')">DEL</button></div></td></tr>`).join('');
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

// Reference data: Manufacturers / Models
async function openRef(){
  document.getElementById('refModal').classList.add('show');
  await loadRef();
}
async function loadRef(){
  const r=await api('/api/manufacturers'); const mfrs=r?await r.json():[];
  const ml=document.getElementById('mfrList'); ml.innerHTML=mfrs.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('')||'<option disabled>none</option>';
  if(mfrs.length)loadModels(mfrs[0].id);
}
async function loadModels(mfrId){
  const r=await api('/api/models'); const all=r?await r.json():[];
  const list=all.filter(m=>String(m.manufacturer_id)===String(mfrId));
  const ml=document.getElementById('modList'); ml.innerHTML=list.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('')||'<option disabled>none yet</option>';
}
window.openRef=openRef;

// ---------- Tickets (osTicket-style) ----------
let _usersCache=null;
async function getUsersCached(){
  if(_usersCache) return _usersCache;
  // /api/users is admin-only; read-write/read-only users get a 403 {error:...} body here,
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
  const t=d.ticket, reps=d.replies||[];
  document.getElementById('tkModalTitle').textContent=t.code+' · '+t.subject;
  // populate assignee select from Users
  try{
    const users=await getUsersCached();
    const sel=document.getElementById('tkAssignee');
    sel.innerHTML='<option value="">— Unassigned —</option>'+users.map(u=>`<option ${u.username===t.assignee?'selected':''}>${esc(u.username)}</option>`).join('');
  }catch(e){}
  document.getElementById('tkDetail').innerHTML=`
    <div class="tkmeta">
      <div><b>Priority:</b> <span class="prio ${t.priority}">${esc(t.priority)}</span></div>
      <div><b>Status:</b> ${esc(t.status)}</div>
      <div><b>Category:</b> ${esc(t.category||'—')}</div>
      <div><b>Requester:</b> ${esc(t.requester||'—')} ${t.requester_email?('('+esc(t.requester_email)+')'):''}</div>
      <div><b>Assignee:</b> ${esc(t.assignee||'—')}</div>
      <div><b>Source:</b> ${esc(t.source||'Web')}</div>
      <div><b>Asset:</b> ${esc(t.asset_id||'—')}</div>
      <div><b>Due:</b> ${esc(t.due_date||'—')} <b>SLA:</b> ${t.sla_hours}h</div>
    </div>
    <div class="tkdesc">${esc(t.description||'')}</div>
    <div class="tkreplies">${reps.map(rp=>`<div class="rep ${rp.author_role}"><div class="repmeta"><b>${esc(rp.author)}</b> · ${esc(rp.author_role)} · ${esc(rp.created_at)}</div><div>${esc(rp.body)}</div></div>`).join('')||'<div class="muted">No replies yet.</div>'}</div>
    <div class="tkactions">
      <label>Status <select id="tkStatusUpd">${TICKET_STATUSES.map(s=>`<option ${s===t.status?'selected':''}>${s}</option>`).join('')}</select></label>
      <label>Priority <select id="tkPrioUpd">${PRIORITIES.map(s=>`<option ${s===t.priority?'selected':''}>${s}</option>`).join('')}</select></label>
    </div>`;
  document.getElementById('tkModal').classList.add('show');
}
window.openTicketById=(id)=>openTicket(id);
async function sendReply(){
  if(!curTicketId)return;
  const body=document.getElementById('tkReply').value.trim(); if(!body){toast('✕ empty');return;}
  const r=await api('/api/tickets/'+curTicketId+'/reply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({body})});
  const su=document.getElementById('tkStatusUpd').value, pr=document.getElementById('tkPrioUpd').value;
  await api('/api/tickets/'+curTicketId,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:su,priority:pr})});
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
async function saveNewTicket(){
  const subject=document.getElementById('t_subject').value.trim();
  if(!subject){toast('✕ subject required');return;}
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
  const r=await api('/api/tickets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r&&r.ok){document.getElementById('tkFormModal').classList.remove('show');toast('✓ TICKET CREATED');loadTickets();}
  else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}
window.openNewTicket=openNewTicket;
window.openTicket=openTicket;

// ---------- Contracts (GLPI) ----------
async function loadContracts(){
  const r=await api('/api/contracts'); if(!r)return; const list=await r.json();
  const tb=document.getElementById('ctBody');
  tb.innerHTML=list.map(c=>`<tr><td>${esc(c.name)}</td><td>${esc(c.vendor||'—')}</td><td>${esc(c.type||'—')}</td><td>${esc(c.start_date||'—')}</td><td>${esc(c.end_date||'—')}</td><td class="mono">${fmtMoney(c.cost||0, CURRENCY)}</td><td class="mono">${esc(c.asset_id||'—')}</td></tr>`).join('');
  document.getElementById('ctEmpty').style.display=list.length?'none':'block';
}
async function newContract(){
  const name=prompt('Contract name:'); if(!name)return;
  const vendor=prompt('Vendor:')||''; const type=prompt('Type (Warranty/Support/Lease):')||'';
  const start=prompt('Start date (YYYY-MM-DD):')||''; const end=prompt('End date (YYYY-MM-DD):')||'';
  const cost=prompt('Cost:')||0; const asset=prompt('Linked Asset ID (optional):')||'';
  const r=await api('/api/contracts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,vendor,type,start_date:start,end_date:end,cost:parseFloat(cost)||0,asset_id:asset})});
  if(r&&r.ok){toast('✓ CONTRACT ADDED');loadContracts();}else if(r){const j=await r.json().catch(()=>({}));toast('✕ '+(j.error||'failed'));}
}
// ---------- Locations (GLPI) ----------
async function loadLocations(){
  const r=await api('/api/locations'); if(!r)return; const list=await r.json();
  const ul=document.getElementById('locList');
  ul.innerHTML=list.map(l=>`<li>${esc(l.name)} <button class="btn sm danger" onclick="delLoc(${l.id})">✕</button></li>`).join('')||'<li class="muted">No locations yet.</li>';
}
async function addLoc(){
  const n=document.getElementById('locInput').value.trim(); if(!n)return;
  const r=await api('/api/locations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n})});
  if(r&&r.ok){document.getElementById('locInput').value='';loadLocations();}
}
window.delLoc=async(id)=>{const r=await api('/api/locations',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});if(r&&r.ok)loadLocations();};

window.loadTickets=loadTickets;window.openNewTicket=openNewTicket;window.sendReply=sendReply;
window.loadContracts=loadContracts;window.newContract=newContract;
window.loadLocations=loadLocations;window.addLoc=addLoc;


document.getElementById('navEmployees').onclick=()=>showPage('page-employees');
document.getElementById('navTrash').onclick=()=>showPage('page-trash');
document.getElementById('navTickets').onclick=()=>showPage('page-tickets');
document.getElementById('navContracts').onclick=()=>showPage('page-contracts');
document.getElementById('navLocations').onclick=()=>showPage('page-locations');
document.getElementById('logoutBtn').onclick=async()=>{ try{ await api('/api/logout',{method:'POST'}); }catch(e){} location.href='/'; };
document.getElementById('navSettings').onclick=()=>showPage('page-usettings');
document.getElementById('navBackup').onclick=()=>openBackup();
const ni3=document.getElementById('navImport'); if(ni3) ni3.onclick=()=>showPage('page-import');
const ne=document.getElementById('navExport'); if(ne) ne.onclick=()=>window.location='/api/export';
const na2=document.getElementById('navAdd'); if(na2) na2.onclick=()=>openModal();
document.getElementById('navHome').onclick=()=>showPage('page-dashboard');
document.getElementById('dashEditLayout').onclick=()=>setEditLayout(true);
document.getElementById('dashSaveLayout').onclick=()=>{ const o=saveDashLayout(); try{ localStorage.setItem(DASH_LAYOUT_KEY, JSON.stringify(o)); }catch(e){} setEditLayout(false); document.getElementById('dashLayoutMsg').textContent='✓ Layout saved'; };
document.getElementById('dashResetLayout').onclick=()=>{ try{ localStorage.removeItem(DASH_LAYOUT_KEY); }catch(e){} document.getElementById('dashLayoutMsg').textContent='↺ Reset to default'; location.reload(); };
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

// Self-heal: clear any stale/corrupt nexus_* localStorage from older builds so an
// old empty-column or bad-layout selection can't blank the UI for returning users.
(function healStorage(){
  try{
    const KEEP=new Set(['nexus_dash_layout_v1','nexus_cols','nexus_sess','nexus_scan_cleared']);
    const bad=[];
    for(let i=localStorage.length-1;i>=0;i--){
      const k=localStorage.key(i);
      if(k && k.indexOf('nexus_')===0 && !KEEP.has(k)) bad.push(k);
    }
    bad.forEach(k=>localStorage.removeItem(k));
    // also repair nexus_cols if it's empty/invalid
    try{
      const c=localStorage.getItem('nexus_cols');
      if(c){ const v=JSON.parse(c); if(!Array.isArray(v)||v.length===0) localStorage.removeItem('nexus_cols'); }
    }catch(e){ localStorage.removeItem('nexus_cols'); }
    if(bad.length) console.log('[ITGUY] healed stale storage keys:', bad);
  }catch(e){}
})();

(async()=>{
 try{
  const me=await fetch('/api/me').then(r=>r.json());
  if(!me.user){location.href='/'+(location.search||'');return;}
  MY_ROLE=me.role;
  window.sessionUser=me.user;
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
    navEmployees: me.role===ROLE_ADMIN || me.role===ROLE_EDIT,
    navTrash: me.role===ROLE_ADMIN || me.role===ROLE_EDIT,
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
      m.addEventListener('click',e=>{ if(e.target===m) m.classList.remove('show'); });
      new MutationObserver(mo=>{
        if(m.classList.contains('show')) bringToFront(m);
      }).observe(m,{attributes:true,attributeFilter:['class']});
      m.dataset._wired='1';
    }
  });
}
function bringToFront(m){
  // keep explicitly-stacked modals (profile/users/ref) above the generic base
  const fixed={usersModal:210, refModal:220};
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
  deepdark:   { label:'Deep Dark',   bg_type:'solid', bg:'#0a0d13', comp_bg:'#121826', accent:'#ff3b30', accent2:'#c0392b', radius:12, font:'Inter',           theme:'dark'  },
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
  const baseHex = isGrad ? bgA : hex6(bgRaw, '#0a0d13');
  const theme = isLightHex(baseHex) ? 'light' : 'dark';
  return {
    theme_preset: String(s.theme_preset || 'deepdark'),
    theme: theme,
    bg_type: isGrad ? 'gradient' : 'solid',
    bg: hex6(isGrad ? bgA : bgRaw, '#0a0d13'),
    bgA: bgA, bgB: bgB,
    comp_bg: hex6(s.comp_bg, '#121826'),
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
  // /api/settings is admin-only: a read-only/read-write user gets back {error:"forbidden"},
  // not a settings object. Applying that would reset everyone's live theme to hardcoded
  // defaults just from opening Settings — bail out instead and leave the theme untouched.
  if(s.error || s.bg===undefined){ dbg('loadCustom: not a settings object (likely forbidden) — leaving theme untouched'); showCustomError('Only admins can view or change appearance settings.'); return; }
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
}
window.loadProfile = loadProfile;

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
  const sv = g('saveUsetBtn');
  if (sv) sv.onclick = async () => {
    const body = {
      language: g('uLang').value, currency: g('uCur').value, region: g('uRegion').value,
      notify_new: g('uNew').checked ? 1 : 0, notify_delete: g('uDel').checked ? 1 : 0,
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
  // System users table — login accounts from the Users table (NOT the employee directory)
  window.loadCfgUsers = async function(){
    const body = document.getElementById('cfgUsersBody');
    if (!body) return;
    try {
      const r = await api('/api/users');
      if (!r) return;
      const list = await r.json();
      body.innerHTML = (list || []).map(u => `<tr>`
        + `<td>${esc(u.username||'')}</td>`
        + `<td>${esc(ROLE_LABELS[u.role] || u.role || '')}</td>`
        + `<td>${esc(u.display||'')}</td>`
        + `<td>${esc(u.email||'')}</td>`
        + `<td class="row-actions"><button class="btn sm ghost" onclick="editUser('${esc(u.username)}')">Edit</button>`
        + `<button class="btn sm danger" onclick="delUser('${esc(u.username)}')">Delete</button></td>`
        + `</tr>`).join('')
        || '<tr><td colspan="5" class="empty">No system users yet.</td></tr>';
    } catch(e) {}
  };
  loadCfgUsers();
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
    notify_on_reply: g('notify_on_reply').checked
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
