const fs = require('fs');
const { JSDOM } = require('jsdom');
const BASE = 'http://127.0.0.1:5000';
const html = fs.readFileSync('index.html', 'utf8');
const js = fs.readFileSync('app.js', 'utf8');
let errors = [];
const dom = new JSDOM(html, {
  runScripts: 'outside-only', resources: undefined, url: BASE + '/',
  beforeParse(window){
    window.fetch = (u, opt) => fetch(String(u).startsWith('/') ? BASE+u : u, opt);
    window.matchMedia = q => ({ matches:false, media:q, addEventListener(){}, removeEventListener(){}, addListener(){}, removeListener(){} });
  }
});
const { window } = dom;
window.addEventListener('error', e => errors.push(e.error ? e.error.message : e.message));
try { window.eval(js); } catch(e){ errors.push('eval: '+e.message); }
const results = [];
function check(n, c, e){ results.push((c?'PASS':'FAIL')+'  '+n+(e?'  '+e:'')); }

// wireModalClose runs in IIFE; if it bailed (no /api/me), call manually
try { window.wireModalClose(); } catch(e){ errors.push('wireModalClose: '+e.message); }

const settings = window.document.getElementById('profile');   // Settings modal
const userModal = window.document.getElementById('userModal'); // Add/Edit User modal
check('modals exist', !!settings && !!userModal);

// open Settings first
settings.classList.add('show');
const z1 = parseInt(window.getComputedStyle(settings).zIndex) || 0;
// open Add User on top
userModal.classList.add('show');
const z2 = parseInt(window.getComputedStyle(userModal).zIndex) || 0;
check('Add User modal has higher z-index than Settings', z2 > z1, `settings=${z1} user=${z2}`);
// both visible
check('both modals .show', settings.classList.contains('show') && userModal.classList.contains('show'));

console.log(results.join('\n'));
console.log('JS errors:', errors.length ? errors.join(' | ') : 'none');
