"""
feedmaker — 把没有官方 RSS 的列表页转成 RSS。

策略：抓取列表页 HTML，按"文章 URL 规律"提取链接（而不是写死 CSS class，
后者一改版就失效），链接文字作为标题，可选地从标题尾部剥离时间戳作为发布时间。

新增一个站点只需在 sites.yml 里加一段配置，无需改代码。
访问 http://<host>:8000/feed/<site_id> 即可得到 RSS。
"""
import os
import re
import time
import datetime as dt
from urllib.parse import urljoin, urlparse

import yaml
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from flask import Flask, Response, abort

app = Flask(__name__)

CONFIG_PATH = os.environ.get("FEEDMAKER_CONFIG", "/app/sites.yml")
CACHE_TTL = int(os.environ.get("FEEDMAKER_CACHE_TTL", "600"))  # 秒
TIMEOUT = int(os.environ.get("FEEDMAKER_TIMEOUT", "20"))
MAX_ITEMS = int(os.environ.get("FEEDMAKER_MAX_ITEMS", "30"))

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# 标题尾部的时间戳，例如 "...新订单 2026-06-08 15:56:01"
TIME_RE = re.compile(r"\s*(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\s*$")

_cache = {}  # site_id -> (timestamp, xml_bytes)


def load_sites():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["sites"]


def extract_items(cfg, html):
    """从列表页 HTML 中提取 (url, title, pubdate) 列表。"""
    soup = BeautifulSoup(html, "lxml")
    base = cfg["base_url"]
    pattern = re.compile(cfg["link_pattern"])
    strip_time = cfg.get("title_strip_time", False)

    # 关键词过滤：include 命中任一才保留；exclude 命中任一就丢弃（不区分大小写）
    inc = [w.lower() for w in cfg.get("include", [])]
    exc = [w.lower() for w in cfg.get("exclude", [])]

    seen = set()
    items = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not pattern.search(href):
            continue
        url = urljoin(base, href)
        # 只保留与站点同域的文章链接
        if urlparse(url).netloc and urlparse(base).netloc not in urlparse(url).netloc:
            continue
        title = a.get("title") or a.get_text(" ", strip=True)
        title = re.sub(r"\s+", " ", title or "").strip()

        pub = None
        if strip_time:
            m = TIME_RE.search(title)
            if m:
                title = TIME_RE.sub("", title).strip()
                try:
                    pub = dt.datetime(
                        *[int(x) for x in m.groups()],
                        tzinfo=dt.timezone(dt.timedelta(hours=8)),  # 北京时间
                    )
                except ValueError:
                    pub = None

        if not title or len(title) < 6:
            continue
        low = title.lower()
        if inc and not any(w in low for w in inc):
            continue
        if exc and any(w in low for w in exc):
            continue
        if url in seen:
            continue
        seen.add(url)
        items.append({"url": url, "title": title, "pub": pub})
        if len(items) >= MAX_ITEMS:
            break
    return items


def build_rss(cfg, items):
    fg = FeedGenerator()
    fg.title(cfg["name"])
    fg.link(href=cfg["list_url"], rel="alternate")
    fg.description(cfg.get("description", cfg["name"]))
    fg.language(cfg.get("language", "zh-cn"))
    now = dt.datetime.now(dt.timezone.utc)
    for it in items:
        fe = fg.add_entry()
        fe.id(it["url"])
        fe.title(it["title"])
        fe.link(href=it["url"])
        fe.guid(it["url"], permalink=True)
        fe.pubDate(it["pub"] or now)
    return fg.rss_str(pretty=True)


def fetch_html(url, encoding=None):
    headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    r = requests.get(url, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    if encoding:
        r.encoding = encoding
    elif r.encoding is None or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding
    return r.text


@app.route("/feed/<site_id>")
def feed(site_id):
    sites = load_sites()
    if site_id not in sites:
        abort(404, f"unknown site: {site_id}")

    cached = _cache.get(site_id)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return Response(cached[1], mimetype="application/rss+xml; charset=utf-8")

    cfg = sites[site_id]
    try:
        html = fetch_html(cfg["list_url"], cfg.get("encoding"))
    except Exception as e:
        # 抓取失败时回退到旧缓存，避免阅读器报错
        if cached:
            return Response(cached[1], mimetype="application/rss+xml; charset=utf-8")
        abort(502, f"fetch failed: {e}")

    items = extract_items(cfg, html)
    xml = build_rss(cfg, items)
    _cache[site_id] = (time.time(), xml)
    return Response(xml, mimetype="application/rss+xml; charset=utf-8")


@app.route("/digest.xml")
def digest():
    """每日日报 RSS（由 digest.py 生成并写入共享目录）。手机阅读器订阅此地址。"""
    path = os.environ.get("DIGEST_FILE", "/app/digest/digest.xml")
    if not os.path.exists(path):
        abort(404, "日报尚未生成，请先运行 digest.py")
    with open(path, "rb") as f:
        data = f.read()
    return Response(data, mimetype="application/rss+xml; charset=utf-8")


@app.route("/")
def index():
    sites = load_sites()
    lines = ["<h3>feedmaker</h3><ul>"]
    for sid, cfg in sites.items():
        lines.append(f'<li><a href="/feed/{sid}">/feed/{sid}</a> — {cfg["name"]}</li>')
    lines.append("</ul>")
    return "".join(lines)


@app.route("/health")
def health():
    return {"status": "ok", "sites": list(load_sites().keys())}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
