// 具身智能新手名词表 · 首页交互。页面先出框架，再异步加载数据（data/<lang>.<hash>.json）。
(() => {
  const LANG = document.documentElement.lang.startsWith("zh") ? "zh" : "en";
  const BASE = LANG === "zh" ? "/" : "/en/";
  const L = {
    zh: {
      tier: {1: "入门必知", 2: "常用", 3: "进阶"},
      tierBtns: [["1", "入门必知", "var(--must)"], ["2", "入门 + 常用", "var(--accent)"], ["all", "全部", ""]],
      all: "全部", count: (a, b) => `${a} / ${b}`,
      searchCount: (n, f) => f ? `搜到 ${n} 条，另有 ${f} 条相近（全部分级）` : `搜到 ${n} 条（全部分级）`,
      fuzzyOnly: n => `没有完全匹配的词条，下面 ${n} 条最接近`, fuzzyNote: "相近的词条（拼写接近，或问句里提到的词）",
      capped: n => `先显示了前 ${n} 条`, showAll: n => `显示全部 ${n} 条 →`,
      empty: q => `没有匹配「${q}」的词条。试试英文全称或缩写，或把分类切回「全部」。`,
      next: "下一类", example: "例子", aka: "也叫", src: "来源", asof: "截至", terms: n => `${n} 条`,
      perma: "单独页面", loadFail: "词条加载失败，请刷新重试。",
      stages: ["先建立地图", "认识机器人本体", "工具与仿真", "怎么学：数据、训练、模型", "谁在做、怎么说"],
      zhSource: "",
    },
    en: {
      tier: {1: "Essential", 2: "Common", 3: "Advanced"},
      tierBtns: [["1", "Essential", "var(--must)"], ["2", "Essential + Common", "var(--accent)"], ["all", "All", ""]],
      all: "All", count: (a, b) => `${a} / ${b}`,
      searchCount: (n, f) => f ? `${n} matches, plus ${f} close matches (all levels)` : `${n} matches (all levels)`,
      fuzzyOnly: n => `No exact matches. The ${n} closest entries:`, fuzzyNote: "Close matches (similar spelling, or terms named in your query)",
      capped: n => `Showing the first ${n}`, showAll: n => `Show all ${n} →`,
      empty: q => `No entries match “${q}”. Try the full name or an abbreviation, or switch the category back to All.`,
      next: "Next category", example: "Example", aka: "Also called", src: "Sources", asof: "As of", terms: n => `${n} terms`,
      perma: "Open as a page", loadFail: "Couldn't load the entries. Please refresh the page.",
      stages: ["Start with the map", "Meet the robot body", "Tools & simulation", "How robots learn: data, training, models", "Who's building it & how they talk"],
      zhSource: " (Chinese)",
    },
  }[LANG];
  const STAGE_AT = [0, 1, 6, 8, 12];
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  // 搜索统一按「规范化」后的文字比：全角转半角、大小写不分、π 记作 pi；compact 再去掉空格和标点，
  // 这样 ROS2 / ROS 2、RS485 / RS-485、π0.5 / pi05、zero rpc / zerorpc 都能互相搜到
  const norm = s => String(s ?? "").normalize("NFKC").toLowerCase().replace(/π/g, "pi");
  const compact = s => norm(s).replace(/[^\p{L}\p{N}]+/gu, "");
  const CJK = /[㐀-鿿豈-﫿]/;
  const hasCJK = s => /[一-鿿]/.test(s || "");

  let DATA, byId, catIdx, IDX;
  const CAP = 200;
  const state = {cat: "all", tier: "1", q: "", all: false};
  try { const s = JSON.parse(localStorage.getItem("glossary-view") || "{}"); if (s.tier) state.tier = s.tier; } catch (e) {}

  // 逐字规范化并记下每个字来自原文哪一位，高亮时才能标回原文（π → pi 这类会改变长度）
  function normMap(raw) {
    let s = ""; const map = [];
    for (let i = 0; i < raw.length; i++) {
      const n = raw[i].normalize("NFKC").toLowerCase().replace(/π/g, "pi");
      for (let k = 0; k < n.length; k++) { s += n[k]; map.push(i); }
    }
    return {s, map};
  }

  function hl(text, toks) {
    const raw = String(text ?? "");
    if (!toks || !toks.length || !raw) return esc(raw);
    const {s, map} = normMap(raw);
    let cs = ""; const cmap = [];
    for (let i = 0; i < s.length; i++) if (/[\p{L}\p{N}]/u.test(s[i])) { cs += s[i]; cmap.push(map[i]); }
    const ranges = [];
    for (const t of toks) {
      const short = isShort(t);   // ik、rl 这类短词只标整词，不标 like、world 里的
      for (const [hay, m, needle] of short ? [[s, map, t.n]] : [[s, map, t.n], [cs, cmap, t.c]]) {
        if (!needle) continue;
        for (let i = hay.indexOf(needle); i >= 0 && ranges.length < 60; i = hay.indexOf(needle, i + needle.length)) {
          if (short && (/[a-z0-9]/.test(hay[i - 1] || "") || /[a-z0-9]/.test(hay[i + needle.length] || ""))) continue;
          ranges.push([m[i], m[i + needle.length - 1] + 1]);
        }
      }
    }
    if (!ranges.length) return esc(raw);
    ranges.sort((a, b) => a[0] - b[0]);
    const merged = [];
    for (const r of ranges) { const last = merged[merged.length - 1]; if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]); else merged.push(r.slice()); }
    let out = "", p = 0;
    for (const [a, b] of merged) { out += esc(raw.slice(p, a)) + "<mark>" + esc(raw.slice(a, b)) + "</mark>"; p = b; }
    return out + esc(raw.slice(p));
  }

  // ---------- 搜索 ----------
  // 打分：名字完全一致 1000 > 名字开头 900 > 名字里包含 800 > 每个词都在名字里 700 > 某个词正好是词条名 650 >
  // 一句话解释里有 500 > 正文里有 400。完全匹配不到 8 条时，再列「相近的」：拼错几个字的（170 左右），
  // 或查询里包含了某个词条名的（「逆运动学求解」里的「逆运动学」，160 往上）
  // 名字逐字规范化，同时记下哪些位置是「词的开头」：空格标点之后、大小写切换处（OpenVLA 的 V）、
  // 字母和数字交界（π0 的 0）、每个汉字。英文只认从词开头匹配，免得 tyro 命中 Agili-ty Ro-botics
  const ALNUM = /[\p{L}\p{N}]/u, UPPER = /\p{Lu}/u, LOWER = /\p{Ll}/u, DIGIT = /\p{N}/u;
  function analyze(raw) {
    let n = "", c = "", prev = "";
    const nS = new Set(), cS = new Set();
    for (const ch0 of String(raw)) {
      const ch = ch0.normalize("NFKC");
      const low = ch.toLowerCase().replace(/π/g, "pi");
      if (ALNUM.test(ch)) {
        const p = prev;
        if (!p || !ALNUM.test(p) || CJK.test(ch) || CJK.test(p) || (LOWER.test(p) && UPPER.test(ch)) || DIGIT.test(p) !== DIGIT.test(ch)) {
          nS.add(n.length); cS.add(c.length);
        }
        c += low;
      }
      n += low;
      prev = ch.slice(-1);
    }
    return {n, c, nS, cS};
  }

  function prepIndex() {
    IDX = DATA.terms.map((t, i) => {
      const names = [t.name, t.alt, t.abbr, ...(t.aliases || [])].filter(Boolean).map(analyze);
      const nN = names.map(a => a.n), nC = names.map(a => a.c);
      // 拼写纠错用的英文词：名字拆成单词，再加上去掉空格的整名（difusionpolicy 也能对上 Diffusion Policy）
      const words = new Set();
      nN.forEach((n, k) => {
        n.split(/[^a-z0-9]+/).forEach(w => { if (w.length >= 3) words.add(w); });
        if (/^[a-z0-9]{4,}$/.test(nC[k])) words.add(nC[k]);
      });
      return {t, i, names, nN, nC, words: [...words], oneN: norm(t.one_liner),
              bodyN: norm([t.one_liner, t.explanation, t.example].join(" "))};
    });
    NAMES = new Set(IDX.flatMap(x => x.nC));
  }
  let NAMES;

  // 三个字母以内的英文词（ik、rl、vla）前后都要是词的边界；更长的英文词只要求从词的开头开始；中文不限
  const isShort = t => t.c.length <= 3 && /^[a-z0-9]+$/.test(t.c);
  function inName(x, t) {
    const short = isShort(t), anywhere = CJK.test(t.c[0] || "");
    for (const a of x.names) {
      for (const [str, needle, S] of [[a.n, t.n, a.nS], [a.c, t.c, a.cS]]) {
        if (!needle) continue;
        for (let i = str.indexOf(needle); i >= 0; i = str.indexOf(needle, i + 1)) {
          if (!anywhere && !S.has(i)) continue;
          const j = i + needle.length;
          if (short && j < str.length && ALNUM.test(str[j]) && !S.has(j)) continue;
          return true;
        }
      }
    }
    return false;
  }
  function inText(hay, t) {
    if (!t.n) return false;
    if (CJK.test(t.n[0])) return hay.includes(t.n);
    const short = isShort(t);
    for (let i = hay.indexOf(t.n); i >= 0; i = hay.indexOf(t.n, i + 1)) {
      if (/[a-z0-9]/.test(hay[i - 1] || "")) continue;
      if (short && /[a-z0-9]/.test(hay[i + t.n.length] || "")) continue;
      return true;
    }
    return false;
  }

  // 「什么是 VLA」「what is a vla」这类问句：问法用词不参与匹配（全是问法用词时照常搜）
  const STOP_EN = new Set("what whats is are was a an the of in on for to and or how does do did why which who with vs versus mean means meaning define definition explain about between difference".split(" "));
  const ZH_HEAD = /^(什么是|什么叫|啥是|请问|介绍一下|如何|怎么|为什么)/;
  const ZH_TAIL = /(是什么意思|什么意思|是什么|是啥|的区别|区别|的意思|意思|的含义|含义|的定义|怎么样|怎么用|有什么用|有什么|吗|呢|啊)$/;
  const STOP_ZH_ONLY = new Set(["的", "和", "与", "跟", "及", "或"]);
  function stripZh(c) {
    let rest = c, prev;
    do { prev = rest; rest = rest.replace(ZH_HEAD, "").replace(ZH_TAIL, ""); } while (rest && rest !== prev);
    return rest;
  }

  function tokenize(qN) {
    const seen = new Set(), all = [], kept = [];
    for (const w of qN.split(/\s+/)) {
      for (const p of w.match(/[㐀-鿿豈-﫿]+|[^㐀-鿿豈-﫿]+/g) || []) {
        const c = compact(p);
        if (!c || seen.has(c)) continue;
        seen.add(c);
        const t = {n: p.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "") || c, c};
        all.push(t);
        if (CJK.test(c)) {
          const rest = stripZh(c);
          if (rest && !STOP_ZH_ONLY.has(rest)) kept.push(rest === c ? t : {n: rest, c: rest});
        } else if (!STOP_EN.has(c)) kept.push(t);
      }
    }
    return kept.length ? kept : all;
  }

  // 查询里有没有包含某个词条名：中文名两个字以上直接找；英文名三个字母以上，还要前后不是字母数字（react 里的 act 不算）
  function nameInQuery(qN, qC, x) {
    let best = 0;
    x.nN.forEach((n, k) => {
      const c = x.nC[k];
      if (CJK.test(c)) { if (c.length >= 2 && qC.includes(c)) best = Math.max(best, c.length); return; }
      if (c.length < 3) return;
      for (let i = qN.indexOf(n); i >= 0; i = qN.indexOf(n, i + 1)) {
        if (!/[a-z0-9]/.test(qN[i - 1] || "") && !/[a-z0-9]/.test(qN[i + n.length] || "")) { best = Math.max(best, c.length); break; }
      }
    });
    return best;
  }

  // p 和 s 差几个字（增、删、换、相邻对调各算 1），超过 max 就算不像。
  // anywhere = false：只和 s 的开头一段比（英文按单词开头对齐，打了一半的词也能纠错）；true：和 s 的任意一段比（中文）
  let B0 = [], B1 = [], B2 = [];
  function approx(p, s, max, anywhere) {
    const m = p.length;
    let prev2 = B0, prev = B1, cur = B2;
    for (let i = 0; i <= m; i++) prev[i] = i;
    let best = m;
    for (let j = 1; j <= s.length; j++) {
      cur[0] = anywhere ? 0 : j;
      let low = cur[0];
      for (let i = 1; i <= m; i++) {
        let v = Math.min(prev[i] + 1, cur[i - 1] + 1, prev[i - 1] + (p[i - 1] === s[j - 1] ? 0 : 1));
        if (i > 1 && j > 1 && p[i - 1] === s[j - 2] && p[i - 2] === s[j - 1] && prev2[i - 2] + 1 < v) v = prev2[i - 2] + 1;
        cur[i] = v;
        if (v < low) low = v;
      }
      if (cur[m] < best) { best = cur[m]; if (!best) break; }
      if (!anywhere && low > max) break;
      [prev2, prev, cur] = [prev, cur, prev2];
    }
    return best <= max ? best : max + 1;
  }

  // 允许错几个字：英文 4–7 个字母错 1 个，8–11 个错 2 个，更长错 3 个；中文 2–5 个字错 1 个，6 个以上错 2 个
  const typoBudget = c => CJK.test(c) ? (c.length >= 6 ? 2 : c.length >= 2 ? 1 : 0)
    : /^\d+$/.test(c) ? 0 : c.length >= 12 ? 3 : c.length >= 8 ? 2 : c.length >= 4 ? 1 : 0;

  // 返回 [错了几个字, 是不是整个名字都对上了]；对不上返回 null
  function typoCost(x, t) {
    const max = typoBudget(t.c);
    if (!max) return null;
    let best = max + 1, full = false;
    const cjk = CJK.test(t.c), p = t.c;
    const pool = cjk ? x.nC.filter(c => CJK.test(c)) : x.words;
    for (const w of pool) {
      if (w.length + max < p.length) continue;
      // 英文首字母一般不会打错：要求首字母相同（或前两个字母对调），免得 udev 去掉 u 后对上 device
      if (!cjk && w[0] !== p[0] && !(w[0] === p[1] && w[1] === p[0])) continue;
      const d = approx(t.c, w, max, CJK.test(t.c));
      const isFull = x.nC.includes(w) && Math.abs(w.length - t.c.length) <= max;
      if (d < best || (d === best && isFull && !full)) { best = d; full = isFull; }
    }
    return best > max ? null : [best, full];
  }

  function search(raw) {
    const qN = norm(raw).replace(/\s+/g, " ").trim(), qC = compact(qN);
    if (!qC) return null;
    const toks = tokenize(qN);
    // 整句比两遍：原样一遍，去掉问法用词后再一遍（「什么是逆运动学」→「逆运动学」）
    const wholes = [{n: qN, c: qC}];
    const core = {n: toks.map(t => t.n).join(" "), c: toks.map(t => t.c).join("")};
    if (core.c && core.c !== qC) wholes.push(core);
    const pair = toks.filter(t => NAMES.has(t.c)).length >= 2;   // 查询里至少有两个词各自正好是词条名
    const exact = [];
    for (const x of IDX) {
      let s = 0;
      if (wholes.some(w => x.nC.includes(w.c))) s = 1000;
      else if (wholes.some(w => x.nC.some(c => c.startsWith(w.c)))) s = 900;
      else if (wholes.some(w => inName(x, w))) s = 800;
      else if (toks.every(t => inName(x, t))) s = 700;
      else if (pair && toks.some(t => x.nC.includes(t.c))) s = 650;   // 「VLA 和 VLM 的区别」：两个词各自的词条
      else if (toks.every(t => inName(x, t) || inText(x.oneN, t))) s = 500;
      else if (wholes.some(w => inText(x.bodyN, w)) || toks.every(t => inName(x, t) || inText(x.bodyN, t))) s = 400;
      if (s) exact.push({x, s});
    }
    // 完全匹配不到 8 条、也没有哪个词条名正好对上时，再找「相近」的：查询里包含了某个词条名，或拼错了几个字
    let near = [];
    if (exact.length < 8 && !exact.some(e => e.s >= 900)) {
      const seen = new Set(exact.map(e => e.x.i));
      for (const x of IDX) {
        if (seen.has(x.i)) continue;
        let s = 0;
        const k = nameInQuery(qN, qC, x);
        if (k) s = 160 + Math.min(k, 30);
        let cost = 0, typo = false, full = true;
        for (const t of toks) {
          if (inName(x, t)) continue;
          if (inText(x.bodyN, t)) { cost += 0.5; full = false; continue; }   // 只在正文里出现，排后一点
          const c = typoCost(x, t);
          if (!c) { cost = Infinity; break; }
          cost += c[0]; full = full && c[1]; typo = true;
        }
        if (typo && cost !== Infinity) s = Math.max(s, 200 - 30 * cost + (full ? 10 : 0));
        if (s) near.push({x, s});
      }
    }
    const cmp = (a, b) => b.s - a.s || a.x.t.tier - b.x.t.tier || a.x.t.name.length - b.x.t.name.length || a.x.i - b.x.i;
    exact.sort(cmp);
    near = near.sort(cmp).slice(0, 30);
    return {exact, fuzzy: near, toks: [...wholes, ...toks]};
  }

  function termHTML(t, q) {
    const alt = t.alt && norm(t.alt) !== norm(t.name) ? `<span class="alt">${hl(t.alt, q)}</span>` : "";
    const ab = t.abbr && ![norm(t.name), norm(t.alt)].includes(norm(t.abbr)) ? `<span class="ab">${hl(t.abbr, q)}</span>` : "";
    const rel = (t.related || []).map((r, i) => {
      const id = (t.related_ids || [])[i];
      return id && byId[id] && id !== t.id ? `<a href="#${id}" data-jump="${id}">${esc(byId[id].name)}</a>` : `<span>${esc(r)}</span>`;
    }).join("");
    const src = (t.sources || []).map(s => {
      let h = s.url; try { h = new URL(s.url).hostname; } catch (e) {}
      const mark = L.zhSource && hasCJK(s.title) ? L.zhSource : "";
      return `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || h)}${mark}</a>`;
    }).join("　");
    const aka = (t.aliases || []).length ? `<span class="aka">${L.aka} ${t.aliases.map(a => hl(a, q)).join(LANG === "zh" ? "、" : ", ")}</span>` : "";
    let where = "";
    if (q) {
      const ci = catIdx[t.category], c = DATA.cats[ci], s = c.sections[t.sec];
      where = `<div class="where">${ci + 1} ${esc(c.name)}${s ? ` › ${ci + 1}.${t.sec + 1} ${esc(s.title)}` : ""}</div>`;
    }
    return `<article class="term" id="${t.id}">${where}
      <div class="head"><h4>${hl(t.name, q)}</h4>${alt}${ab}<a class="perma" href="${BASE}t/${t.id}/" title="${L.perma}" aria-label="${L.perma}">↗</a><span class="tier t${t.tier}">${L.tier[t.tier] || ""}</span></div>
      <p class="one">${hl(t.one_liner, q)}</p>
      <p class="exp">${esc(t.explanation)}</p>
      ${t.example ? `<p class="ex"><span class="k">${L.example}</span>${esc(t.example)}</p>` : ""}
      <div class="foot">${aka}${rel ? `<div class="rel">${rel}</div>` : ""}${src ? `<span class="src">${L.src}　${src}</span>` : ""}${t.as_of ? `<span>${L.asof} ${esc(t.as_of)}</span>` : ""}</div>
    </article>`;
  }

  function catHTML(c, ci, items) {
    const bySec = new Map();
    items.forEach(t => { if (!bySec.has(t.sec)) bySec.set(t.sec, []); bySec.get(t.sec).push(t); });
    const secs = [...bySec.keys()].sort((a, b) => a - b);
    const route = secs.map(si => `<li><a href="#s-${c.key}-${si}" data-sec="s-${c.key}-${si}"><span class="sno">${ci + 1}.${si + 1}</span><span class="t">${esc(c.sections[si]?.title || "")}</span><span class="n">${bySec.get(si).length}</span></a></li>`).join("");
    const body = secs.map(si => {
      const s = c.sections[si] || {};
      return `<div class="sec" id="s-${c.key}-${si}"><h3><span class="sno">${ci + 1}.${si + 1}</span>${esc(s.title || "")}</h3>${s.blurb ? `<p class="sec-blurb">${esc(s.blurb)}</p>` : ""}${bySec.get(si).map(t => termHTML(t, "")).join("")}</div>`;
    }).join("");
    return `<section class="cat" id="cat-${c.key}">
      <div class="cat-head"><span class="cno">${String(ci + 1).padStart(2, "0")}</span><h2>${esc(c.name)}</h2><span class="n">${L.terms(items.length)}</span></div>
      <p class="cat-blurb">${esc(c.blurb)}</p>
      ${secs.length > 1 ? `<ol class="route">${route}</ol>` : ""}
      ${body}
    </section>`;
  }

  function render() {
    document.querySelectorAll("[data-cat]").forEach(b => b.setAttribute("aria-pressed", b.dataset.cat === state.cat));
    document.querySelectorAll("[data-tier]").forEach(b => b.setAttribute("aria-pressed", b.dataset.tier === state.tier));
    const R = state.q.trim() ? search(state.q) : null;
    const q = !!R;
    const inCat = t => state.cat === "all" || t.category === state.cat;
    const cc = {all: 0};
    const tally = t => { cc[t.category] = (cc[t.category] || 0) + 1; cc.all++; };
    if (R) { R.exact.forEach(e => tally(e.x.t)); R.fuzzy.forEach(e => tally(e.x.t)); }
    else DATA.terms.forEach(t => { if (state.tier === "all" || t.tier <= Number(state.tier)) tally(t); });
    document.querySelectorAll("#rail [data-cat] .n").forEach(el => el.textContent = cc[el.parentNode.dataset.cat] || 0);
    $("#tiers").classList.toggle("off", q);
    let html = "";
    if (R) {
      const ex = R.exact.filter(e => inCat(e.x.t)), fz = R.fuzzy.filter(e => inCat(e.x.t));
      $("#count").textContent = ex.length || !fz.length ? L.searchCount(ex.length, fz.length) : L.fuzzyOnly(fz.length);
      if (!ex.length && !fz.length) { $("#list").innerHTML = `<p class="empty">${esc(L.empty(state.q))}</p>`; return; }
      const shown = state.all ? ex : ex.slice(0, CAP);   // 只敲一两个字母时会命中上千条，先显示一部分，免得卡
      html = `<section class="cat">` + shown.map(e => termHTML(e.x.t, R.toks)).join("")
        + (shown.length < ex.length ? `<div class="next"><button type="button" class="btn" data-more><span class="k">${L.capped(CAP)}</span><span class="v">${L.showAll(ex.length)}</span></button></div>` : "")
        + (fz.length && ex.length ? `<p class="fuzzy-note">${L.fuzzyNote}</p>` : "")
        + fz.map(e => termHTML(e.x.t, [])).join("") + `</section>`;
      $("#list").innerHTML = html;
      return;
    }
    const list = DATA.terms.filter(t => inCat(t) && (state.tier === "all" || t.tier <= Number(state.tier)));
    $("#count").textContent = L.count(list.length, DATA.terms.length);
    if (!list.length) { $("#list").innerHTML = `<p class="empty">${esc(L.empty(state.q))}</p>`; return; }
    DATA.cats.forEach((c, ci) => { const items = list.filter(t => t.category === c.key); if (items.length) html += catHTML(c, ci, items); });
    if (state.cat !== "all") {
      const ci = catIdx[state.cat], nx = DATA.cats[ci + 1];
      if (nx) html += `<div class="next"><button type="button" class="btn" data-next="${nx.key}"><span class="k">${L.next}</span><span class="v">${ci + 2} ${esc(nx.name)} →</span></button></div>`;
    }
    $("#list").innerHTML = html;
  }

  function pickCat(key) { state.cat = key; render(); window.scrollTo({top: 0}); }

  function jumpTo(id) {
    const t = byId[id]; if (!t) return;
    if (!document.getElementById(t.id)) {
      state.cat = t.category;
      if (state.tier !== "all" && t.tier > Number(state.tier)) state.tier = "all";
      state.q = ""; $("#q").value = ""; render();
    }
    const el = document.getElementById(t.id);
    if (el) {
      document.querySelectorAll(".term.hit").forEach(x => x.classList.remove("hit"));
      el.classList.add("hit"); el.scrollIntoView();
      try { history.replaceState(null, "", "#" + t.id); } catch (e) {}
    }
  }

  function init(data) {
    DATA = data;
    byId = Object.fromEntries(DATA.terms.map(t => [t.id, t]));
    catIdx = Object.fromEntries(DATA.cats.map((c, i) => [c.key, i]));
    prepIndex();

    let rail = `<button type="button" class="btn" data-cat="all"><span class="no"></span><span>${L.all}</span><span class="n"></span></button>`;
    DATA.cats.forEach((c, i) => {
      const st = STAGE_AT.indexOf(i);
      if (st >= 0) rail += `<div class="stage">${L.stages[st]}</div>`;
      rail += `<button type="button" class="btn" data-cat="${c.key}"><span class="no">${i + 1}</span><span>${esc(c.name)}</span><span class="n"></span></button>`;
    });
    $("#rail").innerHTML = rail;
    $("#chips").innerHTML = `<button type="button" class="btn" data-cat="all">${L.all}</button>` +
      DATA.cats.map((c, i) => `<button type="button" class="btn" data-cat="${c.key}"><span class="no">${i + 1}</span>${esc(c.name)}</button>`).join("");
    for (const el of [$("#rail"), $("#chips")]) el.addEventListener("click", e => { const b = e.target.closest("[data-cat]"); if (b) pickCat(b.dataset.cat); });

    const tierN = k => k === "all" ? DATA.terms.length : DATA.terms.filter(t => t.tier <= Number(k)).length;
    $("#tiers").innerHTML = L.tierBtns.map(([k, l, c]) => `<button type="button" class="btn" data-tier="${k}">${c ? `<span class="dot" style="background:${c}"></span>` : ""}${l}<span class="tn">${tierN(k)}</span></button>`).join("");
    $("#tiers").addEventListener("click", e => {
      const b = e.target.closest("[data-tier]"); if (!b) return;
      state.tier = b.dataset.tier;
      try { localStorage.setItem("glossary-view", JSON.stringify({tier: state.tier})); } catch (err) {}
      render();
    });

    let timer;
    $("#q").addEventListener("input", e => { clearTimeout(timer); timer = setTimeout(() => { state.q = e.target.value; state.all = false; render(); }, 120); });
    document.addEventListener("keydown", e => {
      if (e.key === "/" && document.activeElement !== $("#q")) { e.preventDefault(); $("#q").focus(); }
      if (e.key === "Escape" && document.activeElement === $("#q")) { $("#q").value = ""; state.q = ""; render(); }
    });
    document.addEventListener("click", e => {
      const nx = e.target.closest("[data-next]"); if (nx) { pickCat(nx.dataset.next); return; }
      if (e.target.closest("[data-more]")) { state.all = true; render(); return; }
      const sec = e.target.closest("[data-sec]"); if (sec) { e.preventDefault(); document.getElementById(sec.dataset.sec)?.scrollIntoView(); return; }
      const a = e.target.closest("[data-jump]"); if (a) { e.preventDefault(); jumpTo(a.dataset.jump); }
    });

    // 支持 /?q=关键词 直接打开搜索结果，方便分享
    try { const q0 = new URLSearchParams(location.search).get("q"); if (q0) { $("#q").value = q0; state.q = q0; } } catch (e) {}
    render();
    const h = decodeURIComponent(location.hash.slice(1));
    if (h && byId[h]) { state.cat = byId[h].category; state.tier = "all"; render(); jumpTo(h); }
    else if (h.startsWith("cat-") && catIdx[h.slice(4)] !== undefined) pickCat(h.slice(4));
  }

  const url = document.querySelector('meta[name="glossary-data"]').content;
  fetch(url).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(init)
    .catch(() => { const el = $("#list .loading"); if (el) el.textContent = L.loadFail; });
})();
