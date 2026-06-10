from src import summarizer

ITEMS = [
    {"url": "u1", "title": "亚马逊上调佣金", "text": "正文1", "source": "A", "category": "platform"},
    {"url": "u2", "title": "无关娱乐新闻", "text": "正文2", "source": "B", "category": "market"},
    {"url": "u3", "title": "海运运价上涨", "text": "", "source": "C", "category": "logistics"},
]


def test_summarize_batch_maps_results_and_drops_irrelevant():
    def fake_chat(prompt, token, max_tokens=2000):
        assert "亚马逊上调佣金" in prompt
        return {"results": [
            {"id": 1, "relevant": True, "importance": "high", "summary": "佣金详细总结"},
            {"id": 2, "relevant": False},
            {"id": 3, "relevant": True, "importance": "normal", "summary": "运价一句话"},
        ]}

    out = summarizer.summarize_batch(ITEMS, "tok", chat=fake_chat)
    assert [it["url"] for it in out] == ["u1", "u3"]
    assert out[0]["importance"] == "high"
    assert out[0]["summary"] == "佣金详细总结"


def test_summarize_batch_missing_id_keeps_item_with_empty_summary():
    out = summarizer.summarize_batch(ITEMS[:1], "tok", chat=lambda *a, **k: {"results": []})
    assert out[0]["summary"] == ""
    assert out[0]["importance"] == "normal"


def test_group_items_orders_merges_and_backfills():
    items = [
        {"url": "u1", "title": "A", "summary": "s", "source": "S", "category": "platform"},
        {"url": "u2", "title": "B", "summary": "s", "source": "S", "category": "logistics"},
        {"url": "u3", "title": "B2 同一事件", "summary": "s", "source": "S2", "category": "logistics"},
        {"url": "u4", "title": "C 漏分", "summary": "s", "source": "S", "category": "market"},
    ]

    def fake_chat(prompt, token, max_tokens=2000):
        return {
            "groups": {"platform": [1], "logistics": [2], "compliance": [], "market": []},
            "merged": [[2, 3]],
        }

    groups = summarizer.group_items(items, "tok", chat=fake_chat)
    assert [it["url"] for it in groups["platform"]] == ["u1"]
    assert [it["url"] for it in groups["logistics"]] == ["u2"]  # u3 因 merged 被合并丢弃
    assert [it["url"] for it in groups["market"]] == ["u4"]     # AI 漏分时回退源 category


def test_group_items_degrades_on_ai_error():
    def fail_chat(prompt, token, max_tokens=2000):
        raise summarizer.AIError("boom")

    items = [{"url": "u1", "title": "A", "summary": "", "source": "S", "category": "compliance"}]
    groups = summarizer.group_items(items, "tok", chat=fail_chat)
    assert [it["url"] for it in groups["compliance"]] == ["u1"]


def test_group_by_category_routes_unknown_category_to_market():
    items = [{"url": "u1", "title": "A", "summary": "", "source": "S", "category": "weird"}]
    groups = summarizer.group_by_category(items)
    assert [it["url"] for it in groups["market"]] == ["u1"]
    assert set(groups.keys()) == set(summarizer.CATEGORIES)


def test_group_items_backfill_routes_unknown_category_to_market():
    items = [{"url": "u1", "title": "A", "summary": "s", "source": "S", "category": "weird"}]

    def fake_chat(prompt, token, max_tokens=2000):
        return {"groups": {"platform": [], "logistics": [], "compliance": [], "market": []}, "merged": []}

    groups = summarizer.group_items(items, "tok", chat=fake_chat)
    assert [it["url"] for it in groups["market"]] == ["u1"]
    assert set(groups.keys()) == set(summarizer.CATEGORIES)


def test_summarize_batch_caps_summary_length():
    def fake_chat(prompt, token, max_tokens=2000):
        return {"results": [{"id": 1, "relevant": True, "importance": "normal", "summary": "长" * 2000}]}
    out = summarizer.summarize_batch(ITEMS[:1], "tok", chat=fake_chat)
    assert len(out[0]["summary"]) == 500
