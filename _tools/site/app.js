// 具身智能新手名词表 · 首页交互。页面先出框架，再异步加载数据（data/<lang>.<hash>.json）。
(() => {
  const LANG = document.documentElement.lang.startsWith("zh") ? "zh" : "en";
  const BASE = LANG === "zh" ? "/" : "/en/";
  const L = {
    zh: {
      tier: {1: "入门必知", 2: "常用", 3: "进阶"},
      tierBtns: [["1", "入门必知", "var(--must)"], ["2", "入门 + 常用", "var(--accent)"], ["all", "全部", ""]],
      all: "全部", count: (a, b) => `${a} / ${b}`, searchCount: n => `搜到 ${n} 条（全部分级）`,
      empty: q => `没有匹配「${q}」的词条。试试英文全称或缩写，或把分类切回「全部」。`,
      next: "下一类", example: "例子", aka: "也叫", src: "来源", asof: "截至", terms: n => `${n} 条`,
      perma: "单独页面", loadFail: "词条加载失败，请刷新重试。",
      stages: ["先建立地图", "认识机器人本体", "工具与仿真", "怎么学：数据、训练、模型", "谁在做、怎么说"],
      zhSource: "",
    },
    en: {
      tier: {1: "Essential", 2: "Common", 3: "Advanced"},
      tierBtns: [["1", "Essential", "var(--must)"], ["2", "Essential + Common", "var(--accent)"], ["all", "All", ""]],
      all: "All", count: (a, b) => `${a} / ${b}`, searchCount: n => `${n} matches (all levels)`,
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
  const norm = s => String(s ?? "").toLowerCase().replace(/π/g, "pi");
  const hasCJK = s => /[一-鿿]/.test(s || "");

  let DATA, byId, catIdx, HAY, NAMEHAY;
  const state = {cat: "all", tier: "1", q: ""};
  try { const s = JSON.parse(localStorage.getItem("glossary-view") || "{}"); if (s.tier) state.tier = s.tier; } catch (e) {}

  function hl(text, q) {
    const s = esc(text); if (!q) return s;
    const i = norm(text).indexOf(q); if (i < 0) return s;
    const raw = String(text);
    return esc(raw.slice(0, i)) + "<mark>" + esc(raw.slice(i, i + q.length)) + "</mark>" + esc(raw.slice(i + q.length));
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
    const q = norm(state.q.trim());
    const tierOK = t => q || state.tier === "all" || t.tier <= Number(state.tier);
    const hit = t => tierOK(t) && (!q || HAY[t.id].includes(q));
    const cc = {all: 0};
    DATA.terms.forEach(t => { if (hit(t)) { cc[t.category] = (cc[t.category] || 0) + 1; cc.all++; } });
    document.querySelectorAll("#rail [data-cat] .n").forEach(el => el.textContent = cc[el.parentNode.dataset.cat] || 0);
    $("#tiers").classList.toggle("off", !!q);
    const list = DATA.terms.filter(t => (state.cat === "all" || t.category === state.cat) && hit(t));
    $("#count").textContent = q ? L.searchCount(list.length) : L.count(list.length, DATA.terms.length);
    if (!list.length) { $("#list").innerHTML = `<p class="empty">${esc(L.empty(state.q))}</p>`; return; }
    let html = "";
    if (q) {
      list.sort((a, b) => (NAMEHAY[b.id].includes(q) - NAMEHAY[a.id].includes(q)) || a.tier - b.tier);
      html = `<section class="cat">` + list.map(t => termHTML(t, q)).join("") + `</section>`;
    } else {
      DATA.cats.forEach((c, ci) => { const items = list.filter(t => t.category === c.key); if (items.length) html += catHTML(c, ci, items); });
      if (state.cat !== "all") {
        const ci = catIdx[state.cat], nx = DATA.cats[ci + 1];
        if (nx) html += `<div class="next"><button type="button" class="btn" data-next="${nx.key}"><span class="k">${L.next}</span><span class="v">${ci + 2} ${esc(nx.name)} →</span></button></div>`;
      }
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
    HAY = Object.fromEntries(DATA.terms.map(t => [t.id, norm([t.name, t.alt, t.abbr, ...(t.aliases || []), t.one_liner, t.explanation].join(" "))]));
    NAMEHAY = Object.fromEntries(DATA.terms.map(t => [t.id, norm([t.name, t.alt, t.abbr, ...(t.aliases || [])].join(" "))]));

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
    $("#q").addEventListener("input", e => { clearTimeout(timer); timer = setTimeout(() => { state.q = e.target.value; render(); }, 120); });
    document.addEventListener("keydown", e => {
      if (e.key === "/" && document.activeElement !== $("#q")) { e.preventDefault(); $("#q").focus(); }
      if (e.key === "Escape" && document.activeElement === $("#q")) { $("#q").value = ""; state.q = ""; render(); }
    });
    document.addEventListener("click", e => {
      const nx = e.target.closest("[data-next]"); if (nx) { pickCat(nx.dataset.next); return; }
      const sec = e.target.closest("[data-sec]"); if (sec) { e.preventDefault(); document.getElementById(sec.dataset.sec)?.scrollIntoView(); return; }
      const a = e.target.closest("[data-jump]"); if (a) { e.preventDefault(); jumpTo(a.dataset.jump); }
    });

    render();
    const h = decodeURIComponent(location.hash.slice(1));
    if (h && byId[h]) { state.cat = byId[h].category; state.tier = "all"; render(); jumpTo(h); }
    else if (h.startsWith("cat-") && catIdx[h.slice(4)] !== undefined) pickCat(h.slice(4));
  }

  const url = document.querySelector('meta[name="glossary-data"]').content;
  fetch(url).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(init)
    .catch(() => { const el = $("#list .loading"); if (el) el.textContent = L.loadFail; });
})();
