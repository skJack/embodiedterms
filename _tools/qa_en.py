"""英文版整体检查：缺文件、校验失败、中英词名对不上（防止英文内容挂到别的词条下）。
用法：python3 _tools/qa_en.py"""
import glob
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tok = lambda s: {w for w in re.findall(r"[a-z0-9]+", str(s or "").lower().replace("π", "pi")) if len(w) >= 2}
STOP = {"the", "and", "of", "for", "in", "on", "with", "to", "a", "an", "by", "robot", "robotics", "model", "series", "system"}
missing, invalid, suspects = [], [], []
for f in sorted(glob.glob(os.path.join(ROOT, "_batches", "*.json"))):
    base = os.path.basename(f)[:-5]
    ef = os.path.join(ROOT, "_batches_en", f"{base}.json")
    if not os.path.exists(ef):
        missing.append(base)
        continue
    r = subprocess.run([sys.executable, os.path.join(ROOT, "_tools", "validate_en.py"), base], capture_output=True, text=True)
    if r.stdout.strip() != "OK":
        invalid.append((base, r.stdout.strip()[:200]))
        continue
    zh = json.load(open(f, encoding="utf-8"))["terms"]
    en = json.load(open(ef, encoding="utf-8"))["terms"]
    for i, (z, e) in enumerate(zip(zh, en)):
        zt = (tok(z.get("name_en")) | tok(z.get("abbr")) | set().union(*[tok(a) for a in z.get("aliases") or []] or [set()])) - STOP
        et = (tok(e.get("name_en")) | set().union(*[tok(a) for a in e.get("aliases") or []] or [set()])) - STOP
        if zt and et and not (zt & et):
            suspects.append((f"{base}#{i}", z["name_zh"], z["name_en"], e["name_en"]))
print("缺英文文件:", missing)
print("校验失败:", invalid)
print(f"词名对不上（需人工看）: {len(suspects)} 条")
for s in suspects:
    print("  ", " | ".join(s))
