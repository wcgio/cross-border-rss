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
            url = it["url"] if it["url"].startswith(("https://", "http://")) else "#"
            parts.append(f'<p class="meta"><a href="{html.escape(url)}">原文 ↗</a></p></article>')
        parts.append("</section>")
    if source_errors:
        parts.append("<section><h2>源异常</h2><ul>")
        for name, err in source_errors:
            parts.append(f"<li>{html.escape(name)}：{html.escape(err)}</li>")
        parts.append("</ul></section>")
    return "".join(parts)


def render_page(title, body_html, footer=""):
    """组装整页。title 会被转义；body_html 与 footer 必须是调用方构建的可信 HTML。"""
    return PAGE_TMPL.format(title=html.escape(title), body=body_html, footer=footer)


def render_index(date_str, body_html, archive_dates, title=None):
    links = " · ".join(f'<a href="archive/{html.escape(d)}.html">{html.escape(d)}</a>' for d in archive_dates)
    body = body_html + f"<section><h2>历史归档</h2><p>{links}</p></section>"
    page_title = title if title is not None else f"跨境/物流日报 {date_str}"
    return render_page(
        page_title, body,
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
