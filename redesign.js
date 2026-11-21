/* IT-Vault design layer (loaded after app.js).
 *
 * One set of line icons for the whole app, in place of emoji: emoji are a
 * different drawing on every phone and every Windows build, never line up
 * with text, and ignore the theme colour. Also: the item-type icons for the
 * asset list, the per-category icon choice, and the phone layout's bottom
 * tab bar + menu drawer.
 *
 * Everything here decorates what app.js renders; nothing in app.js depends on
 * it beyond the optional window.typeIcon() used by the asset list.
 */
(function () {
  'use strict';

  // 24x24 line icons (stroke = currentColor), so they follow the theme
  const P = {
    home: '<path d="m3 10 9-7 9 7v10a2 2 0 0 1-2 2h-4v-7H9v7H5a2 2 0 0 1-2-2z"/>',
    laptop: '<path d="M20 16V7a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v9m16 0H4m16 0 1.28 2.55a1 1 0 0 1-.9 1.45H3.62a1 1 0 0 1-.9-1.45L4 16"/>',
    desktop: '<rect x="2" y="4" width="13" height="10" rx="1.5"/><path d="M6 18h5M8.5 14v4"/><rect x="17" y="4" width="5" height="16" rx="1"/><path d="M19.5 8h.01"/>',
    monitor: '<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8M12 17v4"/>',
    smartphone: '<rect width="14" height="20" x="5" y="2" rx="2"/><path d="M12 18h.01"/>',
    tablet: '<rect width="16" height="20" x="4" y="2" rx="2"/><path d="M12 18h.01"/>',
    router: '<rect width="20" height="8" x="2" y="14" rx="2"/><path d="M6.01 18H6M10.01 18H10M15 10v4M17.84 7.17a4 4 0 0 0-5.66 0M20.66 4.34a8 8 0 0 0-11.31 0"/>',
    switch: '<rect x="2" y="7" width="20" height="10" rx="2"/><path d="M6 11v2M9 11v2M12 11v2M15 11v2M18.5 12h.01"/>',
    wifi: '<path d="M12 20h.01M2 8.82a15 15 0 0 1 20 0M5 12.86a10 10 0 0 1 14 0M8.5 16.43a5 5 0 0 1 7 0"/>',
    camera: '<path d="M3 6.5 15.5 3l2 6.5L5 13z"/><path d="m17.5 7.5 3.5-1 .5 4-3.3 1"/><path d="M8.5 12.5 9.5 17H5M5 14.5v5"/>',
    drive: '<path d="M22 12H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/><path d="M6 16h.01M10 16h.01"/>',
    server: '<rect width="20" height="8" x="2" y="2" rx="2"/><rect width="20" height="8" x="2" y="14" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
    printer: '<path d="M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect width="12" height="8" x="6" y="14"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    shieldcheck: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    headphones: '<path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"/>',
    battery: '<rect width="16" height="10" x="2" y="7" rx="2"/><path d="M22 11v2M6 11v2M10 11v2"/>',
    keyboard: '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="M6 8h.01M10 8h.01M14 8h.01M18 8h.01M8 12h.01M12 12h.01M16 12h.01M7 16h10"/>',
    projector: '<rect x="2" y="8" width="20" height="9" rx="2"/><circle cx="16" cy="12.5" r="2.5"/><path d="M6 12.5h4M6 17v2M18 17v2"/>',
    box: '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><path d="m3.3 7 8.7 5 8.7-5M12 22V12"/>',
    file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z"/><path d="M14 2v4a2 2 0 0 0 2 2h4M16 13H8M16 17H8M10 9H8"/>',
    ticket: '<path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2z"/><path d="M13 5v2M13 17v2M13 11v2"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    userplus: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6M22 11h-6"/>',
    folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    trash: '<path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    radar: '<path d="M19.07 4.93A10 10 0 0 0 6.99 3.34M4 6h.01M2.29 9.62A10 10 0 1 0 21.31 8.35M16.24 7.76A6 6 0 1 0 8.23 16.67M12 18h.01M17.99 11.66A6 6 0 0 1 15.77 16.67"/><circle cx="12" cy="12" r="2"/><path d="m13.41 10.59 5.66-5.66"/>',
    activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5M3 12a9 3 0 0 0 18 0"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    power: '<path d="M12 2v10M18.4 6.6a9 9 0 1 1-12.77.04"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
    mail: '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
    message: '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22z"/>',
    send: '<path d="m22 2-7 20-4-9-9-4zM22 2 11 13"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    copy: '<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    eye: '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
    edit: '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/>',
    qr: '<rect width="5" height="5" x="3" y="3" rx="1"/><rect width="5" height="5" x="16" y="3" rx="1"/><rect width="5" height="5" x="3" y="16" rx="1"/><path d="M21 16h-3a2 2 0 0 0-2 2v3M21 21v.01M12 7v3a2 2 0 0 1-2 2H7M3 12h.01M12 3h.01M12 16v.01M16 12h1M21 12v.01M12 21v-1"/>',
    refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8M21 3v5h-5M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16M8 16H3v5"/>',
    zap: '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
    more: '<circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>',
    swap: '<path d="M8 3 4 7l4 4M4 7h16M16 21l4-4-4-4M20 17H4"/>',
    wrench: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    hourglass: '<path d="M5 22h14M5 2h14M17 22v-4.17a2 2 0 0 0-.59-1.42L12 12l-4.41 4.41A2 2 0 0 0 7 17.83V22M7 2v4.17a2 2 0 0 0 .59 1.42L12 12l4.41-4.41A2 2 0 0 0 17 6.17V2"/>',
    layout: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18M9 21V9"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    tag: '<path d="M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.42l8.7 8.7a2.43 2.43 0 0 0 3.42 0l6.58-6.58a2.43 2.43 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r=".5"/>',
    lock: '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    key: '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3"/>',
    bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    image: '<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21"/>',
    columns: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M12 3v18"/>',
    pen: '<path d="M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    chevron: '<path d="m9 18 6-6-6-6"/>',
    alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3M12 9v4M12 17h.01"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    building: '<rect width="16" height="20" x="4" y="2" rx="2"/><path d="M9 22v-4h6v4M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01"/>',
    palette: '<circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/><circle cx="8.5" cy="7.5" r=".5"/><circle cx="6.5" cy="12.5" r=".5"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.93 0 1.65-.75 1.65-1.69 0-.44-.18-.84-.44-1.13-.29-.29-.44-.65-.44-1.13a1.64 1.64 0 0 1 1.67-1.67h2c3.05 0 5.56-2.5 5.56-5.56C21.96 6.01 17.46 2 12 2"/>',
  };
  const svg = (name, cls) =>
    `<svg class="ic${cls ? ' ' + cls : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${P[name] || P.box}</svg>`;
  window.icon = svg;
  window.ICON_NAMES = P;

  /* ---- item types ---- */
  // What a category is called says what it is, nearly always. A category can
  // also have its icon picked by hand (Product Catalog), which wins.
  const TYPE_RULES = [
    [/laptop|notebook|macbook|chromebook|ultrabook/i, 'laptop'],
    [/phone|mobile|iphone|android|smartphone|handset/i, 'smartphone'],
    [/tablet|ipad|\btab\b/i, 'tablet'],
    [/monitor|display|screen|\btv\b|television/i, 'monitor'],
    [/desktop|workstation|\bpc\b|computer|all.?in.?one|imac|thin client/i, 'desktop'],
    [/access.?point|\bap\b|wi-?fi|wireless|wlan/i, 'wifi'],
    [/router|gateway|modem/i, 'router'],
    [/switch|\bhub\b/i, 'switch'],
    [/firewall|fortigate|\butm\b|sophos|palo alto/i, 'shield'],
    [/server|\bnas\b|\bsan\b|hypervisor/i, 'server'],
    [/\bnvr\b|\bdvr\b|storage|disk|drive|backup/i, 'drive'],
    [/camera|cctv|webcam|ip cam/i, 'camera'],
    [/printer|scanner|copier|\bmfp\b|plotter/i, 'printer'],
    [/head(set|phone)|earphone|earbud|speaker|audio/i, 'headphones'],
    [/\bups\b|battery|power|\bpdu\b|inverter/i, 'battery'],
    [/keyboard|mouse|peripheral|dock/i, 'keyboard'],
    [/projector/i, 'projector'],
  ];
  window.CAT_ICONS = window.CAT_ICONS || {};
  window.CAT_PHOTOS = window.CAT_PHOTOS || {};
  function typeIconName(t) {
    t = String(t || '');
    const own = window.CAT_ICONS[t];
    if (own && P[own]) return own;
    for (const [re, n] of TYPE_RULES) if (re.test(t)) return n;
    return 'box';
  }
  window.typeIconName = typeIconName;
  const escA = v => String(v == null ? '' : v).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  // a product photo, when the category has one, else its icon
  window.typeIcon = t => {
    const ph = window.CAT_PHOTOS[String(t || '')];
    if (ph) return `<span class="ticon has-photo"><img src="${escA(ph)}" alt="" loading="lazy"></span>`;
    return `<span class="ticon ti-${typeIconName(t)}">${svg(typeIconName(t))}</span>`;
  };
  window.catLookHTML = c => c.photo
    ? `<span class="ticon has-photo"><img src="${escA(c.photo)}" alt=""></span>`
    : `<span class="ticon">${svg(c.icon && P[c.icon] ? c.icon : typeIconName(c.name))}</span>`;
  // the icons a category can be given in the Product Catalog
  window.ICON_CHOICES = ['laptop', 'desktop', 'monitor', 'smartphone', 'tablet', 'router', 'switch', 'wifi', 'shield',
    'server', 'drive', 'camera', 'printer', 'headphones', 'battery', 'keyboard', 'projector', 'box'];

  async function loadCategoryIcons() {
    try {
      const r = await fetch('/api/categories');
      if (!r.ok) return;
      const list = await r.json();
      const m = {}, ph = {};
      (list || []).forEach(c => { if (!c) return; if (c.icon) m[c.name] = c.icon; if (c.photo) ph[c.name] = c.photo; });
      window.CAT_ICONS = m; window.CAT_PHOTOS = ph;
      if (typeof render === 'function') { try { render(); } catch (e) { /* not on screen yet */ } }
    } catch (e) { /* signed out, or offline: the name rules still apply */ }
  }
  window.loadCategoryIcons = loadCategoryIcons;

  /* ---- the sidebar and the dashboard cards ---- */
  const NAV = { navHome: 'home', navAssets: 'laptop', navContracts: 'file', navTickets: 'ticket', navDirectory: 'users',
    navCatalog: 'folder', navLostFound: 'search', navTrash: 'trash', navAudit: 'list', navScan: 'radar',
    navHeartbeat: 'activity', navBackup: 'database', navSettings: 'settings' };
  function iconNav() {
    for (const [id, name] of Object.entries(NAV)) {
      const a = document.getElementById(id);
      if (!a) continue;
      a.title = (a.textContent || '').trim();
      const ni = a.querySelector('.ni');
      if (ni && !ni.querySelector('svg')) ni.innerHTML = svg(name);
    }
    const kpi = { c1: 'box', c2: 'swap', c3: 'wrench', c4: 'hourglass', c5: 'shieldcheck',
      'hbk-down': 'alert', 'hbk-pending': 'refresh', 'hbk-up': 'check', 'hbk-paused': 'clock', 'hbk-avg': 'activity' };
    document.querySelectorAll('.kpi').forEach(k => {
      const ico = k.querySelector('.kpi-ico');
      const c = [...k.classList].find(x => kpi[x]);
      if (ico && c && !ico.querySelector('svg')) ico.innerHTML = svg(kpi[c]);
    });
    const out = document.getElementById('logoutBtn');
    if (out && !out.querySelector('svg')) out.innerHTML = svg('power') + '<span>Sign out</span>';
  }

  /* ---- emoji at the start of a button become the matching icon ---- */
  const EMO = [
    ['📨', 'send'], ['📧', 'mail'], ['💬', 'message'], ['📋', 'copy'], ['🔗', 'link'], ['🖨️', 'printer'], ['🖨', 'printer'],
    ['🗑️', 'trash'], ['🗑', 'trash'], ['⬆', 'upload'], ['📤', 'upload'], ['⬇', 'download'], ['📥', 'download'],
    ['✓', 'check'], ['✔', 'check'], ['✕', 'x'], ['✖', 'x'], ['＋', 'plus'], ['👁', 'eye'], ['📄', 'file'],
    ['⚡', 'zap'], ['🔄', 'refresh'], ['↺', 'refresh'], ['♻️', 'refresh'], ['♻', 'refresh'], ['⚙️', 'settings'], ['⚙', 'settings'], ['✎', 'pen'],
    ['✏️', 'pen'], ['✏', 'pen'], ['⏻', 'power'], ['🔍', 'search'], ['🔎', 'search'], ['🏷️', 'tag'], ['🏷', 'tag'],
    ['🔒', 'lock'], ['🔑', 'key'], ['📷', 'camera'], ['💾', 'database'], ['🖼️', 'image'], ['🖼', 'image'],
    ['👤', 'user'], ['🛡️', 'shield'], ['🛡', 'shield'], ['🔔', 'bell'], ['📡', 'radar'], ['🔧', 'wrench'],
    ['🧾', 'file'], ['📑', 'file'], ['📊', 'layout'], ['🏠', 'home'], ['💻', 'laptop'], ['🎫', 'ticket'],
    ['👥', 'users'], ['🗂️', 'folder'], ['🗂', 'folder'], ['📁', 'folder'], ['⚠️', 'alert'], ['⚠', 'alert'],
    ['🧑', 'user'], ['⏱️', 'clock'], ['⏱', 'clock'], ['🗄️', 'database'], ['🗄', 'database'], ['🛜', 'wifi'], ['🏢', 'building'],
    ['🎨', 'palette'], ['💀', 'alert'], ['🧭', 'search'], ['📶', 'wifi'], ['🌐', 'link'], ['📞', 'message'], ['🗒️', 'file'], ['🗒', 'file'],
  ];
  const BTN_SEL = 'button, .btn, a.btn, .cfgitem, label.btn';
  /* Button labels in one voice. Half the app said COMMIT, TEST EMAIL, SEND
     LINK and the other half Save notifications -- shouting next to talking.
     An all-capitals label becomes sentence case; acronyms stay as they are. */
  const ACRO = new Set(['QR', 'PDF', 'SMTP', 'LDAP', 'AD', 'CSV', 'API', 'SLA', 'IT', 'ID', 'UPS', 'MAC', 'URL', 'IP',
    'EMP', '2FA', 'OTP', 'UI', 'AMC', 'XLSX', 'SSL', 'DB', 'SQL', 'NVR', 'DVR', 'AP', 'HR', 'OK', 'AI', 'TOTP', 'USB']);
  const SPECIAL = { WHATSAPP: 'WhatsApp', UNIFI: 'UniFi', EXCEL: 'Excel', 'IT-VAULT': 'IT-Vault', COMMIT: 'Save' };
  function sentence(t) {
    let first = true;
    return t.replace(/[A-Z0-9][A-Z0-9'’-]*/g, w => {
      const bare = w.replace(/['’]S$/, '');
      if (SPECIAL[w]) { first = false; return SPECIAL[w]; }
      if (ACRO.has(bare) || ACRO.has(w)) { first = false; return w; }
      if (/^\d/.test(w)) { first = false; return w.toLowerCase(); }
      const out = first ? w.charAt(0) + w.slice(1).toLowerCase() : w.toLowerCase();
      first = false; return out;
    });
  }
  function calmLabel(el) {
    if (el.closest('.bnav,.seg,.row-more')) return;
    el.childNodes.forEach(n => {
      if (n.nodeType !== 3) return;
      const v = n.nodeValue;
      if ((v.match(/[A-Z]/g) || []).length >= 2 && !/[a-z]/.test(v)) n.nodeValue = sentence(v);
    });
  }
  function iconify(el) {
    if (!el || el.nodeType !== 1) return;
    calmLabel(el);
    if (el.querySelector(':scope > svg.ic')) return;
    let t = el.firstChild;
    while (t && t.nodeType === 3 && !t.nodeValue.trim()) t = t.nextSibling;
    if (!t || t.nodeType !== 3) return;
    const s = t.nodeValue.replace(/^\s+/, '');
    for (const [e, n] of EMO) {
      if (!s.startsWith(e)) continue;
      t.nodeValue = s.slice(e.length).replace(/^[️\s]+/, '');
      el.insertAdjacentHTML('afterbegin', svg(n));
      el.classList.add('has-ic');
      return;
    }
    // "+ Add asset" style labels
    if (/^\+\s?\S/.test(s)) {
      t.nodeValue = s.replace(/^\+\s?/, '');
      el.insertAdjacentHTML('afterbegin', svg('plus'));
      el.classList.add('has-ic');
    }
  }
  function sweep(root) {
    if (!root || root.nodeType !== 1) return;
    if (root.matches && root.matches(BTN_SEL)) iconify(root);
    root.querySelectorAll && root.querySelectorAll(BTN_SEL).forEach(iconify);
  }
  let pending = new Set(), queued = false;
  const mo = new MutationObserver(muts => {
    for (const m of muts) {
      if (m.type === 'childList') {
        m.addedNodes.forEach(n => { if (n.nodeType === 1) pending.add(n); });
        if (m.target && m.target.nodeType === 1 && m.target.matches && m.target.matches(BTN_SEL)) pending.add(m.target);
      }
    }
    if (!queued && pending.size) {
      queued = true;
      requestAnimationFrame(() => { queued = false; const p = [...pending]; pending = new Set(); p.forEach(sweep); });
    }
  });

  /* ---- phone: bottom tab bar + the sidebar as a drawer ---- */
  const TABS = [['navHome', 'home', 'Home'], ['navAssets', 'laptop', 'Assets'], ['navTickets', 'ticket', 'Tickets'],
    ['navDirectory', 'users', 'People'], [null, 'menu', 'More']];
  function buildPhoneNav() {
    if (document.getElementById('bnav')) return;
    const nav = document.createElement('nav');
    nav.id = 'bnav';
    nav.className = 'bnav';
    nav.setAttribute('aria-label', 'Main');
    nav.innerHTML = TABS.map(([id, ic, label]) =>
      `<button type="button" data-for="${id || ''}">${svg(ic)}<span>${label}</span></button>`).join('');
    document.body.appendChild(nav);
    const scrim = document.createElement('div');
    scrim.className = 'drawer-scrim';
    document.body.appendChild(scrim);
    const close = () => document.body.classList.remove('drawer-open');
    scrim.addEventListener('click', close);
    nav.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return;
      const id = b.dataset.for;
      if (!id) { document.body.classList.toggle('drawer-open'); return; }
      const a = document.getElementById(id); if (a) a.click();
      close();
    });
    // choosing anything in the drawer closes it
    document.querySelector('.side .nav')?.addEventListener('click', e => { if (e.target.closest('a')) close(); });
    document.getElementById('logoutBtn')?.addEventListener('click', close);
    syncTabs();
  }
  function syncTabs() {
    const nav = document.getElementById('bnav'); if (!nav) return;
    let anyActive = false;
    nav.querySelectorAll('button[data-for]').forEach(b => {
      const id = b.dataset.for;
      if (!id) return;
      const a = document.getElementById(id);
      // a tab for something this role cannot open is not shown
      b.hidden = !a || a.style.display === 'none';
      const on = !!(a && a.classList.contains('active'));
      b.classList.toggle('on', on); anyActive = anyActive || on;
    });
    const more = nav.querySelector('button[data-for=""]');
    if (more) more.classList.toggle('on', !anyActive);
  }

  /* ---- start ---- */
  function start() {
    iconNav();
    sweep(document.body);
    buildPhoneNav();
    mo.observe(document.body, { childList: true, subtree: true });
    const navEl = document.querySelector('.side .nav');
    if (navEl) new MutationObserver(syncTabs).observe(navEl, { attributes: true, subtree: true, attributeFilter: ['class', 'style'] });
    loadCategoryIcons();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();

/* Settings > Customization > Light & dark */
(function () {
  const ICON = { system: 'monitor', light: 'sun', dark: 'moon' };
  function paint(state) {
    document.querySelectorAll('#modePanel .mode-row').forEach(row => {
      const v = state[row.dataset.key] || 'system';
      row.querySelectorAll('.seg button').forEach(b => {
        const on = b.dataset.v === v;
        b.classList.toggle('on', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); b.setAttribute('role', 'radio');
      });
    });
  }
  async function load() {
    if (!document.getElementById('modePanel')) return;
    try { const r = await fetch('/api/settings/modes'); if (r.ok) paint(await r.json()); } catch (e) {}
  }
  document.addEventListener('click', async e => {
    const b = e.target.closest('#modePanel .seg button'); if (!b) return;
    const row = b.closest('.mode-row'); const key = row.dataset.key; const v = b.dataset.v;
    row.querySelectorAll('.seg button').forEach(x => x.classList.toggle('on', x === b));
    try {
      const r = await fetch('/api/settings/modes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ [key]: v }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) { if (window.toast) toast('✕ ' + (j.error || 'Not saved')); load(); return; }
      paint(j);
      if (key === 'ui_mode' && window.setUiMode) {
        setUiMode(v);
        try { if (window.__ME_THEME) applyCustomVars(window.__ME_THEME); } catch (err) {}
      }
      if (window.toast) toast('✓ ' + ({ ui_mode: 'App', sign_mode: 'Acknowledgement pages', portal_mode: 'Portal' })[key] + ': ' + b.textContent);
    } catch (err) { if (window.toast) toast('✕ Could not save'); }
  });
  // icons on the switch, and load the saved choice when Customization opens
  function decorate() {
    document.querySelectorAll('#modePanel .seg button').forEach(b => {
      if (!b.querySelector('svg') && window.icon) b.insertAdjacentHTML('afterbegin', window.icon(ICON[b.dataset.v]));
    });
  }
  document.addEventListener('click', e => { if (e.target.closest('.cfgitem[data-sec="custom"]')) setTimeout(load, 50); });
  function start() { decorate(); load(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();

/* Product Catalog: choose a category's icon, or give it a product photo */
(function () {
  window.openCatLook = function (id) {
    const c = (window.__CATS || []).find(x => x.id === id); if (!c) return;
    const choices = (window.ICON_CHOICES || []).map(n =>
      `<button type="button" class="look-opt${c.icon === n ? ' on' : ''}" data-icon="${n}" title="${n}">${window.icon(n)}</button>`).join('');
    const wrap = document.createElement('div');
    wrap.className = 'modal show ui-dialog';
    wrap.innerHTML = `<div class="modal-box look-box" role="dialog" aria-modal="true">
      <h3>${String(c.name).replace(/[<>&]/g, '')}</h3>
      <p class="sec-hint" style="margin:0 0 12px">How these items look in the asset list. A product photo is used when there is one; otherwise this icon.</p>
      <div class="look-photo">
        <span class="look-prev">${window.catLookHTML(c)}</span>
        <label class="btn ghost sm">${window.icon('image')}<span>${c.photo ? 'Replace photo' : 'Upload a photo'}</span><input type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden></label>
        ${c.photo ? `<button type="button" class="btn ghost sm" data-act="rmphoto">${window.icon('trash')}<span>Remove photo</span></button>` : ''}
      </div>
      <div class="look-lbl">Icon</div>
      <div class="look-grid"><button type="button" class="look-opt auto${!c.icon ? ' on' : ''}" data-icon="" title="Automatic, from the name">Auto</button>${choices}</div>
      <div class="m-actions"><button type="button" class="btn ghost" data-act="close">Done</button></div></div>`;
    const done = () => { wrap.remove(); if (typeof loadCatCategories === 'function') loadCatCategories(); };
    wrap.addEventListener('click', async e => {
      if (e.target === wrap || e.target.closest('[data-act="close"]')) return done();
      const opt = e.target.closest('.look-opt');
      if (opt) {
        const r = await fetch(`/api/categories/${id}/look`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ icon: opt.dataset.icon }) });
        if (r.ok) { c.icon = opt.dataset.icon; wrap.querySelectorAll('.look-opt').forEach(o => o.classList.toggle('on', o === opt)); if (!c.photo) wrap.querySelector('.look-prev').innerHTML = window.catLookHTML(c); }
        else if (window.toast) toast('✕ Not saved');
      }
      if (e.target.closest('[data-act="rmphoto"]')) {
        const r = await fetch(`/api/categories/${id}/look`, { method: 'DELETE' });
        if (r.ok) { if (window.toast) toast('✓ Photo removed'); done(); }
      }
    });
    wrap.querySelector('input[type=file]').addEventListener('change', async e => {
      const f = e.target.files[0]; if (!f) return;
      const fd = new FormData(); fd.append('photo', f);
      const r = await fetch(`/api/categories/${id}/look`, { method: 'POST', body: fd });
      const j = await r.json().catch(() => ({}));
      if (r.ok) { if (window.toast) toast('✓ Photo saved'); done(); } else if (window.toast) toast('✕ ' + (j.error || 'Upload failed'));
    });
    document.body.appendChild(wrap);
  };
})();

/* Settings > General > Public address */
(function () {
  async function load() {
    const inp = document.getElementById('pubUrl'); if (!inp) return;
    try {
      const r = await fetch('/api/settings/public-url'); if (!r.ok) return;
      paint(await r.json());
    } catch (e) {}
  }
  function paint(j) {
    const inp = document.getElementById('pubUrl'), st = document.getElementById('pubUrlState');
    if (document.activeElement !== inp) inp.value = j.public_url || '';
    const where = '<span class="mono">' + String(j.effective || '').replace(/[<>&]/g, '') + '</span>';
    st.className = 'pub-state ' + (j.local_only ? 'warn' : 'ok');
    st.innerHTML = j.env_override
      ? 'Set by the server (ITVAULT_PUBLIC_URL): links use ' + where + '.'
      : j.local_only
        ? '<b>Links now point to ' + where + '</b>, which only this computer can open. Enter the address others use, such as this PC\'s network address.'
        : 'Links use ' + where + '.';
  }
  document.addEventListener('click', async e => {
    if (e.target.closest('.cfgitem[data-sec="general"]')) setTimeout(load, 50);
    if (!e.target.closest('#pubUrlSave')) return;
    const r = await fetch('/api/settings/public-url', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ public_url: document.getElementById('pubUrl').value }) });
    const j = await r.json().catch(() => ({}));
    if (r.ok) { paint(j); if (window.toast) toast('✓ Public address saved'); }
    else if (window.toast) toast('✕ ' + (j.error || 'Not saved'));
  });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', load); else load();
})();

/* Contract types get an icon, from what the type is called */
(function () {
  const RULES = [
    [/licen[cs]e|software|key/i, 'key'], [/subscri|saas|cloud|365|renew/i, 'refresh'],
    [/\bamc\b|maint|repair|support|service level|\bsla\b/i, 'wrench'], [/warrant|guarantee|insur/i, 'shieldcheck'],
    [/lease|rent|hire/i, 'file'], [/internet|isp|connect|line|telecom|\bsim\b|mobile/i, 'wifi'],
    [/domain|host|dns|ssl|certific/i, 'link'], [/support|helpdesk/i, 'headphones'], [/hardware|purchase/i, 'box'],
  ];
  window.contractTypeIcon = t => {
    let n = 'file';
    for (const [re, ic] of RULES) if (re.test(String(t || ''))) { n = ic; break; }
    return `<span class="ticon sm">${window.icon(n)}</span>`;
  };
})();

/* Change an asset's status from the list: click its pill */
(function () {
  window.openStatusMenu = function (e, id) {
    e.stopPropagation();
    const menu = document.getElementById('rowMenu'); if (!menu) return;
    const a = (typeof assets !== 'undefined' ? assets : []).find(x => x._id === id); if (!a) return;
    const key = 'st' + id;
    if (window.__statusMenuFor === key && menu.style.display !== 'none') { menu.style.display = 'none'; window.__statusMenuFor = null; return; }
    window.__statusMenuFor = key;
    const list = (typeof STATUSES !== 'undefined' ? STATUSES : []);
    const col = s => (typeof statusColor === 'function' ? statusColor(s) : 'var(--muted)');
    menu.innerHTML = '<div class="rm-head">Change status</div>' + list.map(s =>
      `<button type="button" class="rm-st${s === a.Status ? ' on' : ''}" data-s="${s}"><span class="rm-dot" style="background:${col(s)}"></span>${s}${s === a.Status ? window.icon('check', 'rm-ok') : ''}</button>`).join('');
    menu.querySelectorAll('.rm-st').forEach(b => b.onclick = ev => { ev.stopPropagation(); menu.style.display = 'none'; window.__statusMenuFor = null; setStatus(a, b.dataset.s); });
    const r = e.currentTarget.getBoundingClientRect();
    menu.style.display = 'flex';
    const mr = menu.getBoundingClientRect();
    let left = Math.min(r.left, window.innerWidth - mr.width - 8); if (left < 8) left = 8;
    let top = r.bottom + 6; if (top + mr.height > window.innerHeight - 8) top = r.top - mr.height - 6;
    menu.style.left = left + 'px'; menu.style.top = top + 'px';
  };
  async function setStatus(a, s) {
    if (s === a.Status) return;
    // checking out needs someone to check it out to: that is the form's job
    if (s === 'Checked-Out' && !(a.EmployeeID || '').trim()) {
      if (typeof openModal === 'function') {
        await openModal(a._id);
        const st = document.getElementById('f_Status'); if (st) { st.value = 'Checked-Out'; st.dispatchEvent(new Event('change')); }
        const emp = document.getElementById('f_EmployeeID'); if (emp) emp.focus();
        if (window.toast) toast('Pick who it is checked out to, then Save');
      }
      return;
    }
    if (s === 'Returned' && a.EmployeeID && !(await uiConfirm(`Mark "${a.Name || a.AssetTag}" as returned? It will be unassigned from its employee, and the signed copy marked RETURNED goes to them and to IT.`, { okLabel: 'Mark returned', danger: false }))) return;
    const r = await api('/api/assets/' + a._id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ Status: s }) });
    if (!r) return;
    if (!r.ok) { toast('✕ Not changed: ' + await apiError(r)); return; }
    toast('✓ ' + (a.AssetTag || a.Name || 'Asset') + ' is now ' + s);
    if (typeof load === 'function') load();
    if (typeof loadDashboard === 'function') loadDashboard();
  }
})();

