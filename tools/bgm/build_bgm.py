"""Extract every story BGM from the game's own content server and encode it to opus.

Pipeline (all local, nothing is redistributed by this script):
  1. ask the official config server for the current resource version
  2. fetch hot_update_list.json and pick the bundles under audio/sound_beta_2/music/
  3. download each bundle (.dat = zip holding one .ab) from the content CDN
  4. unpack the .ab with ArknightsStudioCLI (needs the .NET 6 runtime) -> FSB5 files
  5. decode FSB5 with vgmstream -> wav, encode with ffmpeg -> opus
  6. write opus/<folder>/<clip>.opus plus bgm_files.json (clip stem -> relative path)

Usage:  python tools/bgm/build_bgm.py [--work DIR] [--bitrate 56k] [--jobs 6]
Re-running skips bundles and clips that already exist, so new events only add work.

Tools expected (override with env vars):
  DOTNET            C:\\Users\\<you>\\.dotnet\\dotnet.exe
  ARKSTUDIO_DIR     folder holding ArknightsStudioCLI.dll
  VGMSTREAM         vgmstream-cli.exe
  ffmpeg            on PATH
"""
import argparse, concurrent.futures, json, os, re, shutil, subprocess, sys, time, urllib.request, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_WORK = os.path.join(os.path.dirname(ROOT), '_cache', 'bgm')
CONF = 'https://ak-conf.hypergryph.com/config/prod/official/Android/version'
CDN = 'https://ak.hycdn.cn/assetbundle/official/Android/assets/{ver}/{file}'
UA = {'User-Agent': 'Mozilla/5.0 (TerraReader bgm build; personal use)'}

def get(url, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', default=os.environ.get('BGM_WORK', DEFAULT_WORK))
    ap.add_argument('--bitrate', default='56k')
    ap.add_argument('--jobs', type=int, default=6)
    ap.add_argument('--only', default='', help='substring filter on bundle names (for testing)')
    a = ap.parse_args()
    work = a.work
    dotnet = os.environ.get('DOTNET', os.path.expanduser('~/.dotnet/dotnet.exe'))
    studio = os.environ.get('ARKSTUDIO_DIR', os.path.join(work, 'ArknightsStudioCLI'))
    vgm = os.environ.get('VGMSTREAM', os.path.join(work, 'vgmstream', 'vgmstream-cli.exe'))
    for p, what in ((dotnet, 'dotnet'), (os.path.join(studio, 'ArknightsStudioCLI.dll'), 'ArknightsStudioCLI'), (vgm, 'vgmstream-cli')):
        if not os.path.exists(p): sys.exit(f'missing {what}: {p}')
    if not shutil.which('ffmpeg'): sys.exit('ffmpeg not on PATH')
    d_bundles, d_ab, d_fsb, d_wav, d_opus = [os.path.join(work, x) for x in ('bundles', 'ab', 'fsb', 'wav', 'opus')]
    for d in (d_bundles, d_ab, d_fsb, d_wav, d_opus): os.makedirs(d, exist_ok=True)

    # 1-2. manifest
    ver = json.loads(get(CONF))['resVersion']
    print('resVersion', ver)
    hul = json.loads(get(CDN.format(ver=ver, file='hot_update_list.json'), 300))
    music = [b for b in hul['abInfos'] if b['name'].lower().startswith('audio/sound_beta_2/music/')]
    if a.only: music = [b for b in music if a.only in b['name']]
    print('music bundles', len(music), 'total MB', sum((b.get('totalSize') or b.get('abSize') or 0) for b in music) // 1048576)

    # 3. download + unzip
    def fetch(b):
        name = b['name']; dat = name.replace('/', '_').replace('.ab', '.dat')
        dst = os.path.join(d_bundles, dat); abdst = os.path.join(d_ab, name.replace('/', os.sep))
        if os.path.exists(abdst): return 'skip'
        for attempt in range(3):
            try:
                data = get(CDN.format(ver=ver, file=dat), 300)
                open(dst, 'wb').write(data)
                with zipfile.ZipFile(dst) as z: z.extractall(d_ab)
                os.remove(dst)
                return 'ok'
            except Exception as e:
                err = e; time.sleep(3 * (attempt + 1))
        return f'fail {name}: {err}'
    t0 = time.time(); done = 0; fails = []
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
        for r in ex.map(fetch, music):
            done += 1
            if r.startswith('fail'): fails.append(r)
            if done % 50 == 0: print(f'  downloaded {done}/{len(music)}  {time.time() - t0:.0f}s', flush=True)
    print('download done, failures:', len(fails)); [print('  ', f) for f in fails[:10]]

    # 4. unpack all .ab -> fsb (one CLI run over the folder; it skips existing files)
    print('unpacking with ArknightsStudioCLI ...', flush=True)
    r = subprocess.run([dotnet, os.path.join(studio, 'ArknightsStudioCLI.dll'), d_ab, '-t', 'audio', '-g', 'containerFull',
                        '-o', d_fsb, '--audio-format', 'none', '--log-level', 'warning'], capture_output=True, text=True)
    tail = (r.stdout or '').strip().splitlines()[-2:]
    print('\n'.join(tail))

    # 5. fsb -> wav -> opus
    fsbs = []
    for dp, _, fs in os.walk(d_fsb):
        for f in fs:
            if f.lower().endswith('.fsb'): fsbs.append(os.path.join(dp, f))
    print('clips', len(fsbs))
    def convert(fsb):
        rel = os.path.relpath(fsb, d_fsb)
        # keep the game folder (e.g. music/beta2_180603/m_dia_escape_loop) as the key
        m = re.search(r'(music[\\/].*)\.fsb$', rel, re.I)
        key = (m.group(1) if m else os.path.splitext(rel)[0]).replace('\\', '/').lower()
        out = os.path.join(d_opus, key + '.opus')
        if os.path.exists(out) and os.path.getsize(out) > 0: return key
        os.makedirs(os.path.dirname(out), exist_ok=True)
        wav = os.path.join(d_wav, os.path.basename(key) + '.wav')
        r1 = subprocess.run([vgm, '-o', wav, fsb], capture_output=True, text=True)
        if r1.returncode != 0 or not os.path.exists(wav): return f'FAIL decode {key}'
        r2 = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', wav, '-c:a', 'libopus', '-b:a', a.bitrate, '-vbr', 'on', out], capture_output=True, text=True)
        try: os.remove(wav)
        except OSError: pass
        return key if r2.returncode == 0 else f'FAIL encode {key}: {r2.stderr[-200:]}'
    keys = []; bad = []; done = 0; t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max(2, os.cpu_count() // 2)) as ex:
        for r in ex.map(convert, fsbs):
            done += 1
            (bad if r.startswith('FAIL') else keys).append(r)
            if done % 100 == 0: print(f'  converted {done}/{len(fsbs)}  {time.time() - t0:.0f}s', flush=True)
    print('converted', len(keys), 'failed', len(bad)); [print('  ', b) for b in bad[:10]]

    # 6. index: clip stem -> relative path (what the app needs to build a URL)
    index = {os.path.basename(k): k + '.opus' for k in sorted(keys)}
    json.dump(index, open(os.path.join(d_opus, 'bgm_files.json'), 'w'), separators=(',', ':'))
    total = sum(os.path.getsize(os.path.join(d_opus, v)) for v in index.values())
    print(f'bgm_files.json: {len(index)} clips, {total // 1048576} MB of opus in {d_opus}')

if __name__ == '__main__':
    main()
