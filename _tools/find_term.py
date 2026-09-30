"""在全表里按关键词找词条（中英文、缩写、别名都搜）：python3 find_term.py <关键词> [关键词...]"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
qs = [q.lower() for q in sys.argv[1:]]
for path in sorted(glob.glob(os.path.join(ROOT, "_batches", "*.json"))):
    base = os.path.basename(path)[:-5]
    for i, t in enumerate(json.load(open(path, encoding="utf-8"))["terms"]):
        hay = " ".join([t.get("name_zh", ""), t.get("name_en", ""), t.get("abbr", "")] + list(t.get("aliases") or [])).lower()
        if any(q in hay for q in qs):
            print(f"{base}#{i} | {t['name_zh']} | {t['name_en']}")
