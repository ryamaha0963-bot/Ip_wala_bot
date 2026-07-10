import asyncio
import json
import logging
import re
import socket
import time
from dataclasses import dataclass
from typing import Any, Optional, List

from pyrogram import Client
from pyrogram.errors import ChatAdminRequired, FloodWait, UserAlreadyParticipant
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

    async def join_and_extract(self, record: VCRecord):
        """Join VC, extract IPs from call parameters."""
        joined = False
        notice = None
        try:
            # अपना खुद का peer (user) join_as में डालें
            my_peer = await self.user_client.resolve_peer('me')
            call_params = getattr(record.call, "params", None)
            if call_params is None:
                # अगर params न मिले तो static fallback (शायद काम न करे)
                call_params = types.DataJSON(data=json.dumps({
                    "ufrag": "test",
                    "pwd": "test123",
                    "fingerprints": [],
                    "ssrc": 11111111
                }))
                notice = "No params found – using static (join may fail)."
            await self.user_client.invoke(
                functions.phone.JoinGroupCall(
                    call=types.InputGroupCall(id=record.call.id, access_hash=record.call.access_hash),
                    join_as=my_peer,
                    params=call_params,
                    muted=True,
                    video_stopped=True
                )
            )
            joined = True
            LOGGER.info("Joined VC: %s", record.title)
            await asyncio.sleep(2)
        except UserAlreadyParticipant:
            joined = True
        except (ChatAdminRequired, Exception) as e:
            notice = f"Join failed: {e}"
            LOGGER.warning(notice)

        # अब metadata fetch करें
        try:
            group_call = await self.user_client.invoke(
                functions.phone.GetGroupCall(
                    call=types.InputGroupCall(id=record.call.id, access_hash=record.call.access_hash),
                    limit=100
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
            parsed = {}
            notice = (notice or "") + f" GetGroupCall failed: {e}"

        # IP निकालें
        extracted_ips = self._extract_ips(parsed)
        return {
            "title": record.title,
            "joined": joined,
            "notice": notice,
            "extracted_ips": extracted_ips
        }

    def _extract_ips(self, parsed):
        ips = []
        # endpoints से
        for ep in parsed.get("endpoints", []):
            if ":" in ep:
                parts = ep.rsplit(":", 1)
                if len(parts)==2:
                    ip, port = parts
                    if self._is_valid_ip(ip):
                        ips.append({"ip": ip, "port": port, "type": "endpoint"})
        # servers से
        for s in parsed.get("servers", []):
            ip = s.get("ip") or s.get("host")
            port = s.get("port", 0)
            if ip and self._is_valid_ip(ip):
                ips.append({"ip": ip, "port": port, "type": "server"})
        # deep regex (IPv4)
        text = json.dumps(parsed)
        ipv4 = re.findall(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b', text)
        for ip in set(ipv4):
            if self._is_valid_ip(ip) and not any(x["ip"]==ip for x in ips):
                ips.append({"ip": ip, "port": 0, "type": "deep_extract"})
        return ips

    def _is_valid_ip(self, ip):
        try:
            socket.inet_aton(ip)
            return True
        except:
            return False

    async def leave_call(self, record):
        try:
            await self.user_client.invoke(
                functions.phone.LeaveGroupCall(
                    call=types.InputGroupCall(id=record.call.id, access_hash=record.call.access_hash),
                    source=0
                )
            )
        except Exception:
            pass
