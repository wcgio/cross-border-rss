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
