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
.tabs > input {{ display: none; }}
.tab-bar {{ display: flex; gap: 4px; flex-wrap: wrap; margin: 12px 0 0;
  border-bottom: 1px solid #8884; position: sticky; top: 0;
  background: Canvas; padding-top: 4px; }}
.tab-bar label {{ padding: 6px 12px; cursor: pointer; color: #888;
  border-bottom: 2px solid transparent; font-size: .95em; user-select: none; }}
.tab-bar .count {{ font-size: .8em; opacity: .7; }}
.tabs .panel {{ display: none; }}
#tab-platform:checked ~ .tab-bar label[for="tab-platform"],
#tab-logistics:checked ~ .tab-bar label[for="tab-logistics"],
#tab-compliance:checked ~ .tab-bar label[for="tab-compliance"],
#tab-market:checked ~ .tab-bar label[for="tab-market"] {{
  color: inherit; font-weight: 600; border-bottom-color: #e0a000; }}
#tab-platform:checked ~ #panel-platform,
#tab-logistics:checked ~ #panel-logistics,
#tab-compliance:checked ~ #panel-compliance,
#tab-market:checked ~ #panel-market {{ display: block; }}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
<footer class="meta"><p>{footer}</p></footer>
</body>
</html>
"""


def _render_article(it):
    cls = "high" if it.get("importance") == "high" else "normal"
    url = it["url"] if it["url"].startswith(("https://", "http://")) else "#"
    summary = (
        f"<p>{html.escape(it['summary'])}</p>"
        if it.get("summary")
        else '<p class="meta">（仅标题，未能获取正文）</p>'
    )
    return (
        f'<article class="{cls}"><h3>{html.escape(it["title"])}</h3>'
        f'<p class="meta">{html.escape(it.get("source") or "")}</p>'
        f"{summary}"
        f'<p class="meta"><a href="{html.escape(url)}">原文 ↗</a></p></article>'
    )


def render_groups_html(groups):
    """线性分节版（RSS 阅读器用：不能依赖 CSS 交互）。"""
    parts = []
    for key, label in CATEGORIES.items():
        items = groups.get(key) or []
        if not items:
            continue
        parts.append(f"<section><h2>{label}</h2>")
        parts.extend(_render_article(it) for it in items)
        parts.append("</section>")
    return "".join(parts)


def render_groups_tabbed(groups):
    """网页版：四主题 Tab 切换（纯 CSS radio 实现，零 JS）。空分类不出 Tab。"""
    keys = [k for k in CATEGORIES if groups.get(k)]
    if not keys:
        return ""
    parts = ['<div class="tabs">']
    for i, key in enumerate(keys):
        checked = " checked" if i == 0 else ""
        parts.append(f'<input type="radio" name="tab" id="tab-{key}"{checked}>')
    parts.append('<nav class="tab-bar">')
    for key in keys:
        parts.append(
            f'<label for="tab-{key}">{CATEGORIES[key]} '
            f'<span class="count">{len(groups[key])}</span></label>'
        )
    parts.append("</nav>")
    for key in keys:
        parts.append(f'<section class="panel" id="panel-{key}">')
        parts.extend(_render_article(it) for it in groups[key])
        parts.append("</section>")
    parts.append("</div>")
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
