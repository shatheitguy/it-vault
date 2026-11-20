// IT-Vault -- self-hosted IT asset and helpdesk manager.
// Copyright (C) 2026 Sharqan Ahamed (Sha The IT Guy)
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The WhatsApp link (Settings -> Notifications -> WhatsApp).
//
// An admin scans a QR with the company's WhatsApp (Linked devices), and from
// then on the server sends acknowledgement links and signed PDFs to employees
// on its own -- the same way WhatsApp Web does, through the Baileys library.
//
// Baileys is Node and IT-Vault is Python, so this is a small helper process the
// Python server starts (wa.py) and talks to over 127.0.0.1 only, with a token
// it hands over in the environment. Nothing else can reach it.
//
// WhatsApp does not allow this officially: a number that sends a lot of
// messages can be blocked. So messages go one at a time, a few seconds apart,
// and only ever to the install's own employees.
import fs from 'fs'
import path from 'path'
import http from 'http'
import crypto from 'crypto'

const PORT = Number(process.env.WA_PORT) || 0
const TOKEN = process.env.WA_TOKEN || ''
const DIR = process.env.WA_DIR || path.resolve('wa-auth')
const KEY = Buffer.from(process.env.WA_KEY || '', 'hex')
const PARENT = Number(process.env.ITVAULT_PPID) || 0

if (!TOKEN || KEY.length !== 32) {
  console.error('[whatsapp] started without WA_TOKEN / WA_KEY -- refusing to run')
  process.exit(2)
}

/* ---- the linked device's keys, locked ----
   The same files Baileys keeps (creds.json and one file per key), but each one
   encrypted with AES-256-GCM under a key derived from the server's own secret.
   A copy of the folder on its own can't be used to act as the linked phone.
   A file that can't be opened (the secret changed) counts as missing, and
   WhatsApp simply asks for a new QR. */
const PREFIX = 'itv1:'
const isLocked = s => typeof s === 'string' && s.startsWith(PREFIX)
function lock(text) {
  const iv = crypto.randomBytes(12)
  const c = crypto.createCipheriv('aes-256-gcm', KEY, iv)
  const ct = Buffer.concat([c.update(text, 'utf8'), c.final()])
  return PREFIX + Buffer.concat([iv, c.getAuthTag(), ct]).toString('base64')
}
function unlock(s) {
  try {
    const b = Buffer.from(s.slice(PREFIX.length), 'base64')
    const d = crypto.createDecipheriv('aes-256-gcm', KEY, b.subarray(0, 12))
    d.setAuthTag(b.subarray(12, 28))
    return Buffer.concat([d.update(b.subarray(28)), d.final()]).toString('utf8')
  } catch { return null }
}

