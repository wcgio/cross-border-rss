# GitHub Actions 全托管跨境资讯日报 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 零服务器的跨境电商/国际物流资讯日报：GitHub Actions 每天 07:00（北京时间）抓源、AI 分级总结、发布到 Cloudflare Pages（rss.cgio.qzz.io）并推送 Telegram，崩溃时 Gotify 通知。

**Architecture:** 单一 Python 管道（src/ 下六个职责单一的模块 + pipeline.py 编排），产物与去重状态 commit 回仓库，Cloudflare Pages Git 集成自动发布 `docs/`。所有外部依赖（网络、AI、推送）都有降级路径，保证日报照常生成。

**Tech Stack:** Python 3.12+（feedparser / requests / BeautifulSoup / trafilatura / feedgen / PyYAML）、pytest、GitHub Actions、GitHub Models（openai/gpt-4o-mini）、Cloudflare Pages、Telegram Bot API、Gotify。

**Spec:** `docs/superpowers/specs/2026-06-11-github-actions-digest-design.md`

---

## 文件结构

```
.
├── .github/workflows/digest.yml   # 定时 workflow：test job + digest job
├── src/
│   ├── __init__.py
│   ├── fetcher.py        # 抓单个源：RSS 解析 + 列表页 URL 正则提取
│   ├── filters.py        # 关键词过滤、seen 去重（纯函数）
│   ├── extractor.py      # 正文降级链：feed 内容 → trafilatura → 仅标题
│   ├── summarizer.py     # GitHub Models map/reduce 两段式总结
│   ├── render.py         # digest.xml / HTML 渲染（纯函数）
│   ├── notify.py         # Telegram 推送 + Gotify 故障通知
│   └── pipeline.py       # 编排 + 顶层崩溃捕获
├── sources.yml           # 源配置（新增源只改这里）
├── requirements.txt
├── pyproject.toml        # pytest 配置
├── tests/
│   ├── fixtures/{sample_rss.xml, ebrun.html}
│   └── test_{filters,fetcher,extractor,summarizer,render,notify,pipeline}.py
├── data/seen.json        # 去重状态（workflow 维护提交）
├── docs/                 # Cloudflare Pages 发布目录（index.html / digest.xml / archive/）
└── legacy/               # 退役的 NAS docker 栈归档
```

**条目（item）数据结构**，贯穿全管道的 dict：`{url, title, source, category, pub, feed_content, text, summary, importance}`，前六个字段由 fetcher 产生，`text` 由 extractor 补充，`summary`/`importance` 由 summarizer 补充。

**category 取值**：`platform`（平台政策）/ `logistics`（国际物流）/ `compliance`（关税合规）/ `market`（大盘趋势）。

---

### Task 1: 项目脚手架与 legacy 归档

**Files:**
- Move: `app.py` `digest.py` `sites.yml` `docker-compose.yml` `.env.example` `crossborder-feeds.tar.gz` `README.md` → `legacy/`
- Create: `src/__init__.py` `requirements.txt` `pyproject.toml` `tests/__init__.py`
- Modify: `.gitignore`

- [ ] **Step 1: 归档 legacy 文件**

```bash
mkdir -p legacy src tests/fixtures data
git mv app.py digest.py sites.yml docker-compose.yml .env.example crossborder-feeds.tar.gz README.md legacy/
```

- [ ] **Step 2: 写依赖与配置文件**

`requirements.txt`：

```
feedparser>=6.0
requests>=2.31
beautifulsoup4>=4.12
lxml>=5.0
PyYAML>=6.0
feedgen>=1.0
trafilatura>=1.8
pytest>=8.0
```

`pyproject.toml`：

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

`src/__init__.py` 与 `tests/__init__.py`：空文件。

`.gitignore` 整体替换为（关键：**删掉原来的 `data/` 一行**，`data/seen.json` 必须可提交）：

```
.DS_Store
.env
__pycache__/
*.pyc
.venv/
.pytest_cache/
```

- [ ] **Step 3: 建虚拟环境并安装依赖**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -c "import feedparser, trafilatura, feedgen, yaml, bs4, requests; print('ok')"
```

Expected: 输出 `ok`。若 Python 3.14 下 lxml/trafilatura 无可用 wheel 安装失败，改用 `brew install python@3.12 && python3.12 -m venv .venv` 重建。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: scaffold python pipeline, archive legacy docker stack"
```

---

### Task 2: filters.py（关键词过滤 + seen 去重）

**Files:**
- Create: `src/filters.py`
- Test: `tests/test_filters.py`

- [ ] **Step 1: 写失败测试**

`tests/test_filters.py`：

```python
import datetime as dt

from src import filters


def make(url="u1", title="亚马逊上调FBA费用"):
    return {"url": url, "title": title}


def test_keyword_filter_include_exclude():
    items = [make("u1", "亚马逊上调FBA费用"), make("u2", "某公司招聘运营"), make("u3", "Temu 美区新政")]
    out = filters.keyword_filter(items, include=["亚马逊", "temu"], exclude=["招聘"])
    assert [it["url"] for it in out] == ["u1", "u3"]


def test_keyword_filter_no_rules_keeps_all():
    items = [make("u1"), make("u2")]
    assert filters.keyword_filter(items) == items


def test_dedup_unseen():
    seen = {"u1": "2026-06-10"}
    out = filters.dedup_unseen([make("u1"), make("u2")], seen)
    assert [it["url"] for it in out] == ["u2"]


def test_update_seen_adds_and_prunes():
    today = dt.date(2026, 6, 11)
    seen = {"old": "2026-06-01", "kept": "2026-06-08"}
    out = filters.update_seen(seen, [make("u2")], today, keep_days=7)
    assert "old" not in out
    assert out["kept"] == "2026-06-08"
    assert out["u2"] == "2026-06-11"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_filters.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.filters'`）

- [ ] **Step 3: 实现**

`src/filters.py`：

```python
"""关键词过滤与跨天去重。纯函数，无 IO。"""
import datetime as dt


def keyword_filter(items, include=None, exclude=None):
    """include 命中任一才保留；exclude 命中任一就丢弃（不区分大小写，作用于标题）。"""
    inc = [w.lower() for w in (include or [])]
    exc = [w.lower() for w in (exclude or [])]
    out = []
    for it in items:
        low = it["title"].lower()
        if inc and not any(w in low for w in inc):
            continue
        if exc and any(w in low for w in exc):
            continue
        out.append(it)
    return out


def dedup_unseen(items, seen):
    """seen: {url: 'YYYY-MM-DD'}，返回未见过的条目。"""
    return [it for it in items if it["url"] not in seen]


def update_seen(seen, items, today, keep_days=7):
    """把本次条目并入 seen，并清理超过 keep_days 的旧记录。"""
    cutoff = today - dt.timedelta(days=keep_days)
    kept = {u: d for u, d in seen.items() if dt.date.fromisoformat(d) >= cutoff}
    for it in items:
        kept[it["url"]] = today.isoformat()
    return kept
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_filters.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/filters.py tests/test_filters.py
git commit -m "feat: keyword filter and cross-day seen dedup"
```

---

### Task 3: fetcher.py（RSS 解析 + 列表页正则提取）

