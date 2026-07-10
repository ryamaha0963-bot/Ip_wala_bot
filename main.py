import asyncio
import logging
import sys
from pyrogram import Client, idle
from config import Config
from vc_detector import VCDetector
from bot import IPExtractorBot

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

async def main():
    cfg = Config.from_env()
    # Bot client
    bot = Client("ip_bot", api_id=cfg.api_id, api_hash=cfg.api_hash, bot_token=cfg.bot_token)
    # User client (for joining VC)
    user = Client("ip_user", api_id=cfg.api_id, api_hash=cfg.api_hash, session_string=cfg.session_string)
    await bot.start()
    await user.start()
    LOGGER.info("Clients started")

    detector = VCDetector(user)
    handler = IPExtractorBot(bot, detector, admin_id=cfg.admin_id)

    # Startup message (optional)
    if cfg.admin_id:
        try:
            await bot.send_message(cfg.admin_id, "✅ IP Extractor Bot is online! Use /scan")
        except:
            pass

    await idle()
    await bot.stop()
    await user.stop()

if __name__ == "__main__":
    asyncio.run(main())