async function useLockedAuthState(dir, B) {
  const { BufferJSON, initAuthCreds, proto } = B
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 })
  const fileOf = name => path.join(dir, name.replace(/\//g, '__').replace(/:/g, '-'))
  // one read / write at a time per file: Baileys asks for many keys at once
  const chains = new Map()
  const serial = (p, job) => {
    const run = (chains.get(p) || Promise.resolve()).then(job, job)
    chains.set(p, run.catch(() => {}))
    return run
  }
  const write = (data, name) => {
    const p = fileOf(name)
    return serial(p, async () => {
      // a temporary file put in place: a crash never leaves half a file
      const tmp = `${p}.${process.pid}.tmp`
      await fs.promises.writeFile(tmp, lock(JSON.stringify(data, BufferJSON.replacer)), { mode: 0o600 })
      await fs.promises.rename(tmp, p)
    })
  }
  const read = name => {
    const p = fileOf(name)
    return serial(p, async () => {
      try {
        const raw = await fs.promises.readFile(p, 'utf8')
        const json = isLocked(raw) ? unlock(raw) : raw
        return json ? JSON.parse(json, BufferJSON.reviver) : null
      } catch { return null }
    })
  }
  const remove = name => {
    const p = fileOf(name)
    return serial(p, () => fs.promises.rm(p, { force: true }))
  }
  const creds = (await read('creds.json')) || initAuthCreds()
  return {
    state: {
      creds,
      keys: {
        get: async (type, ids) => {
          const out = {}
          await Promise.all(ids.map(async id => {
            let v = await read(`${type}-${id}.json`)
            if (type === 'app-state-sync-key' && v) v = proto.Message.AppStateSyncKeyData.fromObject(v)
            out[id] = v
          }))
          return out
        },
        set: async data => {
          const jobs = []
          for (const cat in data) for (const id in data[cat]) {
            const v = data[cat][id]
            jobs.push(v ? write(v, `${cat}-${id}.json`) : remove(`${cat}-${id}.json`))
          }
          await Promise.all(jobs)
        },
      },
    },
    saveCreds: () => write(creds, 'creds.json'),
  }
}

/* ---- the connection ---- */
const st = { sock: null, status: 'off', qr: null, me: null, error: null, want: false, tries: 0, queue: Promise.resolve(), starting: false, timer: null }
const linked = () => fs.existsSync(path.join(DIR, 'creds.json'))
function wipe() { try { fs.rmSync(DIR, { recursive: true, force: true }) } catch { /* gone already */ } }

async function start() {
  st.want = true
  if (st.timer) { clearTimeout(st.timer); st.timer = null }
  // st.sock is only set after several awaits, so a second start() in that
  // window (the helper's own resume plus a Link click) opened a second socket
  // on the same keys; WhatsApp then replaced one and its close handler wiped
  // the state of the live one. The flag is set before the first await.
  if (st.starting || (st.sock && st.status !== 'off')) return
  st.starting = true
  st.status = 'connecting'; st.error = null
  try {
    const B = await import('@whiskeysockets/baileys')
    const makeWASocket = B.makeWASocket || B.default
    const { state, saveCreds } = await useLockedAuthState(DIR, B)
    const pino = (await import('pino')).default
    let version
    try { version = (await B.fetchLatestBaileysVersion()).version } catch { /* the built-in one */ }
    const sock = makeWASocket({
      auth: state, version, printQRInTerminal: false, browser: B.Browsers.windows('Desktop'),
      logger: pino({ level: 'silent' }), markOnlineOnConnect: false, syncFullHistory: false,
      shouldSyncHistoryMessage: () => false, generateHighQualityLinkPreview: false,
    })
    st.sock = sock
    st.starting = false
    sock.ev.on('creds.update', saveCreds)
    sock.ev.on('connection.update', u => {
      if (st.sock !== sock) return          // an old socket's late events change nothing
      if (u.qr) { st.status = 'qr'; st.qr = u.qr }
      if (u.connection === 'open') {
        st.status = 'on'; st.qr = null; st.tries = 0; st.error = null
        st.me = String(sock.user?.id || '').split(':')[0].split('@')[0] || null
        console.log('[whatsapp] linked', st.me ? `+${st.me}` : '')
      }
      if (u.connection === 'close') {
        const code = Number(u.lastDisconnect?.error?.output?.statusCode) || 0
        st.sock = null; st.status = 'off'; st.qr = null
        if (code === B.DisconnectReason.loggedOut) {
          // unlinked from the phone: the next link starts from a new QR
          wipe(); st.me = null; st.want = false; st.error = 'logged_out'
          console.log('[whatsapp] unlinked from the phone')
          return
        }
        if (code === B.DisconnectReason.connectionReplaced) {
          // another copy of this link took over (a restart that overlapped):
          // reconnecting would only knock that one off in turn
          st.want = false; st.error = 'replaced'
          console.log('[whatsapp] replaced by another session of this link; standing down')
          return
        }
        // A linked phone is retried for as long as it stays linked: 3s, 6s,
        // 12s ... then every 5 minutes. Giving up after eight tries (about two
        // minutes) meant a router reboot switched WhatsApp off until someone
        // pressed Link again. A QR nobody scans still stops after three.
        if (st.want && (linked() || st.tries < 3)) {
          st.tries++
          const wait = Math.min(300_000, 3000 * 2 ** Math.min(st.tries - 1, 7))
          st.timer = setTimeout(() => { st.timer = null; if (st.want) void start() }, wait)
        } else st.want = false
      }
    })
  } catch (e) {
    st.sock = null; st.status = 'off'; st.error = String(e?.message || e).slice(0, 200)
    console.error('[whatsapp]', st.error)
  } finally {
    st.starting = false
  }
}

async function logout() {
  st.want = false
  if (st.timer) { clearTimeout(st.timer); st.timer = null }   // or the pending retry relinks
  try { await st.sock?.logout() } catch { /* already gone */ }
  try { st.sock?.end?.(undefined) } catch { /* closed */ }
  st.sock = null; st.status = 'off'; st.qr = null; st.me = null; st.error = null
  wipe()
}

/** One message at a time, 3 seconds apart -- WhatsApp blocks numbers that send fast.
 *  'ok' | 'not_linked' | 'not_on_whatsapp' | 'bad_number' | 'failed' */
function send({ number, text, document, fileName, caption, image, imageType }) {
  const num = String(number || '').replace(/\D/g, '')
  if (num.length < 8 || num.length > 15) return Promise.resolve('bad_number')
  if (st.status !== 'on' || !st.sock) return Promise.resolve('not_linked')
  const job = st.queue.then(async () => {
    try {
      const [r] = (await st.sock.onWhatsApp(num)) || []
      if (!r?.exists) return 'not_on_whatsapp'
      if (document) {
        await st.sock.sendMessage(r.jid, {
          document: Buffer.from(document, 'base64'), mimetype: 'application/pdf',
          fileName: String(fileName || 'document.pdf').slice(0, 120),
          caption: String(caption || text || '').slice(0, 1500) || undefined,
        })
      } else if (image) {
        // the banner: the message rides on it as the caption
        await st.sock.sendMessage(r.jid, {
          image: Buffer.from(image, 'base64'), mimetype: String(imageType || 'image/jpeg'),
          caption: String(caption || text || '').slice(0, 1500) || undefined,
        })
      } else {
        await st.sock.sendMessage(r.jid, { text: String(text || '').slice(0, 1500) })
      }
      return 'ok'
    } catch (e) {
      console.error('[whatsapp] send', e?.message || e)
      return 'failed'
    }
  })
  // the gap holds back the NEXT message, not this answer: whoever pressed
  // Send hears back the moment WhatsApp took it
  st.queue = job.catch(() => {}).then(() => new Promise(res => setTimeout(res, 3000)))
  return job
}

/* ---- the local API the Python server calls ---- */
function body(req) {
  return new Promise((res, rej) => {
    const parts = []; let n = 0
    req.on('data', c => { n += c.length; if (n > 25 * 1024 * 1024) { rej(new Error('too large')); req.destroy() } else parts.push(c) })
    req.on('end', () => { try { res(parts.length ? JSON.parse(Buffer.concat(parts).toString('utf8')) : {}) } catch (e) { rej(e) } })
    req.on('error', rej)
  })
}
const reply = (res, code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(obj)) }
const status = () => ({ status: st.status, qr: st.status === 'qr' ? st.qr : null, me: st.me, error: st.error, linked: linked() })

