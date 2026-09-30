"""校验一批术语释义 JSON：python3 validate_batch.py <file> [应有条数]，通过时只打印 OK。"""
import json
import sys

path = sys.argv[1]
expected = int(sys.argv[2]) if len(sys.argv) > 2 else None
errs = []
try:
    d = json.load(open(path, encoding="utf-8"))
except Exception as e:
    print("INVALID JSON:", e)
    sys.exit(1)

terms = d.get("terms")
if not isinstance(terms, list):
    errs.append("terms 不是数组")
    terms = []
if expected is not None and len(terms) != expected:
    errs.append(f"条数 {len(terms)} != 应有 {expected}")

for i, t in enumerate(terms):
    tag = f"[{i}] {t.get('name_zh') or t.get('name_en')}"
    for k in ["name_zh", "name_en", "one_liner", "explanation"]:
        if not isinstance(t.get(k), str) or not t[k].strip():
            errs.append(f"{tag} 缺 {k}")
    for k in ["abbr", "example", "as_of"]:
        if k in t and not isinstance(t[k], str):
            errs.append(f"{tag} {k} 应为字符串")
    for k in ["aliases", "related"]:
        if not isinstance(t.get(k, []), list):
            errs.append(f"{tag} {k} 应为数组")
    if t.get("tier") not in (1, 2, 3):
        errs.append(f"{tag} tier 应为 1/2/3")
    ol = t.get("one_liner") or ""
    if len(ol) > 60:
        errs.append(f"{tag} one_liner 太长（{len(ol)} 字，应 ≤40 汉字左右）")
    ex = t.get("explanation") or ""
    if len(ex) < 50 or len(ex) > 500:
        errs.append(f"{tag} explanation 长度 {len(ex)}，应在 80–250 字左右")
    src = t.get("sources")
    if not isinstance(src, list) or not src:
        errs.append(f"{tag} 缺 sources")
    else:
        for s in src:
            if not isinstance(s, dict) or not str(s.get("url", "")).startswith("http"):
                errs.append(f"{tag} source 格式不对：{s}")

if errs:
    print("\n".join(errs))
    sys.exit(1)
print("OK")
