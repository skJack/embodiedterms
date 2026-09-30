"""列出某一类的全部词条：python3 dump_cat.py <类别key>
每行：key | 分级 | 中文名 | 英文名 | 一句话。key 形如 mechanics-03#4（批文件名#序号），排序文件里用它。"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cat = sys.argv[1]
for path in sorted(glob.glob(os.path.join(ROOT, "_batches", f"{cat}-*.json"))):
    base = os.path.basename(path)[:-5]
    for i, t in enumerate(json.load(open(path, encoding="utf-8"))["terms"]):
        print(f"{base}#{i} | T{t['tier']} | {t['name_zh']} | {t['name_en']} | {t['one_liner']}")
