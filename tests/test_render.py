import datetime as dt

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
    body = render.render_groups_html(GROUPS)
    assert "平台政策" in body and "国际物流" in body
    assert "重大政策&lt;标题&gt;" in body  # HTML 转义
    assert 'class="high"' in body
    assert "仅标题" in body                # 无总结的条目有标注


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


def test_render_index_escapes_archive_dates():
    page = render.render_index("2026-06-11", "", ["<script>x</script>"])
    assert "<script>x</script>" not in page


def test_render_groups_html_blocks_javascript_urls():
    groups = {"platform": [{"url": "javascript:alert(1)", "title": "标题足够长条目",
                            "summary": "s", "importance": "normal", "source": "S"}]}
    body = render.render_groups_html(groups)
    assert "javascript:" not in body


def test_render_rss_zero_items_suffix():
    xml = render.render_rss("2026-06-11", "<p>B</p>", 0, "https://x")
    assert "（无新内容）".encode() in xml


def test_render_page_escapes_title():
    page = render.render_page("A<B>C", "")
    assert "A&lt;B&gt;C" in page


def test_render_index_custom_title():
    page = render.render_index("2026-06-11", "", [], title="自定义标题X")
    assert "自定义标题X" in page


def test_render_index_has_telegram_subscribe_link():
    page = render.render_index("2026-06-11", "<p>B</p>", ["2026-06-11"])
    assert 'href="https://t.me/crossborderdaily"' in page
    assert "digest.xml" in page   # RSS 链接仍保留


def test_render_index_calendar_embeds_dates_and_today():
    now = dt.datetime(2026, 6, 17, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=8)))
    page = render.render_index("2026-06-17", "<p>B</p>", ["2026-06-17", "2026-06-16"], now=now)
    assert 'id="cal"' in page                      # 日历容器
    assert 'TODAY="2026-06-17"' in page            # 今天
    assert '"2026-06-16"' in page                   # 可用日期嵌入
    assert page.index('id="cal"') < page.index("<p>B</p>")  # 日历在顶部


def test_render_index_no_calendar_without_now():
    page = render.render_index("2026-06-17", "<p>B</p>", ["2026-06-17"])
    assert 'id="cal"' not in page                   # 无 now 时不渲染日历


def test_render_index_archive_groups_by_month():
    dates = ["2026-06-17", "2026-06-16", "2026-05-31", "2026-05-01", "2026-04-30"]
    page = render.render_index("2026-06-17", "<p>B</p>", dates)
    assert "<details><summary>2026-06" not in page          # 当月平铺，不折叠
    assert 'href="archive/2026-06-17.html"' in page
    assert "<details><summary>2026-05（2 篇）</summary>" in page  # 旧月折叠
    assert "<details><summary>2026-04（1 篇）</summary>" in page
    assert 'href="archive/2026-05-01.html"' in page          # 折叠块内链接仍在


def test_render_index_topbar_and_window():
    now = dt.datetime(2026, 6, 17, 12, 5, tzinfo=dt.timezone(dt.timedelta(hours=8)))
    page = render.render_index("2026-06-17", "<p>B</p>", ["2026-06-17"], now=now, lookback_hours=24)
    assert 'class="topbar"' in page
    # 订阅行在标题与正文之间（即顶部），不在页脚
    assert page.index('class="topbar"') < page.index("<p>B</p>")
    assert "更新于" not in page                       # 推送时间已移除
    assert 'href="https://t.me/crossborderdaily"' in page
    assert 'class="window"' in page                   # 时间段说明
    assert "2026-06-16 12:05" in page                 # 窗口起点 = now - 24h
    assert "至 2026-06-17 12:05" in page              # 窗口终点


def test_render_groups_tabbed_structure():
    body = render.render_groups_tabbed(GROUPS)
    assert body.count('type="radio"') == 2                # 只为非空分类生成 Tab
    assert 'id="tab-platform" checked' in body            # 第一个非空分类默认选中
    assert 'id="tab-logistics" checked' not in body
    assert '<label for="tab-platform">平台政策 <span class="count">1</span></label>' in body
    assert 'id="panel-platform"' in body
    assert "重大政策&lt;标题&gt;" in body                  # 条目渲染与转义复用
    assert "仅标题" in body


def test_render_groups_tabbed_empty():
    assert render.render_groups_tabbed({}) == ""
    assert render.render_groups_tabbed({"platform": []}) == ""


def test_high_importance_article_gets_badge():
    body = render.render_groups_html(GROUPS)
    assert '<span class="badge">重点</span>' in body
    assert body.count('<span class="badge">') == 1   # 普通条目没有角标


def test_render_groups_tabbed_source_bar_counts_and_order():
    groups = {
        "platform": [
            {"url": "https://e/1", "title": "标题一", "summary": "s", "importance": "normal", "source": "甲"},
            {"url": "https://e/2", "title": "标题二", "summary": "s", "importance": "normal", "source": "乙"},
        ],
        "logistics": [
            {"url": "https://e/3", "title": "标题三", "summary": "s", "importance": "normal", "source": "乙"},
        ],
    }
    body = render.render_groups_tabbed(groups)
    assert '<span class="chip">乙 <b>2</b></span>' in body      # 数字加粗
    assert '<span class="chip">甲 <b>1</b></span>' in body
    assert body.index("乙 <b>2</b>") < body.index("甲 <b>1</b>")        # 按条数降序
    assert body.index('class="sources"') < body.index('type="radio"')  # 位于 Tab 上方
