# embodiedterms · 具身智能新手名词表

**在线阅读：https://embodiedterms.com**（English: https://embodiedterms.com/en/）

VLA、π0、ZMP、谐波减速器、大小脑、数采厂……刚入门具身智能，论文、组会和新闻里的名词一个接一个，搜出来要么零零散散，要么中英文对不上。这个项目把它们整理成一份按学习顺序排好的名词表：

- **2947 个名词，14 类**，每个词都有一句话解释、展开说明、例子和来源链接
- **三级难度**：入门必知 240 条 · 常用 885 条 · 进阶 1822 条；新手先看入门必知就能建立地图
- **按学习路线排**：先认识机器人本体（形态、零件、怎么动、怎么控制、怎么感知），再到软件和仿真，然后是数据、训练和模型，最后是公司和行业说法；每类内部再分由浅入深的小节
- **中英双语**：英文版按英文读者的习惯改写，不是逐句直译；中文、英文、缩写都能搜
- **每个词一个页面**，可以单独分享；有「上一个 / 下一个」，能顺着学习顺序读

| # | 类别 | 条数 | # | 类别 | 条数 |
|---|---|---|---|---|---|
| 1 | 基础概念与任务 | 150 | 8 | 仿真与评测 | 210 |
| 2 | 机器人类型与代表产品 | 179 | 9 | 数据与采集 | 178 |
| 3 | 硬件与本体部件 | 196 | 10 | 训练与学习方法 | 203 |
| 4 | 力学与运动学 | 168 | 11 | 模型与架构 | 184 |
| 5 | 控制与规划 | 203 | 12 | 代表性模型与工作 | 332 |
| 6 | 感知与传感器 | 307 | 13 | 公司与机构 | 237 |
| 7 | 软件与工具链 | 251 | 14 | 行业黑话与商业 | 149 |

## 内容是怎么来的，可信度如何

内容由 AI 辅助检索和整理：每个词都经过联网搜索，并附上实际核对过的来源链接。其中「公司与机构」「机器人类型与代表产品」「代表性模型与工作」三类，以及全部 240 条「入门必知」，又做过一轮独立的事实核查，修正了数百处年份、数字、归属和概念上的错误。其余「常用」「进阶」词条只在写作时核对过来源，**难免有错**，引用关键事实前请以来源为准。事实截至 2026-09-30。

