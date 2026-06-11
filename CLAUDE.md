# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

零服务器的跨境电商/国际物流资讯日报管道，GitHub Actions 每天 UTC 23:00（北京时间 07:00）运行：

```
sources.yml → fetcher（抓源）→ filters（关键词过滤 + seen.json 跨天去重）
→ extractor（正文降级链）→ summarizer（GitHub Models map/reduce 分级总结）
→ render（digest.xml + index.html + archive/）→ commit 回仓库
→ Cloudflare Pages 自动发布（https://rss.cgio.qzz.io）→ Telegram 推送
崩溃 → Gotify 通知（src/pipeline.py main 的顶层捕获 + workflow 的 if: failure() 兜底）
```

设计文档：`docs/superpowers/specs/2026-06-11-github-actions-digest-design.md`

## 常用命令

```bash
source .venv/bin/activate
pytest -q                                  # 全部测试（网络/AI 全 mock，不出网）
pytest tests/test_fetcher.py -v            # 单文件
pytest tests/test_filters.py::test_dedup_unseen -v   # 单测试
python -m src.pipeline                     # 本地跑管道（需 GITHUB_TOKEN；TG/Gotify 凭据缺省时跳过推送）
```

## 架构要点

- **降级保日报**：单源失败记「源异常」小节；单篇正文失败退回 feed 摘要再退回仅标题；AI map 失败该批退回标题、reduce 失败按源 category 归类——任何故障都不应阻止日报生成，改动时维持这一不变量
- **`data/seen.json` 是跨天去重状态**，由 workflow commit 维护；删除它会导致次日日报重复
- **scrape 源用 URL 正则提链接**（抗改版，不依赖 CSS class），新增源只改 `sources.yml` 不改代码
- **时区硬编码北京时间**（`TZ8 = UTC+8`），日报按日 guid 去重，每天恰好一条 RSS entry
- summarizer 的 prompt 模板含 JSON 大括号，用 `.replace()` 填充而非 `.format()`
- 未知 category 一律归入 market（summarizer 两处显式成员检查），防止条目被渲染层静默丢弃
- `docs/` 是 Cloudflare Pages 发布根目录（构建命令留空）；spec/plan 文档也在其下，会一并公开，属预期行为
- `legacy/` 是退役的 NAS docker 栈，仅作参考，勿在其上开发

## 凭据

全部在 GitHub Secrets（`TG_BOT_TOKEN`、`TG_CHAT_ID`、`GOTIFY_URL`、`GOTIFY_TOKEN`），代码只读环境变量。
错误路径不得携带凭据：Telegram 失败抛 RuntimeError 只含状态码与响应文本（不含 URL/token）；Gotify 崩溃通知只含 traceback 摘要。
