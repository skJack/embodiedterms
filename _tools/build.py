"""把 _batches/*.json 按学习顺序汇总成 terms.json、术语表.md、术语表.html。

用法：python3 _tools/build.py
- 类别顺序见 CATS（先本体、再软件仿真、再数据训练模型、最后公司行业）
- 每类内部的小节和顺序来自 _order/<类别>.json（由 dump_cat.py / validate_order.py 配合生成）
- _order 里列为 duplicates 的条目、以及 _order/drop.json 里跨类别的重复会被去掉
"""
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = "2026-09-30"

# 学习顺序：先建立地图 → 认识本体（形态、零件、怎么动、怎么控、怎么感知）→ 工具与仿真 → 数据、训练、模型 → 公司与行业
CATS = [
    ("concept", "基础概念与任务", "先建立地图：具身智能在做什么、机器人要完成哪些任务、常说的「泛化」「跨本体」指什么。"),
    ("robot", "机器人类型与代表产品", "认识机器人长什么样：从机械臂到人形的各种形态，以及市面上的代表型号。"),
    ("hardware", "硬件与本体部件", "把机器人拆开看：电机、减速器、丝杠、灵巧手、算力平台这些零件各管什么。"),
    ("mechanics", "力学与运动学", "机器人怎么动的物理基础：位姿怎么表示、正逆运动学、雅可比、动力学和平衡。"),
    ("control", "控制与规划", "让关节按想要的方式动：从 PID 到力控、MPC、运动规划和全身控制。"),
    ("perception", "感知与传感器", "机器人怎么看和摸：相机、深度、IMU、力和触觉，以及点云、标定、SLAM。"),
    ("software", "软件与工具链", "把本体、控制和感知串起来的软件：ROS 2、URDF、运动库、学习框架和部署工具。"),
    ("sim", "仿真与评测", "在电脑里练和考：仿真器怎么工作、仿真和真机的差距，以及常用的评测基准。"),
    ("data", "数据与采集", "学习的原料：演示数据怎么采、有哪些数据集、数据怎么处理和规模化。"),
    ("training", "训练与学习方法", "模型怎么学出来：模仿学习、强化学习、预训练和微调，以及让它更稳的技巧。"),
    ("model", "模型与架构", "学出来的模型长什么样：Transformer、VLM、动作怎么生成、VLA 和世界模型。"),
    ("named_model", "代表性模型与工作", "按发展脉络看有名的模型：从 SayCan、RT-2 到 π 系列、GR00T 和世界模型。"),
    ("company", "公司与机构", "谁在做具身智能：科技巨头、国内外本体和模型公司、零部件厂商和研究机构。"),
    ("industry", "行业黑话与商业", "看懂新闻稿、路演和群聊里的说法：本体、大小脑、数据飞轮、量产……"),
]
CAT_ORDER = {k: i for i, (k, _, _) in enumerate(CATS)}
TIER = {1: "入门必知", 2: "常用", 3: "进阶"}


def norm(s):
    return re.sub(r"[^a-z0-9一-鿿]", "", str(s or "").lower().replace("π", "pi"))


# 被去重删掉的词条：它们的名字仍指向保留的那条，别处的「相关」链接不会断
REDIRECTS = []


def load_orders():
    orders, dropped = {}, {}
    for k, _, _ in CATS:
        p = os.path.join(ROOT, "_order", f"{k}.json")
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            orders[k] = d
            dropped.update({x["drop"]: x["keep"] for x in d.get("duplicates", [])})
    p = os.path.join(ROOT, "_order", "drop.json")  # 跨类别的重复
    if os.path.exists(p):
        dropped.update({x["drop"]: x["keep"] for x in json.load(open(p, encoding="utf-8"))["drop"]})
    return orders, dropped


