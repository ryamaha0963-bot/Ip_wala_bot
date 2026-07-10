import asyncio
import json
import re
import socket
import logging
from dataclasses import dataclass
from typing import Any, Optional, List

from telethon import TelegramClient
from telethon.tl import functions, types
from telethon.errors import FloodWaitError

LOGGER = logging.getLogger(__name__)

@dataclass
class VCRecord:
    dialog_id: int
    title: str
    peer: Any
    call: Any
    chat_id: int

class VCDetector:
    def __init__(self, user_client: TelegramClient, cooldown: int = 5):
        self.user_client = user_client
        self.cooldown = cooldown
        self._last_scan = 0

    async def scan_active_voice_chats(self, limit=50):
        now = asyncio.get_event_loop().time()
        if now - self._last_scan < self.cooldown:
            await asyncio.sleep(self.cooldown - (now - self._last_scan))
        self._last_scan = now
        results = []
        async for dialog in self.user_client.iter_dialogs(limit=limit):
            chat = dialog.entity
            try:
                peer = await self.user_client.get_input_entity(chat)
                call = await self._get_call(peer)
                if call:
                    results.append(VCRecord(
                        dialog_id=chat.id,
                        title=getattr(chat, 'title', str(chat.id)),
                        peer=peer,
                        call=call,
                        chat_id=chat.id
                    ))
            except FloodWaitError as e:
                raise
            except Exception:
                continue
        return results

    async def _get_call(self, peer):
        if isinstance(peer, types.InputPeerChannel):
            full = await self.user_client(functions.channels.GetFullChannelRequest(channel=peer))
            return getattr(full.full_chat, 'call', None)
        elif isinstance(peer, types.InputPeerChat):
            full = await self.user_client(functions.messages.GetFullChatRequest(chat_id=peer.chat_id))
            return getattr(full.full_chat, 'call', None)
        return None

    async def extract_ips_from_call(self, record: VCRecord):
        """Fetch call info and extract IPs – no join required."""
        try:
            group_call = await self.user_client(
                functions.phone.GetGroupCallRequest(
                    call=types.InputGroupCall(
                        id=record.call.id,
                        access_hash=record.call.access_hash
                    ),
                    limit=1
                )
            )
            call_obj = group_call.call
            params_raw = getattr(call_obj, 'params', None)
            params_data = getattr(params_raw, 'data', '{}') if params_raw else '{}'
            try:
                parsed = json.loads(params_data)
            except:
                parsed = {}
        except Exception as e:
            return {
                "title": record.title,
                "extracted_ips": [],
                "notice": f"GetGroupCall failed: {e}"
            }

        ips = self._extract_ips(parsed)
        return {
            "title": record.title,
            "extracted_ips": ips,
            "notice": ""
        }

    def _extract_ips(self, parsed):
        ips = []
        # endpoints
        for ep in parsed.get('endpoints', []):
            if ':' in ep:
                parts = ep.rsplit(':', 1)
                if len(parts)==2:
                    ip, port = parts
                    if self._is_valid_ip(ip):
                        ips.append({"ip": ip, "port": port, "type": "endpoint"})
        # servers
        for s in parsed.get('servers', []):
            ip = s.get('ip') or s.get('host')
            port = s.get('port', 0)
            if ip and self._is_valid_ip(ip):
                ips.append({"ip": ip, "port": port, "type": "server"})
        # deep regex
        text = json.dumps(parsed)
        ipv4 = re.findall(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b', text)
        for ip in set(ipv4):
            if self._is_valid_ip(ip) and not any(x['ip']==ip for x in ips):
                ips.append({"ip": ip, "port": 0, "type": "deep_extract"})
        return ips

    def _is_valid_ip(self, ip):
        try:
            socket.inet_aton(ip)
            return True
        except:
            return False