/* Pictures: brand logos, model photos, an asset's own photo.
   What an asset shows, first one there wins:
     its own photo  >  its model's photo  >  its category's photo  >  the type icon
   and the brand's logo rides on the corner as a small badge. */
(function () {
  const escA = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  window.LOOKS = { brands: {}, models: {}, assets: {} };

  async function loadLooks() {
    try {
      const r = await fetch('/api/catalog/looks');
      if (!r.ok) return;
      window.LOOKS = await r.json();
      if (typeof render === 'function') { try { render(); } catch (e) { /* not on screen */ } }
    } catch (e) { /* offline or signed out: icons still work */ }
  }
  window.loadLooks = loadLooks;

  function picFor(a) {
    const L = window.LOOKS || {};
    const own = (L.assets || {})[a._id];
    if (own) return { url: own, from: 'asset' };
    const mk = String(a.Manufacturer || '').toLowerCase() + '|' + String(a.Model || '').toLowerCase();
    const mod = a.Model && ((L.models || {})[mk] || (L.models || {})['|' + String(a.Model).toLowerCase()]);
    if (mod) return { url: mod, from: 'model' };
    const cat = (window.CAT_PHOTOS || {})[String(a.Type || '')];
    if (cat) return { url: cat, from: 'category' };
    return null;
  }
  window.assetPicture = picFor;

  window.assetThumb = function (a) {
    const p = picFor(a);
    const logo = a.Manufacturer && ((window.LOOKS || {}).brands || {})[a.Manufacturer];
    const badge = logo ? `<img class="brand-badge" src="${escA(logo)}" alt="" title="${escA(a.Manufacturer)}" loading="lazy">` : '';
    if (p) return `<span class="ticon has-photo">${'<img src="' + escA(p.url) + '" alt="" loading="lazy">'}${badge}</span>`;
    return (window.typeIcon ? window.typeIcon(a.Type) : '').replace(/<\/span>$/, badge + '</span>');
  };

  // the catalogue's own tiles
  const initial = n => escA((String(n || '?').trim()[0] || '?').toUpperCase());
  window.brandTile = m => m.logo
    ? `<span class="ticon has-photo"><img src="${escA(m.logo)}" alt=""></span>`
    : `<span class="ticon ticon-letter">${initial(m.name)}</span>`;
  window.modelTile = m => m.photo
    ? `<span class="ticon has-photo"><img src="${escA(m.photo)}" alt=""></span>`
    : `<span class="ticon">${window.icon ? window.icon('image') : ''}</span>`;

  /* One dialog for every picture: upload, paste a link, or (brands) fetch
     the logo from the website. */
  function openPictureDialog(o) {
    const wrap = document.createElement('div');
    wrap.className = 'modal show ui-dialog';
    const prev = () => o.current
      ? `<span class="ticon has-photo pic-prev"><img src="${escA(o.current)}" alt=""></span>`
      : `<span class="ticon pic-prev">${window.icon ? window.icon(o.kind === 'brand' ? 'tag' : 'image') : ''}</span>`;
    wrap.innerHTML = `<div class="modal-box look-box pic-box" role="dialog" aria-modal="true">
      <h3>${escA(o.title)}</h3>
      <p class="sec-hint" style="margin:0 0 14px">${escA(o.hint)}</p>
      <div class="pic-top">
        <div class="pic-slot">${prev()}</div>
        <div class="pic-acts">
          <label class="btn ghost sm">${window.icon ? window.icon('upload') : ''}<span>Upload a picture</span><input type="file" accept="image/png,image/jpeg,image/webp,image/gif,image/x-icon" hidden></label>
          ${o.current ? `<button type="button" class="btn ghost sm danger" data-act="rm">${window.icon ? window.icon('trash') : ''}<span>Remove</span></button>` : ''}
        </div>
      </div>
      ${o.kind === 'brand' ? `<div class="pic-row"><label>From the brand's website</label>
        <div class="pic-inline"><input data-f="site" placeholder="e.g. dell.com" value="${escA(o.website || '')}"><button type="button" class="btn sm" data-act="site">Get logo</button></div></div>` : ''}
      <div class="pic-row"><label>From a link to a picture</label>
        <div class="pic-inline"><input data-f="url" placeholder="https://…/picture.png"><button type="button" class="btn sm ghost" data-act="url">Use link</button></div></div>
      <div class="pic-msg muted" aria-live="polite"></div>
      <div class="m-actions"><button type="button" class="btn ghost" data-act="close">Done</button></div></div>`;
    const msg = t => { wrap.querySelector('.pic-msg').textContent = t || ''; };
    const finish = () => { wrap.remove(); if (o.onDone) o.onDone(); loadLooks(); };
    const send = async (init, busy) => {
      msg(busy);
      wrap.querySelectorAll('button,input').forEach(b => b.disabled = true);
      try {
        const r = await fetch(`/api/img/${o.kind}/${encodeURIComponent(o.ref)}`, init);
        const j = await r.json().catch(() => ({}));
        if (!r.ok) { msg('✕ ' + (j.error || 'Not saved')); return; }
        if (window.toast) toast(init.method === 'DELETE' ? '✓ Picture removed' : '✓ Picture saved');
        finish();
      } finally { wrap.querySelectorAll('button,input').forEach(b => b.disabled = false); }
    };
    const json = body => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    wrap.addEventListener('click', e => {
      if (e.target === wrap || e.target.closest('[data-act="close"]')) return finish();
      const act = (e.target.closest('[data-act]') || {}).dataset;
      if (!act) return;
      if (act.act === 'rm') send({ method: 'DELETE' }, 'Removing…');
      if (act.act === 'site') { const v = wrap.querySelector('[data-f="site"]').value.trim(); if (v) send(json({ website: v }), 'Looking for the logo on ' + v + '…'); }
      if (act.act === 'url') { const v = wrap.querySelector('[data-f="url"]').value.trim(); if (v) send(json({ url: v }), 'Fetching the picture…'); }
    });
    wrap.addEventListener('keydown', e => {
      if (e.key !== 'Enter') return;
      const f = e.target.dataset && e.target.dataset.f;
      if (f) { e.preventDefault(); wrap.querySelector(`[data-act="${f}"]`).click(); }
    });
    wrap.querySelector('input[type=file]').addEventListener('change', e => {
      const f = e.target.files[0]; if (!f) return;
      const fd = new FormData(); fd.append('photo', f);
      send({ method: 'POST', body: fd }, 'Uploading…');
    });
    document.body.appendChild(wrap);
    const first = wrap.querySelector('[data-f="site"]') || wrap.querySelector('[data-f="url"]');
    if (first && o.kind === 'brand' && !o.current) first.focus();
  }
  window.openPictureDialog = openPictureDialog;

  window.openBrandLogo = function (id) {
    const m = (window.__MFRS || []).find(x => x.id === id); if (!m) return;
    openPictureDialog({ kind: 'brand', ref: id, title: m.name + ' logo', current: m.logo, website: m.website,
      hint: 'Shown on every ' + m.name + ' asset. Type the brand\'s website and IT-Vault finds the logo for you, or upload one.',
      onDone: () => { if (typeof loadCatManufacturers === 'function') loadCatManufacturers(); } });
  };
  window.openModelPhoto = function (id) {
    const m = (window.__MODELS || []).find(x => x.id === id); if (!m) return;
    openPictureDialog({ kind: 'model', ref: id, title: (m.manufacturer ? m.manufacturer + ' ' : '') + m.name, current: m.photo,
      hint: 'The product photo for this model. Every asset of this model shows it, unless the asset has a photo of its own.',
      onDone: () => { if (typeof loadCatModels === 'function') loadCatModels(); } });
  };

  /* The asset form's photo box */
  let pending = null;
  window.renderAssetPhotoBox = function (id, a) {
    const box = document.getElementById('assetPhotoBox'); if (!box) return;
    pending = null;
    const p = id ? picFor(a || {}) : null;
    const from = { asset: 'This asset\'s own photo.', model: 'Using the photo of its model, from the Product Catalog.',
                   category: 'Using its category\'s photo, from the Product Catalog.' };
    const draw = () => {
      const has = p && p.from === 'asset';
      box.innerHTML = `<label>PHOTO</label>
        <div class="pic-top">
          <div class="pic-slot">${pending ? '<span class="ticon has-photo pic-prev"><img id="apPrev" alt=""></span>'
            : p ? `<span class="ticon has-photo pic-prev"><img src="${escA(p.url)}" alt=""></span>`
            : `<span class="ticon pic-prev">${window.typeIcon ? '' : ''}${window.icon ? window.icon('image') : ''}</span>`}</div>
          <div class="pic-side">
            <div class="muted pic-note">${pending ? 'Saved with the asset.' : p ? from[p.from] : 'No photo yet. Add one here, or give its model a photo in the Product Catalog and every asset of that model gets it.'}</div>
            <div class="pic-acts">
              <label class="btn ghost sm">${window.icon ? window.icon('upload') : ''}<span>${has || pending ? 'Replace photo' : 'Add a photo'}</span><input type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden></label>
              ${has ? '<button type="button" class="btn ghost sm danger" data-act="rm">' + (window.icon ? window.icon('trash') : '') + '<span>Remove</span></button>' : ''}
            </div>
          </div>
        </div>`;
      if (pending) { const rd = new FileReader(); rd.onload = () => { const i = document.getElementById('apPrev'); if (i) i.src = rd.result; }; rd.readAsDataURL(pending); }
      // tap the picture to see it full size
      const shown = box.querySelector('.pic-slot img');
      if (shown) { shown.parentElement.classList.add('zoomable'); shown.parentElement.title = 'View photo';
        shown.parentElement.onclick = () => window.openPhotoViewer(shown.src, (a && a.Name) || 'Photo'); }
      box.querySelector('input[type=file]').addEventListener('change', async e => {
        const f = e.target.files[0]; if (!f) return;
        if (!id) { pending = f; draw(); return; }          // a new asset: sent once it is saved
        const fd = new FormData(); fd.append('photo', f);
        const r = await fetch(`/api/img/asset/${encodeURIComponent(id)}`, { method: 'POST', body: fd });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) { if (window.toast) toast('✕ ' + (j.error || 'Photo not saved')); return; }
        if (window.toast) toast('✓ Photo saved');
        await loadLooks(); window.renderAssetPhotoBox(id, a);
      });
      const rm = box.querySelector('[data-act="rm"]');
      if (rm) rm.addEventListener('click', async () => {
        const r = await fetch(`/api/img/asset/${encodeURIComponent(id)}`, { method: 'DELETE' });
        if (r.ok) { if (window.toast) toast('✓ Photo removed'); await loadLooks(); window.renderAssetPhotoBox(id, a); }
      });
    };
    draw();
  };
  window.uploadPendingAssetPhoto = async function (newId) {
    if (!pending) return;
    const fd = new FormData(); fd.append('photo', pending); pending = null;
    const r = await fetch(`/api/img/asset/${encodeURIComponent(newId)}`, { method: 'POST', body: fd });
    if (!r.ok && window.toast) toast('⚠ Saved, but the photo was not: ' + ((await r.json().catch(() => ({}))).error || 'try again'));
    loadLooks();
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', loadLooks); else loadLooks();
})();

/* A picture, full size, over the page. Click anywhere or press Esc to close. */
window.openPhotoViewer = function (src, title) {
  if (!src) return;
  const v = document.createElement('div');
  v.className = 'photo-viewer';
  v.innerHTML = `<figure><img src="${String(src).replace(/"/g, '&quot;')}" alt=""><figcaption>${String(title || '').replace(/[<>&]/g, '')}</figcaption></figure><button type="button" class="pv-x" aria-label="Close">✕</button>`;
  const close = () => { v.remove(); document.removeEventListener('keydown', esc); };
  const esc = e => { if (e.key === 'Escape') close(); };
  v.addEventListener('click', close); document.addEventListener('keydown', esc);
  document.body.appendChild(v);
};
