# cross-border-rss

零服务器的跨境电商 / 国际物流资讯日报。GitHub Actions 每天北京时间 12:00 运行，只收录近 24 小时发布的资讯：
抓取各源 → 过滤去重 → 正文提取 → AI 分级总结（GitHub Models，免费）→ 发布到
Cloudflare Pages → Telegram 推送。崩溃时 Gotify 通知。

## 访问

- 网页日报：https://rss.cgio.qzz.io/
- RSS 订阅：https://rss.cgio.qzz.io/digest.xml
- 历史归档：https://rss.cgio.qzz.io/archive/YYYY-MM-DD.html
- Telegram：bot 每天推送到频道

> GitHub 定时任务可能比 12:00 晚数分钟到半小时，属正常现象。

## 新增资讯源

编辑 `sources.yml`：有 RSS 的站填 `name/type: rss/url/category` 四项；没有 RSS 的站用
`type: scrape`，照已有条目填 `base_url` 和 `link_pattern`（文章 URL 的正则）。提交即生效。

## 配置（GitHub Secrets）

| Secret | 用途 |
|---|---|
| `TG_BOT_TOKEN` | Telegram bot token（@BotFather 创建） |
| `TG_CHAT_ID` | 推送目标：频道 `@用户名` 或 `-100` 开头 ID |
| `GOTIFY_URL` | Gotify 服务地址 |
| `GOTIFY_TOKEN` | Gotify 应用 token |

AI 总结使用 GitHub Models，workflow 内置 `GITHUB_TOKEN` 即可调用，无需额外配置。

## 本地开发

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q                # 测试不出网，网络/AI 全部 mock
GITHUB_TOKEN=<pat> .venv/bin/python -m src.pipeline   # 本地跑一次管道
```

`legacy/` 是退役的 NAS docker 栈（RSSHub + FreshRSS 方案），仅作归档。
