/* Departments ("spaces"), the extra fields an item category asks for,
   preventive maintenance, and the department switcher.

   IT-Vault is no longer only for IT: Facilities, Fleet, Furniture... each is
   a department with its own asset ID prefix (IT-1001, FM-1001), categories,
   fields and staff. Everything here talks to the endpoints in app.py:
   /api/spaces, /api/fields, /api/assets/<id>/plans, /api/maint/due. */
(function () {
  const $ = id => document.getElementById(id);
  const h = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const J = body => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const say = (m, ok = true) => window.toast && toast((ok ? '✓ ' : '✕ ') + m);
  const errOf = async r => { try { return (await r.json()).error || ('HTTP ' + r.status); } catch (e) { return 'HTTP ' + r.status; } };
  const isAdmin = () => (window.MY_ROLE || (window.ME && ME.role)) === 'admin';

  window.SPACES = [];
  let cur = '';
  try { cur = localStorage.getItem('itv_space') || ''; } catch (e) {}
  window.currentSpace = () => cur;
  window.spaceQuery = sep => cur ? `${sep}space=${encodeURIComponent(cur)}` : '';
  const spaceById = id => (window.SPACES || []).find(s => String(s.id) === String(id));
  window.spaceNameOf = a => { const s = spaceById(a.SpaceID || 1); return s ? s.name : 'IT'; };
  // "Department" in the list's grouping menu, beside the others
  function addGroupOption() {
    const gb = $('groupBy'); if (!gb || gb.querySelector('option[value="SpaceName"]')) return;
    if (window.SPACES.length < 2) return;
    const o = document.createElement('option'); o.value = 'SpaceName'; o.textContent = 'Department';
    gb.insertBefore(o, gb.options[1] || null);
    if (window.LABELS) LABELS.SpaceName = 'Department';
  }

  // ---------------------------------------------------------------- switcher
  async function loadSpaces() {
    try { const r = await fetch('/api/spaces'); if (!r.ok) return; window.SPACES = await r.json(); } catch (e) { return; }
    if (cur && !spaceById(cur)) { cur = ''; try { localStorage.removeItem('itv_space'); } catch (e) {} }
    drawSwitcher(); addGroupOption();
  }
  window.loadSpaces = loadSpaces;

  /* Departments as tabs at the top of Assets (and the dashboard): All, then
     each department this account may see. Someone limited to one department
     gets no tabs at all -- they only ever see theirs. */
  function drawSwitcher() {
    const old = $('spaceSwitch'); if (old) old.remove();
    const hosts = document.querySelectorAll('[data-space-tabs]');
    const many = window.SPACES.length > 1;
    hosts.forEach(host => {
      host.style.display = many ? '' : 'none';
      if (!many) { host.innerHTML = ''; return; }
      const total = window.SPACES.reduce((n, s) => n + (s.assets || 0), 0);
      // asset counts mean nothing on the ticket desk, so that strip goes without
      const counts = host.dataset.spaceTabs !== 'tickets';
      const n = v => counts ? `<span class="sp-n">${v}</span>` : '';
      host.innerHTML = `<button type="button" data-id="" class="${!cur ? 'on' : ''}"><span class="sp-dot all"></span>All${n(total)}</button>`
        + window.SPACES.map(s => `<button type="button" data-id="${s.id}" class="${String(s.id) === cur ? 'on' : ''}"><span class="sp-dot" style="background:${h(s.color || 'var(--accent)')}"></span>${h(s.name)}${n(s.assets)}</button>`).join('');
      host.onclick = e => {
        const b = e.target.closest('[data-id]'); if (!b) return;
        cur = b.dataset.id; try { localStorage.setItem('itv_space', cur); } catch (e) {}
        drawSwitcher();
        try { if (typeof load === 'function') load(); } catch (e) {}
        try { if (typeof loadStats === 'function') loadStats(); } catch (e) {}
        try { if ($('page-tickets') && $('page-tickets').style.display !== 'none' && typeof loadTickets === 'function') loadTickets(); } catch (e) {}
        try { if ($('page-dashboard') && $('page-dashboard').style.display !== 'none' && typeof loadDashboard === 'function') loadDashboard(); } catch (e) {}
        if ($('maintPanel') && $('maintPanel').style.display !== 'none') loadMaintPage();
        updateMaintCount();
      };
    });
  }

  // ---------------------------------------------------------------- asset form
  let formAsset = null, formId = null, extraVals = {};
  window.formSpace = () => ($('f_SpaceID') && $('f_SpaceID').value) || (formAsset && formAsset.SpaceID) || cur || (window.SPACES[0] && window.SPACES[0].id) || 1;

  window.renderSpaceBits = function (id, a) {
    formId = id; formAsset = a || {}; extraVals = Object.assign({}, (a && a.Extra) || {});
    const ff = $('formFields'); if (!ff) return;
    // department picker, at the top of the form
    // only departments this account edits are offered; one it only views
    // still shows (ticked, locked) so the form says where the asset lives
    const editable = window.SPACES.filter(s => s.can_edit !== false);
    const home = formAsset.SpaceID ? spaceById(formAsset.SpaceID) : null;
    const viewOnly = !!(home && home.can_edit === false);
    if (viewOnly) {
      const note = document.createElement('div'); note.className = 'sp-viewonly';
      note.textContent = 'View only: you are a viewer in ' + home.name + ', so changes here will not be saved.';
      ff.insertBefore(note, ff.firstChild);
    }
    if (window.SPACES.length > 1) {
      const pickFrom = viewOnly ? [home].concat(editable.filter(s => s.id !== home.id)) : editable;
      const curOk = cur && editable.some(s => String(s.id) === String(cur)) ? cur : '';
      const sid = String(formAsset.SpaceID || curOk || (editable[0] || window.SPACES[0]).id);
      const box = document.createElement('div'); box.className = 'invbox spacebox';
      box.innerHTML = `<label>DEPARTMENT</label>
        <div class="sp-pick">${pickFrom.map(s => `<label class="sp-chip"><input type="radio" name="f_space" value="${s.id}" ${String(s.id) === sid ? 'checked' : ''} ${viewOnly ? 'disabled' : ''}><span><i class="sp-dot" style="background:${h(s.color || 'var(--accent)')}"></i>${h(s.name)} <em>${h(s.prefix)}</em></span></label>`).join('')}</div>
        <input type="hidden" id="f_SpaceID" value="${h(sid)}">`;
      ff.insertBefore(box, ff.firstChild);
      box.querySelectorAll('input[name=f_space]').forEach(r => r.onchange = async () => {
        $('f_SpaceID').value = r.value;
        window.applyHiddenFields(Number(r.value));
        // the category list follows the department
        if (typeof loadCategoryOptions === 'function') { const ty = $('f_Type'); await loadCategoryOptions(ty ? ty.value : ''); }
        if (!id) {   // a new asset takes the next ID of the department it goes into
          const t = $('f_AssetTag'); const res = await fetch('/api/assets/next-tag?space=' + r.value);
          if (t && res.ok) t.value = (await res.json()).tag || t.value;
        }
        drawExtra();
      });
    }
    // the extra fields this kind of asset has
    const xb = document.createElement('div'); xb.className = 'invbox extrabox'; xb.id = 'extraBox';
    const ref = $('assetPhotoBox') || ff.querySelector('.refbox');
    ref && ref.parentNode ? ref.parentNode.insertBefore(xb, ref) : ff.appendChild(xb);
    const type = $('f_Type'); if (type) type.addEventListener('change', drawExtra);
    drawExtra();
    // the category list fills in a moment later; draw again once it has
    setTimeout(() => { if ($('extraBox') && $('f_Type') && $('f_Type').value && $('f_Type').value !== (formAsset.Type || '')) drawExtra(); }, 900);
    // preventive maintenance, for an asset that exists
    if (id) {
      const mb = document.createElement('div'); mb.className = 'invbox planbox'; mb.id = 'planBox';
      const after = $('assetPhotoBox');
      after && after.nextSibling ? after.parentNode.insertBefore(mb, after.nextSibling) : ff.appendChild(mb);
      drawPlans();
    }
  };

  async function drawExtra() {
    const xb = $('extraBox'); if (!xb) return;
    // keep what was typed before redrawing for another category
    xb.querySelectorAll('[data-xk]').forEach(el => { extraVals[el.dataset.xk] = el.type === 'checkbox' ? (el.checked ? '1' : '') : el.value; });
    const cat = ($('f_Type') && $('f_Type').value) || (formAsset && formAsset.Type) || '';
    let defs = [];
    try { const r = await fetch(`/api/fields?for_asset=1&space=${formSpace()}&category=${encodeURIComponent(cat)}`); defs = r.ok ? await r.json() : []; } catch (e) {}
    xb.dataset.defs = JSON.stringify(defs);
    if (!defs.length) { xb.style.display = 'none'; xb.innerHTML = ''; return; }
    xb.style.display = '';
    const input = d => {
      const v = extraVals[d.key] == null ? '' : extraVals[d.key];
      const req = d.required ? ' required' : '';
      if (d.type === 'checkbox') return `<label class="toggle"><input type="checkbox" data-xk="${h(d.key)}" ${v ? 'checked' : ''}><span>${h(d.label)}</span></label>`;
      if (d.type === 'choice') return `<select data-xk="${h(d.key)}"${req}><option value="">-- choose --</option>${(d.options || '').split(',').map(o => o.trim()).filter(Boolean).map(o => `<option ${o === v ? 'selected' : ''}>${h(o)}</option>`).join('')}</select>`;
      if (d.type === 'textarea') return `<textarea data-xk="${h(d.key)}" rows="2"${req}>${h(v)}</textarea>`;
      const t = d.type === 'number' ? 'number' : d.type === 'date' ? 'date' : 'text';
      return `<input type="${t}" data-xk="${h(d.key)}" value="${h(v)}"${t === 'number' ? ' step="any"' : ''}${req}>`;
    };
    xb.innerHTML = `<label>${h(cat ? cat.toUpperCase() + ' DETAILS' : 'DETAILS')}</label>
      <div class="grid2">${defs.map(d => d.type === 'checkbox'
        ? `<div class="field2">${input(d)}</div>`
        : `<div class="field2"><label>${h(d.label)}${d.required ? ' <span class="req">*</span>' : ''}</label>${input(d)}</div>`).join('')}</div>`;
  }

  window.collectSpaceFields = function (row) {
    const sid = $('f_SpaceID'); row.SpaceID = Number(sid ? sid.value : formSpace()) || 1;
    const xb = $('extraBox'); const out = Object.assign({}, extraVals);
    if (xb) xb.querySelectorAll('[data-xk]').forEach(el => { out[el.dataset.xk] = el.type === 'checkbox' ? (el.checked ? '1' : '') : el.value.trim(); });
    let defs = []; try { defs = JSON.parse((xb && xb.dataset.defs) || '[]'); } catch (e) {}
    for (const d of defs) if (d.required && d.type !== 'checkbox' && !String(out[d.key] || '').trim()) return `${d.label} is required for this kind of asset.`;
    row.Extra = out;
    return '';
  };

  async function drawPlans() {
    const mb = $('planBox'); if (!mb || !formId) return;
    let plans = [];
    try { const r = await fetch(`/api/assets/${formId}/plans`); plans = r.ok ? await r.json() : []; } catch (e) {}
    const due = p => p.days_left == null ? '' : p.days_left < 0 ? `<span class="pl-late">${-p.days_left} days overdue</span>`
      : p.days_left <= 7 ? `<span class="pl-soon">due in ${p.days_left} day${p.days_left === 1 ? '' : 's'}</span>` : `<span class="muted">in ${p.days_left} days</span>`;
    mb.innerHTML = `<label>PREVENTIVE MAINTENANCE</label>
      ${plans.length ? `<div class="pl-list">${plans.map(p => `<div class="pl-row">
          <div class="pl-main"><b>${h(p.title)}</b><span class="muted">every ${p.every_n} ${h(p.every_unit)} · next ${h(p.next_due || '—')} ${due(p)}${p.last_done ? ' · last ' + h(p.last_done) : ''}</span></div>
          <button type="button" class="btn sm" data-done="${p.id}">Done</button>
          <button type="button" class="btn sm ghost" data-del="${p.id}">Remove</button></div>`).join('')}</div>`
        : '<p class="muted" style="margin:0 0 10px">No schedule yet. Add what has to be done and how often; reminders go out when it falls due.</p>'}
      <div class="pl-add">
        <input id="plTitle" placeholder="e.g. Filter clean, Service, Inspection">
        <span class="muted">every</span><input id="plN" type="number" min="1" value="3" style="width:70px">
        <select id="plUnit"><option>days</option><option>weeks</option><option selected>months</option><option>years</option></select>
        <span class="muted">last done</span><input id="plLast" type="date">
        <button type="button" class="btn sm" id="plAdd">Add schedule</button>
      </div>`;
    mb.querySelector('#plAdd').onclick = async () => {
      const r = await fetch(`/api/assets/${formId}/plans`, J({ title: $('plTitle').value.trim(), every_n: $('plN').value, every_unit: $('plUnit').value, last_done: $('plLast').value }));
      if (r.ok) { say('Schedule added'); drawPlans(); updateMaintCount(); } else say(await errOf(r), false);
    };
    mb.querySelectorAll('[data-done]').forEach(b => b.onclick = () => markDone(b.dataset.done, drawPlans));
    mb.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => {
      if (!(await uiConfirm('Remove this maintenance schedule? The history of jobs already done stays.'))) return;
      const r = await fetch('/api/plans/' + b.dataset.del, { method: 'DELETE' }); if (r.ok) { drawPlans(); updateMaintCount(); } else say(await errOf(r), false);
    });
  }

  async function markDone(pid, after) {
    const note = await uiPrompt('Mark this job done. Anything to note? (cost, parts, who did it)', '');
    if (note === null) return;
    const r = await fetch(`/api/plans/${pid}/done`, J({ note: note || 'Planned maintenance done' }));
    if (r.ok) { const j = await r.json(); say('Done. Next one ' + j.next_due); after && after(); } else say(await errOf(r), false);
  }

  // ---------------------------------------------------------------- Maintenance due
  // Not a page of its own: a panel that opens in place on Assets (the button
  // shows how many are due), and a widget on the dashboard.
  let maintDays = 30;
  const dueCell = p => p.days_left < 0 ? `<span class="pl-late">${-p.days_left}d overdue</span>`
    : p.days_left <= 7 ? `<span class="pl-soon">${h(p.next_due)}</span>` : h(p.next_due);
  async function fetchDue(days) {
    try { const r = await fetch(`/api/maint/due?days=${days}` + spaceQuery('&')); return r.ok ? await r.json() : []; } catch (e) { return []; }
  }
  const openAsset = id => { if (typeof openModal === 'function') { showPage('page-assets'); openModal(id); } };

  // Nothing about maintenance shows until someone adds a schedule to an asset.
  async function hasPlans() {
    try { const r = await fetch('/api/maint/due?count=1' + spaceQuery('&')); return r.ok ? ((await r.json()).plans || 0) > 0 : false; } catch (e) { return false; }
  }
  window.refreshMaintVisibility = async function () {
    const any = await hasPlans();
    const mb = $('maintBtn'); if (mb) mb.style.display = any ? '' : 'none';
    const pg = $('maintPanel'); if (pg && !any) pg.style.display = 'none';
    const w = $('dashMaint') && $('dashMaint').closest('.widget'); if (w) w.classList.toggle('mt-none', !any);
    return any;
  };
  async function updateMaintCount() {
    const b = $('maintCount'); if (!b) return;
    if (!(await window.refreshMaintVisibility())) { b.textContent = ''; return; }
    const rows = await fetchDue(7);
    b.textContent = rows.length ? rows.length : '';
    b.classList.toggle('late', rows.some(p => p.days_left < 0));
  }

  window.loadMaintPage = async function () {
    const pg = $('maintPanel'); if (!pg) return;
    pg.innerHTML = `<div class="mt-head"><div class="secthead">MAINTENANCE DUE</div><span class="spacer" style="flex:1"></span>
        <select id="mtDays"><option value="7">Next 7 days</option><option value="30">Next 30 days</option><option value="90">Next 90 days</option><option value="365">This year</option></select>
        <button class="btn sm ghost" id="mtClose" type="button">Close</button></div>
      <p class="sec-hint" style="margin:4px 0 10px">Planned jobs due or overdue${cur && spaceById(cur) ? ' in ' + h(spaceById(cur).name) : ''}. Add a schedule on an asset: open it and use Preventive maintenance.</p>
      <div class="tablewrap"><table id="mtGrid"><thead><tr><th>DUE</th><th>JOB</th><th>ASSET</th><th>LOCATION</th><th>EVERY</th><th></th></tr></thead><tbody id="mtBody"></tbody></table>
      <div class="empty" id="mtEmpty" style="display:none">Nothing due. Schedules you add on assets appear here when they fall due.</div></div>`;
    $('mtDays').value = String(maintDays);
    $('mtDays').onchange = () => { maintDays = Number($('mtDays').value); loadMaintPage(); };
    $('mtClose').onclick = () => { pg.style.display = 'none'; };
    const rows = await fetchDue(maintDays);
    $('mtBody').innerHTML = rows.map(p => `<tr>
        <td>${dueCell(p)}</td><td><b>${h(p.title)}</b></td>
        <td><a href="#" data-open="${h(p.asset_id)}">${h(p.asset_name)}</a> <span class="muted mono">${h(p.asset_tag)}</span></td>
        <td>${h(p.location || '—')}</td><td>${p.every_n} ${h(p.every_unit)}</td>
        <td><button class="btn sm" data-done="${p.id}">Done</button></td></tr>`).join('');
    $('mtEmpty').style.display = rows.length ? 'none' : 'block';
    $('mtBody').querySelectorAll('[data-done]').forEach(b => b.onclick = () => markDone(b.dataset.done, () => { loadMaintPage(); updateMaintCount(); }));
    $('mtBody').querySelectorAll('[data-open]').forEach(a => a.onclick = e => { e.preventDefault(); openAsset(a.dataset.open); });
  };

  async function drawDashMaint() {
    const box = $('dashMaint'); if (!box) return;
    const rows = (await fetchDue(30)).slice(0, 6);
    box.innerHTML = rows.length ? `<div class="dm-list">${rows.map(p => `<button type="button" class="dm-row" data-open="${h(p.asset_id)}">
        <span class="dm-when">${dueCell(p)}</span><span class="dm-what"><b>${h(p.title)}</b><span class="muted">${h(p.asset_name)} · ${h(p.asset_tag)}</span></span></button>`).join('')}</div>`
      : '<div class="empty" style="padding:16px">Nothing due in the next 30 days.</div>';
    box.querySelectorAll('[data-open]').forEach(b => b.onclick = () => openAsset(b.dataset.open));
  }

  // ---------------------------------------------------------------- Settings › Departments
  async function loadSpacesPanel() {
    const p = $('spacesPanel'); if (!p) return;
    await loadSpaces();
    p.innerHTML = `<p class="sec-hint" style="margin-top:0">Run more than IT from one place: Facilities, Fleet, Furniture, Tools… Each department has its own asset ID prefix (IT-1001, FM-1001), categories and extra fields. Who can edit or only view each one is set per person in Settings › Users.</p>
      <div class="sp-cards">${window.SPACES.map(s => `<div class="sp-card">
          <span class="sp-dot big" style="background:${h(s.color || 'var(--accent)')}"></span>
          <div class="sp-info"><b>${h(s.name)}</b><span class="muted">IDs ${h(s.prefix)}-${s.next_no}… · ${s.assets} asset${s.assets === 1 ? '' : 's'}</span></div>
          <button class="btn sm ghost" data-fields="${s.id}">Fields</button>
          ${isAdmin() ? `<button class="btn sm ghost" data-edit="${s.id}">Edit</button>${s.id !== 1 && !s.assets ? `<button class="btn sm danger" data-del="${s.id}">Delete</button>` : ''}` : ''}
        </div>`).join('')}</div>
      ${isAdmin() ? '<div class="m-actions" style="justify-content:flex-start"><button class="btn" id="spAdd">＋ Add a department</button></div>' : ''}
      <p class="sec-hint sp-files" id="spFiles"></p>`;
    if (isAdmin()) fetch('/api/department-files').then(r => r.ok ? r.json() : null).then(j => {
      const e = $('spFiles'); if (j && e) e.innerHTML = `📁 Every department's photos, invoices, signed handovers and ticket attachments are also saved as files, one folder per department, in <code>${h(j.path)}</code>.`;
    }).catch(() => {});
    p.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => spaceDialog(spaceById(b.dataset.edit)));
    p.querySelectorAll('[data-fields]').forEach(b => b.onclick = () => openFieldsEditor({ space_id: Number(b.dataset.fields), title: spaceById(b.dataset.fields).name + ': fields on every asset' }));
    p.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => {
      if (!(await uiConfirm('Delete this department? Its categories stay, shared with the others.'))) return;
      const r = await fetch('/api/spaces/' + b.dataset.del, { method: 'DELETE' }); if (r.ok) loadSpacesPanel(); else say(await errOf(r), false);
    });
    const add = $('spAdd'); if (add) add.onclick = () => spaceDialog(null);
  }
  window.loadSpacesPanel = loadSpacesPanel;

  async function spaceDialog(sp) {
    let tpls = [];
    if (!sp) { try { tpls = await (await fetch('/api/space-templates')).json(); } catch (e) {} }
    const wrap = document.createElement('div'); wrap.className = 'modal show ui-dialog';
    wrap.innerHTML = `<div class="modal-box sp-dialog" role="dialog" aria-modal="true">
      <h3>${sp ? 'Edit ' + h(sp.name) : 'Add a department'}</h3>
      ${sp ? '' : `<p class="sec-hint" style="margin:0 0 10px">Start from a template: it sets up the ID prefix, the item categories and the fields each asks for. Nothing else is created: maintenance schedules are only ever added by you, on an asset.</p>
        <div class="tpl-grid">${tpls.map((t, i) => `<label class="tpl"><input type="radio" name="tpl" value="${h(t.key)}" ${i === 0 ? 'checked' : ''}>
          <span><b>${h(t.name)}</b><em>${t.prefix ? h(t.prefix) + '-1001' : 'your own'}</em><small>${h((t.categories || []).slice(0, 5).join(', '))}${(t.categories || []).length > 5 ? '…' : ''}</small></span></label>`).join('')}</div>`}
      <div class="grid2" style="margin-top:12px">
        <div class="field2"><label>Name</label><input id="spName" value="${h(sp ? sp.name : '')}" placeholder="e.g. Facilities"></div>
        <div class="field2"><label>Asset ID prefix</label><input id="spPrefix" value="${h(sp ? sp.prefix : '')}" maxlength="12" placeholder="e.g. FM" style="text-transform:uppercase"></div>
        <div class="field2"><label>Colour</label><input id="spColor" type="color" value="${h((sp && sp.color) || '#3b9eff')}"></div>
        <div class="field2"><label>Numbers start at</label><input id="spNext" type="number" min="1" value="${sp ? sp.next_no : 1001}"></div>
      </div>
      <p class="muted" id="spPreview" style="margin:8px 0 0"></p>
      <div class="m-actions"><button class="btn ghost" data-x>Cancel</button><button class="btn" data-ok>${sp ? 'Save' : 'Add department'}</button></div></div>`;
    document.body.appendChild(wrap);
    const pv = () => { const p = ($('spPrefix').value || 'XX').toUpperCase().replace(/[^A-Z0-9]/g, ''); $('spPreview').textContent = `New assets get ${p}-${$('spNext').value || 1001}, ${p}-${(Number($('spNext').value) || 1001) + 1}…`; };
    const fillFrom = () => { const k = (wrap.querySelector('input[name=tpl]:checked') || {}).value; const t = tpls.find(x => x.key === k); if (!t) return;
      $('spName').value = t.key === 'blank' ? '' : t.name; $('spPrefix').value = t.prefix; if (t.color) $('spColor').value = t.color; pv(); };
    wrap.querySelectorAll('input[name=tpl]').forEach(r => r.onchange = fillFrom); if (!sp) fillFrom();
    ['spPrefix', 'spNext'].forEach(i => $(i).oninput = pv); pv();
    wrap.addEventListener('click', async e => {
      if (e.target === wrap || e.target.closest('[data-x]')) return wrap.remove();
      if (!e.target.closest('[data-ok]')) return;
      const body = { name: $('spName').value.trim(), prefix: $('spPrefix').value.trim(), color: $('spColor').value, next_no: Number($('spNext').value) || 1001 };
      if (!sp) body.template = (wrap.querySelector('input[name=tpl]:checked') || {}).value || 'blank';
      const r = await fetch(sp ? '/api/spaces/' + sp.id : '/api/spaces', { method: sp ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (r.ok) { wrap.remove(); say(sp ? 'Saved' : 'Department added'); loadSpacesPanel(); if (typeof loadCatalog === 'function') loadCatalog(); }
      else say(await errOf(r), false);
    });
  }

  // ---------------------------------------------------------------- the field editor
  window.openFieldsEditor = async function (o) {
    const wrap = document.createElement('div'); wrap.className = 'modal show ui-dialog';
    const deptMode = o.space_id != null && !o.category;
    wrap.innerHTML = `<div class="modal-box fl-dialog" role="dialog" aria-modal="true"><h3>${h(o.title || 'Fields')}</h3>
      ${deptMode ? `<div class="fl-sec">BUILT-IN FIELDS</div>
      <p class="sec-hint" style="margin:0 0 8px">Switch off the ones this department doesn't use. They leave its asset form; anything already saved in them is kept.</p>
      <div id="flBuiltins" class="fl-builtins"></div>
      <div class="fl-sec">EXTRA FIELDS</div>` : ''}
      <p class="sec-hint" style="margin:0 0 10px">${o.category ? `Every <b>${h(o.category)}</b> asks for these, on top of its department's own.` : 'Your own fields, on every asset in this department.'} Required ones must be filled in before the asset saves.</p>
      <div id="flList"></div>
      <div class="fl-add">
        <input id="flLabel" placeholder="Field name, e.g. Plate number">
        <select id="flType"><option value="text">Text</option><option value="number">Number</option><option value="date">Date</option><option value="choice">List</option><option value="checkbox">Yes / no</option><option value="textarea">Long text</option></select>
        <input id="flOpts" placeholder="List choices, comma separated" style="display:none">
        <label class="toggle"><input type="checkbox" id="flReq"><span>Required</span></label>
        <button class="btn sm" id="flAdd">Add field</button>
      </div>
      <div class="m-actions"><button class="btn ghost" data-x>Done</button></div></div>`;
    document.body.appendChild(wrap);
    $('flType').onchange = () => { $('flOpts').style.display = $('flType').value === 'choice' ? '' : 'none'; };
    if (deptMode) drawBuiltins(o.space_id);
    const draw = async () => {
      let all = []; try { all = await (await fetch('/api/fields')).json(); } catch (e) {}
      const mine = all.filter(f => (o.category ? f.category === o.category : !f.category) && (o.space_id == null ? f.space_id == null : f.space_id === o.space_id));
      const TY = { text: 'Text', number: 'Number', date: 'Date', choice: 'List', checkbox: 'Yes / no', textarea: 'Long text' };
      $('flList').innerHTML = mine.length ? mine.map(f => `<div class="fl-row"><b>${h(f.label)}</b><span class="muted">${TY[f.type] || f.type}${f.type === 'choice' ? ': ' + h(f.options) : ''}${f.required ? ' · required' : ''}</span><button class="btn sm danger" data-fdel="${f.id}">Remove</button></div>`).join('')
        : '<p class="muted">No fields yet.</p>';
      $('flList').querySelectorAll('[data-fdel]').forEach(b => b.onclick = async () => { await fetch('/api/fields/' + b.dataset.fdel, { method: 'DELETE' }); draw(); });
    };
    $('flAdd').onclick = async () => {
      const r = await fetch('/api/fields', J({ label: $('flLabel').value.trim(), type: $('flType').value, options: $('flOpts').value,
        required: $('flReq').checked, space_id: o.space_id || null, category: o.category || null }));
      if (r.ok) { $('flLabel').value = ''; $('flOpts').value = ''; $('flReq').checked = false; draw(); } else say(await errOf(r), false);
    };
    wrap.addEventListener('click', e => { if (e.target === wrap || e.target.closest('[data-x]')) wrap.remove(); });
    draw();
  };

  // ---------------------------------------------------------------- built-in fields per department
  let BUILTINS = null;
  async function builtins() {
    if (!BUILTINS) { try { BUILTINS = await (await fetch('/api/asset-builtins')).json(); } catch (e) { BUILTINS = []; } }
    return BUILTINS;
  }
  const ALWAYS = [['AssetTag', 'Asset ID'], ['Name', 'Name'], ['Type', 'Item category'], ['Status', 'Status']];
  async function drawBuiltins(sid) {
    const box = $('flBuiltins'); if (!box) return;
    const list = await builtins();
    const sp = spaceById(sid) || {}; const off = new Set(sp.hidden_fields || []);
    box.innerHTML = ALWAYS.map(([k, l]) => `<div class="fl-bi"><span>${h(l)}</span><em>always</em></div>`).join('')
      + list.map(f => `<label class="fl-bi toggle"><span>${h(f.label)}</span><input type="checkbox" data-bk="${h(f.key)}" ${off.has(f.key) ? '' : 'checked'}></label>`).join('');
    box.querySelectorAll('input[data-bk]').forEach(cb => cb.onchange = async () => {
      const hidden = [...box.querySelectorAll('input[data-bk]')].filter(x => !x.checked).map(x => x.dataset.bk);
      const r = await fetch('/api/spaces/' + sid, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ hidden_fields: hidden }) });
      if (r.ok) { await loadSpaces(); say(cb.checked ? 'Shown on ' + (sp.name || 'its') + ' assets' : 'Hidden on ' + (sp.name || 'its') + ' assets'); }
      else { cb.checked = !cb.checked; say(await errOf(r), false); }
    });
  }

  // On the asset form: take off the built-in fields its department switched
  // off. Hidden, not removed, so a save still sends what they hold.
  window.applyHiddenFields = function (sid) {
    const sp = spaceById(sid) || {}; const off = new Set(sp.hidden_fields || []);
    const f2 = id => { const e = $(id); return e ? e.closest('.field2') : null; };
    const box = id => { const e = $(id); return e ? e.closest('.invbox') : null; };
    const map = {
      Serial: [f2('f_Serial')], MacAddress: [f2('f_MacAddress')], Location: [f2('f_Location')],
      Brand: [document.querySelector('#formFields .refbox')], Photo: [$('assetPhotoBox')],
      PurchaseDate: [f2('f_PurchaseDate')], WarrantyMonths: [f2('f_WarrantyMonths')], Price: [f2('f_Price')],
      Assignment: ['f_EmployeeID', 'f_RequestedBy', 'f_ReceivedBy', 'f_NotesReceived', 'f_EmpDepartment', 'f_EmpDesignation'].map(f2),
      Note: [box('f_Note')], Invoice: [box('f_InvoiceFile')],
    };
    Object.entries(map).forEach(([k, els]) => els.forEach(el => { if (el) el.classList.toggle('bi-off', off.has(k)); }));
    // a section whose every field is off goes too
    document.querySelectorAll('#formFields .invbox').forEach(b => {
      const g = b.querySelector('.grid2'); if (!g) return;
      const fields = [...g.children].filter(x => x.classList.contains('field2'));
      b.classList.toggle('bi-off', fields.length > 0 && fields.every(x => x.classList.contains('bi-off')));
    });
  };

  // ---------------------------------------------------------------- import / export: which department
  function pickDialog(o) {
    const wrap = document.createElement('div'); wrap.className = 'modal show ui-dialog';
    wrap.innerHTML = `<div class="modal-box ie-dialog" role="dialog" aria-modal="true"><h3>${h(o.title)}</h3>
      <p class="sec-hint" style="margin:0 0 12px">${o.hint}</p>
      <div class="ie-list">${o.choices.map((c, i) => `<label class="ie-opt"><input type="radio" name="ieSp" value="${h(c.value)}" ${c.value === o.selected || (!o.selected && i === 0) ? 'checked' : ''}>
        <span>${c.color ? `<i class="sp-dot" style="background:${h(c.color)}"></i>` : ''}<b>${h(c.label)}</b>${c.sub ? `<em>${h(c.sub)}</em>` : ''}</span></label>`).join('')}</div>
      ${o.note ? `<p class="sec-hint" style="margin:12px 0 0">${o.note}</p>` : ''}
      <div class="m-actions"><button class="btn ghost" data-x>Cancel</button><button class="btn" data-ok>${h(o.ok)}</button></div></div>`;
    document.body.appendChild(wrap);
    wrap.addEventListener('click', e => {
      if (e.target === wrap || e.target.closest('[data-x]')) return wrap.remove();
      if (!e.target.closest('[data-ok]')) return;
      const v = (wrap.querySelector('input[name=ieSp]:checked') || {}).value || '';
      wrap.remove(); o.done(v);
    });
  }
  window.openExportDialog = function () {
    const sps = window.SPACES || [];
    if (sps.length < 2) { window.location = '/api/export'; return; }
    pickDialog({ title: 'Export assets', ok: 'Export', selected: String(cur || ''),
      hint: 'Which department\'s assets go into the spreadsheet? It carries each asset\'s department and its extra fields as columns.',
      choices: [{ value: '', label: 'All departments', sub: sps.reduce((n, s) => n + (s.assets || 0), 0) + ' assets' }]
        .concat(sps.map(s => ({ value: String(s.id), label: s.name, sub: (s.assets || 0) + ' assets · ' + s.prefix, color: s.color || 'var(--accent)' }))),
      done: v => { window.location = '/api/export' + (v ? '?space=' + encodeURIComponent(v) : ''); } });
  };
  window.openImportDialog = function (pickFile) {
    const sps = (window.SPACES || []).filter(s => s.can_edit !== false);
    if ((window.SPACES || []).length < 2 || sps.length < 1) { window.IMPORT_SPACE = ''; pickFile(); return; }
    pickDialog({ title: 'Import assets', ok: 'Choose file…', selected: String(cur && sps.some(s => String(s.id) === String(cur)) ? cur : sps[0].id),
      hint: 'New assets from the sheet go into this department and get its asset IDs.',
      note: 'A sheet with an <b>Asset Department</b> column puts each row in the department it names instead. Columns named like a department\'s extra fields (e.g. <i>Rating (kVA)</i>) fill those in.',
      choices: sps.map(s => ({ value: String(s.id), label: s.name, sub: s.prefix + '-…', color: s.color || 'var(--accent)' })),
      done: v => { window.IMPORT_SPACE = v; pickFile(); } });
  };

  // ---------------------------------------------------------------- Users: which departments
  // Stored as "1,3:r": a bare id = works there with their role, ":r" = can
  // only look there. Empty = every department. On screen that is one plain
  // choice, "All departments" or "Only some", and a row per department.
  let userSp = { mode: 'all', on: {} };
  window.fillUserSpaces = function (csv) {
    const on = {};
    String(csv || '').split(',').filter(Boolean).forEach(x => { const [id, m] = x.split(':'); on[id] = m === 'r' ? 'r' : 'w'; });
    userSp = { mode: Object.keys(on).length ? 'some' : 'all', on };
    drawUserSpaces();
  };
  window.drawUserSpaces = function () {
    const box = $('u_spaces'); if (!box) return;
    const wrap = box.closest('.field2'); const head = wrap && wrap.previousElementSibling;
    const many = (window.SPACES || []).length > 1;
    [wrap, head && head.classList.contains('um-sec') ? head : null].forEach(e => { if (e) e.style.display = many ? '' : 'none'; });
    if (!many) return;
    const role = ($('u_role') || {}).value || '';
    if (role === 'admin') { box.innerHTML = '<p class="um-hint" style="margin:0">Admins always have every department.</p>'; return; }
    const ro = role === 'read-only';
    const opt = (v, cur, t) => `<option value="${v}" ${v === cur ? 'selected' : ''}>${t}</option>`;
    box.innerHTML = `<div class="um-mode">
        <label class="${userSp.mode === 'all' ? 'on' : ''}"><input type="radio" name="uSpMode" value="all" ${userSp.mode === 'all' ? 'checked' : ''}><b>All departments</b><span>Now and any added later</span></label>
        <label class="${userSp.mode === 'some' ? 'on' : ''}"><input type="radio" name="uSpMode" value="some" ${userSp.mode === 'some' ? 'checked' : ''}><b>Only some</b><span>Choose below</span></label>
      </div>` + (userSp.mode === 'some' ? '<div class="sp-roles">' + window.SPACES.map(s => {
        const cur = userSp.on[String(s.id)] || '';
        return `<div class="sp-role-row${cur ? ' is-on' : ''}"><span class="sp-role-name"><i class="sp-dot" style="background:${h(s.color || 'var(--accent)')}"></i>${h(s.name)}</span>`
          + `<select data-sid="${s.id}">${opt('', cur, 'No access')}${ro ? opt('r', cur === 'w' ? 'r' : cur, 'Can look') : opt('w', cur, 'Can change') + opt('r', cur, 'Can only look')}</select></div>`;
      }).join('') + '</div>' : '');
    box.querySelectorAll('input[name=uSpMode]').forEach(r => r.onchange = () => { userSp.mode = r.value; drawUserSpaces(); });
    box.querySelectorAll('select[data-sid]').forEach(sel => sel.onchange = () => {
      if (sel.value) userSp.on[sel.dataset.sid] = sel.value; else delete userSp.on[sel.dataset.sid];
      sel.closest('.sp-role-row').classList.toggle('is-on', !!sel.value);
    });
  };
  // "" = all; null = "Only some" with none picked (the dialog refuses to save)
  window.collectUserSpaces = function () {
    if (!$('u_spaces') || (window.SPACES || []).length < 2) return '';
    const role = ($('u_role') || {}).value || '';
    if (role === 'admin' || userSp.mode === 'all') return '';
    const ids = Object.keys(userSp.on).filter(k => window.SPACES.some(s => String(s.id) === k));
    if (!ids.length) return null;
    // a Viewer is saved as exactly what the screen shows: "look" everywhere,
    // so a later promotion to Editor doesn't quietly turn into "change"
    const lookOnly = role === 'read-only';
    return ids.sort((a, b) => a - b).map(k => (lookOnly || userSp.on[k] === 'r') ? k + ':r' : k).join(',');
  };
  // one line for the users list: "All", or "IT · Facilities (look only)"
  window.userSpacesSummary = function (u) {
    if (u.role === 'admin' || (window.SPACES || []).length < 2) return '<span class="muted">All</span>';
    const parts = String(u.spaces || '').split(',').filter(Boolean);
    if (!parts.length) return '<span class="muted">All</span>';
    const out = parts.map(x => { const [id, m] = x.split(':'); const s = spaceById(id); if (!s) return '';
      return `<span class="u-dep${m === 'r' ? ' ro' : ''}" title="${m === 'r' ? 'can only look' : 'can change'}"><i class="sp-dot" style="background:${h(s.color || 'var(--accent)')}"></i>${h(s.name)}${m === 'r' ? ' <em>look only</em>' : ''}</span>`; }).join('');
    // its departments were all deleted: it sees nothing until given one
    return out || '<span class="muted">None (edit to choose)</span>';
  };

  // ---------------------------------------------------------------- wiring
  function start() {
    loadSpaces().then(() => { if ($('u_spaces')) fillUserSpaces(''); });
    const mb = $('maintBtn');
    if (mb) mb.onclick = () => { const pg = $('maintPanel'); const open = pg.style.display === 'none'; pg.style.display = open ? '' : 'none'; if (open) loadMaintPage(); };
    updateMaintCount();
    // the dashboard widget follows the dashboard's own refreshes
    if (typeof window.loadDashboard === 'function') {
      const orig = window.loadDashboard;
      window.loadDashboard = async function () { const r = await orig.apply(this, arguments); drawDashMaint(); return r; };
    }
    drawDashMaint();
    document.addEventListener('click', e => {
      if (e.target.closest('#addUserBtn,[onclick*="addUser"]')) setTimeout(() => fillUserSpaces(''), 60);
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
