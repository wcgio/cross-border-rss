"""渲染 digest.xml 与 HTML 页面。纯函数：分组数据 → 字符串/字节。"""
import datetime as dt
import html
import json
from collections import Counter

from feedgen.feed import FeedGenerator

from .summarizer import CATEGORIES

TZ8 = dt.timezone(dt.timedelta(hours=8))
TG_CHANNEL = "https://t.me/crossborderdaily"  # 公开频道，页脚订阅入口

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
body.wide {{ max-width: 980px; }}
h1 {{ font-size: 1.4em; margin-bottom: 4px; }}
.topbar {{ display: flex; justify-content: flex-end; font-size: 14px; }}
.window {{ background: rgba(64, 158, 255, .1); border-left: 4px solid #409eff;
  border-radius: 0 6px 6px 0; padding: 8px 12px; color: #666; font-size: .85em;
  margin: 6px 0 16px; }}
h2 {{ font-size: 1.15em; border-bottom: 1px solid #8884; padding-bottom: 4px; }}
h3 {{ font-size: 1em; margin: 0 0 4px; }}
article {{ margin: 12px 0; padding: 12px 14px; border: 1px solid #8883;
  border-radius: 10px; background: rgba(136, 136, 136, .07); }}
article.high {{ border-left: 3px solid #e64545; }}
article p:last-child {{ margin-bottom: 0; }}
article h3 {{ margin-top: 0; }}
.meta {{ color: #888; font-size: .85em; margin: 2px 0; }}
.badge {{ background: #e64545; color: #fff; font-size: .72em; font-weight: 600;
  padding: 1px 6px; border-radius: 4px; margin-right: 6px; vertical-align: 2px; }}
.sources {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0 0; font-size: .82em; }}
.sources .chip {{ color: #409eff; background: rgba(64, 158, 255, .12);
  border: 1px solid rgba(64, 158, 255, .35); border-radius: 6px; padding: 2px 9px; }}
.sources .chip b {{ color: CanvasText; font-weight: 700; margin-left: 2px; }}
a {{ color: inherit; }}
details {{ margin: 4px 0; }}
summary {{ cursor: pointer; color: #888; }}
.layout {{ display: flex; gap: 24px; align-items: flex-start; }}
.main {{ flex: 1; min-width: 0; }}
.side {{ width: 244px; flex: none; position: sticky; top: 12px; align-self: flex-start; }}
.side h2 {{ margin-top: 0; }}
.cal {{ width: 100%; padding: 10px;
  border: 1px solid #8884; border-radius: 10px; font-size: 13px; box-sizing: border-box; }}
.cal-hd {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
.cal-title {{ font-weight: 600; }}
.cal-nav button {{ background: none; border: none; color: inherit; cursor: pointer;
  font-size: 16px; line-height: 1; padding: 0 5px; }}
.cal-nav button[disabled] {{ opacity: .25; cursor: default; }}
.cal-grid {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; text-align: center; }}
.cal-wd {{ color: #888; font-size: 11px; padding: 2px 0; }}
.cal-day {{ display: flex; align-items: center; justify-content: center; aspect-ratio: 1;
  border-radius: 50%; text-decoration: none; }}
.cal-day.on {{ color: #409eff; }}
.cal-day.on:hover {{ background: rgba(64, 158, 255, .14); }}
.cal-day.off {{ color: #bbb; }}
.cal-day.today {{ background: #409eff; color: #fff; font-weight: 600; }}
.cal-empty {{ aspect-ratio: 1; }}
@media (max-width: 760px) {{
  body.wide {{ max-width: 720px; }}
  .layout {{ flex-direction: column; }}
  .side {{ width: 100%; position: static; }}
  .cal {{ max-width: 320px; margin: 0 auto; }}
}}
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
  color: inherit; font-weight: 600; border-bottom-color: #e64545; }}
#tab-platform:checked ~ #panel-platform,
#tab-logistics:checked ~ #panel-logistics,
#tab-compliance:checked ~ #panel-compliance,
#tab-market:checked ~ #panel-market {{ display: block; }}
</style>
</head>
<body class="{body_class}">
<h1>{title}</h1>
{body}
<footer class="meta"><p>{footer}</p></footer>
</body>
</html>
"""


def _render_article(it):
    high = it.get("importance") == "high"
    cls = "high" if high else "normal"
    badge = '<span class="badge">重点</span>' if high else ""
    url = it["url"] if it["url"].startswith(("https://", "http://")) else "#"
    summary = (
        f"<p>{html.escape(it['summary'])}</p>"
        if it.get("summary")
        else '<p class="meta">（仅标题，未能获取正文）</p>'
    )
    return (
        f'<article class="{cls}"><h3>{badge}{html.escape(it["title"])}</h3>'
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
    counts = Counter(it.get("source") or "未知来源" for k in keys for it in groups[k])
    chips = "".join(
        f'<span class="chip">{html.escape(s)} <b>{n}</b></span>'
        for s, n in counts.most_common()
    )
    parts = [f'<div class="sources">{chips}</div>', '<div class="tabs">']
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


def render_page(title, body_html, footer="", body_class=""):
    """组装整页。title 会被转义；body_html 与 footer 必须是调用方构建的可信 HTML。"""
    return PAGE_TMPL.format(title=html.escape(title), body=body_html, footer=footer,
                           body_class=body_class)


# 客户端日历：根据嵌入的可用日期列表渲染当月，今天高亮、有日报的可点、未来/无数据不可点。
# ‹ › 翻月：向后到最早有数据的月、向前到当前月为止。纯原生 JS，无外部依赖。
_CAL_JS = """
var avail=new Set(DATES);
var sorted=DATES.slice().sort();
var minYM=sorted.length?sorted[0].slice(0,7):TODAY.slice(0,7);
var curYM=TODAY.slice(0,7);
var tp=TODAY.split("-").map(Number);
var tY=tp[0],tM=tp[1]-1,tD=tp[2];
var vY=tY,vM=tM;
var WD=["日","一","二","三","四","五","六"];
function p(n){return(n<10?"0":"")+n;}
function draw(){
  var ym=vY+"-"+p(vM+1);
  var startDow=new Date(vY,vM,1).getDay();
  var days=new Date(vY,vM+1,0).getDate();
  var canPrev=ym>minYM,canNext=ym<curYM;
  var h='<div class="cal-hd"><span class="cal-title">'+vY+'年'+(vM+1)+'月</span><span class="cal-nav">';
  h+='<button data-d="-1"'+(canPrev?'':' disabled')+'>\\u2039</button>';
  h+='<button data-d="1"'+(canNext?'':' disabled')+'>\\u203a</button></span></div>';
  h+='<div class="cal-grid">';
  for(var i=0;i<7;i++)h+='<span class="cal-wd">'+WD[i]+'</span>';
  for(var b=0;b<startDow;b++)h+='<span class="cal-empty"></span>';
  for(var d=1;d<=days;d++){
    var ds=ym+"-"+p(d);
    var c="cal-day"+((vY===tY&&vM===tM&&d===tD)?" today":"");
    if(avail.has(ds))h+='<a class="'+c+' on" href="'+BASE+'archive/'+ds+'.html">'+d+'</a>';
    else h+='<span class="'+c+' off">'+d+'</span>';
  }
  h+='</div>';
  var el=document.getElementById('cal');
  el.innerHTML=h;
  el.querySelectorAll('.cal-nav button').forEach(function(btn){
    if(btn.disabled)return;
    btn.onclick=function(){
      vM+=Number(btn.getAttribute('data-d'));
      if(vM<0){vM=11;vY--;}
      if(vM>11){vM=0;vY++;}
      draw();
    };
  });
}
draw();
"""


def render_calendar(archive_dates, now, base=""):
    """右侧日历容器 + 内联渲染脚本。base 是回到站点根的相对前缀（归档页用 "../"）。"""
    data = (f'var DATES={json.dumps(archive_dates)};'
            f'var TODAY="{now.strftime("%Y-%m-%d")}";'
            f'var BASE={json.dumps(base)};\n')
    return '<div class="cal" id="cal"></div><script>\n(function(){\n' + data + _CAL_JS + '})();\n</script>'


def render_index(date_str, body_html, archive_dates, title=None, now=None, lookback_hours=24, base=""):
    # base：回到站点根的相对前缀。首页 ""，每日归档页 "../"。
    subscribe = (
        f'<span class="subscribe">订阅：<a href="{TG_CHANNEL}">Telegram 频道</a>'
        f' · <a href="{base}digest.xml">RSS</a></span>'
    )
    window = ""
    if now is not None:
        fmt = "%Y-%m-%d %H:%M"
        start = now - dt.timedelta(hours=lookback_hours)
        window = (
            f'<p class="window">本期收录北京时间 {start.strftime(fmt)} 至 '
            f'{now.strftime(fmt)} 发布的资讯<br>每天 12:00 更新一次，仅含过去 24 小时的新内容。</p>'
        )
    topbar = f'<div class="topbar">{subscribe}</div>{window}'
    main = topbar + body_html
    page_title = title if title is not None else f"跨境/物流日报 {date_str}"

    if now is None:  # 测试等无时间场景：单栏，无日历
        return render_page(page_title, main)
    # 日历即归档：PC 在右侧栏、移动端落到底部居中
    side = f'<h2>历史归档</h2>{render_calendar(archive_dates, now, base)}'
    body = (
        f'<div class="layout"><div class="main">{main}</div>'
        f'<aside class="side">{side}</aside></div>'
    )
    return render_page(page_title, body, body_class="wide")


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
