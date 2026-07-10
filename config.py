import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    bot_token: str
    session_string: str
    admin_id: int | None = None

    @classmethod
    def from_env(cls):
        required = {
            "API_ID": os.getenv("API_ID"),
            "API_HASH": os.getenv("API_HASH"),
            "BOT_TOKEN": os.getenv("BOT_TOKEN"),
            "SESSION_STRING": os.getenv("SESSION_STRING"),
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing: {', '.join(missing)}")
        return cls(
            api_id=int(required["API_ID"]),
            api_hash=required["API_HASH"],
            bot_token=required["BOT_TOKEN"],
            session_string=required["SESSION_STRING"],
            admin_id=int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None,
        )
