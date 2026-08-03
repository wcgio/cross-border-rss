from src import notify

GROUPS = {"platform": [
    {"url": "https://e.com/1", "title": "标题", "summary": "总结", "importance": "high"},
]}
CATS = {"platform": "平台政策"}


def test_telegram_messages_contains_content_and_link():
    msgs = notify.telegram_messages(GROUPS, CATS, "2026-06-11", "https://rss.cgio.qzz.io")
    assert len(msgs) == 1
    assert "平台政策" in msgs[0] and "总结" in msgs[0]
    assert "https://rss.cgio.qzz.io/archive/2026-06-11" in msgs[0]
    assert "https://rss.cgio.qzz.io/archive/2026-06-11.html" not in msgs[0]


def test_telegram_messages_splits_long_content():
    many = {"platform": [
        {"url": f"https://e.com/{i}", "title": "标题" * 30, "summary": "总结内容" * 100, "importance": "normal"}
        for i in range(20)
    ]}
    msgs = notify.telegram_messages(many, CATS, "2026-06-11", "https://x")
    assert len(msgs) > 1
    assert all(len(m) <= notify.TG_LIMIT for m in msgs)


def test_send_telegram_without_creds_is_noop(monkeypatch):
    monkeypatch.delenv("TG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TG_CHAT_ID", raising=False)
    notify.send_telegram(["msg"])  # 不抛异常即通过


def test_send_gotify_without_creds_is_noop(monkeypatch):
    monkeypatch.delenv("GOTIFY_URL", raising=False)
    monkeypatch.delenv("GOTIFY_TOKEN", raising=False)
    notify.send_gotify("t", "m")  # 不抛异常即通过


def test_send_gotify_posts_message(monkeypatch):
    calls = []
    monkeypatch.setenv("GOTIFY_URL", "https://gotify.example.com/")
    monkeypatch.setenv("GOTIFY_TOKEN", "tok")
    monkeypatch.setattr(notify.requests, "post",
                        lambda url, **kw: calls.append((url, kw)) or type("R", (), {"status_code": 200})())
    notify.send_gotify("标题", "内容")
    url, kw = calls[0]
    assert url == "https://gotify.example.com/message"
    assert kw["params"]["token"] == "tok"
    assert kw["json"]["priority"] == 8


# FIX 1 — oversized single block must be truncated
def test_telegram_messages_truncates_single_oversized_block():
    groups = {"platform": [{"url": "https://e.com/1", "title": "题" * 5000,
                            "summary": "s", "importance": "normal"}]}
    msgs = notify.telegram_messages(groups, CATS, "2026-06-11", "https://x")
    assert all(len(m) <= notify.TG_LIMIT for m in msgs)


# FIX 2 — token must not appear in exception message
import pytest


def test_send_telegram_error_does_not_leak_token(monkeypatch):
    monkeypatch.setenv("TG_BOT_TOKEN", "SECRET-TOKEN-123")
    monkeypatch.setenv("TG_CHAT_ID", "@chan")

    def fake_post(url, **kw):
        return type("R", (), {"status_code": 400, "text": '{"ok":false,"description":"Bad Request"}'})()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    with pytest.raises(RuntimeError) as ei:
        notify.send_telegram(["msg"])
    assert "SECRET-TOKEN-123" not in str(ei.value)


# FIX 3 — happy path: each chunk is posted once
def test_send_telegram_posts_each_chunk(monkeypatch):
    calls = []
    monkeypatch.setenv("TG_BOT_TOKEN", "tok")
    monkeypatch.setenv("TG_CHAT_ID", "@chan")

    def fake_post(url, **kw):
        calls.append((url, kw))
        return type("R", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    notify.send_telegram(["m1", "m2"])
    assert len(calls) == 2
    assert "sendMessage" in calls[0][0]
    assert calls[0][1]["json"]["disable_web_page_preview"] is True
    assert calls[0][1]["json"]["chat_id"] == "@chan"


# FIX 4 — gotify failure warn includes title
def test_send_gotify_failure_includes_title(monkeypatch, capsys):
    monkeypatch.setenv("GOTIFY_URL", "https://gotify.example.com/")
    monkeypatch.setenv("GOTIFY_TOKEN", "tok")

    def fake_post(url, **kw):
        raise notify.requests.RequestException("connection refused")

    monkeypatch.setattr(notify.requests, "post", fake_post)
    notify.send_gotify("我的标题", "内容")
    out = capsys.readouterr().out
    assert "我的标题" in out
