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
    monkeypatch.setattr(pipeline, "LOOKBACK_HOURS", 10**6)  # fixture 日期固定，测试不验证时间窗

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
    assert (tmp_path / "docs" / "archive" / today / "index.html").exists()
    archive = (tmp_path / "docs" / "archive" / today / "index.html").read_text(encoding="utf-8")
    assert 'BASE="../../"' in archive
    assert "archive/'+ds+'.html" not in archive
    seen = json.loads((tmp_path / "data" / "seen.json").read_text(encoding="utf-8"))
    assert "https://example.com/a1" in seen
    assert sent and "Ocean freight rates jump 20%" in sent[0]
    index = (tmp_path / "docs" / "index.html").read_text(encoding="utf-8")
    assert 'class="tab-bar"' in index                       # 网页是 Tab 版
    xml = (tmp_path / "docs" / "digest.xml").read_bytes()
    assert b"tab-bar" not in xml and b"<h2>" in xml          # RSS 保持线性分节


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
    monkeypatch.setattr(pipeline, "LOOKBACK_HOURS", 10**6)  # fixture 日期固定，测试不验证时间窗

    def boom(url, encoding=None):
        raise OSError("connection refused")

    monkeypatch.setattr(pipeline.fetcher, "fetch_url", boom)
    monkeypatch.setattr(pipeline.notify, "send_telegram", lambda msgs: None)

    pipeline.run()  # 不应崩溃

    index = (tmp_path / "docs" / "index.html").read_text(encoding="utf-8")
    assert "源异常" not in index   # 源故障详情不对外展示
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


def test_run_partial_source_failure_no_abnormal_title(tmp_path, monkeypatch):
    (tmp_path / "sources.yml").write_text(
        'sources:\n'
        '  - name: "Good"\n'
        '    type: rss\n'
        '    url: "https://good.example.com/feed"\n'
        '    category: logistics\n'
        '  - name: "Bad"\n'
        '    type: rss\n'
        '    url: "https://bad.example.com/feed"\n'
        '    category: market\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline, "SOURCES", str(tmp_path / "sources.yml"))
    monkeypatch.setattr(pipeline, "SEEN_FILE", str(tmp_path / "data" / "seen.json"))
    monkeypatch.setattr(pipeline, "DOCS", str(tmp_path / "docs"))
    monkeypatch.setattr(pipeline, "LOOKBACK_HOURS", 10**6)  # fixture 日期固定，测试不验证时间窗
    xml = (FIXTURES / "sample_rss.xml").read_text(encoding="utf-8")

    def fetch(url, encoding=None):
        if "bad" in url:
            raise OSError("refused")
        return xml

    monkeypatch.setattr(pipeline.fetcher, "fetch_url", fetch)
    monkeypatch.setattr(pipeline.extractor, "extract_text", lambda it, **kw: {**it, "text": ""})
    monkeypatch.setattr(pipeline, "summarize_batch",
                        lambda batch, token: [{**it, "summary": "s", "importance": "normal"} for it in batch])
    monkeypatch.setattr(pipeline, "group_items", lambda items, token: pipeline.group_by_category(items))
    monkeypatch.setattr(pipeline.notify, "send_telegram", lambda msgs: None)

    pipeline.run()

    index = (tmp_path / "docs" / "index.html").read_text(encoding="utf-8")
    assert "源异常" not in index and "Bad" not in index   # 源故障详情不对外展示
    assert "今日抓取异常" not in index   # 只有部分失败时不打异常标


def test_run_ai_batch_failure_falls_back_to_titles(tmp_path, monkeypatch):
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
    monkeypatch.setattr(pipeline, "LOOKBACK_HOURS", 10**6)  # fixture 日期固定，测试不验证时间窗
    xml = (FIXTURES / "sample_rss.xml").read_text(encoding="utf-8")
    monkeypatch.setattr(pipeline.fetcher, "fetch_url", lambda url, encoding=None: xml)
    monkeypatch.setattr(pipeline.extractor, "extract_text", lambda it, **kw: {**it, "text": ""})

    def fail_batch(batch, token):
        raise pipeline.AIError("model down")

    monkeypatch.setattr(pipeline, "summarize_batch", fail_batch)
    monkeypatch.setattr(pipeline, "group_items", lambda items, token: pipeline.group_by_category(items))
    monkeypatch.setattr(pipeline.notify, "send_telegram", lambda msgs: None)

    pipeline.run()  # 不应崩溃

    index = (tmp_path / "docs" / "index.html").read_text(encoding="utf-8")
    assert "Ocean freight rates jump 20%" in index   # 条目退回标题展示
    assert "仅标题" in index
    seen = json.loads((tmp_path / "data" / "seen.json").read_text(encoding="utf-8"))
    assert "https://example.com/a1" in seen
