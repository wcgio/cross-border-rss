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
    body = render.render_groups_html(GROUPS, source_errors=[("坏源", "HTTP 502")])
    assert "平台政策" in body and "国际物流" in body
    assert "重大政策&lt;标题&gt;" in body  # HTML 转义
    assert 'class="high"' in body
    assert "仅标题" in body                # 无总结的条目有标注
    assert "源异常" in body and "坏源" in body


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
