import asyncio
import json
import logging
import re
import socket
import time
from dataclasses import dataclass
from typing import Any, Optional, List

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.raw import functions, types

LOGGER = logging.getLogger(__name__)

@dataclass
class VCRecord:
    dialog_id: int
    title: str
    peer: Any
    call: Any
    chat_id: int

class VCDetector:
    def __init__(self, user_client: Client, cooldown: int = 5):
        self.user_client = user_client
        self.cooldown = cooldown
        self._last_scan = 0

    async def scan_active_voice_chats(self, limit=50):
        now = time.time()
        if now - self._last_scan < self.cooldown:
            await asyncio.sleep(self.cooldown - (now - self._last_scan))
        self._last_scan = time.time()
        results = []
        async for dialog in self.user_client.get_dialogs(limit=limit):
            chat = dialog.chat
            try:
                peer = await self.user_client.resolve_peer(chat.id)
                call = await self._get_call(peer)
                if call:
                    results.append(VCRecord(
                        dialog_id=chat.id,
                        title=chat.title or str(chat.id),
                        peer=peer,
                        call=call,
                        chat_id=chat.id
                    ))
            except FloodWait as e:
                raise
            except Exception:
                continue
        return results

    async def _get_call(self, peer):
        if isinstance(peer, types.InputPeerChannel):
            full = await self.user_client.invoke(
                functions.channels.GetFullChannel(channel=peer)
            )
            return getattr(full.full_chat, "call", None)
        if isinstance(peer, types.InputPeerChat):
            full = await self.user_client.invoke(
                functions.messages.GetFullChat(chat_id=peer.chat_id)
            )
            return getattr(full.full_chat, "call", None)
        return None

    async def extract_ips_from_call(self, record: VCRecord):
        """Directly fetch call info and extract IPs – no join needed."""
        try:
            group_call = await self.user_client.invoke(
                functions.phone.GetGroupCall(
                    call=types.InputGroupCall(
                        id=record.call.id,
                        access_hash=record.call.access_hash
                    ),
                    limit=1  # we don't need participants
                )
            )
            call_obj = group_call.call
            params_raw = getattr(call_obj, "params", None)
            params_data = getattr(params_raw, "data", "{}") if params_raw else "{}"
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
        # endpoints se
        for ep in parsed.get("endpoints", []):
            if ":" in ep:
                parts = ep.rsplit(":", 1)
                if len(parts) == 2:
                    ip, port = parts
                    if self._is_valid_ip(ip):
                        ips.append({"ip": ip, "port": port, "type": "endpoint"})
        # servers se
        for s in parsed.get("servers", []):
            ip = s.get("ip") or s.get("host")
            port = s.get("port", 0)
            if ip and self._is_valid_ip(ip):
                ips.append({"ip": ip, "port": port, "type": "server"})
        # deep regex
        text = json.dumps(parsed)
        ipv4 = re.findall(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b', text)
        for ip in set(ipv4):
            if self._is_valid_ip(ip) and not any(x["ip"] == ip for x in ips):
                ips.append({"ip": ip, "port": 0, "type": "deep_extract"})
        return ips

    def _is_valid_ip(self, ip):
        try:
            socket.inet_aton(ip)
            return True
        except:
            return False
