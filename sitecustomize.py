"""Avoid leaking the Telegram bot token in HTTP request log URLs."""
import logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
