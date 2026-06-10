# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

自托管的跨境电商 / 国际物流资讯管道：

```
来源站点 → RSSHub / feedmaker（转 RSS）→ FreshRSS（聚合+过滤）→ 手机 RSS App + 每日日报
```

## ⚠️ 目录结构注意

**当前目录是扁平化副本，不是可直接部署的结构。** 完整部署结构在 `crossborder-feeds.tar.gz` 中：

```
crossborder-feeds/
├── docker-compose.yml
├── feeds.opml                # FreshRSS 预填订阅源
├── feedmaker/                # app.py、digest.py、sites.yml、Dockerfile、requirements.txt
└── push/                     # push.py、.env.example
```

`docker-compose.yml` 引用 `./feedmaker/`（build 上下文）和 `./push/.env`（env_file），在当前扁平目录下无法直接 `docker compose up`。修改代码后如需同步到部署包，记得保持两边一致。

## 常用命令

```bash
# 启动整个栈（需在 crossborder-feeds/ 完整结构下）
docker compose up -d --build

# 修改 sites.yml 后生效（挂载热改，无需重新 build）
docker compose restart feedmaker

# 手动生成一次每日日报（digest 服务在 "tools" profile，默认不随 up 启动）
docker compose run --rm digest

# 生产环境：宿主机 cron，北京时间每天 07:00 生成日报
# 0 7 * * *  cd /path/to/crossborder-feeds && docker compose run --rm digest >> digest.log 2>&1
```

无测试套件、无 linter 配置。

## 架构

四个容器（docker-compose.yml）：

- **rsshub**（:1200）+ **redis**：通用站点转 RSS，内置上千路由
- **feedmaker**（:8000，Flask，[app.py](app.py)）：把无 RSS 的中文站列表页转成 RSS
- **freshrss**（:8080）：聚合器，每 30 分钟刷新（`CRON_MIN`），同时通过 Google Reader API 给 digest/push 提供数据
- **digest**（一次性任务，[digest.py](digest.py)）：从 FreshRSS API 拉过去 24h 条目 → 关键词过滤 → 可选 AI 摘要 → 写出 `data/digest/digest.xml`，feedmaker 在 `/digest.xml` 对外提供

数据流关键点：digest **不直接抓源站**，只消费 FreshRSS 聚合结果；feedmaker 与 digest 共用同一个镜像，通过 `./data/digest` 共享卷衔接（feedmaker 只读挂载，digest 可写）。

### feedmaker 设计原则

- 提取文章靠 **URL 正则**（`link_pattern`），不靠 CSS class——抗站点改版。新增站点只改 [sites.yml](sites.yml)，不改代码。
- 抓取带 10 分钟内存缓存（`FEEDMAKER_CACHE_TTL`）；抓取失败回退旧缓存，避免阅读器报错。
- `title_strip_time: true` 处理标题尾部带 `2026-06-08 15:56:01` 时间戳的站点，剥离后用作发布时间。

### 三层关键词过滤（分工明确，改动时别混淆）

1. **sites.yml** 的 `include`/`exclude`——只作用于 feedmaker 抓的源
2. **FreshRSS** 的 `intitle:` 过滤规则——作用于原生 RSS 源（36氪、The Loadstar 等）
3. **`.env`** 的 `KEYWORDS_INCLUDE`/`KEYWORDS_EXCLUDE` + AI 摘要剔除——digest 阶段，统一作用于聚合结果

### 时区约定

全栈固定 `Asia/Shanghai`（UTC+8），代码里硬编码为 `dt.timezone(dt.timedelta(hours=8))`。日报回看窗口 `DIGEST_LOOKBACK_HOURS=24` 配合 07:00 cron，滚动窗口不受国外夏令时影响。改动时间相关逻辑时保持这个约定。

## 配置

- 运行时密钥在 `push/.env`（从 [.env.example](.env.example) 复制），digest 容器和 push.py 共用
- AI 摘要可选：`AI_API_URL` 含 `anthropic` 时走 Anthropic Messages API 格式，否则走 OpenAI 兼容格式（[digest.py](digest.py) 的 `ai_summary_html`）；失败时降级为纯标题列表，不中断日报生成
- 容器内访问 FreshRSS 用服务名 `http://freshrss`，宿主机运行 push.py 时改 `http://localhost:8080`
