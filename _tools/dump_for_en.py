"""打印一个批文件里需要做英文版的字段（精简格式，省 token）：python3 dump_for_en.py <批名，如 concept-03>"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
base = sys.argv[1].removesuffix(".json")
d = json.load(open(os.path.join(ROOT, "_batches", f"{base}.json"), encoding="utf-8"))
print(f"# {base} | category={d.get('category')} | {len(d['terms'])} 条")
for i, t in enumerate(d["terms"]):
    print(f"\n## key={base}#{i} | tier={t['tier']}")
    print("name_zh:", t["name_zh"])
    print("name_en:", t["name_en"])
    if t.get("abbr"):
        print("abbr:", t["abbr"])
    if t.get("aliases"):
        print("aliases:", " ; ".join(t["aliases"]))
    print("one_liner:", t["one_liner"])
    print("explanation:", t["explanation"])
    if t.get("example"):
        print("example:", t["example"])
    print(f"related ({len(t.get('related') or [])}):", " ; ".join(t.get("related") or []))