**Files:**
- Create: `src/fetcher.py` `tests/fixtures/sample_rss.xml` `tests/fixtures/ebrun.html`
- Test: `tests/test_fetcher.py`

- [ ] **Step 1: 写 fixtures**

`tests/fixtures/sample_rss.xml`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Test Feed</title>
<link>https://example.com</link>
<description>test</description>
<item>
  <title>Ocean freight rates jump 20%</title>
  <link>https://example.com/a1</link>
  <description>Spot rates rose sharply on Asia-Europe lanes this week.</description>
  <pubDate>Wed, 10 Jun 2026 08:00:00 GMT</pubDate>
</item>
<item>
  <title>Port congestion eases</title>
  <link>https://example.com/a2</link>
  <description>Congestion at major hubs eased.</description>
  <pubDate>Wed, 10 Jun 2026 09:00:00 GMT</pubDate>
</item>
</channel>
</rss>
```

`tests/fixtures/ebrun.html`（覆盖：时间戳剥离、重复链接、外域链接、过短标题、不匹配链接）：

```html
<html><body>
<nav><a href="/label/6.html">跨境电商</a></nav>
<div class="list">
  <a href="/677729.html">Temu美区半托管招商升级 2026-06-10 15:56:01</a>
  <a href="/677730.html">短讯</a>
  <a href="/677729.html">Temu美区半托管招商升级 2026-06-10 15:56:01</a>
  <a href="https://other.com/677731.html">外部站点文章标题很长很长</a>
  <a href="/activity/zhibo">直播预告页面</a>
</div>
</body></html>
```

- [ ] **Step 2: 写失败测试**

`tests/test_fetcher.py`：

```python
import datetime as dt
from pathlib import Path

from src import fetcher

FIXTURES = Path(__file__).parent / "fixtures"

RSS_CFG = {"name": "Test Feed", "type": "rss", "url": "https://example.com/feed", "category": "logistics"}

SCRAPE_CFG = {
    "name": "亿邦动力 · 跨境电商",
    "type": "scrape",
    "url": "https://m.ebrun.com/label/6.html",
    "base_url": "https://m.ebrun.com",
    "link_pattern": "/\\d{5,}\\.html",
    "title_strip_time": True,
    "category": "platform",
}


def test_parse_rss_extracts_fields():
    xml = (FIXTURES / "sample_rss.xml").read_text(encoding="utf-8")
    items = fetcher.parse_rss(RSS_CFG, xml)
    assert len(items) == 2
    first = items[0]
    assert first["title"] == "Ocean freight rates jump 20%"
    assert first["url"] == "https://example.com/a1"
    assert first["source"] == "Test Feed"
    assert first["category"] == "logistics"
    assert "rates rose sharply" in first["feed_content"]
    assert first["pub"].tzinfo is not None


def test_parse_listing_extracts_dedups_and_strips_time():
    html = (FIXTURES / "ebrun.html").read_text(encoding="utf-8")
    items = fetcher.parse_listing(SCRAPE_CFG, html)
    assert len(items) == 1  # 短标题、外域、重复、不匹配的都被过滤
    it = items[0]
    assert it["url"] == "https://m.ebrun.com/677729.html"
    assert it["title"] == "Temu美区半托管招商升级"
    assert it["pub"] == dt.datetime(2026, 6, 10, 15, 56, 1, tzinfo=dt.timezone(dt.timedelta(hours=8)))
    assert it["feed_content"] == ""
```

- [ ] **Step 3: 运行确认失败**

Run: `.venv/bin/pytest tests/test_fetcher.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.fetcher'`）

- [ ] **Step 4: 实现**

`src/fetcher.py`（`parse_listing` 移植自 `legacy/app.py` 的 `extract_items`）：

```python
"""抓取单个源：原生 RSS 用 feedparser，scrape 源按 URL 正则从列表页提取链接。"""
import datetime as dt
import re
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TIMEOUT = 20
MAX_ITEMS_PER_SOURCE = 30
TIME_RE = re.compile(r"\s*(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\s*$")
TZ8 = dt.timezone(dt.timedelta(hours=8))


def fetch_url(url, encoding=None):
    r = requests.get(
        url,
        headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    if encoding:
        r.encoding = encoding
    elif r.encoding is None or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding
    return r.text


def parse_rss(cfg, xml_text):
    feed = feedparser.parse(xml_text)
    items = []
    for e in feed.entries[:MAX_ITEMS_PER_SOURCE]:
        content = ""
        if e.get("content"):
            content = e["content"][0].get("value", "")
        elif e.get("summary"):
            content = e["summary"]
        pub = None
        if e.get("published_parsed"):
            pub = dt.datetime(*e["published_parsed"][:6], tzinfo=dt.timezone.utc)
        items.append({
            "url": e.get("link", ""),
            "title": (e.get("title") or "").strip(),
            "source": cfg["name"],
            "category": cfg["category"],
            "pub": pub,
            "feed_content": content,
        })
    return [it for it in items if it["url"] and it["title"]]


def parse_listing(cfg, html):
    """按文章 URL 正则从列表页提取链接（抗改版，不依赖 CSS class）。"""
    soup = BeautifulSoup(html, "lxml")
    base = cfg["base_url"]
    pattern = re.compile(cfg["link_pattern"])
    seen, items = set(), []
    for a in soup.find_all("a", href=True):
        if not pattern.search(a["href"]):
            continue
        url = urljoin(base, a["href"])
        if urlparse(base).netloc not in urlparse(url).netloc:
            continue
        title = re.sub(r"\s+", " ", (a.get("title") or a.get_text(" ", strip=True)) or "").strip()
        pub = None
        if cfg.get("title_strip_time"):
            m = TIME_RE.search(title)
            if m:
                title = TIME_RE.sub("", title).strip()
                try:
                    pub = dt.datetime(*[int(x) for x in m.groups()], tzinfo=TZ8)
                except ValueError:
                    pub = None
        if len(title) < 6 or url in seen:
            continue
        seen.add(url)
        items.append({
            "url": url,
            "title": title,
            "source": cfg["name"],
            "category": cfg["category"],
            "pub": pub,
            "feed_content": "",
        })
        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break
    return items


def fetch_source(cfg):
    """抓单个源。网络/解析异常向上抛，由 pipeline 记录为源异常。"""
    if cfg["type"] == "rss":
        return parse_rss(cfg, fetch_url(cfg["url"]))
    return parse_listing(cfg, fetch_url(cfg["url"], cfg.get("encoding")))
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/pytest tests/test_fetcher.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add src/fetcher.py tests/test_fetcher.py tests/fixtures/
git commit -m "feat: rss parsing and url-pattern listing scraper"
```

---

### Task 4: extractor.py（正文降级链）

**Files:**
- Create: `src/extractor.py`
- Test: `tests/test_extractor.py`

- [ ] **Step 1: 写失败测试**

`tests/test_extractor.py`：

