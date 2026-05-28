from __future__ import annotations

import json
import os
import ipaddress
import re
import subprocess
from dataclasses import asdict, dataclass, field, fields
from json import JSONDecodeError
from pathlib import Path
from typing import Any


def runtime_home() -> Path:
    configured = os.environ.get("COCO_XIAOMUSIC_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.cwd()


def detect_lan_ipv4() -> str:
    try:
        completed = subprocess.run(
            ["ipconfig"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="gbk",
            errors="ignore",
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return ""
    candidates: list[str] = []
    for match in re.finditer(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", completed.stdout or ""):
        value = match.group(0)
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if address.version != 4 or address.is_loopback or address.is_link_local:
            continue
        if address.is_private:
            candidates.append(value)
    return candidates[0] if candidates else ""


def default_hostname() -> str:
    address = detect_lan_ipv4()
    return f"http://{address}" if address else "http://127.0.0.1"


SETTINGS_PATH = runtime_home() / "data" / "app_settings.json"
REPAIRABLE_TEXT_FIELDS = ("search_tts", "found_tts", "error_tts")
LEGACY_KEYWORDS = ("coco", "COCO", "Coco", "CoCo", "可可")
DEFAULT_KEYWORDS = (
    "点歌",
    "点个",
    "点首",
    "点一首",
    "搜歌",
    "搜一个",
    "来一首",
    "来首",
    "放一个",
    "播放",
    "放歌",
    "听歌",
    "可可",
    "coco",
    "COCO",
    "Coco",
    "CoCo",
)


def repair_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        repaired = value.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return repaired if repaired != value else value


def salvage_settings_text(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key in (
        "account",
        "password",
        "hostname",
        "admin_host",
        "coco_base",
        "takeover_mode",
        "edge_tts_voice",
    ):
        match = re.search(rf'"{key}"\s*:\s*"((?:\\.|[^"\\])*)"', text)
        if match:
            try:
                data[key] = json.loads(f'"{match.group(1)}"')
            except JSONDecodeError:
                data[key] = match.group(1)

    for key in ("xiaomusic_port", "admin_port", "last_volume"):
        match = re.search(rf'"{key}"\s*:\s*(\d+)', text)
        if match:
            data[key] = int(match.group(1))

    match = re.search(r'"official_answer_delay_sec"\s*:\s*([0-9.]+)', text)
    if match:
        data["official_answer_delay_sec"] = float(match.group(1))

    for key in ("selected_dids", "manual_target_dids", "coco_keywords"):
        match = re.search(rf'"{key}"\s*:\s*(\[[\s\S]*?\])', text)
        if match:
            try:
                data[key] = json.loads(match.group(1))
            except JSONDecodeError:
                pass
    return data


@dataclass
class AppSettings:
    account: str = ""
    password: str = ""
    selected_dids: tuple[str, ...] = ()
    manual_target_dids: tuple[str, ...] = ()
    hostname: str = field(default_factory=default_hostname)
    xiaomusic_port: int = 8090
    admin_host: str = "0.0.0.0"
    admin_port: int = 8088
    coco_base: str = "https://coco.viper3.top"
    takeover_mode: str = "keyword"
    official_answer_delay_sec: float = 0.0
    search_tts: str = "小爱正在用 coco 搜索 {keyword}"
    found_tts: str = "搜到啦，马上为你播放 {artist} 的 {title}"
    error_tts: str = "coco 暂时没拿到可播放的结果，已经为你换一个试试"
    edge_tts_voice: str = "zh-CN-XiaoyiNeural"
    coco_keywords: tuple[str, ...] = DEFAULT_KEYWORDS
    device_aliases: dict[str, str] | None = None
    last_volume: int = 50

    @classmethod
    def load(cls) -> "AppSettings":
        if not SETTINGS_PATH.exists():
            return cls()
        try:
            raw_settings = SETTINGS_PATH.read_text(encoding="utf-8")
        except OSError:
            return cls()
        try:
            data = json.loads(raw_settings)
        except JSONDecodeError:
            data = salvage_settings_text(raw_settings)
            if not data:
                return cls()
        repaired = False
        for field_name in REPAIRABLE_TEXT_FIELDS:
            current = data.get(field_name)
            fixed = repair_text(current)
            if fixed != current:
                data[field_name] = fixed
                repaired = True

        keywords = data.get("coco_keywords")
        if isinstance(keywords, list):
            repaired_keywords = [str(repair_text(item)) for item in keywords]
            merged_keywords = tuple(dict.fromkeys([*repaired_keywords, *DEFAULT_KEYWORDS]))
            if tuple(keywords) != merged_keywords:
                repaired = True
            data["coco_keywords"] = merged_keywords
        if tuple(data.get("coco_keywords", ())) == LEGACY_KEYWORDS:
            data["coco_keywords"] = DEFAULT_KEYWORDS
            repaired = True

        for key in ("selected_dids", "manual_target_dids"):
            if isinstance(data.get(key), list):
                data[key] = tuple(data[key])

        if data.get("admin_host") in ("", "127.0.0.1", "localhost"):
            data["admin_host"] = "0.0.0.0"
            repaired = True

        if "*" in str(data.get("account", "")):
            data["account"] = ""
            repaired = True

        legacy_did = data.pop("did", "")
        if legacy_did and not data.get("selected_dids"):
            data["selected_dids"] = (legacy_did,)
        if legacy_did and not data.get("manual_target_dids"):
            data["manual_target_dids"] = (legacy_did,)

        known_fields = {field.name for field in fields(cls)}
        data = {key: value for key, value in data.items() if key in known_fields}
        loaded = cls(**data)
        detected_hostname = default_hostname()
        if detected_hostname and loaded.hostname != detected_hostname:
            loaded.hostname = detected_hostname
            repaired = True
        if repaired:
            loaded.save()
        return loaded

    def save(self):
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data["coco_keywords"] = list(self.coco_keywords)
        data["selected_dids"] = list(self.selected_dids)
        data["manual_target_dids"] = list(self.manual_target_dids)
        SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def __post_init__(self):
        if self.device_aliases is None:
            self.device_aliases = {}

    def public_dict(self) -> dict:
        data = asdict(self)
        data["account"] = self.account
        data["password"] = self.password
        data["search_tts"] = repair_text(self.search_tts)
        data["found_tts"] = repair_text(self.found_tts)
        data["error_tts"] = repair_text(self.error_tts)
        data["coco_keywords"] = [repair_text(keyword) for keyword in self.coco_keywords]
        data["selected_dids"] = list(self.selected_dids)
        data["manual_target_dids"] = list(self.manual_target_dids)
        return data

    @staticmethod
    def _mask(value: str) -> str:
        if not value:
            return ""
        if len(value) <= 4:
            return "*" * len(value)
        return f"{value[:3]}****{value[-3:]}"


settings = AppSettings.load()
