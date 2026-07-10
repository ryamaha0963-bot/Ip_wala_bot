import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.handlers import CallbackQueryHandler, MessageHandler

LOGGER = logging.getLogger(__name__)

class IPExtractorBot:
    def __init__(self, bot: Client, detector, admin_id=None):
        self.bot = bot
        self.detector = detector
        self.admin_id = admin_id
        self.active_records = []
        self.selected_record = None
        self.state = {}

        self.bot.add_handler(MessageHandler(self.scan_cmd, filters.command("scan")))
        self.bot.add_handler(MessageHandler(self.start_cmd, filters.command("start")))
        self.bot.add_handler(CallbackQueryHandler(self.callback_handler))

    async def start_cmd(self, client, message):
        await message.reply("👋 Hello! Send /scan to find active voice chats and extract IPs instantly.")

    async def scan_cmd(self, client, message):
        user_id = message.from_user.id
        self.state[user_id] = {"step": "scanning"}
        status = await message.reply("🔍 Scanning dialogs for active VCs...")
        try:
            records = await self.detector.scan_active_voice_chats(limit=50)
        except Exception as e:
            await status.edit_text(f"❌ Scan failed: {e}")
            return
        self.active_records = records
        if not records:
            await status.edit_text("No active voice chat found.")
            return
        buttons = []
        for idx, rec in enumerate(records[:10]):
            title = rec.title[:30]
            buttons.append([InlineKeyboardButton(f"{idx+1}. {title}", callback_data=f"sel:{idx}")])
        await status.edit_text(
            f"✅ Found {len(records)} active VCs. Select one to extract IPs:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        self.state[user_id]["step"] = "selecting"

    async def callback_handler(self, client, callback):
        data = callback.data
        user_id = callback.from_user.id
        if data.startswith("sel:"):
            idx = int(data.split(":")[1])
            if idx >= len(self.active_records):
                await callback.answer("Invalid selection")
                return
            self.selected_record = self.active_records[idx]
            await callback.message.edit_text(
                f"⏳ Extracting IPs from: {self.selected_record.title} ..."
            )
            await callback.answer()
            # Directly extract without join
            result = await self.detector.extract_ips_from_call(self.selected_record)
            ips = result.get("extracted_ips", [])
            if ips:
                ip_list = "\n".join([f"• {ip['ip']}:{ip['port']} ({ip['type']})" for ip in ips])
                msg = f"✅ Extracted IPs from {result['title']}:\n\n{ip_list}"
            else:
                msg = f"⚠️ No IPs extracted. Notice: {result.get('notice', '')}"
            await callback.message.edit_text(msg)
