# 日报聚焦 Amazon/eBay/Etsy 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把日报的 AI 关注焦点与源结构校准到「Amazon/eBay/Etsy 卖家、美欧市场」，无关平台资讯降级保留。

**Architecture:** 只动两层——summarizer 的两个 prompt 模板（编辑视角、重点判定、分组规则）和 sources.yml（补两个 eBay/Etsy/欧洲源 + 关键词微调）。分类体系、渲染、管道逻辑全部不动。

**Tech Stack:** 现有 Python 管道（无新依赖）。

**Spec:** `docs/superpowers/specs/2026-06-11-amazon-ebay-etsy-refocus-design.md`

---

### Task 1: summarizer prompt 聚焦三平台

**Files:**
- Modify: `src/summarizer.py`（MAP_PROMPT、REDUCE_PROMPT 两处字符串）
- Test: `tests/test_summarizer.py`

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_summarizer.py`）

```python
def test_map_prompt_focuses_on_user_platforms():
    for kw in ("Amazon", "eBay", "Etsy", "美国与欧洲"):
        assert kw in summarizer.MAP_PROMPT
    assert "Temu" in summarizer.MAP_PROMPT          # 无关平台显式降级
    assert "一律 normal" in summarizer.MAP_PROMPT


def test_reduce_prompt_routes_other_platforms_to_market():
    assert "归 market" in summarizer.REDUCE_PROMPT
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_summarizer.py -v`
Expected: 新增 2 个测试 FAIL（断言不命中），原有测试 PASS

- [ ] **Step 3: 修改 MAP_PROMPT**

整体替换 `src/summarizer.py` 中的 `MAP_PROMPT` 为：

```python
MAP_PROMPT = """你是资讯编辑，为一位主营 Amazon、eBay、Etsy、面向美国与欧洲市场的跨境电商卖家筛选资讯。\
下面有 {n} 篇文章（编号、标题、正文节选）。对每篇输出一个 JSON 对象，整体输出格式：
{"results": [{"id": 1, "relevant": true, "importance": "high", "summary": "..."}]}
规则：
- 与跨境电商/外贸/国际物流无关的条目 relevant 设为 false，不写 summary
- importance 取 "high" 或 "normal"，默认 normal。high 的门槛很高：仅限直接影响 Amazon/eBay/Etsy \
卖家收入/成本/合规的确定性重大变动（三平台的费用佣金调整、政策生效、账号合规新规），\
或美欧关税、海运运价、平台监管的重大政策，每批最多标 1-2 条 high
- 其他平台（Temu、TikTok Shop、沃尔玛、Shein 等）的资讯一律 normal，作为行业背景保留即可
- 行业观察/数据报告/公司动态一律 normal，拿不准就 normal
- high 的 summary 写 3-4 句（必须包含关键数字、生效时间、对卖家的影响）；normal 的 summary 写 1-2 句
- summary 用中文，直接陈述事实，不写"本文""文章称"
- 正文标注"（无正文，仅标题）"的条目按标题判断，summary 留空字符串

文章列表：
{articles}"""
```

- [ ] **Step 4: 修改 REDUCE_PROMPT 的规则段**

把 REDUCE_PROMPT 中的规则部分替换为（其余不变）：

```python
REDUCE_PROMPT = """下面是今日跨境电商/国际物流资讯各篇的总结（带编号）。输出 JSON：
{"groups": {"platform": [编号...], "logistics": [...], "compliance": [...], "market": [...]}, "merged": [[编号,编号], ...]}
规则：
- 把每个编号分到且只分到一组：platform=平台政策, logistics=国际物流, compliance=关税合规, market=大盘趋势
- platform 组只收 Amazon/eBay/Etsy 及行业通用的平台政策；其他平台（Temu、TikTok Shop、沃尔玛、Shein 等）的动态归 market
- 每组内按重要性从高到低排列
- 报道同一事件的多篇放入 merged（信息最全的编号放在最前，后面的会被合并丢弃）

条目：
{entries}"""
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/pytest -q`
Expected: 全部通过（52 个测试）

- [ ] **Step 6: Commit**

```bash
git add src/summarizer.py tests/test_summarizer.py
git commit -m "feat: focus ai prompts on amazon/ebay/etsy sellers in us-eu markets"
```

---

### Task 2: sources.yml 补源与关键词微调

**Files:**
- Modify: `sources.yml`

- [ ] **Step 1: 新增两个 platform 源**

在 platform 段（亿邦条目之后）插入：

```yaml
  - name: "ChannelX（欧洲电商/eBay）"
    type: rss
    url: "https://channelx.world/feed/"
    category: platform

  - name: "Value Added Resource（eBay/Etsy）"
    type: rss
    url: "https://www.valueaddedresource.net/rss/"
    category: platform
