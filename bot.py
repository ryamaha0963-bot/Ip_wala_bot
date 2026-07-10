import logging
from telethon import events, Button
from telethon.tl.types import KeyboardButtonCallback

LOGGER = logging.getLogger(__name__)

class IPExtractorBot:
    def __init__(self, bot, detector, admin_id=None):
        self.bot = bot
        self.detector = detector
        self.admin_id = admin_id
        self.active_records = []
        self.selected_record = None
        self.state = {}

        # register handlers
        @bot.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await event.reply("👋 Hello! Send /scan to find active voice chats and extract IPs instantly.")

        @bot.on(events.NewMessage(pattern='/scan'))
        async def scan_handler(event):
            user_id = event.sender_id
            self.state[user_id] = {"step": "scanning"}
            status = await event.reply("🔍 Scanning dialogs for active VCs...")
            try:
                records = await self.detector.scan_active_voice_chats(limit=50)
            except Exception as e:
                await status.edit(f"❌ Scan failed: {e}")
                return
            self.active_records = records
            if not records:
                await status.edit("No active voice chat found.")
                return
            buttons = []
            for idx, rec in enumerate(records[:10]):
                title = rec.title[:30]
                buttons.append([Button.inline(f"{idx+1}. {title}", data=f"sel:{idx}")])
            await status.edit(
                f"✅ Found {len(records)} active VCs. Select one to extract IPs:",
                buttons=buttons
            )
            self.state[user_id]["step"] = "selecting"

        @bot.on(events.CallbackQuery())
        async def callback_handler(event):
            data = event.data.decode()
            user_id = event.sender_id
            if data.startswith("sel:"):
                idx = int(data.split(":")[1])
                if idx >= len(self.active_records):
                    await event.answer("Invalid selection", alert=True)
                    return
                self.selected_record = self.active_records[idx]
                await event.edit(f"⏳ Extracting IPs from: {self.selected_record.title} ...")
                await event.answer()
                # extract directly
                result = await self.detector.extract_ips_from_call(self.selected_record)
                ips = result.get("extracted_ips", [])
                if ips:
                    ip_list = "\n".join([f"• {ip['ip']}:{ip['port']} ({ip['type']})" for ip in ips])
                    msg = f"✅ Extracted IPs from {result['title']}:\n\n{ip_list}"
                else:
                    msg = f"⚠️ No IPs extracted. Notice: {result.get('notice', '')}"
                await event.edit(msg)
            else:
                await event.answer("Unknown action")
