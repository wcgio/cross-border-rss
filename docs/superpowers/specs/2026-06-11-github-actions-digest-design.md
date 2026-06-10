# 设计：GitHub Actions 全托管跨境资讯日报

日期：2026-06-11
状态：已与用户确认

## 背景与目标

现有项目是一套基于 NAS 的 docker 栈（RSSHub + FreshRSS + feedmaker + digest），但用户没有 NAS 在实际运行。目标：**零成本、零服务器**，推送到 GitHub 后每天自动产出跨境电商/国际物流日报。

用户确认的关键决策：

| 决策点 | 选择 |
|---|---|
| 运行模式 | GitHub Actions 全托管（docker 栈退役） |
| 阅读形态 | 手机 RSS 阅读器 + GitHub Pages 网页 + Telegram 推送 |
| AI 摘要 | GitHub Models（免费，GITHUB_TOKEN 调用） |
| 关注方向 | 平台政策、国际物流/海运空运、关税与贸易合规、电商大盘 |
| 状态与发布 | 提交制：产物和去重状态 commit 回仓库，Pages 从分支发布 |

前提：GitHub 免费版 Pages 仅支持公开仓库，本仓库设为 public。资讯内容本身公开，无敏感数据；凭据一律放 GitHub Secrets。

## 总体架构

单一 Python 管道 `pipeline.py`，GitHub Actions 定时触发（cron `0 23 * * *` UTC = 北京时间 07:00，另支持 `workflow_dispatch` 手动触发）：

```
sources.yml ──→ 抓取层 ──→ 处理层 ──→ AI 层 ──→ 输出层 ──→ commit ──→ Pages / Telegram
```

1. **抓取层**：`type: rss` 的源用 feedparser 解析；`type: scrape` 的源复用现有 app.py 的「URL 正则提取」逻辑（抗改版，不依赖 CSS class）
2. **处理层**：每源 include/exclude 关键词过滤 → `data/seen.json` 跨天去重（保留 7 天窗口，自动清理过期条目）
3. **AI 层**：GitHub Models 单次调用完成剔除无关、跨源合并同一事件、四主题分组、每条一句话要点，输出 JSON
4. **输出层**：`docs/digest.xml`（RSS，每天一条富 HTML entry，按日 guid 去重）、`docs/index.html`（最新日报 + 历史归档入口）、`docs/archive/YYYY-MM-DD.html`（每日存档）
5. **发布**：workflow 把 `docs/` 与 `data/seen.json` commit 回主分支，Pages 从分支 `/docs` 目录发布；随后 Telegram bot 推送分组要点 + 网页链接

## 模块边界

| 模块 | 职责 | 输入 → 输出 |
|---|---|---|
| `fetcher.py` | 抓单个源 | 源配置 → 条目列表 `[{url, title, source, category, pub}]` |
| `filters.py` | 关键词过滤 + seen 去重 | 条目列表 + seen 集合 → 过滤后列表 |
| `summarizer.py` | GitHub Models 调用与降级 | 条目列表 → 分组结构 `{category: [{point, urls}]}` |
| `render.py` | RSS / HTML 渲染 | 分组结构 + 条目 → digest.xml / html 字符串 |
| `notify.py` | Telegram 推送 | 分组结构 → bot API 调用 |
| `pipeline.py` | 编排以上各步 | sources.yml → 落盘产物 |

各模块为纯函数优先（网络 IO 集中在 fetcher / summarizer / notify），便于单测。

## 渠道源（sources.yml）

每源字段：`name`、`type`（rss/scrape）、`url`、`category`（platform/logistics/compliance/market，作为 AI 分组提示与降级归类依据）、可选 `include`/`exclude`、scrape 源另有 `base_url`/`link_pattern`/`title_strip_time`/`encoding`。

初始源清单：

- **platform 平台政策**：Marketplace Pulse（rss）、EcommerceBytes（rss）、雨果跨境·平台资讯（scrape，迁移现有配置）、亿邦·跨境（scrape，迁移现有配置）；预留 Kill the Newsletter 占位注释——用户将亚马逊/TikTok Shop 卖家通知邮件转 RSS 后填入，补一手政策时效
- **logistics 国际物流**：The Loadstar（rss）、FreightWaves（rss）、Splash247（rss）、gCaptain（rss）
- **compliance 关税合规**：USTR press releases（rss）、海关总署发布（scrape）
- **market 大盘趋势**：Modern Retail（rss）、Retail Dive（rss）、36氪（rss，配出海/跨境关键词 include 过滤）

实施时需逐一核实各源真实 feed 地址（部分英文媒体 feed 地址常变更），失效的标注后跳过。

**反爬风险**：GitHub 海外 IP 抓国内站（雨果/亿邦/海关总署）可能被拦截。策略：带浏览器 UA + 合理超时 + 单源失败不阻塞，失败源记入日报尾部「源异常」小节。首跑后观察，确认被封再考虑公共 RSSHub 实例兜底或换源——不提前过度设计。

## AI 摘要（GitHub Models）

- 端点：`https://models.github.ai/inference/chat/completions`（OpenAI 兼容）
- 鉴权：workflow 中 `permissions: models: read`，用 `GITHUB_TOKEN`，无需额外 key
- 模型：`openai/gpt-4o-mini`（免费额度内；模型 ID 可经环境变量覆盖）
- Prompt 要求输出 JSON：剔除与跨境电商/外贸/国际物流无关的条目 → 同一事件多源合并 → 按四主题分组 → 每条一句中文要点并引用原文条目索引
- 输出经 JSON 解析校验；解析失败重试一次，仍失败则**降级**：按源 `category` 归类输出纯标题列表，日报照常生成

## 错误处理

| 故障 | 行为 |
|---|---|
| 单源抓取失败 | 跳过，记录到「源异常」小节，不阻塞 |
| AI 调用/解析失败 | 重试一次后降级为关键词归类列表 |
| Telegram 推送失败 | 仅打日志，不影响 Pages 发布 |
| 全部源失败 | 仍生成日报，标题标注「今日抓取异常」 |
| workflow 本身失败 | GitHub 默认邮件通知 |

## 测试

- pytest 单测覆盖纯函数：URL 正则提取（雨果/亿邦真实 HTML 片段 fixture）、关键词过滤、seen 去重与过期清理、RSS/HTML 渲染、AI 返回 JSON 的解析与降级路径
- 网络与 AI 调用一律 mock，测试不出网
- CI：workflow 含 test job，日报 job 依赖其通过
- 手动验证：`workflow_dispatch` 触发一次全流程，检查 Pages 三类产物与 Telegram 推送

## 仓库整理与迁移

- `git init`，建 GitHub 公开仓库，推送
- 现有 docker 栈文件（docker-compose.yml、crossborder-feeds.tar.gz、app.py、digest.py、sites.yml、.env.example）移入 `legacy/` 归档，不删除（app.py 的提取逻辑与 sites.yml 配置会被新代码复用/迁移）
- 重写 README 与 CLAUDE.md，反映新架构
- 仓库 Settings：启用 Pages（分支 `/docs`）、配置 Secrets（`TG_BOT_TOKEN`、`TG_CHAT_ID`）——需用户在 GitHub 网页操作的步骤会在实施计划中单独列出

## 非目标（YAGNI）

- 不做全文抓取/正文提取（标题 + 链接 + AI 要点已满足日报场景）
- 不做企业微信推送（用户未选）
- 不做代理池/反爬对抗（先观察首跑结果）
- 不保留 FreshRSS 已读同步（全托管模式的已知取舍，用户已确认）
