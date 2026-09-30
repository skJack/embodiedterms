"""生成可部署到 Cloudflare 的静态站点 site/：中文、英文两版，外加每个词、每个分类各一个静态页面（给搜索引擎和单条分享用）。

用法：python3 _tools/build_site.py [--base-url https://你的域名]
- 中文数据：_batches/ + _order/（复用 build.py 的 load）
- 英文版：_batches_en/ 和 _i18n/en_sections.json；缺英文的词条先用中文顶上，并打印数量
- 词条网址 /t/<slug>/ 第一次完整生成后记进 _tools/slugs.json，之后改名也不变，外链不会失效
- base_url 只影响 canonical、hreflang、sitemap 里的绝对地址，默认读 _tools/site_config.json
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build  # noqa: E402

ROOT = build.ROOT
TOOLS = os.path.join(ROOT, "_tools")
SITE = os.path.join(ROOT, "site")
CFG = json.load(open(os.path.join(TOOLS, "site_config.json"), encoding="utf-8"))
TODAY = build.TODAY
CAT_KEYS = [k for k, _, _ in build.CATS]

SITE_NAME = {"zh": "具身智能新手名词表", "en": "Embodied AI Glossary"}
TIER = {"zh": {1: "入门必知", 2: "常用", 3: "进阶"}, "en": {1: "Essential", 2: "Common", 3: "Advanced"}}
UI = {
    "zh": {
        "home": "名词表", "prev": "上一个", "next": "下一个", "prev_cat": "上一类", "next_cat": "下一类",
        "aka": "也叫", "related": "相关", "sources": "来源", "asof": "信息截至", "example": "例子",
        "in_app": "在完整名词表里查看 →", "switch": "English", "terms": "条",
        "search_ph": "搜中文、英文或缩写，如 VLA / 逆运动学 / 宇树", "loading": "正在加载词条…",
        "lede": "给刚入门具身智能的同学查词用。14 类按学习顺序排：先认识机器人本体（形态、零件、怎么动、怎么控制、怎么感知），"
                "再看工具和仿真，然后是数据、训练和模型，最后是公司和行业说法；每类内部也分成由浅入深的小节。"
                "默认只列 <strong>入门必知</strong> 的 {n1} 条，搜索时不受分级限制。",
        "meta": "<span><b>{n}</b> 条</span><span><b>14</b> 类</span><span>事实截至 <b>{today}</b></span>",
        "cats_title": "按类别浏览",
        "not_found": "这个页面不存在。",
    },
    "en": {
        "home": "Glossary", "prev": "Previous", "next": "Next", "prev_cat": "Previous category", "next_cat": "Next category",
        "aka": "Also called", "related": "Related", "sources": "Sources", "asof": "As of", "example": "Example",
        "in_app": "See it in the full glossary →", "switch": "中文", "terms": "terms",
        "search_ph": "Search in English or Chinese, e.g. VLA / inverse kinematics / Unitree", "loading": "Loading entries…",
        "lede": "A glossary for people new to embodied AI. The 14 categories follow a learning path: first the robot body "
                "(form factors, parts, motion, control, perception), then tools and simulation, then data, training and models, "
                "and finally the companies and the industry's vocabulary. Each category is split into sections that go from basic "
                "to advanced. Only the {n1} <strong>Essential</strong> entries are shown by default; search covers everything.",
        "meta": "<span><b>{n}</b> terms</span><span><b>14</b> categories</span><span>Facts as of <b>{today}</b></span>",
        "cats_title": "Browse by category",
        "not_found": "This page doesn't exist.",
    },
}


def esc(s):
    return html.escape(str(s or ""), quote=True)


def has_cjk(s):
    return bool(re.search(r"[一-鿿]", s or ""))


def write(rel, content, mode="w"):
    path = os.path.join(SITE, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if mode == "wb":
        open(path, "wb").write(content)
    else:
        open(path, "w", encoding="utf-8").write(content)


def hashed(name, data: bytes):
    stem, ext = os.path.splitext(name)
    return f"{stem}.{hashlib.sha1(data).hexdigest()[:10]}{ext}"


# ---------- 数据 ----------

def load_en():
    out = {}
    d = os.path.join(ROOT, "_batches_en")
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not f.endswith(".json"):
            continue
        try:
            for t in json.load(open(os.path.join(d, f), encoding="utf-8"))["terms"]:
                out[t["key"]] = t
        except Exception as e:
            print("跳过英文批（JSON 坏）:", f, e)
    return out


def load_en_sections():
    p = os.path.join(ROOT, "_i18n", "en_sections.json")
    if not os.path.exists(p):
        return {}
    return {c["key"]: c for c in json.load(open(p, encoding="utf-8"))["cats"]}


def slugify(s):
    s = re.sub(r"\(.*?\)|（.*?）", " ", str(s or ""))  # 括号里的补充说明不进网址
    s = s.replace("π", "pi").replace("*", " star ").replace("&", " and ").replace("+", " plus ")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:60].rstrip("-")


def assign_slugs(terms, en, persist):
    path = os.path.join(TOOLS, "slugs.json")
    saved = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    used = set(saved.values())
    out = {}
    for t in terms:
        k = t["key"]
        if k in saved:
            out[k] = saved[k]
            continue
        base = slugify((en.get(k) or {}).get("name_en")) or slugify(t.get("name_en")) or "term"
        s, n = base, 2
        while s in used:
            s, n = f"{base}-{n}", n + 1
        used.add(s)
        out[k] = s
    if persist:
        saved.update(out)
        json.dump(saved, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)
    return out


def make_records(terms, sections, en, en_sec, slugs):
    tid2slug = {t["id"]: slugs[t["key"]] for t in terms}
    en_name = {slugs[t["key"]]: ((en.get(t["key"]) or {}).get("name_en") or t["name_en"]) for t in terms}
    zh, enr, missing = [], [], 0
    for t in terms:
        sid = slugs[t["key"]]
        rel_ids = [tid2slug.get(i) if i else None for i in t.get("related_ids") or []]
        common = dict(id=sid, category=t["category"], sec=t["sec"], tier=t["tier"], sources=t.get("sources") or [],
                      as_of=t.get("as_of", ""), related_ids=rel_ids)
        zh.append(dict(common, name=t["name_zh"], alt=t["name_en"], abbr=t.get("abbr", ""), aliases=t.get("aliases") or [],
                       one_liner=t["one_liner"], explanation=t["explanation"], example=t.get("example", ""),
                       related=t.get("related") or []))
        e = en.get(t["key"])
        if not e:
            missing += 1
            e = dict(name_en=t["name_en"], aliases=[], one_liner=t["one_liner"], explanation=t["explanation"],
                     example=t.get("example", ""), related=t.get("related") or [])
        rel_txt = []
        for i, rid in enumerate(rel_ids):
            if rid:
                rel_txt.append(en_name[rid])
            else:
                er = e.get("related") or []
                rel_txt.append(er[i] if i < len(er) else (t.get("related") or [""])[i])
        enr.append(dict(common, name=e["name_en"], alt=t["name_zh"], abbr=t.get("abbr", ""), aliases=e.get("aliases") or [],
                        one_liner=e["one_liner"], explanation=e["explanation"], example=e.get("example", ""),
                        related=rel_txt))
    cats_zh = [{"key": k, "name": n, "blurb": b, "sections": sections[k]} for k, n, b in build.CATS]
    cats_en = []
    for c in cats_zh:
        ec = en_sec.get(c["key"])
        if ec and len(ec["sections"]) >= len([s for s in c["sections"] if s["title"] != "其他"]):
            secs = [{"title": s["title"], "blurb": s["blurb"]} for s in ec["sections"]]
            secs += c["sections"][len(secs):]  # 兜底：多出来的「其他」小节
            cats_en.append({"key": c["key"], "name": ec["name"], "blurb": ec["blurb"], "sections": secs})
        else:
            cats_en.append(c)
    return {"zh": zh, "en": enr}, {"zh": cats_zh, "en": cats_en}, missing


# ---------- 页面片段 ----------

def paths(lang, kind, x=None):
    pre = "" if lang == "zh" else "/en"
    return {"home": f"{pre}/", "term": f"{pre}/t/{x}/", "cat": f"{pre}/c/{x}/"}[kind]


def head(lang, base, title, desc, kind, x, assets, og_type="website", jsonld=None, extra=""):
    zh_p, en_p = paths("zh", kind, x), paths("en", kind, x)
    canon = base + (zh_p if lang == "zh" else en_p)
    ld = ""
    if jsonld:
        ld = '<script type="application/ld+json">' + json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/") + "</script>"
    return f"""<!doctype html>
