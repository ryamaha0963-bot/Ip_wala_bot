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
        self.state = {}  # per-user state

        # handlers
        self.bot.add_handler(MessageHandler(self.scan_cmd, filters.command("scan")))
        self.bot.add_handler(MessageHandler(self.start_cmd, filters.command("start")))
        self.bot.add_handler(CallbackQueryHandler(self.callback_handler))

    async def start_cmd(self, client, message):
        await message.reply(
            "👋 Hello! Send /scan to find active voice chats."
        )

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
        # build inline buttons
        buttons = []
        for idx, rec in enumerate(records[:10]):  # max 10
            title = rec.title[:30]
            buttons.append([InlineKeyboardButton(f"{idx+1}. {title}", callback_data=f"sel:{idx}")])
        await status.edit_text(
            f"✅ Found {len(records)} active VCs. Select one:",
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
            # ask for confirmation to join
            await callback.message.edit_text(
                f"🎯 Selected: {self.selected_record.title}\n\nJoin this VC to extract IPs?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Join & Extract", callback_data="join:yes")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="join:no")]
                ])
            )
            await callback.answer()
        elif data == "join:yes":
            if not self.selected_record:
                await callback.answer("No VC selected")
                return
            await callback.message.edit_text("⏳ Joining VC and extracting IPs...")
            await callback.answer()
            try:
                result = await self.detector.join_and_extract(self.selected_record)
                ips = result.get("extracted_ips", [])
                if ips:
                    ip_list = "\n".join([f"• {ip['ip']}:{ip['port']} ({ip['type']})" for ip in ips])
                    msg = f"✅ Extracted IPs from {result['title']}:\n\n{ip_list}"
                else:
                    msg = f"⚠️ No IPs extracted. Notice: {result.get('notice', '')}"
                # leave VC automatically
                await self.detector.leave_call(self.selected_record)
                # send result
                await callback.message.edit_text(msg)
            except Exception as e:
                await callback.message.edit_text(f"❌ Error: {e}")
        elif data == "join:no":
            await callback.message.edit_text("❌ Cancelled.")
            await callback.answer()
