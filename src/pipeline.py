#!/usr/bin/env python3
"""日报管道编排：抓取 → 过滤去重 → 正文 → AI 总结分组 → 渲染落盘 → Telegram。

崩溃时把异常位置与报错信息推送 Gotify（不含任何凭据/环境变量值），再以非 0 退出。
运行方式：python -m src.pipeline
"""
import datetime as dt
import json
import os
import re
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
LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", "24"))
TZ8 = dt.timezone(dt.timedelta(hours=8))


def load_seen():
    try:
        with open(SEEN_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def run():
    now = dt.datetime.now(TZ8)
    today = now.date()
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

    items = filters.within_window(items, now, hours=LOOKBACK_HOURS)
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

    body_rss = render.render_groups_html(groups)   # RSS 阅读器：线性分节
    body_web = render.render_groups_tabbed(groups)  # 网页：纯 CSS Tab
    if not summarized:
        notice = "<p>过去24小时没有新资讯。</p>"
        body_rss = notice + body_rss
        body_web = notice + body_web
    title = f"跨境/物流日报 {date_str}" + (f"（{count} 条）" if count else "（无新内容）")
    if not items and source_errors:
        title += "【今日抓取异常】"

    os.makedirs(os.path.join(DOCS, "archive"), exist_ok=True)
    existing = [n[:-5] for n in os.listdir(os.path.join(DOCS, "archive"))
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.html", n)]
    if date_str not in existing:
        existing.append(date_str)
    archive_dates = sorted(existing, reverse=True)

    # 每日归档页与首页同样布局（含右侧日历）；归档页在 /archive/ 下，链接前缀 "../"
    with open(os.path.join(DOCS, "archive", f"{date_str}.html"), "w", encoding="utf-8") as f:
        f.write(render.render_index(date_str, body_web, archive_dates, title=title,
                                    now=now, lookback_hours=LOOKBACK_HOURS, base="../"))
    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as f:
        f.write(render.render_index(date_str, body_web, archive_dates, title=title,
                                    now=now, lookback_hours=LOOKBACK_HOURS, base=""))
    with open(os.path.join(DOCS, "digest.xml"), "wb") as f:
        f.write(render.render_rss(date_str, body_rss, count, SITE_URL))

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
