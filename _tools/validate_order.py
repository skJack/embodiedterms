"""校验某一类的学习顺序文件 _order/<类别key>.json：python3 validate_order.py <类别key>，通过时只打印 OK。"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cat = sys.argv[1]
keys = set()
for path in sorted(glob.glob(os.path.join(ROOT, "_batches", f"{cat}-*.json"))):
    base = os.path.basename(path)[:-5]
    n = len(json.load(open(path, encoding="utf-8"))["terms"])
    keys.update(f"{base}#{i}" for i in range(n))

errs = []
try:
    d = json.load(open(os.path.join(ROOT, "_order", f"{cat}.json"), encoding="utf-8"))
except Exception as e:
    print("读不了或不是合法 JSON：", e)
    sys.exit(1)

dropped = set()
for x in d.get("duplicates", []):
    if x.get("keep") not in keys or x.get("drop") not in keys:
        errs.append(f"duplicates 里的 key 不存在：{x}")
    dropped.add(x.get("drop"))

secs = d.get("sections")
if not isinstance(secs, list) or not (3 <= len(secs) <= 14):
    errs.append("sections 应为 3–14 个小节")
    secs = secs if isinstance(secs, list) else []
seen = []
for s in secs:
    if not str(s.get("title", "")).strip():
        errs.append("有小节缺 title")
    if len(str(s.get("title", ""))) > 16:
        errs.append(f"小节标题太长：{s.get('title')}")
    if not str(s.get("blurb", "")).strip():
        errs.append(f"小节「{s.get('title')}」缺 blurb")
    for k in s.get("keys", []):
        if k not in keys:
            errs.append(f"未知 key：{k}")
        elif k in dropped:
            errs.append(f"{k} 已列为重复要删，不应再出现在小节里")
        elif k in seen:
            errs.append(f"key 出现了两次：{k}")
        seen.append(k)
missing = sorted(keys - set(seen) - dropped)
if missing:
    errs.append(f"漏排 {len(missing)} 条：" + "、".join(missing[:30]))
if errs:
    print("\n".join(errs))
    sys.exit(1)
print("OK")
