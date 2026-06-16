# cron-trigger

每天北京时间 12:00 准点触发日报 workflow 的 Cloudflare Worker。

GitHub Actions 自带的 `schedule` cron 在整点排队高峰常被延迟数分钟到数小时、偶尔直接丢弃，
无法保证准点。改用 Cloudflare Worker 的 Cron Trigger（准时到分钟级）调 GitHub API 触发
`digest.yml` 的 `workflow_dispatch`。

## 部署（控制台方式，最简）

1. **建 GitHub 细粒度 token**：GitHub → Settings → Developer settings → Fine-grained tokens →
   Generate new token。Repository access 选 **仅 `cross-border-rss`**；Permissions →
   Repository permissions → **Actions: Read and write**（只勾这一项即可）。生成后复制 token。
2. **建 Worker**：Cloudflare 控制台 → Workers & Pages → Create → Worker，名字
   `cross-border-rss-cron`，把 `worker.js` 内容粘进去，Deploy。
3. **加 secret**：该 Worker → Settings → Variables and Secrets → 添加 **Secret** 类型变量
   `GH_TOKEN`，值粘上一步的 token，保存（加密存储，不可再次读出）。
4. **加 Cron Trigger**：该 Worker → Settings → Triggers → Cron Triggers → Add，填 `0 4 * * *`（UTC）。
5. **验证**：Worker 页面点 “Send” 触发一次 scheduled 事件，或等当天 12:00；到 GitHub Actions
   看是否出现一次 `daily-digest` run。

## 部署（wrangler CLI 方式）

```bash
cd cron-trigger
npx wrangler deploy
npx wrangler secret put GH_TOKEN   # 粘贴 token
```

cron 已在 `wrangler.toml` 声明，deploy 时自动注册。

## 安全

- token 只有触发本仓库 workflow 的权限，泄露影响面小；仍建议定期轮换。
- token 只存在 Worker secret 与 GitHub 后台，**不写入代码仓库、不输出到日志**。
