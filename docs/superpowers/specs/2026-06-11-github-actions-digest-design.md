# 设计：GitHub Actions 全托管跨境资讯日报

日期：2026-06-11
状态：已与用户确认

## 背景与目标

现有项目是一套基于 NAS 的 docker 栈（RSSHub + FreshRSS + feedmaker + digest），但用户没有 NAS 在实际运行。目标：**零成本、零服务器**，推送到 GitHub 后每天自动产出跨境电商/国际物流日报。

用户确认的关键决策：

| 决策点 | 选择 |
|---|---|
| 运行模式 | GitHub Actions 全托管（docker 栈退役） |
| 阅读形态 | 手机 RSS 阅读器 + 网页日报 + Telegram 推送 |
| AI 摘要 | GitHub Models（免费，GITHUB_TOKEN 调用） |
| 关注方向 | 平台政策、国际物流/海运空运、关税与贸易合规、电商大盘 |
| 状态与发布 | 提交制：产物和去重状态 commit 回仓库 |
| 托管平台 | Cloudflare Pages（用户博客已占用 GitHub Pages；域名同在 Cloudflare，接入零摩擦，带宽不限量，国内可达性更好） |
| 访问域名 | `rss.cgio.qzz.io`（用户托管在 Cloudflare 的域名） |

仓库设为 public（用户选择：Actions 分钟数不限量、便于分享；Cloudflare Pages 本身也支持私有仓库，后续可随时转私有）。资讯内容本身公开，无敏感数据；凭据一律放 GitHub Secrets。

## 总体架构

单一 Python 管道 `pipeline.py`，GitHub Actions 定时触发（cron `0 23 * * *` UTC = 北京时间 07:00，另支持 `workflow_dispatch` 手动触发）：

```
sources.yml ──→ 抓取层 ──→ 处理层 ──→ 正文层 ──→ AI 层 ──→ 输出层 ──→ commit ──→ Cloudflare Pages / Telegram
```

1. **抓取层**：`type: rss` 的源用 feedparser 解析；`type: scrape` 的源复用现有 app.py 的「URL 正则提取」逻辑（抗改版，不依赖 CSS class）
2. **处理层**：每源 include/exclude 关键词过滤 → `data/seen.json` 跨天去重（保留 7 天窗口，自动清理过期条目）
3. **正文层**：每条资讯获取正文用于 AI 总结。优先级：feed 自带 `content`/`description`（足够长则直接用）→ 抓文章页用 trafilatura 提取正文 → 都失败则仅标题。正文截断至前 2000 字符控制 token 用量
4. **AI 层**：GitHub Models 两段式调用——先分批（每批 8-10 篇）把每篇正文压成核心总结，再单次调用完成剔除无关、跨源合并、四主题分组与排序，输出 JSON
5. **输出层**：`docs/digest.xml`（RSS，每天一条富 HTML entry，按日 guid 去重）、`docs/index.html`（最新日报 + 历史归档入口）、`docs/archive/YYYY-MM-DD.html`（每日存档）
6. **发布**：workflow 把 `docs/` 与 `data/seen.json` commit 回主分支，Cloudflare Pages 通过 Git 集成监听 main 分支自动发布（构建命令留空，输出目录 `docs/`），绑定自定义域 `rss.cgio.qzz.io`；随后 Telegram bot 推送（超长自动分多条消息）+ 网页链接。推送目标由 `TG_CHAT_ID` 决定：填用户 chat ID 推私聊，填频道 `@用户名` 或 `-100` 开头 ID 推频道（bot 需为频道管理员并有发帖权限）——推荐建专用频道，日报按天沉淀、可拉人订阅

**每条资讯的呈现 = 标题 + 来源 + 分级核心总结 + 原文链接**。总结目标是读完即掌握核心内容（发生了什么、关键数字/政策变动、对卖家的影响），原文链接仅备查，不是必读。三个通道（RSS entry、网页、Telegram）展示同一份分组总结，网页版按四主题分栏、组内重要在前。

## 模块边界

