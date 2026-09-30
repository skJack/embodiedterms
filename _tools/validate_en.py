"""校验英文版批文件 _batches_en/<批名>.json：python3 validate_en.py <批名>，通过时只打印 OK。"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
base = sys.argv[1].removesuffix(".json")
src = json.load(open(os.path.join(ROOT, "_batches", f"{base}.json"), encoding="utf-8"))["terms"]
try:
    en = json.load(open(os.path.join(ROOT, "_batches_en", f"{base}.json"), encoding="utf-8"))["terms"]
except Exception as e:
    print("读不了或不是合法 JSON：", e)
    sys.exit(1)
errs = []
if len(en) != len(src):
    errs.append(f"条数 {len(en)} != 中文版 {len(src)}")
cjk = re.compile(r"[一-鿿]")
for i, (s, t) in enumerate(zip(src, en)):
    tag = f"[{i}] {t.get('name_en') or s['name_zh']}"
    if t.get("key") != f"{base}#{i}":
        errs.append(f"{tag} key 应为 {base}#{i}")
    for k in ["name_en", "one_liner", "explanation"]:
        if not isinstance(t.get(k), str) or not t[k].strip():
            errs.append(f"{tag} 缺 {k}")
    if not isinstance(t.get("aliases", []), list) or not isinstance(t.get("related", []), list):
        errs.append(f"{tag} aliases / related 应为数组")
    if len(t.get("related") or []) != len(s.get("related") or []):
        errs.append(f"{tag} related 要和中文版一一对应：{len(t.get('related') or [])} != {len(s.get('related') or [])}")
    ol, ex = t.get("one_liner") or "", t.get("explanation") or ""
    if len(ol) > 200:
        errs.append(f"{tag} one_liner 太长（{len(ol)} 字符，应 ≤25 词）")
    if not 250 <= len(ex) <= 1600:
        errs.append(f"{tag} explanation 长度 {len(ex)} 字符，应在 70–200 词左右")
    for k in ["one_liner", "explanation", "example"]:
        if cjk.search(t.get(k) or "") and k != "explanation":
            errs.append(f"{tag} {k} 里不应出现中文")
if errs:
    print("\n".join(errs))
    sys.exit(1)
print("OK")
