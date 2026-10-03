"""Upload the encoded BGM to a Cloudflare R2 bucket under a secret prefix.

Needs an R2 API token (Account > R2 > Manage R2 API Tokens > Object Read & Write).
Put the values in  _cache/bgm/r2.env  (never committed):
  R2_ACCOUNT_ID=...
  R2_ACCESS_KEY_ID=...
  R2_SECRET_ACCESS_KEY=...
  R2_BUCKET=terra-reader-bgm
  R2_PREFIX=bgm/<a long random string>      (made for you on first run if absent)

Usage:  python tools/bgm/upload_r2.py [--work DIR]
Uploads only files whose size differs from what is already in the bucket.
Prints the base URL to paste into the app's settings once the bucket has a public
r2.dev domain (R2 > bucket > Settings > Public access > Allow).
"""
import argparse, json, os, secrets, sys, concurrent.futures
try:
    import boto3
except ImportError:
    sys.exit('pip install boto3')

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_WORK = os.path.join(os.path.dirname(ROOT), '_cache', 'bgm')

def load_env(path):
    env = {}
    if os.path.exists(path):
        for line in open(path, encoding='utf-8'):
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1); env[k.strip()] = v.strip()
    return env

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--work', default=os.environ.get('BGM_WORK', DEFAULT_WORK)); a = ap.parse_args()
    envp = os.path.join(a.work, 'r2.env'); env = load_env(envp)
    for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET'):
        if not env.get(k): sys.exit(f'{k} missing in {envp}')
    if not env.get('R2_PREFIX'):
        env['R2_PREFIX'] = 'bgm/' + secrets.token_urlsafe(24)
        with open(envp, 'a', encoding='utf-8') as f: f.write(f"\nR2_PREFIX={env['R2_PREFIX']}\n")
        print('generated secret prefix', env['R2_PREFIX'])
    s3 = boto3.client('s3', endpoint_url=f"https://{env['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                      aws_access_key_id=env['R2_ACCESS_KEY_ID'], aws_secret_access_key=env['R2_SECRET_ACCESS_KEY'], region_name='auto')
    bucket, prefix = env['R2_BUCKET'], env['R2_PREFIX'].strip('/')
    src = os.path.join(a.work, 'opus')
    index = json.load(open(os.path.join(src, 'bgm_files.json')))
    existing = {}
    token = None
    while True:
        kw = dict(Bucket=bucket, Prefix=prefix + '/')
        if token: kw['ContinuationToken'] = token
        r = s3.list_objects_v2(**kw)
        for o in r.get('Contents', []): existing[o['Key']] = o['Size']
        if not r.get('IsTruncated'): break
        token = r.get('NextContinuationToken')
    todo = []
    for stem, rel in index.items():
        p = os.path.join(src, rel); key = f'{prefix}/{rel}'
        if existing.get(key) != os.path.getsize(p): todo.append((p, key))
    todo.append((os.path.join(src, 'bgm_files.json'), f'{prefix}/bgm_files.json'))
    sprites_dir = os.path.join(a.work, '..', 'sprites', 'webp')          # bodies from tools/sprites/build_missing_sprites.py
    if os.path.isdir(sprites_dir):
        for f in os.listdir(sprites_dir):
            if f.lower().endswith('.webp'):
                p = os.path.join(sprites_dir, f); key = f'{prefix}/sprites/{f}'
                if existing.get(key) != os.path.getsize(p): todo.append((p, key))
    print(f'{len(index)} clips, uploading {len(todo)} files')
    def up(item):
        p, key = item
        ct = 'audio/ogg' if p.endswith('.opus') else 'image/webp' if p.endswith('.webp') else 'application/json'
        s3.upload_file(p, bucket, key, ExtraArgs={'ContentType': ct, 'CacheControl': 'public, max-age=31536000, immutable' if p.endswith(('.opus', '.webp')) else 'public, max-age=300'})
        return key
    n = 0
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        for _ in ex.map(up, todo):
            n += 1
            if n % 100 == 0: print(f'  {n}/{len(todo)}', flush=True)
    print('done.')
    print('Base URL for the app (after enabling the bucket\'s public r2.dev domain):')
    print(f"  https://pub-<your r2.dev id>.r2.dev/{prefix}/")

if __name__ == '__main__':
    main()