```python
from src import extractor


def boom(exc):
    def _f(url):
        raise exc
    return _f


def test_uses_feed_content_when_long_enough():
    item = {"url": "u", "title": "t", "feed_content": "<p>" + "字" * 300 + "</p>"}
    out = extractor.extract_text(item, fetch=boom(AssertionError("不应抓取页面")))
    assert out["text"] == "字" * 300


def test_falls_back_to_trafilatura(monkeypatch):
    monkeypatch.setattr(extractor.trafilatura, "extract", lambda html: "正文内容" * 50)
    item = {"url": "u", "title": "t", "feed_content": ""}
    out = extractor.extract_text(item, fetch=lambda url: "<html>whatever</html>")
    assert out["text"].startswith("正文内容")


def test_fetch_failure_degrades_to_short_feed_content():
    item = {"url": "u", "title": "t", "feed_content": "短摘要"}
    out = extractor.extract_text(item, fetch=boom(OSError("blocked")))
    assert out["text"] == "短摘要"


def test_nothing_available_gives_empty_text():
    item = {"url": "u", "title": "t", "feed_content": ""}
    out = extractor.extract_text(item, fetch=boom(OSError("blocked")))
    assert out["text"] == ""


def test_truncates_to_max():
    item = {"url": "u", "title": "t", "feed_content": "字" * 5000}
    out = extractor.extract_text(item, fetch=boom(AssertionError("不应抓取页面")))
    assert len(out["text"]) == extractor.MAX_TEXT
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_extractor.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`src/extractor.py`：

```python
"""为条目补充正文 text。降级链：feed 自带内容 → trafilatura 抓页面提取 → 空（仅标题）。"""
import re

import trafilatura

from .fetcher import fetch_url

MIN_FEED_CONTENT = 200  # feed 内容达到此长度即不再抓页面
MAX_TEXT = 2000         # 控制 AI token 用量


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def extract_text(item, fetch=fetch_url):
    plain = strip_html(item.get("feed_content"))
    if len(plain) >= MIN_FEED_CONTENT:
        item["text"] = plain[:MAX_TEXT]
        return item
    try:
        html = fetch(item["url"])
        text = (trafilatura.extract(html) or "").strip()
    except Exception:
        text = ""
    item["text"] = (text or plain)[:MAX_TEXT]
    return item
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_extractor.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/extractor.py tests/test_extractor.py
git commit -m "feat: article text extraction with degradation chain"
```

---

### Task 5: summarizer.py（GitHub Models 两段式总结）

**Files:**
- Create: `src/summarizer.py`
- Test: `tests/test_summarizer.py`

- [ ] **Step 1: 写失败测试**

`tests/test_summarizer.py`：

```python
from src import summarizer

ITEMS = [
    {"url": "u1", "title": "亚马逊上调佣金", "text": "正文1", "source": "A", "category": "platform"},
    {"url": "u2", "title": "无关娱乐新闻", "text": "正文2", "source": "B", "category": "market"},
    {"url": "u3", "title": "海运运价上涨", "text": "", "source": "C", "category": "logistics"},
]


def test_summarize_batch_maps_results_and_drops_irrelevant():
    def fake_chat(prompt, token, max_tokens=2000):
        assert "亚马逊上调佣金" in prompt
        return {"results": [
            {"id": 1, "relevant": True, "importance": "high", "summary": "佣金详细总结"},
            {"id": 2, "relevant": False},
            {"id": 3, "relevant": True, "importance": "normal", "summary": "运价一句话"},
        ]}

    out = summarizer.summarize_batch(ITEMS, "tok", chat=fake_chat)
    assert [it["url"] for it in out] == ["u1", "u3"]
    assert out[0]["importance"] == "high"
    assert out[0]["summary"] == "佣金详细总结"


def test_summarize_batch_missing_id_keeps_item_with_empty_summary():
    out = summarizer.summarize_batch(ITEMS[:1], "tok", chat=lambda *a, **k: {"results": []})
    assert out[0]["summary"] == ""
    assert out[0]["importance"] == "normal"


def test_group_items_orders_merges_and_backfills():
    items = [
        {"url": "u1", "title": "A", "summary": "s", "source": "S", "category": "platform"},
        {"url": "u2", "title": "B", "summary": "s", "source": "S", "category": "logistics"},
        {"url": "u3", "title": "B2 同一事件", "summary": "s", "source": "S2", "category": "logistics"},
        {"url": "u4", "title": "C 漏分", "summary": "s", "source": "S", "category": "market"},
    ]

    def fake_chat(prompt, token, max_tokens=2000):
        return {
            "groups": {"platform": [1], "logistics": [2], "compliance": [], "market": []},
            "merged": [[2, 3]],
        }

    groups = summarizer.group_items(items, "tok", chat=fake_chat)
    assert [it["url"] for it in groups["platform"]] == ["u1"]
    assert [it["url"] for it in groups["logistics"]] == ["u2"]  # u3 因 merged 被合并丢弃
    assert [it["url"] for it in groups["market"]] == ["u4"]     # AI 漏分时回退源 category