```

- [ ] **Step 2: 36氪关键词追加 + KTN 占位扩展**

36氪条目的 include 改为：

```yaml
    include: ["跨境", "出海", "亚马逊", "eBay", "Etsy", "欧盟", "VAT", "Temu", "TikTok", "Shein", "关税", "物流", "海运"]
```

KTN 占位注释改为：

```yaml
  # 预留：卖家通知邮件转 RSS（Kill the Newsletter 生成后取消注释填入）
  # Amazon/eBay/Etsy 三平台的卖家通知邮件均可各转一个源
  # - name: "Amazon 卖家通知"
  #   type: rss
  #   url: "https://kill-the-newsletter.com/feeds/XXXX.xml"
  #   category: platform
```

- [ ] **Step 3: 联网核实两个新源**

```bash
.venv/bin/python - <<'EOF'
import yaml
from src import fetcher
for s in yaml.safe_load(open("sources.yml"))["sources"]:
    if "ChannelX" in s["name"] or "Value Added" in s["name"]:
        items = fetcher.fetch_source(s)
        print(f"{s['name']}: {len(items)} items; first: {items[0]['title'][:50] if items else '—'}")
EOF
```

Expected: 两源均返回条目且标题正常。若 feed 地址失效：打开站点首页找 `type="application/rss+xml"` 的 link 标签换真实地址（ChannelX 原名 Tamebay，注意跳转后的域名）；确认无可用 feed 则删除该源并在 commit message 注明。

- [ ] **Step 4: YAML 校验 + 全量回归**

```bash
.venv/bin/python -c "import yaml; print(len(yaml.safe_load(open('sources.yml'))['sources']), 'sources ok')"
.venv/bin/pytest -q
```

Expected: 15 sources ok（13+2）；测试全绿。

- [ ] **Step 5: Commit**

```bash
git add sources.yml
git commit -m "feat: add channelx and value added resource, refocus keywords"
```

---

### Task 3: 推送并确认生效路径

**Files:** 无代码改动。

- [ ] **Step 1: 推送**

```bash
git push
```

- [ ] **Step 2: 确认无需立即重跑**

改动自次日 07:00 日报自动生效（prompt 与源在每次运行时读取）。不重置 `data/seen.json`、不手动触发——避免覆盖当日日报与 AI 限流（参见运维备忘：同日重跑两个坑）。

- [ ] **Step 3: 次日验收清单**（用户或下次会话核对）

- 新源 ChannelX / Value Added Resource 出现在来源标签栏
- 重点条目均为 Amazon/eBay/Etsy 或美欧关税物流合规主题
- Temu/TikTok Shop 等资讯出现在「大盘趋势」Tab 且无红色「重点」标

---

## 验收标准（对照 spec）

- [ ] MAP_PROMPT 含三平台与美欧市场视角，其他平台一律 normal
- [ ] REDUCE_PROMPT 将其他平台动态归 market
- [ ] sources.yml 新增 2 源且联网验证可用；36氪关键词与 KTN 注释更新
- [ ] 分类体系、渲染、管道逻辑零改动；全量测试绿
