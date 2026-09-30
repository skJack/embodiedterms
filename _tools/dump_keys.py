"""按 key 打印中文词条（做英文版用）：python3 dump_keys.py <key 列表 JSON 文件> 或 python3 dump_keys.py key1 key2 ..."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
args = sys.argv[1:]
keys = json.load(open(args[0])) if len(args) == 1 and args[0].endswith(".json") else args
cache = {}
for k in keys:
    base, i = k.split("#")
    if base not in cache:
        cache[base] = json.load(open(os.path.join(ROOT, "_batches", f"{base}.json"), encoding="utf-8"))["terms"]
    t = cache[base][int(i)]
    print(f"\n## key={k} | tier={t['tier']}")
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
