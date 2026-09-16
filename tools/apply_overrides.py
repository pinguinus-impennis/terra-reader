"""Merge hand-corrected face boxes into data/faces.json.

Usage:  python tools/apply_overrides.py path/to/faces_overrides.json
The overrides file is what tools/face_review.html exports. Entries are stored
with flag 2 (manual) and are kept in tools/faces_overrides.json so that
re-running analyze_faces.py never loses them (it merges this file at the end).
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACES = os.path.join(ROOT, 'data', 'faces.json')
KEEP = os.path.join(ROOT, 'tools', 'faces_overrides.json')

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    new = json.load(open(sys.argv[1], encoding='utf-8'))
    keep = json.load(open(KEEP, encoding='utf-8')) if os.path.exists(KEEP) else {}
    keep.update(new)
    json.dump(keep, open(KEEP, 'w', encoding='utf-8'), separators=(',', ':'))
    faces = json.load(open(FACES, encoding='utf-8'))
    for k, v in keep.items():
        v = list(v); v[5] = 2; faces[k] = v
    json.dump(faces, open(FACES, 'w'), separators=(',', ':'))
    print(f'applied {len(new)} new, {len(keep)} total manual boxes -> data/faces.json')

if __name__ == '__main__':
    main()
