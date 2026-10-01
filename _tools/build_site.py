"""生成可部署到 Cloudflare 的静态站点 site/：中文、英文两版，外加每个词、每个分类各一个静态页面（给搜索引擎和单条分享用）。

用法：python3 _tools/build_site.py [--base-url https://你的域名]
- 中文数据：_batches/ + _order/（复用 build.py 的 load）
- 英文版：_batches_en/ 和 _i18n/en_sections.json；缺英文的词条先用中文顶上，并打印数量
- 词条网址 /t/<slug>/ 第一次完整生成后记进 _tools/slugs.json，之后改名也不变，外链不会失效
- base_url 只影响 canonical、hreflang、sitemap 里的绝对地址，默认读 _tools/site_config.json
- 搜索引擎和 AI 用的东西也在这里生成：分享预览图 og/、结构化数据（JSON-LD）、关于页 /about/、
  llms.txt 和全文 llms-full*.txt、固定网址的数据下载 downloads/、IndexNow 的 key 文件
"""
import argparse
import collections
import hashlib
import html
import json
import os
import re
import shutil
import struct
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
BRAND = "EmbodiedTerms"   # 结构化数据里的站名：中英文搜索结果里都看得懂，和域名一致
LANG_TAG = {"zh": "zh-CN", "en": "en"}
LICENSE_URL = "https://creativecommons.org/licenses/by-nc/4.0/"
OG_ALT = {"zh": "具身智能新手名词表：2900+ 个专有名词，中英双语，按学习顺序排",
          "en": "Embodied AI Glossary: 2,900+ embodied-AI and robotics terms for newcomers, in English and Chinese"}
OG_IMG = {}   # main() 里填：lang -> (网址路径, 宽, 高)
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
        "about": "关于本站",
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
        "about": "About",
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


def png_size(data: bytes):
    return struct.unpack(">II", data[16:24])


def uniq(xs, exclude=()):
    """去重（不分大小写），保持顺序，顺便去掉和 exclude 重复的。"""
    seen = {str(e).strip().lower() for e in exclude if e}
    out = []
    for x in xs:
        x = str(x or "").strip()
        if x and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out


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
    return {"home": f"{pre}/", "term": f"{pre}/t/{x}/", "cat": f"{pre}/c/{x}/", "about": f"{pre}/about/"}[kind]