<html lang="{'zh-CN' if lang == 'zh' else 'en'}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canon}">
<link rel="alternate" hreflang="zh-CN" href="{base}{zh_p}">
<link rel="alternate" hreflang="en" href="{base}{en_p}">
<link rel="alternate" hreflang="x-default" href="{base}{zh_p}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canon}">
<meta property="og:site_name" content="{esc(SITE_NAME[lang])}">
<meta property="og:locale" content="{'zh_CN' if lang == 'zh' else 'en_US'}">
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="#EEF1F0" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#121816" media="(prefers-color-scheme: dark)">
<link rel="icon" href="/assets/{assets['favicon']}" type="image/svg+xml">
<link rel="stylesheet" href="/assets/{assets['css']}">
{extra}{ld}
</head>
<body>
"""


def topbar(lang, kind, x, assets):
    other = "en" if lang == "zh" else "zh"
    return (f'<header class="topbar"><a class="brand" href="{paths(lang, "home")}"><img src="/assets/{assets["favicon"]}" alt="">'
            f'{esc(SITE_NAME[lang])}</a><a class="langsw" href="{paths(other, kind, x)}" hreflang="{"en" if other == "en" else "zh-CN"}" '
            f'lang="{"en" if other == "en" else "zh-CN"}">{UI[lang]["switch"]}</a></header>\n')


def footer(lang):
    fb = esc(CFG["feedback_url"])
    if lang == "zh":
        return (f'<footer class="site"><p>整理：<b>{esc(CFG["author_zh"])}</b> · 公众号「{esc(CFG["wechat"])}」</p>'
                '<p>内容由 AI 辅助检索和整理，每条都附了来源链接；「公司与机构」「机器人类型与代表产品」「代表性模型与工作」三类和全部「入门必知」词条经过独立事实核查。'
                f'难免有错，发现问题或想补充词条，欢迎在公众号留言，或到 <a href="{fb}" rel="noopener">GitHub</a> 提 issue。</p>'
                f'<p>内容采用 <a href="https://creativecommons.org/licenses/by-nc/4.0/deed.zh-hans" rel="license noopener">CC BY-NC 4.0</a> 许可，'
                f'转载请署名；<a href="{esc(CFG["repo_url"])}" rel="noopener">源码和数据在 GitHub</a> · 事实截至 {TODAY} · '
                '<a href="/en/" hreflang="en" lang="en">English edition</a></p></footer>\n')
    return (f'<footer class="site"><p>Compiled by <b>{esc(CFG["author_en"])}</b></p>'
            '<p>Researched and drafted with AI assistance; every entry links to its sources. The companies, robots and notable-models '
            'categories and all Essential entries were independently fact-checked. The English edition is adapted from the Chinese '
            f'original. Spotted an error or a missing term? <a href="{fb}" rel="noopener">Open an issue on GitHub</a>.</p>'
            f'<p>Content licensed under <a href="https://creativecommons.org/licenses/by-nc/4.0/" rel="license noopener">CC BY-NC 4.0</a>; '
            f'<a href="{esc(CFG["repo_url"])}" rel="noopener">source and data on GitHub</a> · Facts as of {TODAY} · '
            '<a href="/" hreflang="zh-CN" lang="zh-CN">中文版</a></p></footer>\n')


def desc_of(r, limit=150):
    d = r["one_liner"].strip()
    rest = r["explanation"].strip()
    if len(d) < limit and rest:
        d = d + " " + rest
    return d[:limit].rstrip() + ("…" if len(d) > limit else "")


def src_html(lang, sources):
    out = []
    for s in sources:
        t = s.get("title") or s["url"]
        mark = " (Chinese)" if lang == "en" and has_cjk(t) else ""
        out.append(f'<a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(t)}{mark}</a>')
    return "<br>".join(out)


# ---------- 各类页面 ----------

def page_home(lang, base, recs, cats, assets, data_file):
    u = UI[lang]
    n1 = sum(1 for r in recs if r["tier"] == 1)
    counts = {c["key"]: sum(1 for r in recs if r["category"] == c["key"]) for c in cats}
    title = f"{SITE_NAME[lang]} · 2900+ 个专有名词按学习顺序讲清楚" if lang == "zh" else f"{SITE_NAME[lang]} · 2,900+ terms explained for newcomers"
    desc = ("给刚入门具身智能的同学查词用：2900 多个专有名词，分 14 类按学习顺序排，每条有一句话解释、展开说明、例子和来源。"
            if lang == "zh" else
            "2,900+ embodied-AI and robotics terms for newcomers, in 14 categories ordered as a learning path, each with a one-line "
            "definition, a plain-language explanation, an example and sources.")
    jsonld = {"@context": "https://schema.org", "@type": "DefinedTermSet", "name": SITE_NAME[lang], "url": base + paths(lang, "home"),
              "inLanguage": "zh-CN" if lang == "zh" else "en", "description": desc}
    extra = (f'<meta name="glossary-data" content="/data/{data_file}">\n'
             f'<link rel="preload" href="/data/{data_file}" as="fetch" crossorigin>\n')
    fallback = "".join(
        f'<li><a href="{paths(lang, "cat", c["key"])}">{i + 1} {esc(c["name"])}</a>（{counts[c["key"]]}）<br><span class="d">{esc(c["blurb"])}</span></li>'
        if lang == "zh" else
        f'<li><a href="{paths(lang, "cat", c["key"])}">{i + 1} {esc(c["name"])}</a> ({counts[c["key"]]})<br><span class="d">{esc(c["blurb"])}</span></li>'
        for i, c in enumerate(cats))
    body = f"""<div class="shell">
  <div class="intro">
    <h1>{esc(SITE_NAME[lang])}</h1>
    <div class="meta">{u['meta'].format(n=len(recs), today=TODAY)}</div>
    <p class="lede">{u['lede'].format(n1=n1)}</p>
  </div>
  <nav class="rail" id="rail" aria-label="{'分类' if lang == 'zh' else 'Categories'}"></nav>
  <main>
    <div class="bar">
      <label class="search" for="q">
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="5.2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M11 11l3.6 3.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
        <input id="q" type="search" placeholder="{esc(u['search_ph'])}" autocomplete="off">
        <kbd>/</kbd>
      </label>
      <div class="tiers" id="tiers" role="group"></div>
      <div class="chips" id="chips" role="group"></div>
      <span class="count" id="count"></span>
    </div>
    <div id="list">
      <p class="loading">{u['loading']}</p>
      <h2>{u['cats_title']}</h2>
      <ol class="fallback">{fallback}</ol>
    </div>
  </main>
