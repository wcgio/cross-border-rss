import datetime as dt
import json
from pathlib import Path

import pytest

from src import pipeline

FIXTURES = Path(__file__).parent / "fixtures"


def test_run_produces_outputs(tmp_path, monkeypatch):
    (tmp_path / "sources.yml").write_text(
        'sources:\n'
        '  - name: "Test Feed"\n'
        '    type: rss\n'
        '    url: "https://example.com/feed"\n'
        '    category: logistics\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline, "SOURCES", str(tmp_path / "sources.yml"))
    monkeypatch.setattr(pipeline, "SEEN_FILE", str(tmp_path / "data" / "seen.json"))
    monkeypatch.setattr(pipeline, "DOCS", str(tmp_path / "docs"))

    xml = (FIXTURES / "sample_rss.xml").read_text(encoding="utf-8")
    monkeypatch.setattr(pipeline.fetcher, "fetch_url", lambda url, encoding=None: xml)
    monkeypatch.setattr(pipeline.extractor, "extract_text",
                        lambda it, **kw: {**it, "text": it["feed_content"]})
    monkeypatch.setattr(pipeline, "summarize_batch",
                        lambda batch, token: [{**it, "summary": "总结", "importance": "normal"} for it in batch])
    monkeypatch.setattr(pipeline, "group_items",
                        lambda items, token: pipeline.group_by_category(items))
    sent = []
    monkeypatch.setattr(pipeline.notify, "send_telegram", lambda msgs: sent.extend(msgs))

    pipeline.run()

    today = dt.datetime.now(pipeline.TZ8).date().isoformat()
    assert (tmp_path / "docs" / "digest.xml").exists()
    assert (tmp_path / "docs" / "index.html").exists()
    assert (tmp_path / "docs" / "archive" / f"{today}.html").exists()
    seen = json.loads((tmp_path / "data" / "seen.json").read_text(encoding="utf-8"))
    assert "https://example.com/a1" in seen
    assert sent and "Ocean freight rates jump 20%" in sent[0]


def test_run_records_source_errors(tmp_path, monkeypatch):
    (tmp_path / "sources.yml").write_text(
        'sources:\n'
        '  - name: "Broken"\n'
        '    type: rss\n'
        '    url: "https://broken.example.com/feed"\n'
        '    category: market\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline, "SOURCES", str(tmp_path / "sources.yml"))
    monkeypatch.setattr(pipeline, "SEEN_FILE", str(tmp_path / "data" / "seen.json"))
    monkeypatch.setattr(pipeline, "DOCS", str(tmp_path / "docs"))

    def boom(url, encoding=None):
        raise OSError("connection refused")

    monkeypatch.setattr(pipeline.fetcher, "fetch_url", boom)
    monkeypatch.setattr(pipeline.notify, "send_telegram", lambda msgs: None)

    pipeline.run()  # 不应崩溃

    index = (tmp_path / "docs" / "index.html").read_text(encoding="utf-8")
    assert "源异常" in index and "Broken" in index
    assert "今日抓取异常" in index


def test_main_sends_gotify_on_crash(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "run", lambda: 1 / 0)
    monkeypatch.setattr(pipeline.notify, "send_gotify", lambda title, msg: calls.append((title, msg)))
    with pytest.raises(ZeroDivisionError):
        pipeline.main()
    assert calls
    assert "崩溃" in calls[0][0]
    assert "位置：" in calls[0][1]
