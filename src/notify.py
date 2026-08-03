"""Telegram 日报推送与 Gotify 故障通知。凭据缺失时跳过而不报错。"""
import os

import requests

TG_LIMIT = 4000  # Telegram 单条上限 4096，留余量


def telegram_messages(groups, categories, date_str, site_url):
    """把分组总结编排成若干条不超长的消息文本（纯函数）。"""
    blocks = [f"📰 跨境/物流日报 {date_str}"]
    for key, label in categories.items():
        items = groups.get(key) or []
        if not items:
            continue
        blocks.append(f"\n—— {label} ——")
        for it in items:
            mark = "🔴" if it.get("importance") == "high" else "•"
            text = f"{mark} {it['title']}"
            if it.get("summary"):
                text += f"\n{it['summary']}"
            text += f"\n{it['url']}"
            blocks.append(text[:TG_LIMIT - 50])
    blocks.append(f"\n网页版：{site_url}/archive/{date_str}")

    msgs, cur = [], ""
    for block in blocks:
        if cur and len(cur) + len(block) + 1 > TG_LIMIT:
            msgs.append(cur)
            cur = block
        else:
            cur = f"{cur}\n{block}" if cur else block
    if cur:
        msgs.append(cur)
    return msgs


def send_telegram(messages):
    token = os.environ.get("TG_BOT_TOKEN")
    chat_id = os.environ.get("TG_CHAT_ID")
    if not (token and chat_id):
        print("[warn] TG 凭据未配置，跳过推送")
        return
    for msg in messages:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "disable_web_page_preview": True},
            timeout=30,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Telegram sendMessage 失败：HTTP {r.status_code} {r.text[:200]}")


def send_gotify(title, message):
    """故障通知。自身失败只打日志，绝不掩盖原始异常。"""
    url = os.environ.get("GOTIFY_URL")
    token = os.environ.get("GOTIFY_TOKEN")
    if not (url and token):
        print("[warn] Gotify 凭据未配置，跳过故障通知")
        return
    try:
        requests.post(
            f"{url.rstrip('/')}/message",
            params={"token": token},
            json={"title": title, "message": message, "priority": 8},
            timeout=20,
        )
    except requests.RequestException as e:
        print(f"[warn] Gotify 推送失败（{title!r}）：{e}")
