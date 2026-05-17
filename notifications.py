"""
Unified notification dispatcher for the GCP Bot.
Supports Discord Webhook, Slack Webhook, and local stdout logging.
Configure channels via environment variables — only active channels fire.
"""

import os
import logging
import requests

logger = logging.getLogger("gcp-bot.notifications")

# --- Channel config (loaded from .env) ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

REQUEST_TIMEOUT = 5  # seconds


def send_alert(message: str, level: str = "info") -> None:
    """
    Send an alert to all configured notification channels.

    Args:
        message: The alert text (Markdown-friendly).
        level:   'info' | 'warning' | 'error' — used for emoji prefix if not already present.
    """
    # Prefix with level indicator if no emoji already present
    if not any(message.startswith(e) for e in ["🚨", "⚠️", "✅", "❌", "📊", "💤", "🧹", "📅", "🗂️", "📈", "🔴", "[DRY"]):
        prefix = {"error": "❌ ", "warning": "⚠️ "}.get(level, "")
        message = prefix + message

    logger.info("[notify] %s", message)

    if DISCORD_WEBHOOK_URL:
        _send_discord(message)

    if SLACK_WEBHOOK_URL:
        _send_slack(message)

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        _send_telegram(message)


# ---------------------------------------------------------------------------
# Channel Senders
# ---------------------------------------------------------------------------

def _send_discord(message: str) -> None:
    """
    Post to a Discord channel via Incoming Webhook.
    Splits messages longer than 2000 chars (Discord limit).
    """
    try:
        chunks = [message[i:i+1999] for i in range(0, len(message), 1999)]
        for chunk in chunks:
            resp = requests.post(
                DISCORD_WEBHOOK_URL,
                json={"content": chunk, "username": "GCP Bot"},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        logger.debug("[notify:discord] Sent (%d chars)", len(message))
    except Exception as e:
        logger.error("[notify:discord] Failed: %s", e)


def _send_slack(message: str) -> None:
    """
    Post to a Slack channel via Incoming Webhook.
    Slack supports mrkdwn formatting — *bold*, _italic_.
    """
    try:
        resp = requests.post(
            SLACK_WEBHOOK_URL,
            json={"text": message},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        logger.debug("[notify:slack] Sent")
    except Exception as e:
        logger.error("[notify:slack] Failed: %s", e)


def _send_telegram(message: str) -> None:
    """
    Send a message via Telegram Bot API.
    Uses parse_mode=Markdown for formatting.
    """
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        logger.debug("[notify:telegram] Sent")
    except Exception as e:
        logger.error("[notify:telegram] Failed: %s", e)
