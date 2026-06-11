"""GitHub Models 两段式总结：map（逐篇分级总结）→ reduce（跨源合并 + 四主题分组排序）。"""
import json
import os

import requests

API_URL = os.environ.get("GH_MODELS_URL", "https://models.github.ai/inference/chat/completions")
MODEL = os.environ.get("GH_MODELS_MODEL", "openai/gpt-4o-mini")
BATCH_SIZE = 9
CATEGORIES = {
    "platform": "平台政策",
    "logistics": "国际物流",
    "compliance": "关税合规",
    "market": "大盘趋势",
}


class AIError(Exception):
    """AI 调用或返回解析失败（已重试过）。"""


def _chat(prompt, token, max_tokens=2000):
    r = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _chat_json(prompt, token, max_tokens=2000):
    last = None
    for _ in range(2):  # 失败重试一次
        try:
            return json.loads(_chat(prompt, token, max_tokens))
        except (json.JSONDecodeError, KeyError, IndexError, requests.RequestException) as e:
            last = e
    raise AIError(str(last))


MAP_PROMPT = """你是跨境电商行业资讯编辑。下面有 {n} 篇文章（编号、标题、正文节选）。\
对每篇输出一个 JSON 对象，整体输出格式：
{"results": [{"id": 1, "relevant": true, "importance": "high", "summary": "..."}]}
规则：
- 与跨境电商/外贸/国际物流无关的条目 relevant 设为 false，不写 summary
- importance 取 "high" 或 "normal"，默认 normal。high 的门槛很高：仅限卖家当天必须知晓、\
直接影响其收入/成本/合规的确定性重大变动（平台费用佣金调整、政策生效、关税变化、运价剧烈波动），\
每批最多标 1-2 条 high，行业观察/数据报告/公司动态一律 normal，拿不准就 normal
- high 的 summary 写 3-4 句（必须包含关键数字、生效时间、对卖家的影响）；normal 的 summary 写 1-2 句
- summary 用中文，直接陈述事实，不写"本文""文章称"
- 正文标注"（无正文，仅标题）"的条目按标题判断，summary 留空字符串

文章列表：
{articles}"""


def summarize_batch(items, token, chat=_chat_json):
    """map 阶段：一批条目 → 各自带 summary/importance；relevant=false 的被剔除。"""
    articles = "\n\n".join(
        f"[{i + 1}] 标题：{it['title']}\n正文：{it['text'] or '（无正文，仅标题）'}"
        for i, it in enumerate(items)
    )
    prompt = MAP_PROMPT.replace("{n}", str(len(items))).replace("{articles}", articles)
    data = chat(prompt, token)
    by_id = {r.get("id"): r for r in data.get("results", []) if isinstance(r, dict)}
    out = []
    for i, it in enumerate(items):
        r = by_id.get(i + 1)
        if r is None:
            out.append({**it, "summary": "", "importance": "normal"})
        elif not r.get("relevant", True):
            continue
        else:
            out.append({
                **it,
                "summary": (r.get("summary") or "").strip()[:500],
                "importance": r.get("importance") if r.get("importance") in ("high", "normal") else "normal",
            })
    return out


REDUCE_PROMPT = """下面是今日跨境电商/国际物流资讯各篇的总结（带编号）。输出 JSON：
{"groups": {"platform": [编号...], "logistics": [...], "compliance": [...], "market": [...]}, "merged": [[编号,编号], ...]}
规则：
- 把每个编号分到且只分到一组：platform=平台政策, logistics=国际物流, compliance=关税合规, market=大盘趋势
- 每组内按重要性从高到低排列
- 报道同一事件的多篇放入 merged（信息最全的编号放在最前，后面的会被合并丢弃）

条目：
{entries}"""


def _sort_high_first(result):
    """组内重点在前（稳定排序，各档内保持原相对顺序）。AI 的排序不可靠，代码兜底。"""
    return {k: sorted(v, key=lambda it: it.get("importance") != "high") for k, v in result.items()}


def group_by_category(items):
    """降级路径：按源配置的 category 归类，不调 AI。"""
    result = {key: [] for key in CATEGORIES}
    for it in items:
        cat = it.get("category") if it.get("category") in CATEGORIES else "market"
        result[cat].append(it)
    return _sort_high_first(result)


def group_items(items, token, chat=_chat_json):
    """reduce 阶段：四主题分组 + 组内排序 + 同事件合并；AI 失败降级为 category 归类。"""
    entries = "\n".join(
        f"[{i + 1}] ({it['source']}) {it['title']}：{it['summary'] or '仅标题'}"
        for i, it in enumerate(items)
    )
    try:
        data = chat(REDUCE_PROMPT.replace("{entries}", entries), token, max_tokens=1500)
        groups = data["groups"]
        drop = set()
        for pair in data.get("merged", []):
            if isinstance(pair, list):
                drop.update(pair[1:])
        result, used = {key: [] for key in CATEGORIES}, set()
        for key in CATEGORIES:
            for i in groups.get(key, []):
                if isinstance(i, int) and 1 <= i <= len(items) and i not in drop and i not in used:
                    used.add(i)
                    result[key].append(items[i - 1])
        for i, it in enumerate(items, 1):  # AI 漏分的条目回退源 category
            if i not in used and i not in drop:
                cat = it.get("category") if it.get("category") in CATEGORIES else "market"
                result[cat].append(it)
        return _sort_high_first(result)
    except (AIError, KeyError, TypeError, AttributeError):
        return group_by_category(items)