</div>
"""
    return (head(lang, base, title, desc, "home", None, assets, jsonld=jsonld, extra=extra) + topbar(lang, "home", None, assets)
            + body + footer(lang) + f'<script src="/assets/{assets["js"]}" defer></script>\n</body>\n</html>\n')


def page_term(lang, base, r, prev_r, next_r, cats, byid, assets):
    u = UI[lang]
    ci = CAT_KEYS.index(r["category"])
    c = cats[ci]
    s = c["sections"][r["sec"]] if r["sec"] < len(c["sections"]) else {"title": ""}
    alt = r["alt"] if r["alt"] and r["alt"] != r["name"] else ""
    if lang == "zh":
        title = f"{r['name']}（{alt}）是什么 - {SITE_NAME[lang]}" if alt and len(alt) <= 40 else f"{r['name']} 是什么 - {SITE_NAME[lang]}"
    else:
        title = f"What is {r['name']}? - {SITE_NAME[lang]}"
    desc = desc_of(r)
    jsonld = {"@context": "https://schema.org", "@type": "DefinedTerm", "name": r["name"],
              "alternateName": [x for x in [alt, r.get("abbr")] + list(r.get("aliases") or []) if x],
              "description": r["one_liner"], "url": base + paths(lang, "term", r["id"]),
              "inDefinedTermSet": {"@type": "DefinedTermSet", "name": SITE_NAME[lang], "url": base + paths(lang, "home")}}
    head_bits = f"<h1>{esc(r['name'])}</h1>"
    if alt:
        head_bits += f'<span class="alt">{esc(alt)}</span>'
    if r.get("abbr") and r["abbr"] not in (r["name"], alt):
        head_bits += f'<span class="ab">{esc(r["abbr"])}</span>'
    head_bits += f'<span class="tier t{r["tier"]}">{TIER[lang][r["tier"]]}</span>'
    facts = []
    if r.get("aliases"):
        facts.append((u["aka"], esc(("、" if lang == "zh" else ", ").join(r["aliases"]))))
    rel = []
    for i, name in enumerate(r.get("related") or []):
        ids = r.get("related_ids") or []
        rid = ids[i] if i < len(ids) else None
        if rid and rid in byid and rid != r["id"]:
            rel.append(f'<a href="{paths(lang, "term", rid)}">{esc(byid[rid]["name"])}</a>')
        else:
            rel.append(esc(name))
    if rel:
        facts.append((u["related"], ("、" if lang == "zh" else " · ").join(rel)))
    if r.get("sources"):
        facts.append((u["sources"], src_html(lang, r["sources"])))
    if r.get("as_of"):
        facts.append((u["asof"], esc(r["as_of"])))
    dl = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in facts)
    pn = ""
    if prev_r:
        pn += f'<a class="pv" href="{paths(lang, "term", prev_r["id"])}"><span class="k">← {u["prev"]}</span><span class="v">{esc(prev_r["name"])}</span></a>'
    if next_r:
        pn += f'<a class="nx" href="{paths(lang, "term", next_r["id"])}"><span class="k">{u["next"]} →</span><span class="v">{esc(next_r["name"])}</span></a>'
    body = f"""<main class="page">
  <nav class="crumbs"><a href="{paths(lang, 'home')}">{u['home']}</a><span>›</span><a href="{paths(lang, 'cat', r['category'])}">{ci + 1} {esc(c['name'])}</a><span>›</span><a href="{paths(lang, 'cat', r['category'])}#s-{r['sec']}">{ci + 1}.{r['sec'] + 1} {esc(s['title'])}</a></nav>
  <article class="term-full">
    <div class="head">{head_bits}</div>
    <p class="one">{esc(r['one_liner'])}</p>
    <p class="exp">{esc(r['explanation'])}</p>
    {f'<p class="ex"><span class="k">{u["example"]}</span>{esc(r["example"])}</p>' if r.get("example") else ""}
    <dl class="facts">{dl}</dl>
  </article>
  <nav class="pn">{pn}</nav>
  <p class="back"><a href="{paths(lang, 'home')}#{r['id']}">{u['in_app']}</a></p>