def load():
    orders, dropped = load_orders()
    terms = []
    for path in sorted(glob.glob(os.path.join(ROOT, "_batches", "*.json"))):
        base = os.path.basename(path)[:-5]
        d = json.load(open(path, encoding="utf-8"))
        cat = d.get("category") or base.rsplit("-", 1)[0]
        for i, t in enumerate(d.get("terms", [])):
            key = f"{base}#{i}"
            if key in dropped:
                REDIRECTS.append(([t.get("name_zh"), t.get("name_en"), t.get("abbr")] + list(t.get("aliases") or []), dropped[key]))
                continue
            t["category"], t["key"] = cat, key
            terms.append(t)

    # 每类内部：按 _order 的小节顺序排；没排到的放到该类最后一个「其他」小节
    sections = {}
    rank = {}
    for k, _, _ in CATS:
        secs = orders.get(k, {}).get("sections", [])
        sections[k] = [{"title": s["title"], "blurb": s["blurb"]} for s in secs]
        for si, s in enumerate(secs):
            for j, key in enumerate(s["keys"]):
                rank[key] = (si, j)
    for k, _, _ in CATS:
        if any(t["category"] == k and t["key"] not in rank for t in terms):
            sections[k].append({"title": "其他", "blurb": "暂未归入上面小节的词条。"})
    for t in terms:
        if t["key"] in rank:
            t["sec"], pos = rank[t["key"]]
        else:
            t["sec"], pos = len(sections[t["category"]]) - 1, 10_000 + t.get("tier", 3)
        t["_sort"] = (CAT_ORDER.get(t["category"], 99), t["sec"], pos, t["key"])
    terms.sort(key=lambda t: t["_sort"])

    # 跨批同名去重：保留学习顺序里先出现的
    seen, out = set(), []
    for t in terms:
        k = norm(t.get("name_en")) or norm(t.get("name_zh"))
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    for n, t in enumerate(out):
        t["id"] = f"t{n + 1}"
        t.pop("_sort", None)
    return out, sections


def link_related(terms):
    idx = {}
    for t in terms:
        for s in [t.get("name_zh"), t.get("name_en"), t.get("abbr")] + list(t.get("aliases") or []):
            k = norm(s)
            if len(k) >= 2:
                idx.setdefault(k, t["id"])
    key2id = {t["key"]: t["id"] for t in terms}
    for names, keep in REDIRECTS:
        for s in names:
            k = norm(s)
            if len(k) >= 2 and keep in key2id:
                idx.setdefault(k, key2id[keep])
    def find(r):
        hit = idx.get(norm(r))
        if hit:
            return hit
        # 有些批次把相关词写成「中文名(English)」，整串对不上时在括号处拆开，括号前后各试一次；
        # 名字本身也可能带括号（「Franka 机械臂（Panda / FR3）(…)」），所以从最后一个左括号往前逐个试
        s = str(r or "").strip()
        if s.endswith((")", "）")):
            for i in range(len(s) - 1, 0, -1):
                if s[i] in "(（":
                    for part in (s[:i], s[i + 1:-1]):
                        k = norm(part)
                        if len(k) >= 2 and k in idx:
                            return idx[k]
        return None

    for t in terms:
        t["related_ids"] = [find(r) for r in t.get("related") or []]


def title_of(t):
    zh, en, ab = t.get("name_zh", ""), t.get("name_en", ""), t.get("abbr", "")
    parts = [zh]
    if en and norm(en) != norm(zh):
        parts.append(en)
    if ab and norm(ab) not in (norm(zh), norm(en)):
        parts.append(ab)
    return " · ".join(parts)


