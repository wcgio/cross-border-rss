# 跨境电商 & 国际物流资讯管道

一条自托管管道：**来源 → RSSHub / feedmaker（转 RSS）→ FreshRSS（聚合+过滤）→ 手机 RSS App 阅读 + 每日日报**。
按下面三步走，第一步十分钟内就能看到效果。

```
crossborder-feeds/
├── docker-compose.yml        # rsshub + redis + freshrss + feedmaker (+ digest 任务)
├── feeds.opml                # 预填的订阅源，FreshRSS 直接导入
├── feedmaker/                # 把雨果/亿邦等无 RSS 的站转成 RSS，并提供 /digest.xml
│   ├── app.py  digest.py  sites.yml  Dockerfile  requirements.txt
└── push/                     # 可选：Telegram/企业微信 推送 + 环境变量
    ├── push.py  .env.example
```

---

## 第一步：起主干（RSSHub + FreshRSS）

```bash
cd crossborder-feeds
docker compose up -d --build
```

启动后：

- FreshRSS：`http://<NAS_IP>:8080` —— 首次进去走安装向导，数据库选 **SQLite**（个人用够了，免单独数据库），建好管理员账号。
- RSSHub：`http://<NAS_IP>:1200` —— 看到欢迎页即正常。
- feedmaker：`http://<NAS_IP>:8000` —— 会列出 `/feed/cifnews`、`/feed/ebrun`，点开应能看到 RSS。

**导入订阅源**：FreshRSS 右上角 → 订阅管理 → 导入/导出 → 导入 `feeds.opml`。
导入的源里，`http://feedmaker:8000/...` 和 `36氪/The Loadstar` 等走的是容器内网/公网，FreshRSS 容器都能直接访问。

> 导入后若某个英文源标红报错，多半是该站改了 feed 地址（Supply Chain Dive / FreightWaves / Modern Retail 属于"较可能可用、需你确认"那档）。在浏览器里打开它官网搜 "RSS" 核对真实地址，改掉或删掉即可，不影响其它源。

---

## 第二步：补中文政策面（feedmaker）

雨果、亿邦没有官方 RSS，feedmaker 通过"按文章 URL 规律提取链接"来生成 RSS——比写死 CSS class 抗改版。两个源已在 `sites.yml` 配好并随栈启动。

**加新源**：编辑 `feedmaker/sites.yml`，复制一段改 4 个字段（name / list_url / base_url / link_pattern），然后 `docker compose restart feedmaker`。`link_pattern` 的取法：打开目标站列表页，看文章链接长什么样，例如雨果是 `/article/185800` → `"/article/\\d{4,}"`，亿邦是 `/677729.html` → `"/\\d{5,}\\.html"`。

`title_strip_time: true` 用于标题尾部带 `2026-06-08 15:56:01` 时间戳的站（如亿邦），会自动把它剥离并当作发布时间。

**三层过滤怎么分工**（解决「站点里不全是跨境内容」）：
1. *选对栏目*——已把 list_url 指向跨境栏目页（雨果 `/subject/news`、亿邦 `/label/6.html`），源头就基本对口。
2. *关键词*——feedmaker 抓的源在 `sites.yml` 里用 `include`/`exclude` 过滤标题；36氪、The Loadstar 这类走原生 RSS 的源，在 FreshRSS 里设过滤：订阅管理 → 选中该源 → 过滤 → 用 `intitle:` 规则把无关词自动标为已读（如 `intitle:招聘 OR intitle:recruiting`）。
3. *AI 兜底*——见第三步，生成日报时让模型剔除明显不相关的条目。

**RSSHub 路由**：除了 feedmaker，RSSHub 内置上千路由，可订阅 36氪各分类、微博、Telegram 频道、以及不少平台官方博客。用法是把 `https://rsshub.app/<路由>` 换成你自己的 `http://rsshub:1200/<路由>` 填进 FreshRSS。路由查询见 `https://docs.rsshub.app`。

---

## 第三步：手机上读 + 每日 7 点日报

**先开 API**：FreshRSS → 设置 → 身份验证 → 勾选「允许 API 访问」，设一个 **API 密码**。

### A. 手机 RSS App 直接读（推荐，全部已读同步）

把手机阅读器接到你的 FreshRSS，所有订阅源在手机上看、已读状态双向同步：
- iOS：Reeder、Fiery Feeds、NetNewsWire；安卓：FreshRSS 官方 App、Readrops；跨平台：Folo。
- 添加账户时选 **FreshRSS / Google Reader API**，地址填你经 Cloudflare/Lucky 暴露的 FreshRSS 域名（如 `https://rss.你的域名`），用户名 + 刚才的 API 密码。

### B. 每日「跨境/物流日报」（一条 RSS，早上 7 点更新）

`digest.py` 会把过去 24 小时的条目过滤 + 可选 AI 摘要，生成**每天一条**的日报，feedmaker 在 `/digest.xml` 提供，手机阅读器订阅它即可。

1. `cp push/.env.example push/.env`，填 FreshRSS 账号（容器内用 `FRESHRSS_URL=http://freshrss`）、关键词、可选 AI 端点。
2. 先手动生成一次：
   ```bash
   docker compose run --rm digest
   ```
   然后在手机阅读器里订阅 `https://rss.你的域名/digest.xml`（或内网 `http://<NAS_IP>:8000/digest.xml`）。
3. 加 cron，**北京时间每天 07:00** 生成当天日报：
   ```cron
   0 7 * * *  cd /path/to/crossborder-feeds && /usr/bin/docker compose run --rm digest >> digest.log 2>&1
   ```

### 时区如何处理（保证 7 点看到「最新」）

- FreshRSS 与各容器 TZ 已设 `Asia/Shanghai`，所有时间按北京时间显示；原生 feed 自带时区会被正确换算。
- FreshRSS 每 30 分钟刷新（compose 里 `CRON_MIN`），国外白天发的稿（你这边后半夜）天亮前已入库。
- 日报回看窗口 `DIGEST_LOOKBACK_HOURS=24`，cron 设在 07:00，昨天到今早凌晨的国外最新消息都会纳入。中国无夏令时，滚动 24h 窗口也不受国外夏令时切换影响。

### C. 可选：另发 Telegram / 企业微信

若还想要 IM 通知，`push/push.py` 可拉未读推到 Telegram/企业微信（从宿主机跑时把 `.env` 里 `FRESHRSS_URL` 改成 `http://localhost:8080`）。纯 RSS 阅读则不需要这步。

---

## 关于「官方平台政策」一手来源

亚马逊 Seller Central、TikTok Shop、Temu 的一手公告大多在登录态后台、无 RSS、反爬严，基本无法直接订阅。两条务实路径：

1. **二手媒体兜底**：雨果/亿邦通常当天就转述政策变动（费用、合规、回款、考核口径等），覆盖约九成，慢半天到一天。这步本管道已覆盖。
2. **官方邮件转 RSS**：把各平台卖家通知邮件用 *Kill the Newsletter* 之类邮件转 RSS 服务转成订阅源，再把生成的 feed 地址加进 FreshRSS，补一手时效。

---

## 配合你现有的网络栈

- 对外访问 FreshRSS 走 Cloudflare Tunnel / Lucky 反代到 `8080`，调试用的 `1200`、`8000` 端口跑通后可在 compose 里删掉，只保留容器内网互通，减少暴露面。
- `data/` 目录（FreshRSS 数据 + redis）建议并入你现有的备份策略。
- 抓取已带 10 分钟缓存 + 失败回退旧缓存，不会频繁打到源站；如需更温和可调大 `FEEDMAKER_CACHE_TTL`。
