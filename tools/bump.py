"""Stamp a new cache-busting version into index.html and app.js. Run before committing a deploy."""
import datetime, io, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
v = datetime.datetime.now().strftime('%Y%m%d%H%M')
for f, pat, rep in (('index.html', r'\?v=\w+', '?v=' + v), ('app.js', r"const VERSION = '\w+'", f"const VERSION = '{v}'")):
    p = os.path.join(ROOT, f); s = io.open(p, encoding='utf-8').read(); s2 = re.sub(pat, rep, s)
    io.open(p, 'w', encoding='utf-8').write(s2)
print('version', v)
