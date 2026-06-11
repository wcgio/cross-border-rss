from src import notify

GROUPS = {"platform": [
    {"url": "https://e.com/1", "title": "标题", "summary": "总结", "importance": "high"},
]}
CATS = {"platform": "平台政策"}


def test_telegram_messages_contains_content_and_link():
    msgs = notify.telegram_messages(GROUPS, CATS, "2026-06-11", "https://rss.cgio.qzz.io")
    assert len(msgs) == 1
    assert "平台政策" in msgs[0] and "总结" in msgs[0]
    assert "https://rss.cgio.qzz.io/archive/2026-06-11.html" in msgs[0]


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
