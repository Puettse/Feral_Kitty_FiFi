import os
import json
import shutil
import asyncio
from typing import Any, Dict
from .io_types import JSONDict

# Runtime config location. Override with FKF_CONFIG_PATH (the VPS deploy sets
# it to /opt/fifi/data/config.json — see DEPLOY.md).
CONFIG_PATH = os.environ.get("FKF_CONFIG_PATH", "data/config.json")

# The committed config shipped with the package, used to seed CONFIG_PATH on
# first run so a fresh deploy starts from the repo's config instead of bare
# defaults.
PACKAGED_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "data", "config.json")

DEFAULT_CFG: JSONDict = {
    "renames": {},
    "purge": [],
    "roles": [],
    "safeword": {
        "enabled": True,
        "trigger": "!STOP!",
        "release_trigger": "!Release",
        "log_channel_id": 1400887461907009666,
        "history_limit": 25,
        "roles_to_ping": ["Staff","SECURITY","The Enforcer","Watcher","Red Guard","The Father"],
        "roles_whitelist": ["Staff"],
        "blocked_roles": ["jailed"],
        "cooldown_seconds": 30,
        "lock_message": {"text": "!STOP! HAS BEEN CALLED; CHANNEL IS LOCKED PENDING REVIEW, PLEASE STANDBY. THANK YOU FOR YOUR PATIENCE.","image_url": ""},
        "release_message": {"text": "Channel released. Please continue respectfully.","image_url": ""}
    },
    "reaction_panels": []
}

_lock = asyncio.Lock()

def _deep_merge(dst: JSONDict, src: JSONDict) -> JSONDict:
    # Only merge known top-level sections; shallow is enough for this schema
    merged = json.loads(json.dumps(dst))
    merged.update(src or {})
    if isinstance((src or {}).get("safeword"), dict):
        merged["safeword"] = {**dst.get("safeword", {}), **src["safeword"]}
    if "reaction_panels" not in merged:
        merged["reaction_panels"] = []
    return merged

def _write_atomic(path: str, cfg: JSONDict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

async def load_config() -> JSONDict:
    if not os.path.exists(CONFIG_PATH):
        async with _lock:
            os.makedirs(os.path.dirname(CONFIG_PATH) or ".", exist_ok=True)
            if os.path.exists(PACKAGED_CONFIG_PATH):
                shutil.copyfile(PACKAGED_CONFIG_PATH, CONFIG_PATH)
            else:
                _write_atomic(CONFIG_PATH, DEFAULT_CFG)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return _deep_merge(DEFAULT_CFG, raw)

async def save_config(cfg: JSONDict) -> None:
    async with _lock:
        _write_atomic(CONFIG_PATH, cfg)
