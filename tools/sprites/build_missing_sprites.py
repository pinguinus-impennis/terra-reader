"""Extract the sprite bodies that the public asset mirror lacks, straight from the game's content server.

For every body in data/metrics.json that data/sprites.json cannot resolve, download its
avg/characters/<base>.ab bundle, export the body texture(s) <base>$m with ArknightsStudioCLI
(official portable build: it carries the ASTC decoder), and save them as webp under
  _cache/sprites/webp/<base>$m.webp
Also writes _cache/sprites/sprites_extra.json  { "<base>$m": "sprites/<base>$m.webp" }.
Expressions (#n face patches) are not composited: the body texture carries the default face.

Usage:  python tools/sprites/build_missing_sprites.py [--work DIR] [--jobs 6] [--only substr]
Tools (env overrides): DOTNET, ARKSTUDIO_CLI (path to ArknightsStudioCLI.dll from ArknightsStudioCLI_net6_portable.zip)
"""
import argparse, concurrent.futures, json, os, re, subprocess, sys, time, urllib.request, zipfile
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_WORK = os.path.join(os.path.dirname(ROOT), '_cache', 'sprites')
CONF = 'https://ak-conf.hypergryph.com/config/prod/official/Android/version'
CDN = 'https://ak.hycdn.cn/assetbundle/official/Android/assets/{ver}/{file}'
UA = {'User-Agent': 'Mozilla/5.0 (TerraReader sprite build; personal use)'}

def get(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r: return r.read()

def base_of(path):
    d, _, f = path.rpartition('/'); return (d or re.sub(r'[#$]\d+', '', f)).lower()

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--work', default=os.environ.get('SPRITE_WORK', DEFAULT_WORK)); ap.add_argument('--jobs', type=int, default=6); ap.add_argument('--only', default='')
    a = ap.parse_args(); work = a.work
    dotnet = os.environ.get('DOTNET', os.path.expanduser('~/.dotnet/dotnet.exe'))
    cli = os.environ.get('ARKSTUDIO_CLI', os.path.join(work, 'cli', 'ArknightsStudioCLI.dll'))
    for p in (dotnet, cli):
        if not os.path.exists(p): sys.exit('missing ' + p)
    d_b, d_ab, d_png, d_webp = [os.path.join(work, x) for x in ('bundles', 'ab', 'png', 'webp')]
    for d in (d_b, d_ab, d_png, d_webp): os.makedirs(d, exist_ok=True)

    metrics = json.load(open(os.path.join(ROOT, 'data', 'metrics.json'), encoding='utf-8'))
    sprites = json.load(open(os.path.join(ROOT, 'data', 'sprites.json'), encoding='utf-8'))
    have = {base_of(p) for p in sprites.values() if not p.startswith('~/')}
    missing = sorted(k.lower() for k in metrics if k.lower() not in have)
    ver = json.loads(get(CONF))['resVersion']
    hul = json.loads(get(CDN.format(ver=ver, file='hot_update_list.json'), 300))
    names = {b['name'].lower()[len('avg/characters/'):-3]: b['name'] for b in hul['abInfos'] if b['name'].lower().startswith('avg/characters/')}
    todo = [names[m] for m in missing if m in names and (not a.only or a.only in m)]
    print('resVersion', ver, '| missing bodies', len(missing), '| with a bundle', len(todo))

    def fetch(name):
        dat = name.replace('/', '_').replace('.ab', '.dat'); dst = os.path.join(d_b, dat)
        abdst = os.path.join(d_ab, name.replace('/', os.sep))
        if os.path.exists(abdst): return 'skip'
        for attempt in range(3):
            try:
                open(dst, 'wb').write(get(CDN.format(ver=ver, file=dat), 300))
                with zipfile.ZipFile(dst) as z: z.extractall(d_ab)
                os.remove(dst); return 'ok'
            except Exception as e: err = e; time.sleep(3 * (attempt + 1))
        return f'fail {name}: {err}'
    t0 = time.time(); n = 0; fails = []
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
        for r in ex.map(fetch, todo):
            n += 1
            if r.startswith('fail'): fails.append(r)
            if n % 50 == 0: print(f'  downloaded {n}/{len(todo)} {time.time() - t0:.0f}s', flush=True)
    print('download done, failures', len(fails)); [print('  ', f) for f in fails[:5]]

    print('exporting textures ...', flush=True)
    r = subprocess.run([dotnet, cli, d_ab, '-t', 'tex2d', '-g', 'none', '-o', d_png, '--image-format', 'png', '--log-level', 'warning'], capture_output=True, text=True)
    print((r.stdout or '').strip().splitlines()[-1] if r.stdout else r.stderr[-300:])

    extra = {}
    pngs = [f for f in os.listdir(d_png) if f.lower().endswith('.png')]
    # keep only body textures  <base>$m.png  (skip face patches and alpha/other textures)
    bodies = [f for f in pngs if re.match(r'^[a-z0-9_]+\$\d+\.png$', f, re.I)]
    print('textures', len(pngs), '| body textures', len(bodies))
    def conv(f):
        stem = f[:-4]; out = os.path.join(d_webp, stem + '.webp')
        if not os.path.exists(out):
            im = Image.open(os.path.join(d_png, f)).convert('RGBA')
            alpha = os.path.join(d_png, stem + '[alpha].png')          # some bodies keep their alpha in a sister texture
            if os.path.exists(alpha):
                a = Image.open(alpha).convert('L')
                if a.size != im.size: a = a.resize(im.size, Image.LANCZOS)
                im.putalpha(a)
            if im.height > 1400: im = im.resize((round(im.width * 1400 / im.height), 1400), Image.LANCZOS)
            im.save(out, 'WEBP', quality=86, method=6)
        return stem
    with concurrent.futures.ThreadPoolExecutor(max(2, os.cpu_count() // 2)) as ex:
        for stem in ex.map(conv, bodies): extra[stem.lower()] = 'sprites/' + stem + '.webp'
    json.dump(extra, open(os.path.join(work, 'sprites_extra.json'), 'w', encoding='utf-8'), separators=(',', ':'))
    total = sum(os.path.getsize(os.path.join(d_webp, os.path.basename(v))) for v in extra.values())
    print(f'sprites_extra.json: {len(extra)} bodies, {total // 1048576} MB webp in {d_webp}')

if __name__ == '__main__':
    main()
