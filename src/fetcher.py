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
    for e in feed.entries:
        url = e.get("link", "")
        title = (e.get("title") or "").strip()
        if not url or not title:
            continue
        content = ""
        if e.get("content"):
            content = e["content"][0].get("value", "")
        elif e.get("summary"):
            content = e["summary"]
        pub = None
        if e.get("published_parsed"):
            pub = dt.datetime(*e["published_parsed"][:6], tzinfo=dt.timezone.utc)
        items.append({
            "url": url,
            "title": title,
            "source": cfg["name"],
            "category": cfg["category"],
            "pub": pub,
            "feed_content": content,
        })
        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break
    return items


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
        url_netloc = urlparse(url).netloc
        base_netloc = urlparse(base).netloc
        if not (url_netloc == base_netloc or url_netloc.endswith("." + base_netloc)):
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
