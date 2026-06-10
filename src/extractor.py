"""为条目补充正文 text。降级链：feed 自带内容 → trafilatura 抓页面提取 → 空（仅标题）。"""
import html as html_lib
import re

import trafilatura

from .fetcher import fetch_url

MIN_FEED_CONTENT = 200  # feed 内容达到此长度即不再抓页面
MAX_TEXT = 2000         # 控制 AI token 用量


def strip_html(s):
    text = html_lib.unescape(s or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_text(item, fetch=fetch_url):
    plain = strip_html(item.get("feed_content"))
    if len(plain) >= MIN_FEED_CONTENT:
        item["text"] = plain[:MAX_TEXT]
        return item
    try:
        html = fetch(item["url"])
        text = (trafilatura.extract(html) or "").strip()
    except Exception as e:
        print(f"[warn] 正文提取失败 {item.get('url', '')}: {type(e).__name__}: {e}")
        text = ""
    item["text"] = (text or plain)[:MAX_TEXT]
    return item
