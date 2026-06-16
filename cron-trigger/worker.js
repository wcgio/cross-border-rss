// Cloudflare Worker：每天北京时间 12:00（UTC 04:00）准点触发 GitHub workflow。
// GitHub 自带 cron 在整点常被延迟数分钟到数小时甚至丢弃，Cloudflare Cron Trigger 准时得多。
// GH_TOKEN 为细粒度 PAT（仅 cross-border-rss 仓库、Actions 读写），存为 Worker secret，不入仓库。

const DISPATCH_URL =
  "https://api.github.com/repos/wcgio/cross-border-rss/actions/workflows/digest.yml/dispatches";

export default {
  async scheduled(event, env, ctx) {
    const resp = await fetch(DISPATCH_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "cross-border-rss-cron",
      },
      body: JSON.stringify({ ref: "main" }),
    });
    if (!resp.ok) {
      // 抛错会记入 Worker 日志（Cloudflare 控制台可见），便于排查；不含 token
      throw new Error(`workflow dispatch 失败：HTTP ${resp.status} ${await resp.text()}`);
    }
  },
};