def head(lang, base, title, desc, kind, x, assets, og_type="website", jsonld=None, extra=""):
    zh_p, en_p = paths("zh", kind, x), paths("en", kind, x)
    canon = base + (zh_p if lang == "zh" else en_p)
    ld = ""
    if jsonld:
        ld = ('<script type="application/ld+json">' + json.dumps(jsonld, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
              + "</script>")
    og_img = ""
    if lang in OG_IMG:
        src, w, h = OG_IMG[lang]
        og_img = (f'<meta property="og:image" content="{base}{src}">\n<meta property="og:image:type" content="image/png">\n'
                  f'<meta property="og:image:width" content="{w}">\n<meta property="og:image:height" content="{h}">\n'
                  f'<meta property="og:image:alt" content="{esc(OG_ALT[lang])}">\n'
                  f'<meta name="twitter:image" content="{base}{src}">\n<meta name="twitter:image:alt" content="{esc(OG_ALT[lang])}">\n')
    return f"""<!doctype html>
<html lang="{LANG_TAG[lang]}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="author" content="{esc(CFG['author_zh'] if lang == 'zh' else CFG['author_en'])}">
<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1">
<link rel="canonical" href="{canon}">
<link rel="alternate" hreflang="zh-CN" href="{base}{zh_p}">
<link rel="alternate" hreflang="en" href="{base}{en_p}">
<link rel="alternate" hreflang="x-default" href="{base}{zh_p}">
<link rel="license" href="{LICENSE_URL}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canon}">
<meta property="og:site_name" content="{esc(SITE_NAME[lang])}">
<meta property="og:locale" content="{'zh_CN' if lang == 'zh' else 'en_US'}">
<meta property="og:locale:alternate" content="{'en_US' if lang == 'zh' else 'zh_CN'}">
{og_img}<meta name="twitter:card" content="{'summary_large_image' if og_img else 'summary'}">
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
                f'<a href="{paths("zh", "about")}">{UI["zh"]["about"]}</a> · '
                '<a href="/en/" hreflang="en" lang="en">English edition</a></p></footer>\n')
    return (f'<footer class="site"><p>Compiled by <b>{esc(CFG["author_en"])}</b></p>'
            '<p>Researched and drafted with AI assistance; every entry links to its sources. The companies, robots and notable-models '
            'categories and all Essential entries were independently fact-checked. The English edition is adapted from the Chinese '
            f'original. Spotted an error or a missing term? <a href="{fb}" rel="noopener">Open an issue on GitHub</a>.</p>'
            f'<p>Content licensed under <a href="https://creativecommons.org/licenses/by-nc/4.0/" rel="license noopener">CC BY-NC 4.0</a>; '
            f'<a href="{esc(CFG["repo_url"])}" rel="noopener">source and data on GitHub</a> · Facts as of {TODAY} · '
            f'<a href="{paths("en", "about")}">{UI["en"]["about"]}</a> · '
            '<a href="/" hreflang="zh-CN" lang="zh-CN">中文版</a></p></footer>\n')


# ---------- 结构化数据（JSON-LD）：同一个站、作者、名词表在各页用同一个 @id 互相指 ----------

def ld_ids(base, lang):
    return {"website": f"{base}/#website", "author": f"{base}/#author", "glossary": base + paths(lang, "home") + "#glossary"}


def ld_person(base):
    p = {"@type": "Person", "@id": f"{base}/#author", "name": CFG["author_zh"], "alternateName": "Kelip"}
    if CFG.get("author_url"):
        p["url"] = CFG["author_url"]
        p["sameAs"] = [CFG["author_url"]]
    return p


def ld_website(base, full=False):
    w = {"@type": "WebSite", "@id": f"{base}/#website", "url": f"{base}/", "name": BRAND}
    if full:
        w.update({"alternateName": [SITE_NAME["zh"], SITE_NAME["en"]], "inLanguage": ["zh-CN", "en"],
                  "description": "具身智能和机器人领域 2900 多个专有名词的中英双语入门名词表 / A bilingual glossary of 2,900+ "
                                 "embodied-AI and robotics terms for newcomers.",
                  "author": {"@id": f"{base}/#author"}, "publisher": {"@id": f"{base}/#author"}, "license": LICENSE_URL})
    return w


def ld_glossary(base, lang):
    return {"@type": "DefinedTermSet", "@id": ld_ids(base, lang)["glossary"], "name": SITE_NAME[lang], "url": base + paths(lang, "home")}


def ld_breadcrumb(base, url, trail):
    return {"@type": "BreadcrumbList", "@id": url + "#breadcrumb",
            "itemListElement": [{"@type": "ListItem", "position": i, "name": name, "item": base + p}
                                for i, (name, p) in enumerate(trail, 1)]}


def ld_graph(*nodes):
    return {"@context": "https://schema.org", "@graph": list(nodes)}


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
    ids, home = ld_ids(base, lang), base + paths(lang, "home")
    glossary = dict(ld_glossary(base, lang), inLanguage=LANG_TAG[lang], description=desc, license=LICENSE_URL,
                    author={"@id": ids["author"]}, dateModified=TODAY, isPartOf={"@id": ids["website"]},
                    hasPart=[{"@type": "DefinedTermSet", "name": c["name"], "url": base + paths(lang, "cat", c["key"])} for c in cats])
    jsonld = ld_graph(ld_website(base, full=True), ld_person(base), glossary,
                      {"@type": "WebPage", "@id": home, "url": home, "name": title, "inLanguage": LANG_TAG[lang],
                       "isPartOf": {"@id": ids["website"]}, "mainEntity": {"@id": ids["glossary"]}, "dateModified": TODAY})
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


def has_word(word, text):
    return bool(re.search(r"(?<![A-Za-z0-9])" + re.escape(word) + r"(?![A-Za-z0-9])", text or "", re.I))


def before_colon(s, limit):
    """论文全名太长时，标题里只留冒号前的名字：「Diffusion Policy: Visuomotor Policy Learning…」→「Diffusion Policy」。"""
    return s.split(":")[0].strip() if len(s) > limit and ":" in s else s


def term_title(lang, r):
    """标题里带上缩写：大家搜的常常是「VLA 是什么」「What is ZMP」。"""
    name, ab = r["name"], (r.get("abbr") or "").strip()
    alt = r["alt"] if r["alt"] and r["alt"] != r["name"] else ""
    if lang == "en":
        name = before_colon(name, 60)
    ab = ab if ab and not has_word(ab, name) else ""
    if lang == "zh":
        alt = before_colon(alt, 40)
        words = re.findall(r"[a-z0-9]+", alt.lower())
        overlap = sum(w in re.findall(r"[a-z0-9]+", name.lower()) for w in words) / max(len(words), 1)
        if alt and (len(alt) > 40 or alt.lower() in name.lower() or name.lower() in alt.lower() or overlap >= 0.6):
            alt = ""   # 中文名里已经带了英文（如「World Models 论文（Ha & Schmidhuber）」），不再重复一遍
        extra = [x for x in [ab, alt] if x]
        if ab and alt and has_word(ab, alt):
            extra = [alt]
        inner = f"（{', '.join(extra)}）" if extra else " "
        return f"{name}{inner}是什么 - {SITE_NAME[lang]}"
    return f"What is {name}{f' ({ab})' if ab else ''}? - {SITE_NAME[lang]}"


def page_term(lang, base, r, prev_r, next_r, cats, byid, assets):
    u = UI[lang]
    ci = CAT_KEYS.index(r["category"])
    c = cats[ci]
    s = c["sections"][r["sec"]] if r["sec"] < len(c["sections"]) else {"title": ""}
    alt = r["alt"] if r["alt"] and r["alt"] != r["name"] else ""
    title = term_title(lang, r)
    desc = desc_of(r)
    ids, url = ld_ids(base, lang), base + paths(lang, "term", r["id"])
    webpage = {"@type": "WebPage", "@id": url, "url": url, "name": title, "description": desc, "inLanguage": LANG_TAG[lang],
               "isPartOf": {"@id": ids["website"]}, "breadcrumb": {"@id": url + "#breadcrumb"}, "mainEntity": {"@id": url + "#term"},
               "dateModified": TODAY, "author": {"@id": ids["author"]}, "license": LICENSE_URL}
    if r.get("sources"):
        webpage["citation"] = [{"@type": "CreativeWork", "name": x.get("title") or x["url"], "url": x["url"]} for x in r["sources"]]
    term = {"@type": "DefinedTerm", "@id": url + "#term", "name": r["name"], "description": r["one_liner"], "url": url,
            "inLanguage": LANG_TAG[lang], "inDefinedTermSet": ld_glossary(base, lang)}
    names = uniq([alt, r.get("abbr")] + list(r.get("aliases") or []), exclude=[r["name"]])
    if names:
        term["alternateName"] = names
    jsonld = ld_graph(webpage, term,
                      ld_breadcrumb(base, url, [(u["home"], paths(lang, "home")), (c["name"], paths(lang, "cat", c["key"])),
                                                (r["name"], paths(lang, "term", r["id"]))]),
                      ld_website(base), ld_person(base))
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
    ids, url = ld_ids(base, lang), base + paths(lang, "cat", c["key"])
    jsonld = ld_graph({"@type": "CollectionPage", "@id": url, "url": url, "name": title, "description": desc, "inLanguage": LANG_TAG[lang],
                       "isPartOf": {"@id": ids["website"]}, "breadcrumb": {"@id": url + "#breadcrumb"},
                       "about": ld_glossary(base, lang), "dateModified": TODAY, "author": {"@id": ids["author"]}, "license": LICENSE_URL},
                      ld_breadcrumb(base, url, [(u["home"], paths(lang, "home")), (c["name"], paths(lang, "cat", c["key"]))]),
                      ld_website(base), ld_person(base))
    return (head(lang, base, title, desc, "cat", c["key"], assets, jsonld=jsonld) + topbar(lang, "cat", c["key"], assets)
            + body + footer(lang) + "</body>\n</html>\n")


ABOUT = {
    "zh": """<main class="page about">
  <nav class="crumbs"><a href="/">{home}</a><span>›</span><span>{about}</span></nav>
  <h1>关于这份名词表</h1>
  <p class="lead">给刚入门具身智能的同学查词用：{n} 个专有名词，分 14 类，按学习顺序排。每条有一句话解释、展开说明、例子、相关词和来源链接。中英双语，英文版按英文读者的习惯改写，不是逐句直译。</p>
  <h2>怎么用</h2>
  <ul>
    <li>首页默认只列 <b>入门必知</b> 的 {t1} 条，适合从头读一遍；点「入门 + 常用」或「全部」，可以看到另外 {t2} 条常用词和 {t3} 条进阶词。</li>
    <li>搜索框支持中文、英文和缩写（比如 VLA、逆运动学、宇树），搜索时不受分级限制。</li>
    <li>每个词都有自己的页面，可以直接分享{example}。</li>
  </ul>
  <h2>14 个类别</h2>
  <p>先认识机器人本体：形态、零件、怎么动、怎么控制、怎么感知；再看软件工具和仿真；然后是数据、训练和模型；最后是公司和行业说法。每类内部也分成由浅入深的小节。</p>
  <ol class="cats">{cats}</ol>
  <h2>内容怎么来的</h2>
  <p>词条由 AI 辅助检索和整理，再按学习顺序编排，每条都附了来源链接，方便自己核对。</p>
  <p>「公司与机构」「机器人类型与代表产品」「代表性模型与工作」三类，以及全部 {t1} 条「入门必知」，另外做过一轮独立核查：重新检索，逐条对照来源，改正了查出来的错误。这轮核查同样借助 AI 完成，不等于人工逐条审校，所以难免还有错。</p>
  <p>公司、产品、模型这类会变的信息，事实截至 {today}；个别词条单独标了「信息截至」。</p>
  <h2>纠错和补充</h2>
  <p>发现错误或想补充词条，欢迎到 <a href="{feedback}" rel="noopener">GitHub</a> 提 issue，或在公众号「{wechat}」留言。</p>
  <h2>引用和转载</h2>
  <p>内容采用 <a href="https://creativecommons.org/licenses/by-nc/4.0/deed.zh-hans" rel="license noopener">CC BY-NC 4.0</a> 许可：可以转载和改编，要署名，不能商用。建议这样署名：</p>
  <p><code>{author}，《{name}》，{base}/</code></p>
  <p>引用某一个词条时，请链接到它自己的页面。</p>
  <h2>数据下载</h2>
  <ul>
    <li>JSON：<a href="/downloads/glossary-zh.json">中文版</a> · <a href="/downloads/glossary-en.json" hreflang="en">英文版</a>（全部词条、分类和来源）</li>
    <li>纯文本全文：<a href="/llms-full-zh.txt">中文</a> · <a href="/llms-full.txt" hreflang="en">英文</a>；给 AI 读的索引在 <a href="/llms.txt">llms.txt</a></li>
    <li><a href="{repo}" rel="noopener">GitHub 仓库</a>：全部数据和生成这个网站的脚本，代码采用 MIT 许可</li>
  </ul>
  <h2>作者</h2>
  <p>整理：<b>{author}</b>，公众号「{wechat}」。</p>
</main>
""",
    "en": """<main class="page about">
  <nav class="crumbs"><a href="/en/">{home}</a><span>›</span><span>{about}</span></nav>
  <h1>About this glossary</h1>
  <p class="lead">A glossary for people new to embodied AI: {n} terms in 14 categories, ordered as a learning path. Every entry has a one-line definition, a plain-language explanation, an example, related terms and source links. The site is bilingual; the English edition is adapted for English readers from the Chinese original rather than translated line by line.</p>
  <h2>How to use it</h2>
  <ul>
    <li>The home page starts with the {t1} <b>Essential</b> entries, which you can read straight through. Switch to “Essential + Common” or “All” to see the other {t2} common and {t3} advanced terms.</li>
    <li>Search works with English, Chinese and abbreviations (VLA, inverse kinematics, Unitree) and always covers every level.</li>
    <li>Every term has its own page you can link to{example}.</li>
  </ul>
  <h2>The 14 categories</h2>
  <p>First the robot body (form factors, parts, how it moves, how it is controlled, how it senses), then software and simulation, then data, training and models, and finally companies and the industry's vocabulary. Each category is split into sections that go from basic to advanced.</p>
  <ol class="cats">{cats}</ol>
  <h2>How it was made</h2>
  <p>Entries were researched and drafted with AI assistance, then arranged into the learning path. Every entry links to its sources so you can check them yourself.</p>
  <p>The companies, robots and landmark-models categories, plus all {t1} Essential entries, went through a separate fact-check: a fresh round of research that compared each entry with its sources and fixed the errors it found. That pass was also AI-assisted rather than a line-by-line human review, so mistakes are still possible.</p>
  <p>Facts that change, such as companies, products and models, are current as of {today}; some entries carry their own “As of” date.</p>
  <h2>Corrections</h2>
  <p>Found an error or a missing term? <a href="{feedback}" rel="noopener">Open an issue on GitHub</a>.</p>
  <h2>Citing and reuse</h2>
  <p>Content is licensed under <a href="https://creativecommons.org/licenses/by-nc/4.0/" rel="license noopener">CC BY-NC 4.0</a>: you may share and adapt it with attribution, but not for commercial purposes. Suggested attribution:</p>
  <p><code>{author}, {name}, {base}/en/</code></p>
  <p>When you cite a single term, please link to its own page.</p>
  <h2>Downloads</h2>
  <ul>
    <li>JSON: <a href="/downloads/glossary-en.json">English</a> · <a href="/downloads/glossary-zh.json" hreflang="zh-CN">Chinese</a> (all terms, categories and sources)</li>
    <li>Full text: <a href="/llms-full.txt">English</a> · <a href="/llms-full-zh.txt" hreflang="zh-CN">Chinese</a>, with an index for AI tools at <a href="/llms.txt">llms.txt</a></li>
    <li><a href="{repo}" rel="noopener">GitHub repository</a>: all the data and the scripts that build this site; code under the MIT license</li>
  </ul>
  <h2>Who made it</h2>
  <p>Compiled by <b>{author}</b>.</p>
</main>
""",
}


def page_about(lang, base, recs, cats, assets):
    u = UI[lang]
    tc = collections.Counter(r["tier"] for r in recs)
    counts = collections.Counter(r["category"] for r in recs)
    cat_li = "".join(f'<li><a href="{paths(lang, "cat", c["key"])}">{i + 1} {esc(c["name"])}</a><span class="n">{counts[c["key"]]}</span></li>'
                     for i, c in enumerate(cats))
    ik = next((r for r in recs if r["id"] == "inverse-kinematics"), None)
    example = ""
    if ik:
        example = (f'，比如 <a href="{paths(lang, "term", ik["id"])}">{esc(ik["name"])}</a>' if lang == "zh"
                   else f', such as <a href="{paths(lang, "term", ik["id"])}">{esc(ik["name"])}</a>')
    fmt = (lambda k: f"{k:,}") if lang == "en" else str
    body = ABOUT[lang].format(
        home=u["home"], about=u["about"], n=fmt(len(recs)), t1=fmt(tc[1]), t2=fmt(tc[2]), t3=fmt(tc[3]), example=example, cats=cat_li,
        today=TODAY, feedback=esc(CFG["feedback_url"]), wechat=esc(CFG["wechat"]), repo=esc(CFG["repo_url"]), base=base,
        author=esc(CFG["author_zh"] if lang == "zh" else CFG["author_en"]), name=esc(SITE_NAME[lang]))
    if lang == "zh":
        title = f"关于本站：内容怎么来的、怎么引用 - {SITE_NAME[lang]}"
        desc = f"{SITE_NAME[lang]}的说明：{len(recs)} 个具身智能专有名词怎么整理、哪些经过事实核查、事实截至哪天、怎么引用和转载、数据下载。"
    else:
        title = f"About: how it was made and how to cite it - {SITE_NAME[lang]}"
        desc = (f"How the {len(recs):,} entries of the {SITE_NAME[lang]} were researched and fact-checked, how current they are, "
                "how to cite and reuse them, and where to download the data.")
    ids, url = ld_ids(base, lang), base + paths(lang, "about")
    dataset = {
        "@type": "Dataset", "@id": f"{base}/#dataset", "name": f"{SITE_NAME['en']} / {SITE_NAME['zh']}",
        "description": (f"A bilingual (Chinese and English) glossary of {len(recs):,} embodied-AI and robotics terms in 14 categories, "
                        "each with a one-line definition, a plain-language explanation, an example, related terms and source links. "
                        f"具身智能新手名词表：{len(recs)} 个专有名词，中英双语。"),
        "url": url, "license": LICENSE_URL, "isAccessibleForFree": True, "creator": {"@id": ids["author"]},
        "inLanguage": ["zh-CN", "en"], "dateModified": TODAY,
        "keywords": ["embodied AI", "robotics", "glossary", "humanoid robot", "VLA", "具身智能", "机器人", "名词表"],
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{base}/downloads/glossary-zh.json", "inLanguage": "zh-CN"},
            {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{base}/downloads/glossary-en.json", "inLanguage": "en"},
            {"@type": "DataDownload", "encodingFormat": "text/markdown", "contentUrl": f"{base}/llms-full-zh.txt", "inLanguage": "zh-CN"},
            {"@type": "DataDownload", "encodingFormat": "text/markdown", "contentUrl": f"{base}/llms-full.txt", "inLanguage": "en"}]}
    jsonld = ld_graph({"@type": "AboutPage", "@id": url, "url": url, "name": title, "description": desc, "inLanguage": LANG_TAG[lang],
                       "isPartOf": {"@id": ids["website"]}, "breadcrumb": {"@id": url + "#breadcrumb"}, "about": {"@id": ids["website"]},
                       "author": {"@id": ids["author"]}, "dateModified": TODAY},
                      dataset, ld_breadcrumb(base, url, [(u["home"], paths(lang, "home")), (u["about"], paths(lang, "about"))]),
                      ld_website(base), ld_person(base))
    return (head(lang, base, title, desc, "about", None, assets, jsonld=jsonld) + topbar(lang, "about", None, assets)
            + body + footer(lang) + "</body>\n</html>\n")


# ---------- 给 AI 和程序读的：llms.txt、全文、JSON 下载 ----------

LLM_LABEL = {
    "zh": {"alt": "英文", "abbr": "缩写", "tier": "分级", "aka": "也叫", "url": "链接", "example": "例子", "related": "相关",
           "sources": "来源", "asof": "信息截至", "sep": "；"},
    "en": {"alt": "Chinese", "abbr": "Abbreviation", "tier": "Tier", "aka": "Also called", "url": "URL", "example": "Example",
           "related": "Related", "sources": "Sources", "asof": "As of", "sep": "; "},
}


def llms_index(base, recs, cats):
    """llms.txt：按 llmstxt.org 的格式写一份索引，告诉 AI 这个站有什么、去哪读全文、怎么引用。"""
    n = len(recs["en"])
    tc = collections.Counter(r["tier"] for r in recs["en"])
    counts = collections.Counter(r["category"] for r in recs["en"])
    out = [f"# {SITE_NAME['en']} ({SITE_NAME['zh']})", "",
           f"> A bilingual (English and Chinese) glossary of {n:,} embodied-AI and robotics terms for newcomers, in 14 categories "
           "ordered as a learning path. Every entry has a one-line definition, a plain-language explanation, an example, related "
           f"terms and source links. Facts as of {TODAY}. Compiled by {CFG['author_en']}; content licensed CC BY-NC 4.0.", "",
           f"Each term has its own page, with the same slug in both languages: English at {base}/en/t/<slug>/ and Chinese at "
           f"{base}/t/<slug>/. When you quote or paraphrase a definition, please link to that term's page.", "",
           f"Difficulty tiers: Essential ({tc[1]}), Common ({tc[2]}), Advanced ({tc[3]}). The companies, robots and landmark-models "
           "categories and all Essential entries were re-checked against their sources in a second, AI-assisted research pass.", "",
           "## Categories", ""]
    for i, c in enumerate(cats["en"]):
        out.append(f"- [{i + 1}. {c['name']}]({base}{paths('en', 'cat', c['key'])}): {c['blurb']} ({counts[c['key']]} terms)")
    out += ["", "## 分类（中文）", ""]
    for i, c in enumerate(cats["zh"]):
        out.append(f"- [{i + 1}. {c['name']}]({base}{paths('zh', 'cat', c['key'])})：{c['blurb']}（{counts[c['key']]} 条）")
    out += ["", "## Full text and data", "",
            f"- [Full glossary in English]({base}/llms-full.txt): every term with its definition, explanation, example, related terms and sources, as Markdown",
            f"- [Full glossary in Chinese]({base}/llms-full-zh.txt): 中文全文，格式同上",
            f"- [JSON, English]({base}/downloads/glossary-en.json): the same data, structured",
            f"- [JSON, Chinese]({base}/downloads/glossary-zh.json)", "",
            "## Optional", "",
            f"- [About and methodology]({base}/en/about/): how entries were researched and fact-checked, and how to cite them",
            f"- [关于本站]({base}/about/)",
            f"- [Source code and data on GitHub]({CFG['repo_url']})", ""]
    return "\n".join(out)


def llms_full(lang, base, recs, cats):
    """全文：类 → 小节 → 词条，一个文件读完整个名词表。"""
    L = LLM_LABEL[lang]
    tier = TIER[lang]
    if lang == "zh":
        intro = [f"# {SITE_NAME['zh']}（全文）", "",
                 f"> 给具身智能新手的名词表：{len(recs)} 个专有名词，14 类，按学习顺序排。整理：{CFG['author_zh']}。"
                 f"事实截至 {TODAY}。内容采用 CC BY-NC 4.0 许可，引用请链接到对应词条页。", "",
                 f"网站：{base}/ · 英文版：{base}/llms-full.txt · 说明：{base}/about/", ""]
    else:
        intro = [f"# {SITE_NAME['en']} (full text)", "",
                 f"> A glossary for newcomers to embodied AI: {len(recs):,} terms in 14 categories, ordered as a learning path. "
                 f"Compiled by {CFG['author_en']}. Facts as of {TODAY}. Licensed CC BY-NC 4.0; when citing, link to the term's page.", "",
                 f"Website: {base}/en/ · Chinese edition: {base}/llms-full-zh.txt · About: {base}/en/about/", ""]
    out = intro
    for ci, c in enumerate(cats):
        out += [f"## {ci + 1}. {c['name']}", "", c["blurb"], ""]
        for si, s in enumerate(c["sections"]):
            group = [r for r in recs if r["category"] == c["key"] and r["sec"] == si]
            if not group:
                continue
            out += [f"### {ci + 1}.{si + 1} {s['title']}", ""]
            if s.get("blurb"):
                out += [s["blurb"], ""]
            for r in group:
                facts = []
                if r["alt"] and r["alt"] != r["name"]:
                    facts.append(f"{L['alt']}: {r['alt']}")
                if r.get("abbr") and not has_word(r["abbr"], r["name"]):
                    facts.append(f"{L['abbr']}: {r['abbr']}")
                facts.append(f"{L['tier']}: {tier[r['tier']]}")
                aka = uniq(r.get("aliases") or [], exclude=[r["name"], r["alt"], r.get("abbr")])
                if aka:
                    facts.append(f"{L['aka']}: {', '.join(aka)}")
                out += [f"#### {r['name']}", "", " · ".join(facts), f"{L['url']}: {base}{paths(lang, 'term', r['id'])}", "",
                        r["one_liner"].strip(), ""]
                if r["explanation"].strip():
                    out += [r["explanation"].strip(), ""]
                if r.get("example"):
                    out += [f"{L['example']}: {r['example'].strip()}", ""]
                tail = []
                if r.get("related"):
                    tail.append(f"{L['related']}: {', '.join(x for x in r['related'] if x)}")
                if r.get("sources"):
                    tail.append(f"{L['sources']}: " + L["sep"].join(f"[{x.get('title') or x['url']}]({x['url']})" for x in r["sources"]))
                if r.get("as_of"):
                    tail.append(f"{L['asof']}: {r['as_of']}")
                if tail:
                    out += tail + [""]
    return "\n".join(out)


def download_json(lang, base, recs, cats):
    terms = [dict(r, url=base + paths(lang, "term", r["id"])) for r in recs]
    return {"name": SITE_NAME[lang], "url": base + paths(lang, "home"), "language": LANG_TAG[lang], "as_of": TODAY,
            "author": CFG["author_zh"] if lang == "zh" else CFG["author_en"], "license": "CC BY-NC 4.0", "license_url": LICENSE_URL,
            "source": CFG["repo_url"], "count": len(recs), "categories": cats, "terms": terms}


def page_404(assets):
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>404 - {SITE_NAME['zh']}</title><meta name="robots" content="noindex">
<link rel="icon" href="/assets/{assets['favicon']}" type="image/svg+xml"><link rel="stylesheet" href="/assets/{assets['css']}"></head>
<body><main class="page"><h1>404</h1><p>{UI['zh']['not_found']} <a href="/">返回名词表</a></p>
<p lang="en">{UI['en']['not_found']} <a href="/en/">Back to the glossary</a></p></main></body></html>
"""


def sitemap(base, recs, cats):
    urls = [("home", None), ("about", None)] + [("cat", c["key"]) for c in cats] + [("term", r["id"]) for r in recs]
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

    # 分享预览图：网址固定不带哈希，社交平台按网址缓存，换图后旧链接也不会坏
    for lang in ("zh", "en"):
        src = os.path.join(TOOLS, "site", f"og-{lang}.png")
        if os.path.exists(src):
            data = open(src, "rb").read()
            write(f"og/{lang}.png", data, "wb")
            OG_IMG[lang] = (f"/og/{lang}.png", *png_size(data))

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
        write(f"{pre}about/index.html", page_about(lang, base, recs[lang], cats[lang], assets))
        # 固定网址的数据下载（data/ 下的文件名带哈希，会变，不适合给别人引用）
        write(f"downloads/glossary-{lang}.json",
              json.dumps(download_json(lang, base, recs[lang], cats[lang]), ensure_ascii=False, separators=(",", ":")))

    write("llms.txt", llms_index(base, recs, cats))
    write("llms-full.txt", llms_full("en", base, recs["en"], cats["en"]))
    write("llms-full-zh.txt", llms_full("zh", base, recs["zh"], cats["zh"]))
    if CFG.get("indexnow_key"):
        write(f"{CFG['indexnow_key']}.txt", CFG["indexnow_key"])

    write("404.html", page_404(assets))
    write("sitemap.xml", sitemap(base, recs["zh"], cats["zh"]))
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {base}/sitemap.xml\n")
    txt = "  Content-Type: text/plain; charset=utf-8\n  X-Robots-Tag: noindex\n"   # 全文和词条页内容重复，不进搜索结果，但 AI 照样能读
    write("_headers", "/assets/*\n  Cache-Control: public, max-age=31536000, immutable\n"
                      "/data/*\n  Cache-Control: public, max-age=31536000, immutable\n"
                      f"/llms.txt\n{txt}/llms-full.txt\n{txt}/llms-full-zh.txt\n{txt}"
                      "/downloads/*\n  X-Robots-Tag: noindex\n  Access-Control-Allow-Origin: *\n"
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
