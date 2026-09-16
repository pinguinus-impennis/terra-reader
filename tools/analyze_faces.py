"""Build data/faces.json: per sprite *set* (same body, different expressions),
the face box and figure extent as fractions of the canvas.

  faces.json = { setkey: [cx, cy, face_h, fig_top, fig_bot, flag] }   (all 0..1 of canvas)
  flag 0 = face detected, 1 = estimated from the figure outline (no face found)

Usage:  python tools/analyze_faces.py            (needs: opencv-python-headless<5, pillow, numpy)
Downloads one representative image per set (resized by wsrv.nl) into a cache dir.
"""
import json, os, re, sys, io, time, urllib.request, urllib.parse, concurrent.futures
import numpy as np
from PIL import Image
import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
CACHE = os.environ.get('FACE_CACHE', os.path.join(os.path.dirname(ROOT), '_cache', 'faces'))
CASCADE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lbpcascade_animeface.xml')
RAW = 'raw.githubusercontent.com/ArknightsAssets/ArknightsAssets2/cn/assets/dyn/avg/characters/'
H = 640

def setkey(path):
    d, _, f = path.rpartition('/')
    if '#' in f: f = re.sub(r'#\d+', '', f)      # expressions of one body
    elif '$' in f: pass                          # a body file itself
    elif d: f = d                                # legacy: whole folder is one body
    return (d + '/' + f) if d else f

def is_face_patch(file):
    """Newest sprites store the body as X$m.png and expressions as small X#n$m.png patches."""
    with Image.open(file) as im: return im.height <= 520

def url_for(path):
    return 'https://wsrv.nl/?url=' + urllib.parse.quote(RAW + path + '.png', safe='') + f'&h={H}&output=png'

def raw_url(path):
    return 'https://' + RAW + '/'.join(urllib.parse.quote(x) for x in (path + '.png').split('/'))

def fetch(path):
    out = os.path.join(CACHE, path.replace('/', '__') + '.png')
    if os.path.exists(out) and os.path.getsize(out) > 0: return out
    # wsrv.nl cannot fetch paths containing '#': fall back to the full-size raw file and shrink locally
    use_raw = '#' in path
    for attempt in range(3):
        try:
            req = urllib.request.Request(raw_url(path) if use_raw else url_for(path), headers={'User-Agent': 'TerraReader/0.1 face-analysis'})
            with urllib.request.urlopen(req, timeout=120) as r: data = r.read()
            if len(data) < 200: raise IOError('empty')
            if use_raw:
                im = Image.open(io.BytesIO(data)).convert('RGBA')
                if im.height > H: im = im.resize((round(im.width * H / im.height), H), Image.LANCZOS)
                im.save(out)
            else:
                with open(out, 'wb') as f: f.write(data)
            return out
        except Exception as e:
            time.sleep(2 * (attempt + 1)); err = e
    print('  download failed', path, err, file=sys.stderr); return None

def detect(casc, gray):
    return [tuple(int(v) for v in f) for f in casc.detectMultiScale(gray, scaleFactor=1.03, minNeighbors=2, minSize=(24, 24))]

