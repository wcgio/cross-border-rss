from src import extractor


def boom(exc):
    def _f(url):
        raise exc
    return _f


def test_uses_feed_content_when_long_enough():
    item = {"url": "u", "title": "t", "feed_content": "<p>" + "字" * 300 + "</p>"}
    out = extractor.extract_text(item, fetch=boom(AssertionError("不应抓取页面")))
    assert out["text"] == "字" * 300


def test_falls_back_to_trafilatura(monkeypatch):
    monkeypatch.setattr(extractor.trafilatura, "extract", lambda html: "正文内容" * 50)
    item = {"url": "u", "title": "t", "feed_content": ""}
    out = extractor.extract_text(item, fetch=lambda url: "<html>whatever</html>")
    assert out["text"].startswith("正文内容")


def test_fetch_failure_degrades_to_short_feed_content():
    item = {"url": "u", "title": "t", "feed_content": "短摘要"}
    out = extractor.extract_text(item, fetch=boom(OSError("blocked")))
    assert out["text"] == "短摘要"


def test_nothing_available_gives_empty_text():
    item = {"url": "u", "title": "t", "feed_content": ""}
    out = extractor.extract_text(item, fetch=boom(OSError("blocked")))
    assert out["text"] == ""


def test_truncates_to_max():
    item = {"url": "u", "title": "t", "feed_content": "字" * 5000}
    out = extractor.extract_text(item, fetch=boom(AssertionError("不应抓取页面")))
    assert len(out["text"]) == extractor.MAX_TEXT


def test_strip_html_decodes_entities():
    assert extractor.strip_html("&lt;p&gt;A &amp; B&lt;/p&gt;") == "A & B"


def test_trafilatura_result_is_truncated(monkeypatch):
    monkeypatch.setattr(extractor.trafilatura, "extract", lambda html: "长" * 5000)
    item = {"url": "u", "title": "t", "feed_content": ""}
    out = extractor.extract_text(item, fetch=lambda url: "<html></html>")
    assert len(out["text"]) == extractor.MAX_TEXT