发现错误或想补充词条，欢迎[提 issue](https://github.com/skJack/embodiedterms/issues)，也可以在公众号「可lip说AI」留言。

## 直接拿数据

不想跑脚本的话，网站上有固定网址的导出，每次更新网站会一起更新：

- JSON：[中文](https://embodiedterms.com/downloads/glossary-zh.json) · [英文](https://embodiedterms.com/downloads/glossary-en.json)（全部词条、分类、来源和词条页网址）
- 纯文本全文（Markdown）：[中文](https://embodiedterms.com/llms-full-zh.txt) · [英文](https://embodiedterms.com/llms-full.txt)
- 给 AI 读的索引：[llms.txt](https://embodiedterms.com/llms.txt)

## 目录结构

```
_batches/            中文释义，每个文件 12 条左右（concept-01.json、company-19.json……）
_batches_en/         英文版，和 _batches/ 按文件名、序号一一对应
_order/<类别>.json    该类的小节划分和学习顺序；duplicates 是类内重复
_order/drop.json      跨类别的重复（保留哪条、去掉哪条）
_i18n/en_sections.json  英文的类别名、小节标题和说明
_tools/               构建、校验、生成网站的脚本
  build.py            按学习顺序汇总 → terms.json、术语表.md、术语表.html（本地单文件版）
  build_site.py       生成网站 site/：中英两版首页、每个词和每个分类的静态页、关于页、sitemap、
                      结构化数据、分享预览图、llms.txt 和数据导出
  indexnow.py         部署后把网址推给 Bing 等搜索引擎（IndexNow）
  site/               网站用的样式、脚本、图标
  slugs.json          每个词条固定的网址，已发布，改名也不要改它
  validate_batch.py   校验中文批文件
  validate_en.py      校验英文批文件；qa_en.py 做中英对齐检查
wrangler.jsonc        Cloudflare 部署配置（维护者用）
```

每个词条用 key 标识，格式是「文件名#序号」，比如 `mechanics-03#4` 就是 `_batches/mechanics-03.json` 里 `terms` 的第 5 条（序号从 0 开始）。

中文词条的字段：

| 字段 | 含义 |
|---|---|
| `name_zh` / `name_en` / `abbr` / `aliases` | 中文名、英文名、缩写、别名 |
| `tier` | 1 = 入门必知，2 = 常用，3 = 进阶 |
| `one_liner` | 一句话解释 |
| `explanation` | 展开说明 |
| `example` | 例子（可为空） |
| `related` | 相关词条名 |
| `sources` | 来源链接 `[{title, url}]` |
| `as_of` | 事实对应的时间 |

## 本地运行

只需要 Python 3（无第三方依赖）：

```bash
python3 _tools/build.py        # 生成 terms.json、术语表.md、术语表.html
python3 _tools/build_site.py   # 生成网站到 site/
python3 -m http.server 8000 --directory site   # 浏览器打开 http://localhost:8000
```

## 怎么修改或补充词条

1. 改 `_batches/` 里对应的 JSON。新增词条可以追加到对应类别的最后一个批文件，或新建批文件，比如 `company-21.json`。
2. 同步改 `_batches_en/` 里同一文件、同一序号的英文版：英文是改写，不是直译，事实要和中文一致。
3. 新增的词条要写进 `_order/<类别>.json` 的某个小节，不然会落到该类最后的「其他」小节。
4. 跑校验：

   ```bash
   python3 _tools/validate_batch.py _batches/<文件>.json <条数>
   python3 _tools/validate_en.py <文件名>
   python3 _tools/validate_order.py <类别>
   python3 _tools/qa_en.py
   ```

5. 提 PR，写清改了什么、依据是哪个来源。

## 许可

- 名词释义内容（`_batches/`、`_batches_en/`、`_order/`、`_i18n/` 以及网站文字）：[CC BY-NC 4.0](LICENSE-CONTENT.md)。可以转载、改编，需署名「可lip / embodiedterms.com」，不得商用。
- 程序代码（`_tools/`）：[MIT](LICENSE)。

---

## English

**Read online: https://embodiedterms.com/en/**

A bilingual (Chinese / English) glossary of **2,947 embodied-AI and robotics terms** for newcomers. The terms are grouped into 14 categories that follow a learning path: robot bodies and hardware, then mechanics, control and perception, then software and simulation, then data, training and models, and finally companies and industry jargon. Each category is split into sections that go from basic to advanced.

Every entry has a one-line definition, a plain-language explanation, an example and source links. Entries are graded into 240 *Essential*, 885 *Common* and 1,822 *Advanced* terms. The English edition is adapted for English readers rather than translated line by line.

Content was researched and drafted with AI assistance. The companies, robots and landmark-models categories, plus all Essential entries, were independently fact-checked. Other entries may contain errors, so check the linked sources before relying on a specific fact. Corrections are welcome via [issues](https://github.com/skJack/embodiedterms/issues).

The data is also published at stable URLs: [JSON](https://embodiedterms.com/downloads/glossary-en.json), [full text as Markdown](https://embodiedterms.com/llms-full.txt) and an [llms.txt](https://embodiedterms.com/llms.txt) index (Chinese versions: `glossary-zh.json`, `llms-full-zh.txt`).

Build locally with `python3 _tools/build.py && python3 _tools/build_site.py`; the site is generated into `site/`. Content is licensed under [CC BY-NC 4.0](LICENSE-CONTENT.md); code under [MIT](LICENSE).
