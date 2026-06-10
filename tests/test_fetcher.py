import datetime as dt
from pathlib import Path

from src import fetcher

FIXTURES = Path(__file__).parent / "fixtures"

RSS_CFG = {"name": "Test Feed", "type": "rss", "url": "https://example.com/feed", "category": "logistics"}

SCRAPE_CFG = {
    "name": "亿邦动力 · 跨境电商",
    "type": "scrape",
    "url": "https://m.ebrun.com/label/6.html",
    "base_url": "https://m.ebrun.com",
    "link_pattern": "/\\d{5,}\\.html",
    "title_strip_time": True,
    "category": "platform",
}


def test_parse_rss_extracts_fields():
    xml = (FIXTURES / "sample_rss.xml").read_text(encoding="utf-8")
    items = fetcher.parse_rss(RSS_CFG, xml)
    assert len(items) == 3
    first = items[0]
    assert first["title"] == "Ocean freight rates jump 20%"
    assert first["url"] == "https://example.com/a1"
    assert first["source"] == "Test Feed"
    assert first["category"] == "logistics"
    assert "rates rose sharply" in first["feed_content"]
    assert first["pub"].tzinfo is not None


def test_parse_listing_extracts_dedups_and_strips_time():
    html = (FIXTURES / "ebrun.html").read_text(encoding="utf-8")
    items = fetcher.parse_listing(SCRAPE_CFG, html)
    assert len(items) == 1  # 短标题、外域、重复、不匹配的都被过滤
    it = items[0]
    assert it["url"] == "https://m.ebrun.com/677729.html"
    assert it["title"] == "Temu美区半托管招商升级"
    assert it["pub"] == dt.datetime(2026, 6, 10, 15, 56, 1, tzinfo=dt.timezone(dt.timedelta(hours=8)))
    assert it["feed_content"] == ""
    assert all("evil" not in it["url"] for it in items)


def test_parse_rss_content_branch_missing_pub_and_drops_titleless():
    xml = (FIXTURES / "sample_rss.xml").read_text(encoding="utf-8")
    items = fetcher.parse_rss(RSS_CFG, xml)
    assert len(items) == 3                      # 无标题的 a4 被丢弃
    third = items[2]
    assert third["url"] == "https://example.com/a3"
    assert "Full body content" in third["feed_content"]   # content 分支
    assert third["pub"] is None                            # 无 pubDate
