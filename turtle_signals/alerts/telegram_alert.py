"""alerts/telegram_alert.py — Send briefings and urgent alerts via Telegram."""

import asyncio
import logging

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)
MAX_MSG_LEN = 4096


def _is_configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def _split_message(text: str, max_len: int = MAX_MSG_LEN) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


async def _send_async(text: str, parse_mode: str = "Markdown") -> bool:
    try:
        from telegram import Bot
    except ImportError:
        logger.warning("python-telegram-bot not installed.")
        return False
    if not _is_configured():
        return False
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    chunks = _split_message(text)
    try:
        async with bot:
            for chunk in chunks:
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=chunk, parse_mode=parse_mode)
        return True
    except Exception as exc:
        logger.error("Telegram send failed: %s", exc)
        return False


def send_message(text: str, parse_mode: str = "Markdown") -> bool:
    try:
        return asyncio.run(_send_async(text, parse_mode))
    except RuntimeError:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_send_async(text, parse_mode))


def send_morning_briefing(markdown_text: str) -> bool:
    if not _is_configured():
        return False
    success = send_message(markdown_text)
    if success:
        logger.info("Morning briefing sent via Telegram.")
    return success


def send_urgent_alert(ticker: str, alert_type: str, message: str) -> bool:
    icons = {
        "stop_loss": "STOP-LOSS HIT",
        "system2_entry": "SYSTEM 2 SIGNAL",
        "time_exit": "TIME EXIT",
    }
    header = icons.get(alert_type, "ALERT")
    full_message = f"*{header} - {ticker}*\n\n{message}"
    success = send_message(full_message)
    if success:
        logger.info("Urgent alert sent for %s (%s).", ticker, alert_type)
    return success
