#!/usr/bin/env python3
"""
digest.py — 生成"每日日报"RSS（每天一条）。

流程：连 FreshRSS 取过去 N 小时的条目 → 关键词过滤 → 可选 AI 摘要
     → 写出 /app/digest/digest.xml（feedmaker 在 /digest.xml 对外提供）。

设计为容器内运行（依赖已在 feedmaker 镜像里），由宿主机 cron 在北京时间 07:00 触发：
  0 7 * * *  cd /path/to/crossborder-feeds && docker compose run --rm digest

时区：容器 TZ=Asia/Shanghai；回看窗口默认 24h，覆盖国外后半夜发布的最新稿。
"""
import os
import time
import html
import datetime as dt

import requests
from feedgen.feed import FeedGenerator

FRESHRSS_URL = os.environ["FRESHRSS_URL"].rstrip("/")     # 容器内用 http://freshrss
FRESHRSS_USER = os.environ["FRESHRSS_USER"]
FRESHRSS_API_PASSWORD = os.environ["FRESHRSS_API_PASSWORD"]

LOOKBACK_HOURS = int(os.environ.get("DIGEST_LOOKBACK_HOURS", "24"))
MAX_ITEMS = int(os.environ.get("DIGEST_MAX_ITEMS", "60"))
OUTPUT = os.environ.get("DIGEST_FILE", "/app/digest/digest.xml")
TZ8 = dt.timezone(dt.timedelta(hours=8))                  # 北京时间

# 关键词过滤（对所有来源统一生效，作用在 FreshRSS 聚合结果上）
INCLUDE = [w.strip().lower() for w in os.environ.get("KEYWORDS_INCLUDE", "").split(",") if w.strip()]
EXCLUDE = [w.strip().lower() for w in os.environ.get("KEYWORDS_EXCLUDE", "").split(",") if w.strip()]

# AI 摘要（可选）
AI_API_URL = os.environ.get("AI_API_URL")
AI_API_KEY = os.environ.get("AI_API_KEY")
AI_MODEL = os.environ.get("AI_MODEL", "claude-3-5-haiku-latest")


def greader_login():
    r = requests.post(
        f"{FRESHRSS_URL}/api/greader.php/accounts/ClientLogin",
        data={"Email": FRESHRSS_USER, "Passwd": FRESHRSS_API_PASSWORD},
        timeout=20,
    )
    r.raise_for_status()
    for line in r.text.splitlines():
        if line.startswith("Auth="):
            return line[len("Auth="):]
    raise RuntimeError("FreshRSS API 登录失败，检查账号/API 密码与 API 访问开关")


def fetch_recent(auth):
    cutoff = int(time.time()) - LOOKBACK_HOURS * 3600
    headers = {"Authorization": f"GoogleLogin auth={auth}"}
    params = {"n": 200, "ot": cutoff, "r": "n", "output": "json"}
    url = f"{FRESHRSS_URL}/api/greader.php/reader/api/0/stream/contents/user/-/state/com.google/reading-list"
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()

    items, seen = [], set()
    for it in r.json().get("items", []):
        if it.get("published", 0) < cutoff:
            continue
        link = (it.get("canonical") or it.get("alternate") or [{}])[0].get("href", "")
        title = (it.get("title") or "").strip()
        if not title or link in seen:
            continue
        low = title.lower()
        if INCLUDE and not any(w in low for w in INCLUDE):
            continue
        if EXCLUDE and any(w in low for w in EXCLUDE):
            continue
        seen.add(link)
        items.append({
            "title": title,
            "url": link,
            "source": it.get("origin", {}).get("title", ""),
        })
        if len(items) >= MAX_ITEMS:
            break
    return items


def ai_summary_html(items):
    if not (AI_API_URL and AI_API_KEY):
        return None
    headlines = "\n".join(f"{i}. [{it['source']}] {it['title']}" for i, it in enumerate(items, 1))
    prompt = (
        "下面是过去24小时跨境电商与国际物流的资讯标题。请用中文输出 6-10 条要点：\n"
        "- 先剔除与跨境电商/外贸/国际物流无关的条目\n"
        "- 按重要性排序，合并同一主题，每条一句话\n"
        "- 重点关注：平台政策与合规、费用/佣金变动、关税与税务、物流与海运空运、各平台动态\n"
        "- 只输出要点本身，不要前言\n\n"
        f"{headlines}"
    )
    try:
        if "anthropic" in AI_API_URL:
            headers = {"x-api-key": AI_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
            body = {"model": AI_MODEL, "max_tokens": 1000, "messages": [{"role": "user", "content": prompt}]}
            r = requests.post(AI_API_URL, headers=headers, json=body, timeout=90)
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json().get("content", []))
        else:
            headers = {"Authorization": f"Bearer {AI_API_KEY}", "content-type": "application/json"}
            body = {"model": AI_MODEL, "max_tokens": 1000, "messages": [{"role": "user", "content": prompt}]}
            r = requests.post(AI_API_URL, headers=headers, json=body, timeout=90)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
        return "<p>" + html.escape(text).replace("\n", "<br>") + "</p>"
    except Exception as e:
        print(f"[warn] AI 摘要失败，回退纯列表：{e}")
        return None


def build_body(items, summary_html):
    parts = []
    if summary_html:
        parts.append("<h3>今日要点</h3>")
        parts.append(summary_html)
        parts.append("<h3>全部原文</h3>")
    parts.append("<ul>")
    for it in items:
        src = f"[{html.escape(it['source'])}] " if it["source"] else ""
        parts.append(f'<li>{src}<a href="{html.escape(it["url"])}">{html.escape(it["title"])}</a></li>')
    parts.append("</ul>")
    return "".join(parts)


def main():
    auth = greader_login()
    items = fetch_recent(auth)
    today = dt.datetime.now(TZ8)
    date_str = today.strftime("%Y-%m-%d")

    fg = FeedGenerator()
    fg.title("跨境电商 / 国际物流 · 每日日报")
    fg.link(href="http://feedmaker:8000/digest.xml", rel="self")
    fg.description("每天一条，过去24小时跨境与物流要点汇总")
    fg.language("zh-cn")

    if not items:
        body = "<p>过去24小时没有匹配的新资讯。</p>"
        title = f"跨境/物流日报 {date_str}（无新内容）"
    else:
        body = build_body(items, ai_summary_html(items))
        title = f"跨境/物流日报 {date_str}（{len(items)} 条）"

    fe = fg.add_entry()
    fe.id(f"digest-{date_str}")              # 按日去重：每天一条新条目
    fe.title(title)
    fe.link(href="http://feedmaker:8000/digest.xml")
    fe.guid(f"digest-{date_str}", permalink=False)
    fe.pubDate(today)
    fe.content(body, type="CDATA")

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    fg.rss_file(OUTPUT, pretty=True)
    print(f"已生成 {OUTPUT}：{title}")


if __name__ == "__main__":
    main()
