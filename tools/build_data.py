"""Regenerate data/index.json, data/sprites.json, data/bgm.json.

Usage (from repo root):
  python tools/build_data.py
Requires network (curl/git). Downloads:
  - story_review_table.json, story_variables.json  (ArknightsGamedata jp)
  - jp story txt files (sparse clone, to scan referenced sprite names)
  - ArknightsAssets2 cn tree listing (blob-less clone)
"""
import json, os, re, subprocess, sys, tempfile, glob, collections, datetime

RAW = 'https://raw.githubusercontent.com/ArknightsAssets/ArknightsGamedata/master/jp/gamedata/'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data')

def sh(cmd, cwd=None):
    subprocess.run(cmd, shell=True, check=True, cwd=cwd)

def main():
    work = tempfile.mkdtemp(prefix='terra_')
    print('work dir', work)
    sh(f'curl -sL -o story_review_table.json {RAW}excel/story_review_table.json', work)
    sh(f'curl -sL -o story_variables.json {RAW}story/story_variables.json', work)
    sh('git clone -q --depth 1 --filter=blob:none --sparse https://github.com/ArknightsAssets/ArknightsGamedata akdata', work)
    sh('git sparse-checkout set jp/gamedata/story', os.path.join(work, 'akdata'))
    sh('git clone -q --depth 1 --filter=blob:none --no-checkout --single-branch --branch cn https://github.com/ArknightsAssets/ArknightsAssets2 aa2', work)
    aa2 = subprocess.run('git ls-tree -r --name-only HEAD:assets/dyn/avg', shell=True, check=True, cwd=os.path.join(work, 'aa2'), capture_output=True, text=True).stdout.split()
    story_dir = os.path.join(work, 'akdata', 'jp', 'gamedata', 'story')

    # ---- index.json
    d = json.load(open(os.path.join(work, 'story_review_table.json'), encoding='utf-8'))
    def ep(i):
        e = {'id': i['storyId'], 'code': i.get('storyCode') or '', 'name': i.get('storyName') or '', 'tag': i.get('avgTag') or '', 'txt': i['storyTxt']}
        if i.get('storyInfo'): e['info'] = i['storyInfo']
        if not os.path.exists(os.path.join(story_dir, i['storyTxt'] + '.txt')): e['missing'] = True
        return e
    groups = []
    for v in d.values():
        kind = {'MAINLINE': 'main', 'ACTIVITY': 'event', 'MINI_ACTIVITY': 'mini', 'NONE': 'record'}[v['entryType']]
        eps = sorted(v['infoUnlockDatas'], key=lambda i: i['storySort'])
        g = {'id': v['id'], 'kind': kind, 'name': v['name'], 'start': v['startTime'], 'eps': [ep(i) for i in eps]}
        if kind == 'main':
            n = int(v['id'].split('_')[1]); g['code'] = f'EP{n:02d}'; g['n'] = n
        groups.append(g)
    order = {'main': 0, 'event': 1, 'mini': 2, 'record': 3}
    groups.sort(key=lambda g: (order[g['kind']], g.get('n', 0), g['start'], g['name']))
    for g in groups: g.pop('n', None)
    json.dump({'generated': datetime.date.today().isoformat(), 'source': 'ArknightsAssets/ArknightsGamedata jp', 'groups': groups},
              open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('index.json groups', len(groups), 'episodes', sum(len(g['eps']) for g in groups))

    # ---- sprites.json
    sv = json.load(open(os.path.join(work, 'story_variables.json'), encoding='utf-8'))
    names = set()
    for p in glob.glob(os.path.join(story_dir, '**', '*.txt'), recursive=True):
        if '[uc]info' in p: continue
        for line in open(p, encoding='utf-8', errors='replace'):
            if re.match(r'^\[(character|charslot)', line, re.I):
                for m in re.finditer(r'name2?\s*=\s*"([^"]+)"', line): names.add(m.group(1).strip())
    low = {p.lower(): p for p in aa2}
    def cands(n):
        if n.startswith('$'): n = str(sv.get(n[1:], n))
        n = n.lower(); base = n.split('#')[0].split('$')[0]
        out = [f'characters/{base}/{n}.png', f'characters/{n}.png']
        m = re.match(r'^(.*)_1#0*(\d+)(\$\d+)?$', n)
        if m: out += [f'characters/{m.group(1)}_1/{m.group(1)}_{m.group(2)}.png', f'characters/{m.group(1)}_{m.group(2)}.png']
        m = re.match(r'^(.*)#0*(\d+)(\$\d+)?$', n)
        if m: out += [f'characters/{m.group(1)}/{m.group(1)}_{m.group(2)}.png', f'characters/{m.group(1)}_{m.group(2)}.png', f'characters/{m.group(1)}/{m.group(1)}#{m.group(2)}$1.png']
        if '#' not in n: out += [f'characters/{n}_1/{n}_1.png', f'characters/{n}/{n}_1.png', f'characters/{n}/{n}#1$1.png', f'characters/{n}_1/{n}_1#1$1.png']
        return out
    mp = {}
    for n in sorted(names):
        for c in cands(n):
            if c in low: mp[n.lower()] = low[c][len('characters/'):-4]; break
    json.dump(mp, open(os.path.join(OUT, 'sprites.json'), 'w', encoding='utf-8'), separators=(',', ':'))
    print('sprites.json', len(mp), '/', len(names), 'resolved')

    # ---- bgm.json
    bgm = {}
    for k, v in sv.items():
        if isinstance(v, str) and '/Music/' in v:
            short = re.sub(r'^(m_dia_|m_sys_|m_bat_|m_avg_)', '', v.split('/')[-1]); short = re.sub(r'_(loop|intro)$', '', short)
            bgm[k] = short
    json.dump(bgm, open(os.path.join(OUT, 'bgm.json'), 'w', encoding='utf-8'), separators=(',', ':'))
    print('bgm.json', len(bgm))

if __name__ == '__main__':
    main()
