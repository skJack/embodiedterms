"""把一份英文补丁写回 _batches_en：python3 apply_en.py <补丁.json>
补丁格式：{"terms": [{"key": "concept-01#3", "name_en": ..., "aliases": [...], "one_liner": ..., "explanation": ..., "example": ..., "related": [...]}]}
写回后对涉及的每个批文件跑 validate_en.py 并打印结果。"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
patch = json.load(open(sys.argv[1], encoding="utf-8"))["terms"]
touched = {}
for e in patch:
    base, i = e["key"].split("#")
    path = os.path.join(ROOT, "_batches_en", f"{base}.json")
    if base not in touched:
        touched[base] = json.load(open(path, encoding="utf-8"))
    touched[base]["terms"][int(i)] = {k: e[k] for k in ["key", "name_en", "aliases", "one_liner", "explanation", "example", "related"] if k in e}
for base, d in touched.items():
    json.dump(d, open(os.path.join(ROOT, "_batches_en", f"{base}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "_tools", "validate_en.py"), base], capture_output=True, text=True)
    print(base, r.stdout.strip())