</main>
"""
    return (head(lang, base, title, desc, "term", r["id"], assets, og_type="article", jsonld=jsonld)
            + topbar(lang, "term", r["id"], assets) + body + footer(lang) + "</body>\n</html>\n")


def cat_item(lang, r):
    alt = f'<span class="alt">{esc(r["alt"])}</span>' if r["alt"] and r["alt"] != r["name"] else ""
    dot = f'<span class="t1d" title="{esc(TIER[lang][1])}"></span>' if r["tier"] == 1 else ""
    return (f'<li><div class="nm"><a href="{paths(lang, "term", r["id"])}">{esc(r["name"])}</a>{alt}{dot}</div>'
            f'<div class="d">{esc(r["one_liner"])}</div></li>')


def page_cat(lang, base, ci, cats, recs, assets):
    u = UI[lang]
    c = cats[ci]
    items = [r for r in recs if r["category"] == c["key"]]
    title = f"{c['name']} - {SITE_NAME[lang]}"
    desc = c["blurb"]
    route = "".join(
        f'<li><a href="#s-{si}"><span class="sno">{ci + 1}.{si + 1}</span><span class="t">{esc(s["title"])}</span>'
        f'<span class="n">{sum(1 for r in items if r["sec"] == si)}</span></a></li>'
        for si, s in enumerate(c["sections"]) if any(r["sec"] == si for r in items))
    secs = ""
    for si, s in enumerate(c["sections"]):
        group = [r for r in items if r["sec"] == si]
        if not group:
            continue
        lis = "".join(cat_item(lang, r) for r in group)
        secs += (f'<section id="s-{si}"><h2><span class="sno">{ci + 1}.{si + 1}</span>{esc(s["title"])}</h2>'
                 f'<p class="sec-blurb">{esc(s["blurb"])}</p><ul class="termlist">{lis}</ul></section>')
    pn = ""
    if ci > 0:
        pc = cats[ci - 1]
        pn += f'<a class="pv" href="{paths(lang, "cat", pc["key"])}"><span class="k">← {u["prev_cat"]}</span><span class="v">{ci} {esc(pc["name"])}</span></a>'
    if ci < len(cats) - 1:
        nc = cats[ci + 1]
        pn += f'<a class="nx" href="{paths(lang, "cat", nc["key"])}"><span class="k">{u["next_cat"]} →</span><span class="v">{ci + 2} {esc(nc["name"])}</span></a>'
    body = f"""<main class="page wide cat-page">
  <nav class="crumbs"><a href="{paths(lang, 'home')}">{u['home']}</a><span>›</span><span>{ci + 1} {esc(c['name'])}</span></nav>
  <h1><span class="cno">{ci + 1:02d}</span>{esc(c['name'])}</h1>
  <p class="blurb">{esc(c['blurb'])} · {len(items)} {u['terms']}</p>
  <ol class="route">{route}</ol>
  {secs}
  <nav class="pn">{pn}</nav>
  <p class="back"><a href="{paths(lang, 'home')}#cat-{c['key']}">{u['in_app']}</a></p>
