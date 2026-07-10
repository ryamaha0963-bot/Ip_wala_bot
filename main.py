import asyncio
import logging
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import Config
from vc_detector import VCDetector
from bot import IPExtractorBot

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

async def main():
    try:
        cfg = Config.from_env()
    except Exception as e:
        LOGGER.error(f"Config error: {e}")
        return

    # Bot client – temporary session (StringSession empty) + bot token
    bot = TelegramClient(StringSession(), cfg.api_id, cfg.api_hash)
    try:
        await bot.start(bot_token=cfg.bot_token)
        LOGGER.info("Bot client started")
    except Exception as e:
        LOGGER.error(f"Bot start failed: {e}")
        return

    # User client – use provided Telethon session string (must be from StringSession)
    try:
        user = TelegramClient(StringSession(cfg.session_string), cfg.api_id, cfg.api_hash)
        await user.start()
        LOGGER.info("User client started")
    except Exception as e:
        LOGGER.error(f"User client start failed: {e}. Please check your SESSION_STRING.")
        # Don't return, but bot will still work? Actually we need user client for VC detection.
        # If user fails, we can't proceed.
        return

    detector = VCDetector(user)
    handler = IPExtractorBot(bot, detector, admin_id=cfg.admin_id)

    if cfg.admin_id:
        try:
            await bot.send_message(cfg.admin_id, "✅ IP Extractor Bot is online! Use /scan")
        except Exception as e:
            LOGGER.warning(f"Startup message failed: {e}")

    LOGGER.info("Bot running. Press Ctrl+C to stop.")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        LOGGER.info("Stopped by user")
