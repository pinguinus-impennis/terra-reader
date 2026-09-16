/* Terra Reader — app (TOC + player) */
(() => {
'use strict';

/* ---------------- sources ---------------- */
const SRC = {
  text: 'https://raw.githubusercontent.com/ArknightsAssets/ArknightsGamedata/master/jp/gamedata/story/',
  img:  'raw.githubusercontent.com/ArknightsAssets/ArknightsAssets2/cn/assets/dyn/avg/',
  proxy: 'https://wsrv.nl/?url=',
};
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
const $ = id => document.getElementById(id);

/* ---------------- settings / progress ---------------- */
const store = {
  get(k, d){ try{ const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); }catch(e){ return d; } },
  set(k, v){ try{ localStorage.setItem(k, JSON.stringify(v)); }catch(e){} },
  del(k){ try{ localStorage.removeItem(k); }catch(e){} },
};
const settings = Object.assign({ doc: 'ドクター', font: 16, proxy: true, sys: false, faces: true, band: false }, store.get('tr:settings', {}));
function saveSettings(){ store.set('tr:settings', settings); applySettings(); }
function applySettings(){ document.documentElement.style.setProperty('--fs', settings.font + 'px'); }
const progress = {
  get(id){ return store.get('tr:pos:' + id, null); },
  set(id, v){ store.set('tr:pos:' + id, v); },
  clearAll(){ Object.keys(localStorage).filter(k => k.startsWith('tr:pos:')).forEach(k => store.del(k)); },
};

/* ---------------- data ---------------- */
let INDEX = null, SPRITES = {}, BGM = {}, FACES = {};
async function loadData(){
  const [i, s, b, f] = await Promise.all([
    fetch('data/index.json').then(r => r.json()),
    fetch('data/sprites.json').then(r => r.json()).catch(() => ({})),
    fetch('data/bgm.json').then(r => r.json()).catch(() => ({})),
    fetch('data/faces.json').then(r => r.json()).catch(() => ({})),
  ]);
  INDEX = i; SPRITES = s; BGM = b; FACES = f;
  $('tocSub').textContent = 'ja_JP · ' + INDEX.generated + ' · ' + INDEX.groups.reduce((n, g) => n + g.eps.length, 0) + ' 話';
}
const allEps = () => INDEX.groups.flatMap(g => g.eps.map(e => ({ ...e, g })));
function findEp(id){ return allEps().find(e => e.id === id) || null; }
function nextEp(id){ const a = allEps(); const k = a.findIndex(e => e.id === id); for(let j = k + 1; j < a.length; j++){ if(!a[j].missing) return a[j]; } return null; }

/* ---------------- image URLs ---------------- */
function rawUrl(path){ return 'https://' + SRC.img + path.split('/').map(encodeURIComponent).join('/'); }
function proxied(path, q){ return SRC.proxy + encodeURIComponent(SRC.img + path) + q + '&output=webp&q=80&il'; }
function urlsFor(kind, path){
  const q = kind === 'sprite' ? '&h=720' : '&w=1000';
  const list = [];
  if(settings.proxy && !path.includes('#')) list.push(proxied(path, q));   // wsrv.nl cannot fetch paths with '#'
  list.push(rawUrl(path));
  return list;
}
function spriteCandidates(name){
  const n = String(name).trim().toLowerCase();
  const hit = SPRITES[n]; if(hit) return ['characters/' + hit + '.png'];
  const base = n.split('#')[0].split('$')[0];
  const out = [`characters/${base}/${n}.png`, `characters/${n}.png`];
  let m = /^(.*)_1#0*(\d+)(\$\d+)?$/.exec(n);
  if(m) out.push(`characters/${m[1]}_1/${m[1]}_${m[2]}.png`, `characters/${m[1]}_${m[2]}.png`);
  m = /^(.*)#0*(\d+)(\$\d+)?$/.exec(n);
  if(m) out.push(`characters/${m[1]}/${m[1]}_${m[2]}.png`, `characters/${m[1]}/${m[1]}#${m[2]}$1.png`);
  if(!n.includes('#')) out.push(`characters/${n}_1/${n}_1.png`, `characters/${n}/${n}#1$1.png`);
  return out;
}
/* load an <img> trying a list of urls in order; resolves true/false */
function loadInto(img, urls){
  return new Promise(res => {
    let k = 0;
    const tryNext = () => { if(k >= urls.length){ res(-1); return; } img.onerror = () => { k++; tryNext(); }; img.onload = () => res(k); img.src = urls[k]; };
    tryNext();
  });
}
/* sprite set key: same body, different expressions share one face record */
function setKey(path){
  path = path.replace(/^characters\//, '').replace(/\.png$/i, '');
  const i = path.lastIndexOf('/'); const d = i >= 0 ? path.slice(0, i) : ''; let f = i >= 0 ? path.slice(i + 1) : path;
  if(f.includes('#')) f = f.replace(/#\d+/, ''); else if(f.includes('$')) { /* body file */ } else if(d) f = d;
  return d ? d + '/' + f : f;
}
const preloadCache = new Map();
function preload(urls){ const u = urls[0]; if(preloadCache.has(u)) return; const im = new Image(); preloadCache.set(u, im); loadInto(im, urls); }

/* ---------------- routing ---------------- */
function route(){
  const h = location.hash;
  let m;
  if((m = /^#\/r\/(.+)$/.exec(h))) openStory(decodeURIComponent(m[1]));
  else showToc((m = /^#\/g\/(.+)$/.exec(h)) ? decodeURIComponent(m[1]) : null);
}
addEventListener('hashchange', route);

/* =====================================================================
   TOC
   ===================================================================== */
const toc = { tab: store.get('tr:tab', 'main'), open: new Set(store.get('tr:open', [])), q: '' };
function showToc(openId){
  player.stop();
  document.body.classList.remove('playing');
  $('stage').hidden = true; $('toc').hidden = false;
  if(openId){ const g = INDEX.groups.find(g => g.id === openId); if(g){ toc.tab = g.kind === 'mini' ? 'event' : g.kind; toc.open.add(openId); } }
  renderToc();
  if(openId){ const el = document.querySelector(`[data-g="${CSS.escape(openId)}"]`); if(el) el.scrollIntoView({ block: 'start' }); }
}
function statusOf(ep){
  if(ep.missing) return { cls: 'miss', txt: '配信外' };
  const p = progress.get(ep.id); if(!p) return { cls: '', txt: '' };
  if(p.done) return { cls: 'done', txt: '読了' };
  if(p.total) return { cls: 'now', txt: Math.round((p.i + 1) / p.total * 100) + '%' };
  return { cls: 'now', txt: '途中' };
}
function renderToc(){
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === toc.tab));
  const q = toc.q.trim().toLowerCase();
  const kinds = toc.tab === 'event' ? ['event', 'mini'] : [toc.tab];
  const wrap = $('groups'); wrap.innerHTML = '';
  let shown = 0;
  for(const g of INDEX.groups){
    if(!kinds.includes(g.kind)) continue;
    const eps = q ? g.eps.filter(e => (e.name + ' ' + e.code + ' ' + g.name).toLowerCase().includes(q)) : g.eps;
    if(!eps.length) continue;
    shown++;
    const open = q ? true : toc.open.has(g.id) || (g.kind === 'record');
    const card = document.createElement('section'); card.className = 'chap'; card.dataset.g = g.id;
    const done = g.eps.filter(e => progress.get(e.id)?.done).length;
    const h = document.createElement('button'); h.className = 'h';
    h.innerHTML = `<span class="code"></span><span class="nm"></span><span class="cnt"><b></b>${g.eps.length} 話</span>`;
    h.querySelector('.code').textContent = g.code || (g.kind === 'mini' ? 'MINI' : g.kind === 'event' ? 'EVENT' : '');
    h.querySelector('.nm').textContent = g.name;
    h.querySelector('.cnt b').textContent = done ? done + ' / ' : '';
    h.addEventListener('click', () => { if(toc.open.has(g.id)) toc.open.delete(g.id); else toc.open.add(g.id); store.set('tr:open', [...toc.open]); renderToc(); });
    card.appendChild(h);
    if(open){
      const list = document.createElement('div'); list.className = 'eps';
      for(const e of eps){
        const st = statusOf(e);
        const b = document.createElement('button'); b.className = 'ep' + (st.cls === 'now' ? ' now' : '') + (e.missing ? ' miss' : '');
        b.innerHTML = `<span class="id"></span><span class="ttl"></span><span class="tag"></span><span class="st"></span>`;
        b.querySelector('.id').textContent = e.code || '';
        b.querySelector('.ttl').textContent = e.name || e.code || e.id;
        const tag = b.querySelector('.tag'); if(e.tag && g.kind !== 'record') tag.textContent = e.tag; else tag.remove();
        const s = b.querySelector('.st'); s.textContent = st.txt; if(st.cls) s.classList.add(st.cls);
        b.disabled = !!e.missing;
        b.addEventListener('click', () => { location.hash = '#/r/' + encodeURIComponent(e.id); });
        list.appendChild(b);
      }
      card.appendChild(list);
    }
    wrap.appendChild(card);
  }
  if(!shown){ const d = document.createElement('div'); d.className = 'empty'; d.textContent = '該当なし'; wrap.appendChild(d); }
}
$('tabs').addEventListener('click', e => { const b = e.target.closest('button'); if(!b) return; toc.tab = b.dataset.tab; store.set('tr:tab', toc.tab); renderToc(); });
$('search').addEventListener('input', e => { toc.q = e.target.value; renderToc(); });

/* =====================================================================
   PLAYER
   ===================================================================== */
const el = {};
['stage','visual','bgA','bgB','spL','spM','spR','still','stillImg','bgm','code','feed','cur','fill','knob','rail','btnAuto','btnPeek','btnBack','loading'].forEach(id => el[id] = $(id));

const player = {
  ep: null, steps: [], total: 0, i: -1, chosen: null, branch: null, auto: false,
  typing: null, finishTyping: null, autoTimer: null, instant: false, current: null, waiting: false, done: false, bgSlot: 0, token: 0,
  stop(){ this.stopTyping(); this.setAuto(false); this.token++; },
  stopTyping(){ if(this.typing){ clearTimeout(this.typing); this.typing = null; this.finishTyping = null; } clearTimeout(this.autoTimer); },
  setAuto(on){ this.auto = on; el.btnAuto.classList.toggle('on', on); if(on && !this.typing && !this.waiting && !this.done) this.autoTimer = setTimeout(() => next(), 700); else clearTimeout(this.autoTimer); },
};

/* ---- layout ---- */
function layout(){
  const seam = 72;
  el.stage.classList.toggle('band', !!settings.band);
  const h = (settings.band || el.stage.classList.contains('hasStill')) ? el.stage.clientWidth * 9 / 16 + seam : el.stage.clientHeight * 0.50 + seam * 0.6;
  el.visual.style.height = Math.round(h) + 'px';
  // newest line rests a little above the middle of the text panel
  const panelH = el.stage.clientHeight - h + seam - 22;
  el.stage.style.setProperty('--feedpad', Math.round(panelH * 0.5) + 'px');
  placeSprites();
}
addEventListener('resize', layout);

/* ---- visuals ---- */
function setBg(name){
  const cur = player.bgSlot ? el.bgB : el.bgA, nxt = player.bgSlot ? el.bgA : el.bgB;
  if(!name){ el.bgA.classList.remove('on'); el.bgB.classList.remove('on'); return; }
  if(cur.classList.contains('on') && cur.dataset.name === name) return;
  nxt.dataset.name = name;
  loadInto(nxt, urlsFor('bg', `backgrounds/${name.toLowerCase()}.png`)).then(k => { const ok = k >= 0; if(ok && nxt.dataset.name === name){ nxt.classList.add('on'); cur.classList.remove('on'); } });
  player.bgSlot ^= 1;
}
function setStill(name){
  if(!name){ el.still.classList.remove('on'); el.stage.classList.remove('hasStill'); layout(); return; }
  el.stillImg.dataset.name = name;
  loadInto(el.stillImg, urlsFor('still', `images/${name.toLowerCase()}.png`)).then(k => {
    if(k < 0 || el.stillImg.dataset.name !== name) return;
    el.still.classList.add('on'); el.stage.classList.add('hasStill'); layout();
  });
}
function setChars(chars, focus){
  const c = chars || { l: null, m: null, r: null };
  player.charState = { chars: c, focus: focus || 'all' };
  const shown = ['l','m','r'].filter(k => c[k]);
  const three = shown.length === 3;
  const pos = (k) => three ? k : (shown.length === 2 ? (k === shown[0] ? 'l' : 'r') : 'm');
  for(const k of ['l','m','r']){
    const img = el['sp' + k.toUpperCase()], name = c[k];
    if(!name){ img.classList.remove('on'); img.style.cssText = ''; continue; }
    img.className = 'sp on p' + pos(k) + (three ? ' three' : '');
    if(img.dataset.name !== name){
      const paths = spriteCandidates(name);
      const sameBody = img.dataset.path && setKey(img.dataset.path) === setKey(paths[0]);
      img.dataset.name = name; if(!sameBody){ img.dataset.path = ''; img.style.cssText = ''; img.classList.remove('fx'); }
      const list = paths.flatMap(p => urlsFor('sprite', p).map(u => ({ u, p })));
      loadInto(img, list.map(x => x.u)).then(idx => {
        if(img.dataset.name !== name) return;
        if(idx < 0){ img.classList.remove('on'); return; }
        img.dataset.path = list[idx].p; placeSprites();
      });
    }
  }
  placeSprites();
}
/* face-anchored placement: equal face size, height shown as head offset, 3 people staged in depth */
function placeSprites(){
  const st = player.charState; if(!st) return;
  const c = st.chars, focus = st.focus;
  const shown = ['l','m','r'].filter(k => c[k]); const n = shown.length; if(!n) return;
  const W = el.stage.clientWidth, VH = el.visual.clientHeight, u = W / 400;
  const loaded = shown.filter(k => el['sp' + k.toUpperCase()].classList.contains('on'));
  const front = n === 3 ? ((focus && loaded.includes(focus)) ? focus : (loaded.includes('m') ? 'm' : (loaded[0] || 'm'))) : null;
  const xs = n === 1 ? [.5] : n === 2 ? [.23, .77] : [.15, .5, .85];
  shown.forEach((k, i) => {
    const img = el['sp' + k.toUpperCase()];
    const isSide = n === 3 && k !== front;
    const dim = isSide || focus === 'none' || (n > 1 && focus && focus !== 'all' && focus !== 'keep' && focus !== k);
    img.classList.toggle('dim', dim); img.classList.toggle('front', n === 3 && k === front);
    const f = (settings.faces && img.dataset.path) ? FACES[setKey(img.dataset.path)] : null;
    if(!f || f[0] == null || !img.naturalHeight){ img.classList.remove('fx'); img.style.cssText = ''; return; }
    const FACE = u * (n === 1 ? 88 : n === 2 ? 72 : (isSide ? 52 : 64));
    const eye = VH * (isSide ? .40 : .36);
    const heads = (f[4] - f[1]) / f[2];
    const off = Math.max(-0.7 * FACE, Math.min(0.7 * FACE, 0.45 * (heads - 7.4) * FACE));
    const s = FACE / (f[2] * img.naturalHeight);
    const h = img.naturalHeight * s, w = img.naturalWidth * s;
    let top = eye - off - f[1] * h;
    const figTop = top + f[3] * h;                       // keep tall hats/horns mostly inside the frame
    if(figTop < -0.10 * VH) top += Math.min(-0.10 * VH - figTop, 0.45 * FACE);
    img.classList.add('fx');
    img.style.height = h + 'px'; img.style.width = w + 'px';
    img.style.left = (W * xs[i] - f[0] * w) + 'px'; img.style.top = top + 'px';
  });
}
function setBgm(key){
  if(key === null || key === undefined){ el.bgm.hidden = true; return; }
  const k = String(key).replace(/^\$/, '');
  el.bgm.hidden = false; el.bgm.textContent = '♪ ' + (BGM[k] || k.replace(/^(m_dia_|m_sys_|m_bat_)/, '').replace(/_(loop|intro)$/, ''));
}
function applyVisuals(st){
  if('bg' in st) setBg(st.bg);
  if('still' in st) setStill(st.still);
  if('chars' in st) setChars(st.chars, st.focus || 'all');
  if('bgm' in st) setBgm(st.bgm);
}
function preloadAhead(from){
  let n = 0;
  for(let k = from + 1; k < player.steps.length && n < 4; k++){
    const st = player.steps[k];
    if(st.bg) preload(urlsFor('bg', `backgrounds/${st.bg.toLowerCase()}.png`));
    if(st.still) preload(urlsFor('still', `images/${st.still.toLowerCase()}.png`));
    if(st.chars) Object.values(st.chars).filter(Boolean).forEach(nm => preload(spriteCandidates(nm).flatMap(p => urlsFor('sprite', p))));
    if(st.bg || st.still || st.chars) n++;
  }
}
function seek(){
  const p = Math.max(0, Math.min(1, (player.i + 1) / player.total));
  el.fill.style.width = (p * 100) + '%'; el.knob.style.left = (p * 100) + '%';
}

/* ---- feed ---- */
function clean(t){ return (t || '').replace(/\{@nickname\}/gi, settings.doc).replace(/\{@[^}]+\}/g, ''); }
function scrollEnd(){ el.feed.scrollTop = el.feed.scrollHeight; }
function markPast(){ if(player.current){ player.current.classList.add('past'); player.current = null; } }
function addLine(st, instant){
  markPast();
  const kind = st.kind || (st.spk ? 'line' : 'nar');
  const ln = document.createElement('div'); ln.className = 'ln ' + (kind === 'line' ? '' : kind);
  if(st.spk){ const s = document.createElement('div'); s.className = 'spk'; s.textContent = st.spk; ln.appendChild(s); }
  const t = document.createElement('div'); t.className = 't'; ln.appendChild(t);
  el.feed.appendChild(ln); player.current = ln;
  const text = clean(st.text);
  if(instant || player.instant || REDUCED){ t.textContent = text; scrollEnd(); ready(text, instant); return; }
  typeInto(t, text);
}
function addPick(label){
  markPast();
  const ln = document.createElement('div'); ln.className = 'ln pick';
  const t = document.createElement('div'); t.className = 't'; t.textContent = '▶ ' + label; ln.appendChild(t);
  el.feed.appendChild(ln); scrollEnd();
}
function typeInto(node, text){
  player.stopTyping(); el.cur.classList.remove('on');
  let k = 0;
  const finish = () => { player.typing = null; player.finishTyping = null; node.textContent = text; scrollEnd(); ready(text); };
  const tick = () => {
    k += 1; node.textContent = text.slice(0, k); scrollEnd();
    if(k >= text.length){ finish(); return; }
    player.typing = setTimeout(tick, /[。！？…、\n]/.test(text[k - 1]) ? 110 : 24);
  };
  player.typing = setTimeout(tick, 60);
  player.finishTyping = finish;
}
function ready(text, silent){
  el.cur.classList.add('on');
  if(!silent && player.auto && !player.waiting && !player.done) player.autoTimer = setTimeout(() => next(), 900 + (text ? text.length : 0) * 55);
}
function showChoice(st){
  markPast(); player.waiting = true; el.cur.classList.remove('on');
  const box = document.createElement('div'); box.className = 'ln opts';
  box.innerHTML = '<div class="lab">選択</div>';
  st.decision.forEach((opt, k) => {
    const b = document.createElement('button'); b.className = 'opt';
    const n = document.createElement('span'); n.className = 'n'; n.textContent = k + 1;
    const t = document.createElement('span'); t.textContent = clean(opt);
    b.append(n, t);
    b.addEventListener('click', e => { e.stopPropagation(); player.chosen = st.values[k]; box.remove(); addPick(clean(opt)); player.waiting = false; next(); });
    box.appendChild(b);
  });
  el.feed.appendChild(box); scrollEnd();
}

/* ---- flow ---- */
function visible(st){
  if('branch' in st) player.branch = st.branch;
  if(st.kind === 'decision') return true;
  if(st.kind === 'sys' && !settings.sys) return false;
  return !(player.branch && player.chosen !== null && !player.branch.includes(player.chosen));
}
function next(){
  if(player.waiting || player.done || el.stage.classList.contains('peek') || !player.steps.length) return;
  if(player.typing){ player.finishTyping(); return; }
  clearTimeout(player.autoTimer);
  let st;
  do { player.i += 1; st = player.steps[player.i]; if(!st) return finished(); } while(!visible(st));
  applyVisuals(st); seek(); preloadAhead(player.i);
  if(st.kind === 'decision') showChoice(st); else addLine(st);
  progress.set(player.ep.id, { i: player.i, chosen: player.chosen, total: player.total });
}
function finished(){
  player.i = player.total - 1; player.done = true; seek(); markPast(); el.cur.classList.remove('on'); player.setAuto(false);
  progress.set(player.ep.id, { i: player.i, chosen: player.chosen, total: player.total, done: true });
  const ln = document.createElement('div'); ln.className = 'ln end';
  ln.innerHTML = '了<b></b><div class="btns"></div>';
  ln.querySelector('b').textContent = player.ep.name || player.ep.code;
  const btns = ln.querySelector('.btns');
  const nx = nextEp(player.ep.id);
  if(nx){ const b = document.createElement('button'); b.className = 'primary'; b.textContent = '次の話 ›'; b.addEventListener('click', e => { e.stopPropagation(); location.hash = '#/r/' + encodeURIComponent(nx.id); }); btns.appendChild(b); }
  const r = document.createElement('button'); r.textContent = 'もう一度'; r.addEventListener('click', e => { e.stopPropagation(); restart(); }); btns.appendChild(r);
  const t = document.createElement('button'); t.textContent = '目次'; t.addEventListener('click', e => { e.stopPropagation(); location.hash = '#/g/' + encodeURIComponent(player.ep.g.id); }); btns.appendChild(t);
  el.feed.appendChild(ln); scrollEnd();
}
function resetView(){
  player.stopTyping(); player.i = -1; player.chosen = null; player.branch = null; player.done = false; player.waiting = false; player.current = null; player.charState = null;
  el.feed.innerHTML = '<div class="spacer"></div>'; setStill(null); setChars(null, 'all'); setBg(null); setBgm(null); el.cur.classList.remove('on');
  el.rail.querySelectorAll('.mark').forEach(m => m.remove()); seek();
}
function restart(){ resetView(); player.instant = true; next(); player.instant = false; }
function gotoIndex(target, chosen){
  resetView(); player.chosen = chosen; player.instant = true;
  while(player.i < target){
    player.i += 1; const st = player.steps[player.i]; if(!st) break;
    if(!visible(st)) continue;
    applyVisuals(st);
    if(st.kind === 'decision'){
      if(chosen !== null && chosen !== undefined){ const k = st.values.indexOf(chosen); if(k >= 0) addPick(clean(st.decision[k])); }
      else { player.i -= 1; player.instant = false; showChoice(st); return; }
    } else addLine(st, true);
  }
  player.instant = false; seek(); preloadAhead(player.i);
}
function setPeek(on){ el.stage.classList.toggle('peek', on); el.btnPeek.title = el.btnPeek.ariaLabel = on ? '文章に戻る' : '絵を全画面で見る'; if(on) clearTimeout(player.autoTimer); else if(player.auto) ready('', false); }

/* ---- open a story ---- */
async function openStory(id){
  let jump = null;                                   // #/r/<id>?i=<step>  (debug / sharing a position)
  const q = id.indexOf('?'); if(q >= 0){ const qs = id.slice(q); const m = /[?&]i=(\d+)/.exec(qs); if(m) jump = Number(m[1]); if(/[?&]faces=0/.test(qs)) settings.faces = false; if(/[?&]faces=1/.test(qs)) settings.faces = true; if(/[?&]band=1/.test(qs)) settings.band = true; if(/[?&]band=0/.test(qs)) settings.band = false; id = id.slice(0, q); }
  const ep = findEp(id);
  if(!ep){ location.hash = ''; return; }
  const token = ++player.token;
  $('toc').hidden = true; el.stage.hidden = false; document.body.classList.add('playing');
  player.ep = ep; player.steps = []; player.total = 1;
  el.code.textContent = (ep.code ? ep.code + ' ' : '') + (ep.name || '');
  resetView(); layout(); el.loading.hidden = false;
  try{
    const url = SRC.text + ep.txt.split('/').map(encodeURIComponent).join('/') + '.txt';
    const r = await fetch(url); if(!r.ok) throw new Error('HTTP ' + r.status);
    const src = await r.text();
    if(token !== player.token) return;
    const parsed = TRParser.parse(src);
    player.steps = parsed.steps; player.total = Math.max(1, parsed.steps.length);
    parsed.steps.forEach((st, k) => { if(st.kind === 'decision'){ const m = document.createElement('i'); m.className = 'mark'; m.style.left = ((k + 1) / player.total * 100) + '%'; el.rail.appendChild(m); } });
    el.loading.hidden = true;
    const p = progress.get(ep.id);
    if(jump !== null) gotoIndex(Math.min(jump, player.total - 1), null);
    else if(p && !p.done && typeof p.i === 'number' && p.i >= 0 && p.i < player.total - 1) gotoIndex(p.i, p.chosen ?? null);
    else restart();
  }catch(err){
    if(token !== player.token) return;
    el.loading.hidden = true;
    const ln = document.createElement('div'); ln.className = 'ln err';
    ln.innerHTML = '<div class="t"></div>'; ln.querySelector('.t').textContent = '本文を取得できませんでした（' + err.message + '）。通信状態を確認して、もう一度開いてください。';
    el.feed.appendChild(ln);
  }
}

/* ---- input: tap vs scroll ---- */
let pd = null;
el.stage.addEventListener('pointerdown', e => { pd = { x: e.clientX, y: e.clientY, btn: !!e.target.closest('button') }; });
el.stage.addEventListener('pointerup', e => {
  if(!pd) return; const moved = Math.hypot(e.clientX - pd.x, e.clientY - pd.y); const wasBtn = pd.btn; pd = null;
  if(wasBtn || moved > 8) return;
  if(el.stage.classList.contains('peek')){ setPeek(false); return; }
  next();
});
el.btnAuto.addEventListener('click', () => player.setAuto(!player.auto));
el.btnPeek.addEventListener('click', () => setPeek(!el.stage.classList.contains('peek')));
el.btnBack.addEventListener('click', () => { location.hash = player.ep ? '#/g/' + encodeURIComponent(player.ep.g.id) : ''; });
document.addEventListener('keydown', e => {
  if(el.stage.hidden) return;
  if(e.key === 'Escape'){ setPeek(false); return; }
  if(e.key === ' ' || e.key === 'Enter' || e.key === 'ArrowRight'){ e.preventDefault(); if(el.stage.classList.contains('peek')) setPeek(false); else next(); }
});

/* =====================================================================
   SETTINGS SHEET
   ===================================================================== */
function openSettings(){
  $('setDoc').value = settings.doc; $('setProxy').checked = !!settings.proxy; $('setSys').checked = !!settings.sys; $('setFaces').checked = !!settings.faces; $('setBand').checked = !!settings.band;
  document.querySelectorAll('#setFont button').forEach(b => b.classList.toggle('on', Number(b.dataset.v) === Number(settings.font)));
  $('settings').hidden = false;
}
function closeSettings(){
  settings.doc = $('setDoc').value.trim() || 'ドクター'; settings.proxy = $('setProxy').checked; settings.sys = $('setSys').checked; settings.faces = $('setFaces').checked; settings.band = $('setBand').checked;
  saveSettings(); $('settings').hidden = true; if(!$('toc').hidden) renderToc(); layout(); placeSprites();
}
$('btnSettings').addEventListener('click', openSettings);
$('btnCloseSettings').addEventListener('click', closeSettings);
$('settings').addEventListener('click', e => { if(e.target === $('settings')) closeSettings(); });
$('setFont').addEventListener('click', e => { const b = e.target.closest('button'); if(!b) return; settings.font = Number(b.dataset.v); document.querySelectorAll('#setFont button').forEach(x => x.classList.toggle('on', x === b)); applySettings(); });
$('btnResetProgress').addEventListener('click', () => { if(confirm('既読位置と読了マークをすべて消します。よろしいですか？')){ progress.clearAll(); renderToc(); } });

/* ---------------- boot ---------------- */
applySettings();
loadData().then(route).catch(err => {
  $('toc').hidden = false; $('groups').innerHTML = '<div class="empty">目次データを読み込めませんでした（' + err.message + '）</div>';
});
})();