def test_group_items_degrades_on_ai_error():
    def fail_chat(prompt, token, max_tokens=2000):
        raise summarizer.AIError("boom")

    items = [{"url": "u1", "title": "A", "summary": "", "source": "S", "category": "compliance"}]
    groups = summarizer.group_items(items, "tok", chat=fail_chat)
    assert [it["url"] for it in groups["compliance"]] == ["u1"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_summarizer.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`src/summarizer.py`（注意：prompt 模板里有 JSON 大括号，所以用 `.replace()` 而不是 `.format()` 填充）：

```python
"""GitHub Models 两段式总结：map（逐篇分级总结）→ reduce（跨源合并 + 四主题分组排序）。"""
import json
import os

import requests

API_URL = os.environ.get("GH_MODELS_URL", "https://models.github.ai/inference/chat/completions")
MODEL = os.environ.get("GH_MODELS_MODEL", "openai/gpt-4o-mini")
BATCH_SIZE = 9
CATEGORIES = {
    "platform": "平台政策",
    "logistics": "国际物流",
    "compliance": "关税合规",
    "market": "大盘趋势",
}


class AIError(Exception):
    """AI 调用或返回解析失败（已重试过）。"""


def _chat(prompt, token, max_tokens=2000):
    r = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _chat_json(prompt, token, max_tokens=2000):
    last = None
    for _ in range(2):  # 失败重试一次
        try:
            return json.loads(_chat(prompt, token, max_tokens))
        except (json.JSONDecodeError, KeyError, IndexError, requests.RequestException) as e:
            last = e
    raise AIError(str(last))


MAP_PROMPT = """你是跨境电商行业资讯编辑。下面有 {n} 篇文章（编号、标题、正文节选）。\
对每篇输出一个 JSON 对象，整体输出格式：
{"results": [{"id": 1, "relevant": true, "importance": "high", "summary": "..."}]}
规则：
- 与跨境电商/外贸/国际物流无关的条目 relevant 设为 false，不写 summary
- importance 取 "high" 或 "normal"。high＝重大平台政策/费用/佣金/关税/海运运价剧变等高影响资讯，\
summary 写 3-4 句（必须包含关键数字、生效时间、对卖家的影响）；normal＝一般资讯，summary 写 1-2 句
- summary 用中文，直接陈述事实，不写"本文""文章称"
- 正文标注"（无正文，仅标题）"的条目按标题判断，summary 留空字符串

文章列表：
{articles}"""


def summarize_batch(items, token, chat=_chat_json):
    """map 阶段：一批条目 → 各自带 summary/importance；relevant=false 的被剔除。"""
    articles = "\n\n".join(
        f"[{i + 1}] 标题：{it['title']}\n正文：{it['text'] or '（无正文，仅标题）'}"
        for i, it in enumerate(items)
    )
    prompt = MAP_PROMPT.replace("{n}", str(len(items))).replace("{articles}", articles)
    data = chat(prompt, token)
    by_id = {r.get("id"): r for r in data.get("results", []) if isinstance(r, dict)}
    out = []
    for i, it in enumerate(items):
        r = by_id.get(i + 1)
        if r is None:
            out.append({**it, "summary": "", "importance": "normal"})
        elif not r.get("relevant", True):
            continue
        else:
            out.append({
                **it,
                "summary": (r.get("summary") or "").strip(),
                "importance": r.get("importance") if r.get("importance") in ("high", "normal") else "normal",
            })
    return out


REDUCE_PROMPT = """下面是今日跨境电商/国际物流资讯各篇的总结（带编号）。输出 JSON：
{"groups": {"platform": [编号...], "logistics": [...], "compliance": [...], "market": [...]}, "merged": [[编号,编号], ...]}
规则：
- 把每个编号分到且只分到一组：platform=平台政策, logistics=国际物流, compliance=关税合规, market=大盘趋势
- 每组内按重要性从高到低排列
- 报道同一事件的多篇放入 merged（信息最全的编号放在最前，后面的会被合并丢弃）

条目：
{entries}"""


def group_by_category(items):
    """降级路径：按源配置的 category 归类，不调 AI。"""
    result = {key: [] for key in CATEGORIES}
    for it in items:
        result.setdefault(it.get("category") or "market", []).append(it)
    return result


def group_items(items, token, chat=_chat_json):
    """reduce 阶段：四主题分组 + 组内排序 + 同事件合并；AI 失败降级为 category 归类。"""
    entries = "\n".join(
        f"[{i + 1}] ({it['source']}) {it['title']}：{it['summary'] or '仅标题'}"
        for i, it in enumerate(items)
    )
    try:
        data = chat(REDUCE_PROMPT.replace("{entries}", entries), token, max_tokens=1500)
        groups = data["groups"]
        drop = set()
        for pair in data.get("merged", []):
            if isinstance(pair, list):
                drop.update(pair[1:])
        result, used = {key: [] for key in CATEGORIES}, set()
        for key in CATEGORIES:
            for i in groups.get(key, []):
                if isinstance(i, int) and 1 <= i <= len(items) and i not in drop and i not in used:
                    used.add(i)
                    result[key].append(items[i - 1])
        for i, it in enumerate(items, 1):  # AI 漏分的条目回退源 category
            if i not in used and i not in drop:
                result.setdefault(it.get("category") or "market", []).append(it)
        return result
    except (AIError, KeyError, TypeError, AttributeError):
        return group_by_category(items)
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_summarizer.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/summarizer.py tests/test_summarizer.py
git commit -m "feat: github models map/reduce summarizer with degradation"
```

---

### Task 6: render.py（RSS 与 HTML 渲染）

**Files:**
- Create: `src/render.py`
- Test: `tests/test_render.py`

- [ ] **Step 1: 写失败测试**

`tests/test_render.py`：

```python
from src import render

GROUPS = {
    "platform": [
        {"url": "https://e.com/1", "title": "重大政策<标题>", "summary": "三句详细总结。",
         "importance": "high", "source": "雨果"},
    ],
    "logistics": [
        {"url": "https://e.com/2", "title": "一般资讯条目", "summary": "",
         "importance": "normal", "source": "Loadstar"},
    ],
}


def test_render_groups_html_sections_and_escaping():
    body = render.render_groups_html(GROUPS, source_errors=[("坏源", "HTTP 502")])
    assert "平台政策" in body and "国际物流" in body
    assert "重大政策&lt;标题&gt;" in body  # HTML 转义
    assert 'class="high"' in body
    assert "仅标题" in body                # 无总结的条目有标注
    assert "源异常" in body and "坏源" in body


def test_render_groups_html_skips_empty_sections():
    body = render.render_groups_html({"platform": [], "market": []})
    assert "平台政策" not in body and "大盘趋势" not in body


def test_render_index_contains_archive_links():
    page = render.render_index("2026-06-11", "<p>BODY</p>", ["2026-06-11", "2026-06-10"])
    assert "archive/2026-06-10.html" in page
    assert "digest.xml" in page
    assert "<p>BODY</p>" in page


def test_render_rss_one_entry_per_day():
    xml = render.render_rss("2026-06-11", "<p>BODY</p>", 5, "https://rss.cgio.qzz.io")
    assert b"digest-2026-06-11" in xml
    assert "跨境/物流日报 2026-06-11（5 条）".encode() in xml
    assert b"rss.cgio.qzz.io/archive/2026-06-11.html" in xml
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`src/render.py`：

```python
"""渲染 digest.xml 与 HTML 页面。纯函数：分组数据 → 字符串/字节。"""
import datetime as dt
import html

from feedgen.feed import FeedGenerator

from .summarizer import CATEGORIES

TZ8 = dt.timezone(dt.timedelta(hours=8))

PAGE_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ max-width: 720px; margin: 0 auto; padding: 16px;
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; line-height: 1.6; }}
h1 {{ font-size: 1.4em; }}
h2 {{ font-size: 1.15em; border-bottom: 1px solid #8884; padding-bottom: 4px; }}
h3 {{ font-size: 1em; margin: 0 0 4px; }}
article {{ margin: 14px 0; padding-left: 10px; border-left: 3px solid #8883; }}
article.high {{ border-left-color: #e0a000; }}
.meta {{ color: #888; font-size: .85em; margin: 2px 0; }}
a {{ color: inherit; }}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
<footer class="meta"><p>{footer}</p></footer>
</body>
</html>
"""


def render_groups_html(groups, source_errors=()):
    parts = []
    for key, label in CATEGORIES.items():
        items = groups.get(key) or []
        if not items:
            continue
        parts.append(f"<section><h2>{label}</h2>")
        for it in items:
            cls = "high" if it.get("importance") == "high" else "normal"
            parts.append(f'<article class="{cls}"><h3>{html.escape(it["title"])}</h3>')
            parts.append(f'<p class="meta">{html.escape(it.get("source") or "")}</p>')
            if it.get("summary"):
                parts.append(f"<p>{html.escape(it['summary'])}</p>")
            else:
                parts.append('<p class="meta">（仅标题，未能获取正文）</p>')
            parts.append(f'<p class="meta"><a href="{html.escape(it["url"])}">原文 ↗</a></p></article>')
        parts.append("</section>")
    if source_errors:
        parts.append("<section><h2>源异常</h2><ul>")
        for name, err in source_errors:
            parts.append(f"<li>{html.escape(name)}：{html.escape(err)}</li>")
        parts.append("</ul></section>")
    return "".join(parts)


def render_page(title, body_html, footer=""):
    return PAGE_TMPL.format(title=html.escape(title), body=body_html, footer=footer)


def render_index(date_str, body_html, archive_dates):
    links = " · ".join(f'<a href="archive/{d}.html">{d}</a>' for d in archive_dates)
    body = body_html + f"<section><h2>历史归档</h2><p>{links}</p></section>"
    return render_page(
        f"跨境/物流日报 {date_str}", body,
        footer='RSS 订阅：<a href="digest.xml">digest.xml</a>',
    )


def render_rss(date_str, body_html, item_count, site_url):
    fg = FeedGenerator()
    fg.title("跨境电商 / 国际物流 · 每日日报")
    fg.link(href=site_url, rel="alternate")
    fg.description("每天一条，过去24小时跨境与物流核心资讯总结")
    fg.language("zh-cn")
    fe = fg.add_entry()
    fe.id(f"digest-{date_str}")
    suffix = f"（{item_count} 条）" if item_count else "（无新内容）"
    fe.title(f"跨境/物流日报 {date_str}{suffix}")
    fe.link(href=f"{site_url}/archive/{date_str}.html")
    fe.guid(f"digest-{date_str}", permalink=False)
    fe.pubDate(dt.datetime.now(TZ8))
    fe.content(body_html, type="CDATA")
    return fg.rss_str(pretty=True)
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/render.py tests/test_render.py
git commit -m "feat: rss and mobile-friendly html rendering"
```

---

### Task 7: notify.py（Telegram 推送 + Gotify 故障通知）

**Files:**
- Create: `src/notify.py`
- Test: `tests/test_notify.py`

- [ ] **Step 1: 写失败测试**

`tests/test_notify.py`：

```python
from src import notify

GROUPS = {"platform": [
    {"url": "https://e.com/1", "title": "标题", "summary": "总结", "importance": "high"},
]}
CATS = {"platform": "平台政策"}


def test_telegram_messages_contains_content_and_link():
    msgs = notify.telegram_messages(GROUPS, CATS, "2026-06-11", "https://rss.cgio.qzz.io")
    assert len(msgs) == 1
    assert "平台政策" in msgs[0] and "总结" in msgs[0]
    assert "https://rss.cgio.qzz.io/archive/2026-06-11.html" in msgs[0]


def test_telegram_messages_splits_long_content():
    many = {"platform": [
        {"url": f"https://e.com/{i}", "title": "标题" * 30, "summary": "总结内容" * 100, "importance": "normal"}
        for i in range(20)
    ]}
    msgs = notify.telegram_messages(many, CATS, "2026-06-11", "https://x")
    assert len(msgs) > 1
    assert all(len(m) <= notify.TG_LIMIT for m in msgs)


def test_send_telegram_without_creds_is_noop(monkeypatch):
    monkeypatch.delenv("TG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TG_CHAT_ID", raising=False)
    notify.send_telegram(["msg"])  # 不抛异常即通过


def test_send_gotify_without_creds_is_noop(monkeypatch):
    monkeypatch.delenv("GOTIFY_URL", raising=False)
    monkeypatch.delenv("GOTIFY_TOKEN", raising=False)
    notify.send_gotify("t", "m")  # 不抛异常即通过


def test_send_gotify_posts_message(monkeypatch):
    calls = []
    monkeypatch.setenv("GOTIFY_URL", "https://gotify.example.com/")
    monkeypatch.setenv("GOTIFY_TOKEN", "tok")
    monkeypatch.setattr(notify.requests, "post",
                        lambda url, **kw: calls.append((url, kw)) or type("R", (), {"status_code": 200})())
    notify.send_gotify("标题", "内容")
    url, kw = calls[0]
    assert url == "https://gotify.example.com/message"
    assert kw["params"]["token"] == "tok"
    assert kw["json"]["priority"] == 8
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_notify.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`src/notify.py`：

```python
"""Telegram 日报推送与 Gotify 故障通知。凭据缺失时跳过而不报错。"""
import os

import requests

TG_LIMIT = 4000  # Telegram 单条上限 4096，留余量


def telegram_messages(groups, categories, date_str, site_url):
    """把分组总结编排成若干条不超长的消息文本（纯函数）。"""
    blocks = [f"📰 跨境/物流日报 {date_str}"]
    for key, label in categories.items():
        items = groups.get(key) or []
        if not items:
            continue
        blocks.append(f"\n—— {label} ——")
        for it in items:
            mark = "🔴" if it.get("importance") == "high" else "•"
            text = f"{mark} {it['title']}"
            if it.get("summary"):
                text += f"\n{it['summary']}"
            text += f"\n{it['url']}"
            blocks.append(text)
    blocks.append(f"\n网页版：{site_url}/archive/{date_str}.html")

    msgs, cur = [], ""
    for block in blocks:
        if cur and len(cur) + len(block) + 1 > TG_LIMIT:
            msgs.append(cur)
            cur = block
        else:
            cur = f"{cur}\n{block}" if cur else block
    if cur:
        msgs.append(cur)
    return msgs


def send_telegram(messages):
    token = os.environ.get("TG_BOT_TOKEN")
    chat_id = os.environ.get("TG_CHAT_ID")
    if not (token and chat_id):
        print("[warn] TG 凭据未配置，跳过推送")
        return
    for msg in messages:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "disable_web_page_preview": True},
            timeout=30,
        )
        r.raise_for_status()


def send_gotify(title, message):
    """故障通知。自身失败只打日志，绝不掩盖原始异常。"""
    url = os.environ.get("GOTIFY_URL")
    token = os.environ.get("GOTIFY_TOKEN")
    if not (url and token):
        print("[warn] Gotify 凭据未配置，跳过故障通知")
        return
    try:
        requests.post(
            f"{url.rstrip('/')}/message",
            params={"token": token},
            json={"title": title, "message": message, "priority": 8},
            timeout=20,
        )
    except requests.RequestException as e:
        print(f"[warn] Gotify 推送失败：{e}")
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_notify.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/notify.py tests/test_notify.py
git commit -m "feat: telegram digest push and gotify crash notification"
```

---

### Task 8: pipeline.py（编排 + 崩溃捕获）

**Files:**
- Create: `src/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: 写失败测试**

`tests/test_pipeline.py`：

```python
import datetime as dt
import json
from pathlib import Path

import pytest

from src import pipeline

FIXTURES = Path(__file__).parent / "fixtures"


def test_run_produces_outputs(tmp_path, monkeypatch):
    (tmp_path / "sources.yml").write_text(
        'sources:\n'
        '  - name: "Test Feed"\n'
        '    type: rss\n'
        '    url: "https://example.com/feed"\n'
        '    category: logistics\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline, "SOURCES", str(tmp_path / "sources.yml"))
    monkeypatch.setattr(pipeline, "SEEN_FILE", str(tmp_path / "data" / "seen.json"))
    monkeypatch.setattr(pipeline, "DOCS", str(tmp_path / "docs"))

    xml = (FIXTURES / "sample_rss.xml").read_text(encoding="utf-8")
    monkeypatch.setattr(pipeline.fetcher, "fetch_url", lambda url, encoding=None: xml)
    monkeypatch.setattr(pipeline.extractor, "extract_text",
                        lambda it, **kw: {**it, "text": it["feed_content"]})
    monkeypatch.setattr(pipeline, "summarize_batch",
                        lambda batch, token: [{**it, "summary": "总结", "importance": "normal"} for it in batch])
    monkeypatch.setattr(pipeline, "group_items",
                        lambda items, token: pipeline.group_by_category(items))
    sent = []
    monkeypatch.setattr(pipeline.notify, "send_telegram", lambda msgs: sent.extend(msgs))

    pipeline.run()

    today = dt.datetime.now(pipeline.TZ8).date().isoformat()
    assert (tmp_path / "docs" / "digest.xml").exists()
    assert (tmp_path / "docs" / "index.html").exists()
    assert (tmp_path / "docs" / "archive" / f"{today}.html").exists()
    seen = json.loads((tmp_path / "data" / "seen.json").read_text(encoding="utf-8"))
    assert "https://example.com/a1" in seen
    assert sent and "Ocean freight rates jump 20%" in sent[0]


def test_run_records_source_errors(tmp_path, monkeypatch):
    (tmp_path / "sources.yml").write_text(
        'sources:\n'
        '  - name: "Broken"\n'
        '    type: rss\n'
        '    url: "https://broken.example.com/feed"\n'
        '    category: market\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline, "SOURCES", str(tmp_path / "sources.yml"))
    monkeypatch.setattr(pipeline, "SEEN_FILE", str(tmp_path / "data" / "seen.json"))
    monkeypatch.setattr(pipeline, "DOCS", str(tmp_path / "docs"))

    def boom(url, encoding=None):
        raise OSError("connection refused")

    monkeypatch.setattr(pipeline.fetcher, "fetch_url", boom)
    monkeypatch.setattr(pipeline.notify, "send_telegram", lambda msgs: None)

    pipeline.run()  # 不应崩溃

    index = (tmp_path / "docs" / "index.html").read_text(encoding="utf-8")
    assert "源异常" in index and "Broken" in index
    assert "今日抓取异常" in index


def test_main_sends_gotify_on_crash(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "run", lambda: 1 / 0)
    monkeypatch.setattr(pipeline.notify, "send_gotify", lambda title, msg: calls.append((title, msg)))
    with pytest.raises(ZeroDivisionError):
        pipeline.main()
    assert calls
    assert "崩溃" in calls[0][0]
    assert "位置：" in calls[0][1]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`src/pipeline.py`：

```python
#!/usr/bin/env python3
"""日报管道编排：抓取 → 过滤去重 → 正文 → AI 总结分组 → 渲染落盘 → Telegram。

崩溃时把异常位置与报错信息推送 Gotify（不含任何凭据/环境变量值），再以非 0 退出。
运行方式：python -m src.pipeline
"""
import datetime as dt
import json
import os
import sys
import traceback

import yaml

from . import extractor, fetcher, filters, notify, render
from .summarizer import (AIError, BATCH_SIZE, CATEGORIES, group_by_category,
                         group_items, summarize_batch)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = os.path.join(ROOT, "sources.yml")
SEEN_FILE = os.path.join(ROOT, "data", "seen.json")
DOCS = os.path.join(ROOT, "docs")
SITE_URL = os.environ.get("SITE_URL", "https://rss.cgio.qzz.io")
TZ8 = dt.timezone(dt.timedelta(hours=8))


def load_seen():
    try:
        with open(SEEN_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def run():
    today = dt.datetime.now(TZ8).date()
    date_str = today.isoformat()
    with open(SOURCES, encoding="utf-8") as f:
        sources = yaml.safe_load(f)["sources"]

    items, source_errors = [], []
    for cfg in sources:
        try:
            fetched = fetcher.fetch_source(cfg)
            fetched = filters.keyword_filter(fetched, cfg.get("include"), cfg.get("exclude"))
            items.extend(fetched)
            print(f"[ok] {cfg['name']}: {len(fetched)} 条")
        except Exception as e:
            source_errors.append((cfg["name"], f"{type(e).__name__}: {e}"))
            print(f"[fail] {cfg['name']}: {e}")

    seen = load_seen()
    fresh = filters.dedup_unseen(items, seen)
    uniq, urls = [], set()
    for it in fresh:  # 同 URL 跨源去重
        if it["url"] not in urls:
            urls.add(it["url"])
            uniq.append(it)

    uniq = [extractor.extract_text(it) for it in uniq]

    token = os.environ.get("GITHUB_TOKEN", "")
    summarized = []
    for i in range(0, len(uniq), BATCH_SIZE):
        batch = uniq[i:i + BATCH_SIZE]
        try:
            summarized.extend(summarize_batch(batch, token))
        except AIError as e:
            print(f"[warn] 批次总结失败，退回标题：{e}")
            summarized.extend({**it, "summary": "", "importance": "normal"} for it in batch)

    groups = group_items(summarized, token) if summarized else {}
    count = sum(len(v) for v in groups.values())

    body = render.render_groups_html(groups, source_errors)
    if not summarized:
        body = "<p>过去24小时没有新资讯。</p>" + body
    title = f"跨境/物流日报 {date_str}" + (f"（{count} 条）" if count else "（无新内容）")
    if not items and source_errors:
        title += "【今日抓取异常】"

    os.makedirs(os.path.join(DOCS, "archive"), exist_ok=True)
    with open(os.path.join(DOCS, "archive", f"{date_str}.html"), "w", encoding="utf-8") as f:
        f.write(render.render_page(title, body))
    archive_dates = sorted(
        (n[:-5] for n in os.listdir(os.path.join(DOCS, "archive")) if n.endswith(".html")),
        reverse=True,
    )
    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as f:
        f.write(render.render_index(date_str, body, archive_dates))
    with open(os.path.join(DOCS, "digest.xml"), "wb") as f:
        f.write(render.render_rss(date_str, body, count, SITE_URL))

    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(filters.update_seen(seen, uniq, today), f, ensure_ascii=False, indent=0)

    try:
        notify.send_telegram(notify.telegram_messages(groups, CATEGORIES, date_str, SITE_URL))
    except Exception as e:
        print(f"[warn] Telegram 推送失败：{e}")
    print(f"完成：{title}")


def main():
    try:
        run()
    except Exception:
        tb = traceback.format_exc(limit=8)
        frame = traceback.extract_tb(sys.exc_info()[2])[-1]
        notify.send_gotify(
            "跨境日报管道崩溃",
            f"位置：{frame.filename}:{frame.lineno} in {frame.name}\n\n{tb[-1500:]}",
        )
        raise


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行确认通过（全量回归）**

Run: `.venv/bin/pytest -q`
Expected: 全部通过（27 个测试）

- [ ] **Step 5: Commit**

```bash
git add src/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline orchestration with gotify crash handler"
```

---

### Task 9: sources.yml（源配置 + 真实地址核实）

**Files:**
- Create: `sources.yml`

- [ ] **Step 1: 写初始配置**

`sources.yml`：

```yaml
# 源配置。新增源：rss 类型填 name/type/url/category 四项；
# scrape 类型另需 base_url + link_pattern（文章 URL 的正则），可选 title_strip_time/encoding。
# category: platform=平台政策  logistics=国际物流  compliance=关税合规  market=大盘趋势
# include/exclude: 标题关键词过滤，include 命中任一才保留，exclude 命中任一丢弃。

sources:
  # ── 平台政策 ──────────────────────────────
  - name: "Marketplace Pulse"
    type: rss
    url: "https://www.marketplacepulse.com/rss.xml"
    category: platform

  - name: "EcommerceBytes"
    type: rss
    url: "https://www.ecommercebytes.com/feed/"
    category: platform

  - name: "雨果跨境 · 平台资讯"
    type: scrape
    url: "https://www.cifnews.com/subject/news"
    base_url: "https://www.cifnews.com"
    link_pattern: "/article/\\d{4,}"
    category: platform

  - name: "亿邦动力 · 跨境电商"
    type: scrape
    url: "https://m.ebrun.com/label/6.html"
    base_url: "https://m.ebrun.com"
    link_pattern: "/\\d{5,}\\.html"
    title_strip_time: true
    category: platform
    exclude: ["招聘", "广告", "直播预告"]

  # 预留：卖家通知邮件转 RSS（Kill the Newsletter 生成后取消注释填入）
  # - name: "Amazon 卖家通知"
  #   type: rss
  #   url: "https://kill-the-newsletter.com/feeds/XXXX.xml"
  #   category: platform

  # ── 国际物流 ──────────────────────────────
  - name: "The Loadstar"
    type: rss
    url: "https://theloadstar.com/feed/"
    category: logistics

  - name: "FreightWaves"
    type: rss
    url: "https://www.freightwaves.com/news/feed"
    category: logistics

  - name: "Splash247"
    type: rss
    url: "https://splash247.com/feed/"
    category: logistics

  - name: "gCaptain"
    type: rss
    url: "https://gcaptain.com/feed/"
    category: logistics

  # ── 关税合规 ──────────────────────────────
  - name: "USTR Press Releases"
    type: rss
    url: "https://ustr.gov/rss.xml"
    category: compliance

  - name: "海关总署 · 新闻发布"
    type: scrape
    url: "http://www.customs.gov.cn/customs/xwfb34/index.html"
    base_url: "http://www.customs.gov.cn"
    link_pattern: "/customs/xwfb34/\\d+/index\\.html"
    category: compliance

  # ── 大盘趋势 ──────────────────────────────
  - name: "Modern Retail"
    type: rss
    url: "https://www.modernretail.co/feed/"
    category: market

  - name: "Retail Dive"
    type: rss
    url: "https://www.retaildive.com/feeds/news/"
    category: market

  - name: "36氪"
    type: rss
    url: "https://36kr.com/feed"
    include: ["跨境", "出海", "亚马逊", "Temu", "TikTok", "Shein", "关税", "物流", "海运"]
    category: market
```

- [ ] **Step 2: 逐源核实真实地址**

```bash
.venv/bin/python - <<'EOF'
import yaml, requests
ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
for s in yaml.safe_load(open("sources.yml"))["sources"]:
    try:
        r = requests.get(s["url"], headers=ua, timeout=15)
        kind = "feed" if b"<rss" in r.content[:2000] or b"<feed" in r.content[:2000] else "html"
        print(f"{r.status_code} {kind:5} {s['name']}")
    except Exception as e:
        print(f"FAIL       {s['name']}: {type(e).__name__}")
EOF
```

Expected: 每行 `200`；rss 类型应显示 `feed`。对非 200 或非 feed 的源：打开该站官网搜 "RSS" 找真实 feed 地址替换（USTR、Retail Dive、FreightWaves 的 feed 路径较易变动）；确认无 feed 可用的源直接删掉并在 commit message 里注明。雨果/亿邦/海关总署若被反爬（403/超时），保留配置——它们在 Actions 环境的表现首跑时再观察，单源失败不阻塞。

- [ ] **Step 3: Commit**

```bash
git add sources.yml
git commit -m "feat: initial source list across four categories"
```

---

### Task 10: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/digest.yml`

- [ ] **Step 1: 写 workflow**

`.github/workflows/digest.yml`：

```yaml
name: daily-digest

on:
  schedule:
    - cron: "0 23 * * *" # UTC 23:00 = 北京时间 07:00（GitHub cron 可能延迟数分钟到半小时）
  workflow_dispatch:

permissions:
  contents: write # commit 产物回仓库
  models: read    # 调用 GitHub Models

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -r requirements.txt
      - run: pytest -q

  digest:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -r requirements.txt
      - name: Run pipeline
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          TG_BOT_TOKEN: ${{ secrets.TG_BOT_TOKEN }}
          TG_CHAT_ID: ${{ secrets.TG_CHAT_ID }}
          GOTIFY_URL: ${{ secrets.GOTIFY_URL }}
          GOTIFY_TOKEN: ${{ secrets.GOTIFY_TOKEN }}
        run: python -m src.pipeline
      - name: Commit outputs
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add docs data/seen.json
          git diff --cached --quiet || git commit -m "chore: daily digest $(date -u +%F)"
          git pull --rebase
          git push
      - name: Gotify on failure
        if: failure()
        env:
          GOTIFY_URL: ${{ secrets.GOTIFY_URL }}
          GOTIFY_TOKEN: ${{ secrets.GOTIFY_TOKEN }}
        run: |
          curl -sf -X POST "$GOTIFY_URL/message?token=$GOTIFY_TOKEN" \
            -F title="跨境日报 workflow 失败" \
            -F message="run: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" \
            -F priority=8 || true
```

- [ ] **Step 2: 本地校验 YAML 语法**

Run: `.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/digest.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/digest.yml
git commit -m "ci: daily digest workflow with test gate and gotify fallback"
```

---

### Task 11: README 与 CLAUDE.md 重写

**Files:**
- Create: `README.md`
- Modify: `CLAUDE.md`（整体替换）

- [ ] **Step 1: 写 README.md**

```markdown
# cross-border-rss

零服务器的跨境电商 / 国际物流资讯日报。GitHub Actions 每天北京时间 07:00 运行：
抓取各源 → 过滤去重 → 正文提取 → AI 分级总结（GitHub Models，免费）→ 发布到
Cloudflare Pages → Telegram 推送。崩溃时 Gotify 通知。

## 访问

- 网页日报：https://rss.cgio.qzz.io/
- RSS 订阅：https://rss.cgio.qzz.io/digest.xml
- 历史归档：https://rss.cgio.qzz.io/archive/YYYY-MM-DD.html
- Telegram：bot 每天推送到频道

> GitHub 定时任务可能比 07:00 晚数分钟到半小时，属正常现象。

## 新增资讯源

编辑 `sources.yml`：有 RSS 的站填 `name/type: rss/url/category` 四项；没有 RSS 的站用
`type: scrape`，照已有条目填 `base_url` 和 `link_pattern`（文章 URL 的正则）。提交即生效。

## 配置（GitHub Secrets）

| Secret | 用途 |
|---|---|
| `TG_BOT_TOKEN` | Telegram bot token（@BotFather 创建） |
| `TG_CHAT_ID` | 推送目标：频道 `@用户名` 或 `-100` 开头 ID |
| `GOTIFY_URL` | Gotify 服务地址 |
| `GOTIFY_TOKEN` | Gotify 应用 token |

AI 总结使用 GitHub Models，workflow 内置 `GITHUB_TOKEN` 即可调用，无需额外配置。

## 本地开发

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q                # 测试不出网，网络/AI 全部 mock
GITHUB_TOKEN=<pat> .venv/bin/python -m src.pipeline   # 本地跑一次管道
```

`legacy/` 是退役的 NAS docker 栈（RSSHub + FreshRSS 方案），仅作归档。
```

- [ ] **Step 2: 整体替换 CLAUDE.md**

```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

零服务器的跨境电商/国际物流资讯日报管道，GitHub Actions 每天 UTC 23:00（北京时间 07:00）运行：

```
sources.yml → fetcher（抓源）→ filters（关键词过滤 + seen.json 跨天去重）
→ extractor（正文降级链）→ summarizer（GitHub Models map/reduce 分级总结）
→ render（digest.xml + index.html + archive/）→ commit 回仓库
→ Cloudflare Pages 自动发布（https://rss.cgio.qzz.io）→ Telegram 推送
崩溃 → Gotify 通知（src/pipeline.py main 的顶层捕获 + workflow 的 if: failure() 兜底）
```

设计文档：`docs/superpowers/specs/2026-06-11-github-actions-digest-design.md`

## 常用命令

```bash
source .venv/bin/activate
pytest -q                                  # 全部测试（网络/AI 全 mock，不出网）
pytest tests/test_fetcher.py -v            # 单文件
pytest tests/test_filters.py::test_dedup_unseen -v   # 单测试
python -m src.pipeline                     # 本地跑管道（需 GITHUB_TOKEN；TG/Gotify 凭据缺省时跳过推送）
```

## 架构要点

- **降级保日报**：单源失败记「源异常」小节；单篇正文失败退回 feed 摘要再退回仅标题；AI map 失败该批退回标题、reduce 失败按源 category 归类——任何故障都不应阻止日报生成，改动时维持这一不变量
- **`data/seen.json` 是跨天去重状态**，由 workflow commit 维护；删除它会导致次日日报重复
- **scrape 源用 URL 正则提链接**（抗改版，不依赖 CSS class），新增源只改 `sources.yml` 不改代码
- **时区硬编码北京时间**（`TZ8 = UTC+8`），日报按日 guid 去重，每天恰好一条 RSS entry
- summarizer 的 prompt 模板含 JSON 大括号，用 `.replace()` 填充而非 `.format()`
- `docs/` 是 Cloudflare Pages 发布根目录（构建命令留空）；spec/plan 文档也在其下，会一并公开，属预期行为
- `legacy/` 是退役的 NAS docker 栈，仅作参考，勿在其上开发

## 凭据

全部在 GitHub Secrets（`TG_BOT_TOKEN`、`TG_CHAT_ID`、`GOTIFY_URL`、`GOTIFY_TOKEN`），代码只读环境变量。
Gotify 崩溃通知内容只含 traceback 摘要，不得输出任何凭据或环境变量值。
```

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: rewrite readme and claude.md for serverless architecture"
```

---

### Task 12: 推送到 GitHub

**Files:** 无新文件，仅 git 操作。

- [ ] **Step 1: 确认 gh 登录状态并获取仓库地址**

```bash
gh auth status
```

Expected: 已登录。若未登录，停下来请用户运行 `gh auth login` 后继续。

```bash
gh repo view cross-border-rss --json url --jq .url
```

Expected: 输出 `https://github.com/<用户名>/cross-border-rss`。

- [ ] **Step 2: 添加 remote 并推送**

```bash
git remote add origin "$(gh repo view cross-border-rss --json url --jq .url).git"
git push -u origin main
```

Expected: 推送成功。若远端仓库带有初始化提交（README/LICENSE）导致冲突，先 `git pull --rebase origin main --allow-unrelated-histories` 再推。

- [ ] **Step 3: 验证 workflow 文件被识别**

```bash
gh workflow list --repo "$(gh repo view cross-border-rss --json nameWithOwner --jq .nameWithOwner)"
```

Expected: 列表中出现 `daily-digest`。

---

### Task 13: 部署联调与首跑验证

**Files:** 无代码改动；用户网页操作 + 触发验证。

- [ ] **Step 1: 用户操作清单（停下来等用户确认完成）**

请用户完成以下三组操作：

1. **GitHub Secrets**（仓库 Settings → Secrets and variables → Actions → Repository secrets）：
   添加 `TG_BOT_TOKEN`、`TG_CHAT_ID`、`GOTIFY_URL`（`https://gotify.320360.xyz`）、`GOTIFY_TOKEN`（轮换后的新 token）
2. **Telegram**：频道已建、bot 已设为频道管理员（发布消息权限）
3. **Cloudflare Pages**：控制台 → Workers & Pages → 创建 Pages 项目 → 连接 GitHub 选择 `cross-border-rss`（构建命令**留空**，构建输出目录填 `docs`）→ 部署成功后在 Custom domains 添加 `rss.cgio.qzz.io`

- [ ] **Step 2: 手动触发首跑**

```bash
gh workflow run daily-digest
sleep 30 && gh run list --workflow daily-digest --limit 1
```

Expected: run 状态最终为 `completed success`（用 `gh run watch` 跟踪）。若失败，`gh run view --log-failed` 看日志修复后重跑。

- [ ] **Step 3: 验证产物与各通道**

```bash
git pull
ls docs/archive/          # 应有今日 YYYY-MM-DD.html
curl -sI https://rss.cgio.qzz.io/ | head -1          # HTTP/2 200
curl -s https://rss.cgio.qzz.io/digest.xml | head -5  # RSS XML 开头
```

人工确认：① 网页日报四主题分组、重点条目有详细总结；② Telegram 频道收到推送；③ 手机 RSS 阅读器添加 `https://rss.cgio.qzz.io/digest.xml` 能收到今日一条。

- [ ] **Step 4: 验证 Gotify 故障通知（故意触发一次）**

临时把 `sources.yml` 第一行改成非法 YAML（如行首加 `{{`），commit 推送后 `gh workflow run daily-digest`，确认 Gotify 收到「跨境日报管道崩溃」或「workflow 失败」通知；然后 revert 该 commit 恢复。

```bash
git revert --no-edit HEAD && git push
```

- [ ] **Step 5: 检查抓源情况，调整被反爬的源**

```bash
gh run view --log | grep -E "\[ok\]|\[fail\]"
```

观察雨果/亿邦/海关总署是否 `[fail]`（GitHub 海外 IP 反爬）。若失败：按 spec 约定先保留观察 2-3 天；持续失败再讨论换源或公共 RSSHub 兜底（不在本计划范围内）。

---

## 验收标准（对照 spec）

- [ ] 每天 07:00（北京时间）自动产出日报，三通道可用：`rss.cgio.qzz.io` 网页 + digest.xml RSS + Telegram 频道
- [ ] 每条资讯 = 标题 + 来源 + 分级核心总结（重点 3-4 句含数字/时间/影响，次要 1-2 句）+ 原文链接
- [ ] 四主题分组（平台政策/国际物流/关税合规/大盘趋势），组内重要在前
- [ ] 跨天不出重复条目（seen.json 生效）
- [ ] 全链路降级可用：断网源/无正文/AI 失败均不阻止日报生成
- [ ] 管道崩溃和 workflow 失败均能收到 Gotify 通知
- [ ] `pytest -q` 全绿且不出网；workflow 中 test job 作为 digest job 的前置门禁
```
