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
    """把本次条目并入 seen，并清理超过 keep_days 的旧记录。非法日期会被丢弃。"""
    cutoff = today - dt.timedelta(days=keep_days)
    kept = {}
    for u, d in seen.items():
        try:
            if dt.date.fromisoformat(d) >= cutoff:
                kept[u] = d
        except ValueError:
            # 忽略格式错误的日期记录
            pass
    for it in items:
        kept[it["url"]] = today.isoformat()
    return kept