def analyze(casc, file):
    """-> [cx, cy, face_h, fig_top, fig_bot, flag]  (fractions of canvas; flag 0=detected, 1=estimated)"""
    im = Image.open(file).convert('RGBA'); rgba = np.array(im); ch, cw = rgba.shape[:2]
    alpha = rgba[:, :, 3] > 40
    rows = np.where(alpha.any(1))[0]
    if not len(rows): return None
    top, bot = int(rows[0]), int(rows[-1]); fig = bot - top
    bg = np.full((ch, cw, 3), 128, np.uint8); a = rgba[:, :, 3:4] / 255.0
    rgb = (rgba[:, :, :3] * a + bg * (1 - a)).astype(np.uint8)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    cands = detect(casc, cv2.equalizeHist(gray)) + detect(casc, gray)
    # second pass: upper body only, upscaled x2 (small heads on tall full-body sprites)
    ub = max(1, int(top + fig * 0.45))
    crop = cv2.resize(gray[0:ub, :], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    cands += [(x // 2, y // 2, w // 2, h // 2) for (x, y, w, h) in detect(casc, cv2.equalizeHist(crop))]
    full_body = fig >= 0.8 * ch                # standing figure filling the canvas (vs. bust / close-up)
    def plausible(f):
        x, y, w, h = f; cy = y + h / 2
        heads = (bot - cy) / h                 # eye line -> feet, in face heights
        lo = 4.3 if full_body else 2.5         # a full-body figure is never shorter than ~4.3 faces
        return (cy < top + fig * 0.30) and (lo <= heads <= 14.5) and (cy - top <= 2.6 * h)   # face sits near the top; hats/horns add at most ~1.5 faces
    good = [f for f in cands if plausible(f)]
    r = lambda v: round(v, 4)
    if good:
        hmax = max(f[3] for f in good)
        big = [f for f in good if f[3] >= 0.4 * hmax]
        x, y, w, h = min(big, key=lambda f: f[1])        # the topmost of the reasonably-sized candidates
        return [r((x + w / 2) / cw), r((y + h / 2) / ch), r(h / ch), r(top / ch), r(bot / ch), 0]
    # estimate: assume an average adult (~7.2 face heights tall, face centred ~0.75 face below the top)
    h = fig / 7.2; cy = top + 0.75 * h
    cols = np.where(alpha[int(max(0, cy - h / 2)):int(min(ch, cy + h / 2)), :].any(0))[0]
    cx = (cols[0] + cols[-1]) / 2 if len(cols) else cw / 2
    return [r(cx / cw), r(cy / ch), r(h / ch), r(top / ch), r(bot / ch), 1]

def main():
    os.makedirs(CACHE, exist_ok=True)
    sprites = json.load(open(os.path.join(DATA, 'sprites.json'), encoding='utf-8'))
    sets = {}
    for p in sprites.values():
        k = setkey(p); sets.setdefault(k, []).append(p)
    reps = {k: (sorted(v, key=lambda p: (0 if '#1$' in p or p.endswith('_1') or p == k else 1, p))[0]) for k, v in sets.items()}
    print('sets', len(reps), '-> cache', CACHE)
    faces_path = os.path.join(DATA, 'faces.json')
    faces = json.load(open(faces_path, encoding='utf-8')) if os.path.exists(faces_path) else {}
    todo = [(k, p) for k, p in reps.items() if k not in faces]
    print('to analyze', len(todo))
    casc = cv2.CascadeClassifier(CASCADE)
    done = 0; ok = 0
    remap = {}   # face-patch sets -> body path
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for (k, p), file in zip(todo, ex.map(lambda kp: fetch(kp[1]), todo)):
            if file and '#' in p and is_face_patch(file):
                body = re.sub(r'#\d+', '', p)          # avg_x_1/avg_x_1#3$1 -> avg_x_1/avg_x_1$1
                remap[k] = body; file = fetch(body); k = setkey(body)
            if file:
                res = analyze(casc, file)
                if res: faces[k] = res; ok += res[5] == 0
            done += 1
            if done % 100 == 0:
                json.dump(faces, open(faces_path, 'w'), separators=(',', ':'))
                print(f'  {done}/{len(todo)} analyzed, faces found {ok}', flush=True)
    if remap:   # point every expression of a face-patch set at its body (the body carries a default face)
        changed = 0
        for name, path in list(sprites.items()):
            if setkey(path) in remap: sprites[name] = remap[setkey(path)]; changed += 1
        json.dump(sprites, open(os.path.join(DATA, 'sprites.json'), 'w', encoding='utf-8'), separators=(',', ':'))
        print(f'face-patch sets remapped to body: {len(remap)} sets, {changed} sprite names')
    keep = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'faces_overrides.json')   # hand corrections always win
    if os.path.exists(keep):
        for k, v in json.load(open(keep, encoding='utf-8')).items(): v = list(v); v[5] = 2; faces[k] = v
    json.dump(faces, open(faces_path, 'w'), separators=(',', ':'))
    total = len(faces); found = sum(1 for v in faces.values() if v[5] == 0)
    print(f'faces.json: {total} sets, face detected {found} ({found * 100 // max(1, total)}%), size {os.path.getsize(faces_path) // 1024} KB')

if __name__ == '__main__':
    main()