const server = http.createServer(async (req, res) => {
  const tk = req.headers['x-wa-token'] || ''
  if (tk.length !== TOKEN.length || !crypto.timingSafeEqual(Buffer.from(tk), Buffer.from(TOKEN))) return reply(res, 403, { error: 'forbidden' })
  try {
    if (req.method === 'GET' && req.url === '/status') return reply(res, 200, status())
    if (req.method === 'POST' && req.url === '/start') { await start(); return reply(res, 200, status()) }
    if (req.method === 'POST' && req.url === '/logout') { await logout(); return reply(res, 200, status()) }
    if (req.method === 'POST' && req.url === '/send') return reply(res, 200, { result: await send(await body(req)) })
    return reply(res, 404, { error: 'not found' })
  } catch (e) {
    return reply(res, 500, { error: String(e?.message || e).slice(0, 200) })
  }
})

server.listen(PORT, '127.0.0.1', () => {
  const port = server.address().port
  // the Python side reads this line to learn the port it was given
  console.log(`[whatsapp] bridge listening on 127.0.0.1:${port}`)
  if (linked()) void start()
})

// When IT-Vault stops, this stops with it -- otherwise a restart would find a
// second copy still holding the WhatsApp session.
if (PARENT) {
  setInterval(() => {
    try { process.kill(PARENT, 0) } catch { process.exit(0) }
  }, 5000).unref()
}
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => { try { st.sock?.end?.(undefined) } catch { } process.exit(0) })