</main>
"""
    return (head(lang, base, title, desc, "cat", c["key"], assets) + topbar(lang, "cat", c["key"], assets)
            + body + footer(lang) + "</body>\n</html>\n")


def page_404(assets):
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>404 - {SITE_NAME['zh']}</title><meta name="robots" content="noindex">
<link rel="icon" href="/assets/{assets['favicon']}" type="image/svg+xml"><link rel="stylesheet" href="/assets/{assets['css']}"></head>
<body><main class="page"><h1>404</h1><p>{UI['zh']['not_found']} <a href="/">返回名词表</a></p>
<p lang="en">{UI['en']['not_found']} <a href="/en/">Back to the glossary</a></p></main></body></html>
"""


def sitemap(base, recs, cats):
    urls = [("home", None)] + [("cat", c["key"]) for c in cats] + [("term", r["id"]) for r in recs]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for kind, x in urls:
        zh_u, en_u = base + paths("zh", kind, x), base + paths("en", kind, x)
        alts = (f'<xhtml:link rel="alternate" hreflang="zh-CN" href="{zh_u}"/>'
                f'<xhtml:link rel="alternate" hreflang="en" href="{en_u}"/>'
                f'<xhtml:link rel="alternate" hreflang="x-default" href="{zh_u}"/>')
        for loc in (zh_u, en_u):
            out.append(f"<url><loc>{loc}</loc><lastmod>{TODAY}</lastmod>{alts}</url>")
    out.append("</urlset>")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", help="正式域名，如 https://example.com")
    args = ap.parse_args()
    base = (args.base_url or CFG["base_url"]).rstrip("/")

    terms, sections = build.load()
    build.link_related(terms)
    en, en_sec = load_en(), load_en_sections()
    missing_now = sum(1 for t in terms if t["key"] not in en)
    slugs = assign_slugs(terms, en, persist=(missing_now == 0))
    recs, cats, missing = make_records(terms, sections, en, en_sec, slugs)

    if os.path.isdir(SITE):
        shutil.rmtree(SITE)
    os.makedirs(SITE)

    # 静态资源（文件名带内容哈希，可以放心长期缓存）
    assets = {}
    for key, name in [("css", "style.css"), ("js", "app.js"), ("favicon", "favicon.svg")]:
        data = open(os.path.join(TOOLS, "site", name), "rb").read()
        assets[key] = hashed(name, data)
        write(f"assets/{assets[key]}", data, "wb")

    for lang in ("zh", "en"):
        payload = json.dumps({"lang": lang, "today": TODAY, "cats": cats[lang], "terms": recs[lang]},
                             ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        data_file = hashed(f"{lang}.json", payload)
        write(f"data/{data_file}", payload, "wb")
        pre = "" if lang == "zh" else "en/"
        write(f"{pre}index.html", page_home(lang, base, recs[lang], cats[lang], assets, data_file))
        byid = {r["id"]: r for r in recs[lang]}
        seq = recs[lang]
        for i, r in enumerate(seq):
            write(f"{pre}t/{r['id']}/index.html",
                  page_term(lang, base, r, seq[i - 1] if i > 0 else None, seq[i + 1] if i + 1 < len(seq) else None,
                            cats[lang], byid, assets))
        for ci in range(len(cats[lang])):
            write(f"{pre}c/{cats[lang][ci]['key']}/index.html", page_cat(lang, base, ci, cats[lang], recs[lang], assets))

    write("404.html", page_404(assets))
    write("sitemap.xml", sitemap(base, recs["zh"], cats["zh"]))
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {base}/sitemap.xml\n")
    write("_headers", "/assets/*\n  Cache-Control: public, max-age=31536000, immutable\n"
                      "/data/*\n  Cache-Control: public, max-age=31536000, immutable\n"
                      "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n")

    n_files = sum(len(f) for _, _, f in os.walk(SITE))
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(SITE) for f in fs)
    print(f"site/ 生成完毕：{len(recs['zh'])} 条 × 2 种语言，{n_files} 个文件，共 {size / 1e6:.1f} MB，base_url = {base}")
    if missing:
        print(f"注意：{missing} 条还没有英文版，暂时用中文顶替；网址（slug）也暂不固定，等英文版齐了再生成一次")
    if base.endswith("example.com"):
        print("注意：base_url 还是占位的 example.com，定了域名后用 --base-url 重新生成")


if __name__ == "__main__":
    main()
