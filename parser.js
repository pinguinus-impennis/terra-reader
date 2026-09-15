/* Terra Reader — Arknights story script parser
 * Turns a story .txt into a list of "steps" (one tap each).
 * Visual/audio tags that precede a text line are folded into that line's step.
 * Works in browser (window.TRParser) and Node (module.exports).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.TRParser = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  const TAG = /^\[([A-Za-z_]+)\s*(?:\((.*)\))?\s*\]\s*(.*)$/;
  const NAME = /^\[name\s*=\s*"([^"]*)"\s*\]\s*(.*)$/i;
  const ARG = /(\w+)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^,\)]+))/g;

  function parseArgs(s) {
    const o = {};
    if (!s) return o;
    ARG.lastIndex = 0;
    let m;
    while ((m = ARG.exec(s))) o[m[1].toLowerCase()] = (m[2] !== undefined ? m[2] : m[3]).trim();
    return o;
  }

  function cleanText(t) {
    return (t || '')
      .replace(/\\n/g, '\n')
      .replace(/<[^<>]{1,60}>/g, '')      // <@tu.kw> </> <color=#..> <i> <p=2> …
      .replace(/\{@nbs\}/gi, ' ')
      .replace(/ +$/g, '')
      .trim();
  }

  const SLOT = { l: 'l', left: 'l', m: 'm', middle: 'm', mid: 'm', r: 'r', right: 'r' };
  function slotOf(v) { return SLOT[String(v || 'm').toLowerCase()] || 'm'; }

  function parse(src) {
    const steps = [];
    let title = null;
    let pending = {};
    const cur = { l: null, m: null, r: null };   // running sprite state
    let lastLine = null;                           // for multiline merging

    const flush = (extra) => {
      const st = Object.assign({}, pending, extra);
      steps.push(st);
      pending = {};
      return st;
    };
    const snapshotChars = (focus) => {
      pending.chars = { l: cur.l, m: cur.m, r: cur.r };
      pending.focus = focus;
    };
    const clearChars = () => { cur.l = cur.m = cur.r = null; snapshotChars('all'); };

    const lines = String(src).split(/\r?\n/);
    for (let raw of lines) {
      const line = raw.replace(/^﻿/, '');
      if (!line.trim()) continue;

      // [name="X"] text
      let m = NAME.exec(line);
      if (m) {
        const text = cleanText(m[2]);
        if (!text) continue;
        lastLine = flush({ kind: 'line', spk: m[1].trim(), text });
        continue;
      }

      m = TAG.exec(line);
      if (!m) {                                 // bare narration
        const text = cleanText(line);
        if (text) { lastLine = null; flush({ kind: 'nar', spk: '', text }); }
        continue;
      }

      const tag = m[1].toLowerCase();
      const a = parseArgs(m[2]);
      const rest = cleanText(m[3]);

      switch (tag) {
        case 'header':
          if (rest) title = rest;
          break;

        /* ---- sprites: legacy ---- */
        case 'character': {
          const n1 = a.name, n2 = a.name2;
          if (!n1 && !n2) { clearChars(); break; }
          cur.l = cur.m = cur.r = null;
          if (n1 && n2) { cur.l = n1; cur.r = n2; }
          else cur.m = n1 || n2;
          const f = String(a.focus || '');
          snapshotChars(n1 && n2 ? (f === '1' ? 'l' : f === '2' ? 'r' : 'all') : 'all');
          break;
        }
        /* ---- sprites: modern slots ---- */
        case 'charslot': {
          if (!a.slot && !a.name) { clearChars(); break; }
          const s = slotOf(a.slot);
          if (a.name) cur[s] = a.name; else cur[s] = null;
          let focus = 'keep';
          if (a.focus !== undefined) {
            const f = String(a.focus).toLowerCase();
            focus = f === 'all' ? 'all' : (f === 'n' || f === 'none') ? 'none' : slotOf(f);
          }
          snapshotChars(focus);
          break;
        }

        /* ---- background / stills ---- */
        case 'background':
          pending.bg = a.image || null;
          break;
        case 'image':
          pending.still = a.image || null;
          break;
        case 'cgitem':
          if (a.image) pending.still = a.image;
          break;
        case 'hidecgitem':
          pending.still = null;
          break;

        /* ---- music ---- */
        case 'playmusic':
          pending.bgm = (a.key || a.intro || '').replace(/^\$/, '') || null;
          break;
        case 'stopmusic':
          pending.bgm = null;
          break;

        /* ---- branching ---- */
        case 'decision': {
          let options, values;
          if (a.options) { options = a.options.split(';'); values = (a.values || '').split(';'); }
          else {
            options = []; values = [];
            for (let k = 1; k <= 8; k++) { if (a['option' + k] === undefined) break; options.push(a['option' + k]); values.push(a['value' + k] || String(k)); }
          }
          if (options.length) { lastLine = null; flush({ kind: 'decision', decision: options.map(cleanText), values: values.map(v => v.trim()) }); }
          break;
        }
        case 'predicate':
          if (a.references) pending.branch = a.references.split(';').map(v => v.trim());
          break;

        /* ---- text-bearing tags ---- */
        case 'multiline': {
          if (!rest) break;
          const spk = (a.name || '').trim();
          if (lastLine && lastLine.kind === 'line' && lastLine.spk === spk && lastLine.multi && !Object.keys(pending).length) {
            lastLine.text += '\n' + rest;
          } else {
            lastLine = flush({ kind: 'line', spk, text: rest, multi: true });
          }
          break;
        }
        case 'dialog':
        case 'narration':
        case 'title':
          if (rest) { lastLine = null; flush({ kind: tag === 'title' ? 'title' : 'nar', spk: '', text: rest }); }
          break;
        case 'subtitle':
          if (a.text) { lastLine = null; flush({ kind: 'sub', spk: '', text: cleanText(a.text) }); }
          break;
        case 'sticker':
          if (a.text) { lastLine = null; flush({ kind: 'sticker', spk: '', text: cleanText(a.text) }); }
          break;
        case 'animtext':
          if (rest) { lastLine = null; flush({ kind: 'stamp', spk: '', text: rest }); }
          break;
        case 'voicewithin':
          if (rest) { lastLine = null; flush({ kind: 'inner', spk: '', text: rest }); }
          break;
        case 'popupdialog':
        case 'tutorial':
          if (rest) { lastLine = null; flush({ kind: 'sys', spk: '', text: rest }); }
          break;
        case 'video':
          lastLine = null; flush({ kind: 'sys', spk: '', text: '（映像：' + (a.res || '').split('/').pop() + '）' });
          break;

        default:
          // Blocker, Delay, PlaySound, CameraShake, ImageTween, Effect, … : presentation only
          break;
      }
    }
    return { title, steps };
  }

  return { parse, cleanText, parseArgs };
});