def write_md(terms, sections):
    by = {k: [t for t in terms if t["category"] == k] for k, _, _ in CATS}
    n1 = sum(1 for t in terms if t.get("tier") == 1)
    L = [
        "# 具身智能新手名词表",
        "",
        f"共 {len(terms)} 条，分 {len(CATS)} 类，事实截至 {TODAY}。",
        "",
        "14 类按学习顺序排：先建立地图（1），再认识机器人本体——形态、零件、怎么动、怎么控制、怎么感知（2–6），"
        "然后是软件和仿真（7–8），接着是数据、训练和模型（9–12），最后是公司和行业（13–14）。每类内部也分成由浅入深的小节。",
        "",
        f"每条标了分级：**入门必知**（{n1} 条，新人第一周就会听到）、**常用**（读论文、做项目常见）、**进阶**（专业方向才会碰到）。"
        "第一次看可以只看「入门必知」。",
        "",
        "## 目录",
        "",
    ]
    for ci, (k, name, _) in enumerate(CATS, 1):
        L.append(f"{ci}. [{name}](#{ci}-{name})（{len(by[k])} 条）")
    for ci, (k, name, blurb) in enumerate(CATS, 1):
        L += ["", f"## {ci} {name}", "", f"> {blurb}", ""]
        for si, s in enumerate(sections[k]):
            group = [t for t in by[k] if t["sec"] == si]
            if not group:
                continue
            L += [f"### {ci}.{si + 1} {s['title']}（{len(group)}）", "", f"*{s['blurb']}*", ""]
            for t in group:
                L.append(f"#### {title_of(t)}　`{TIER.get(t.get('tier'), '')}`")
                L.append("")
                L.append(f"**{t['one_liner']}**")
                L.append("")
                L.append(t["explanation"].strip())
                if t.get("example"):
                    L += ["", f"例子：{t['example'].strip()}"]
                tail = []
                if t.get("aliases"):
                    tail.append("别名：" + "、".join(t["aliases"]))
                if t.get("related"):
                    tail.append("相关：" + "、".join(t["related"]))
                src = [f"[{s2.get('title') or s2['url']}]({s2['url']})" for s2 in t.get("sources") or []]
                if src:
                    tail.append("来源：" + "；".join(src))
                if t.get("as_of"):
                    tail.append(f"信息截至 {t['as_of']}")
                if tail:
                    L += [""] + [f"- {x}" for x in tail]
                L.append("")
    open(os.path.join(ROOT, "术语表.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


def write_html(terms, sections):
    tpl_path = os.path.join(ROOT, "_tools", "template.html")
    if not os.path.exists(tpl_path):
        return
    tpl = open(tpl_path, encoding="utf-8").read()
    slim = [
        {k: t.get(k) for k in ["id", "category", "sec", "tier", "name_zh", "name_en", "abbr", "aliases", "one_liner",
                                "explanation", "example", "related", "related_ids", "sources", "as_of"]}
        for t in terms
    ]
    cats = [{"key": k, "name": n, "blurb": b, "sections": sections[k]} for k, n, b in CATS]
    data = json.dumps({"terms": slim, "cats": cats, "today": TODAY}, ensure_ascii=False).replace("</", "<\\/")
    html = tpl.replace("/*__DATA__*/null", data)
    # 发布版：Artifact 会自己套 doctype/head，所以只写片段
    open(os.path.join(ROOT, "_tools", "artifact.html"), "w", encoding="utf-8").write(html)
    # 本地版：双击就能打开
    head = ('<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            '<style>body{margin:0}</style></head><body>\n')
    open(os.path.join(ROOT, "术语表.html"), "w", encoding="utf-8").write(head + html + "\n</body></html>\n")


def main():
    terms, sections = load()
    link_related(terms)
    json.dump(terms, open(os.path.join(ROOT, "terms.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    write_md(terms, sections)
    write_html(terms, sections)
    counts = {n: sum(1 for t in terms if t["category"] == k) for k, n, _ in CATS}
    unsectioned = [n for k, n, _ in CATS if sections[k] and sections[k][-1]["title"] == "其他"]
    print(len(terms), "条", counts)
    if unsectioned:
        print("还没排序或有漏排的类别：", "、".join(unsectioned))


if __name__ == "__main__":
    main()