| 模块 | 职责 | 输入 → 输出 |
|---|---|---|
| `fetcher.py` | 抓单个源 | 源配置 → 条目列表 `[{url, title, source, category, pub, feed_content}]` |
| `filters.py` | 关键词过滤 + seen 去重 | 条目列表 + seen 集合 → 过滤后列表 |
| `extractor.py` | 获取每条资讯的正文 | 条目 → 条目 + `text`（feed 内容 / trafilatura 提取 / 空） |
| `summarizer.py` | GitHub Models 两段式调用与降级 | 条目列表（含正文）→ 分组结构 `{category: [{title, summary, importance, url, source}]}` |
| `render.py` | RSS / HTML 渲染 | 分组结构 + 条目 → digest.xml / html 字符串 |
| `notify.py` | Telegram 推送 + Gotify 故障通知 | 分组结构 → bot API 调用；异常信息 → Gotify message API |
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
- **两段式调用**：
  1. *逐篇总结（map）*：每批 8-10 篇正文一次调用（全天约 6-8 次），每篇输出中文核心总结 + 重要性分级。**分级标准**：重大政策/费用/关税变动等高影响资讯给 3-4 句详细总结（含关键数字、生效时间、对卖家的影响）；一般资讯 1-2 句。同时剔除与跨境电商/外贸/国际物流无关的条目
  2. *分组排序（reduce）*：单次调用，输入各篇总结，完成同一事件跨源合并、四主题分组、组内按重要性排序，输出 JSON
- 输出经 JSON 解析校验；解析失败重试一次，仍失败则**降级**：跳过该批/该步，map 失败的条目退回标题展示，reduce 失败则按源 `category` 归类，日报照常生成

## 错误处理

| 故障 | 行为 |
|---|---|
| 单源抓取失败 | 跳过，记录到「源异常」小节，不阻塞 |
| 单篇正文提取失败 | 降级链：feed 自带摘要 → 仅标题（标注「仅标题」），不阻塞 |
| AI 调用/解析失败 | 重试一次后降级（map 失败退回标题，reduce 失败按源 category 归类） |
| Telegram 推送失败 | 仅打日志，不影响网页发布 |
| 全部源失败 | 仍生成日报，标题标注「今日抓取异常」 |
| 程序崩溃（未处理异常） | Gotify 故障通知（见下），随后非 0 退出 |
| workflow 本身失败 | Gotify 兜底通知 + GitHub 默认邮件通知 |

### 崩溃通知（Gotify）

程序崩溃或 workflow 失败时，推送异常位置与报错信息到用户自托管的 Gotify 服务，两层兜底：

1. **程序内**：`pipeline.py` 顶层 try/except 捕获未处理异常，提取异常类型、出错位置（文件、行号、函数）与报错信息，POST 到 `{GOTIFY_URL}/message?token={GOTIFY_TOKEN}`（高优先级），然后以非 0 退出。通知内容只含 traceback 摘要，**不得包含任何凭据或环境变量值**。
2. **workflow 层**：日报 job 末尾加 `if: failure()` 兜底 step，用 curl 推送「workflow 失败 + run 链接」，覆盖 Python 启动前的故障（依赖安装失败等）。

Gotify 推送自身失败时仅打日志，不掩盖原始异常（原始 traceback 仍输出到 Actions 日志）。

## 测试

- pytest 单测覆盖纯函数：URL 正则提取（雨果/亿邦真实 HTML 片段 fixture）、关键词过滤、seen 去重与过期清理、正文降级链（feed 内容→提取→仅标题）、RSS/HTML 渲染、AI 返回 JSON 的解析与降级路径
- 网络与 AI 调用一律 mock，测试不出网
- CI：workflow 含 test job，日报 job 依赖其通过
- 手动验证：`workflow_dispatch` 触发一次全流程，检查 `rss.cgio.qzz.io` 上三类产物（首页/归档/digest.xml）与 Telegram 推送

## 仓库整理与迁移

- `git init`，建 GitHub 公开仓库，推送
- 现有 docker 栈文件（docker-compose.yml、crossborder-feeds.tar.gz、app.py、digest.py、sites.yml、.env.example）移入 `legacy/` 归档，不删除（app.py 的提取逻辑与 sites.yml 配置会被新代码复用/迁移）
- 重写 README 与 CLAUDE.md，反映新架构
- GitHub 仓库 Settings：配置 Secrets（`TG_BOT_TOKEN`、`TG_CHAT_ID`、`GOTIFY_URL`、`GOTIFY_TOKEN`）
- Cloudflare 控制台：创建 Pages 项目 → Git 集成绑定本仓库（构建命令留空、输出目录 `docs/`）→ 自定义域绑定 `rss.cgio.qzz.io`
- 以上需用户在网页操作的步骤会在实施计划中单独列出
- 安全注意：Gotify token 曾在对话中明文出现，建议配置完 Secrets 后在 Gotify 后台轮换一次 token，再把新值填入 Secrets

## 非目标（YAGNI）

- 不做企业微信推送（用户未选）
- 不做代理池/反爬对抗（先观察首跑结果）
- 不保留 FreshRSS 已读同步（全托管模式的已知取舍，用户已确认）
