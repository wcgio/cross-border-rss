import datetime as dt

from src import filters


def make(url="u1", title="亚马逊上调FBA费用"):
    return {"url": url, "title": title}


def test_keyword_filter_include_exclude():
    items = [make("u1", "亚马逊上调FBA费用"), make("u2", "某公司招聘运营"), make("u3", "Temu 美区新政")]
    out = filters.keyword_filter(items, include=["亚马逊", "temu"], exclude=["招聘"])
    assert [it["url"] for it in out] == ["u1", "u3"]


def test_keyword_filter_no_rules_keeps_all():
    items = [make("u1"), make("u2")]
    assert filters.keyword_filter(items) == items


def test_dedup_unseen():
    seen = {"u1": "2026-06-10"}
    out = filters.dedup_unseen([make("u1"), make("u2")], seen)
    assert [it["url"] for it in out] == ["u2"]


def test_update_seen_adds_and_prunes():
    today = dt.date(2026, 6, 11)
    seen = {"old": "2026-06-01", "kept": "2026-06-08"}
    out = filters.update_seen(seen, [make("u2")], today, keep_days=7)
    assert "old" not in out
    assert out["kept"] == "2026-06-08"
    assert out["u2"] == "2026-06-11"


def test_update_seen_drops_malformed_dates():
    today = dt.date(2026, 6, 11)
    seen = {"bad": "not-a-date", "kept": "2026-06-08"}
    out = filters.update_seen(seen, [], today, keep_days=7)
    assert "bad" not in out
    assert out["kept"] == "2026-06-08"
