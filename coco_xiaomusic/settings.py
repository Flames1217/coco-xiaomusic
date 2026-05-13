import json
from dataclasses import asdict, dataclass
from pathlib import Path


SETTINGS_PATH = Path("data/app_settings.json")
REPAIRABLE_TEXT_FIELDS = ("search_tts", "found_tts", "error_tts")
LEGACY_KEYWORDS = ("coco", "COCO", "Coco", "CoCo", "可可")
DEFAULT_KEYWORDS = ("点歌", "点一首", "搜歌", "可可", "coco", "COCO", "Coco", "CoCo")


def repair_text(value: str) -> str:
    if not isinstance(value, str):
        return value
    if not any(marker in value for marker in ("å", "æ", "ç", "ï", "ä", "", "")):
        return value
    try:
        repaired = value.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return repaired if repaired != value else value


@dataclass
class AppSettings:
    account: str = ""
    password: str = ""
    selected_dids: tuple[str, ...] = ()
    manual_target_dids: tuple[str, ...] = ()
    hostname: str = "http://192.168.1.13"
    xiaomusic_port: int = 8090
    admin_host: str = "127.0.0.1"
    admin_port: int = 8088
    coco_base: str = "https://coco.viper3.top"
    official_answer_delay_sec: float = 0.0
    search_tts: str = "小爱正在用coco搜索{keyword}"
    found_tts: str = "搜到啦，马上为你播放{artist}的{title}"
    error_tts: str = "coco暂时没有拿到可播放的第一条结果"
    edge_tts_voice: str = "zh-CN-XiaoyiNeural"
    coco_keywords: tuple[str, ...] = DEFAULT_KEYWORDS
    device_aliases: dict[str, str] = None

    @classmethod
    def load(cls) -> "AppSettings":
        if not SETTINGS_PATH.exists():
            return cls()
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        repaired = False
        for field_name in REPAIRABLE_TEXT_FIELDS:
            current = data.get(field_name)
            fixed = repair_text(current)
            if fixed != current:
                data[field_name] = fixed
                repaired = True
        keywords = data.get("coco_keywords")
        if isinstance(keywords, list):
            data["coco_keywords"] = tuple(keywords)
        if tuple(data.get("coco_keywords", ())) == LEGACY_KEYWORDS:
            data["coco_keywords"] = DEFAULT_KEYWORDS
            repaired = True
        if float(data.get("official_answer_delay_sec", 0.0) or 0.0) != 0.0:
            data["official_answer_delay_sec"] = 0.0
            repaired = True
        for key in ("selected_dids", "manual_target_dids"):
            if isinstance(data.get(key), list):
                data[key] = tuple(data[key])
        legacy_did = data.pop("did", "")
        if legacy_did and not data.get("selected_dids"):
            data["selected_dids"] = (legacy_did,)
        if legacy_did and not data.get("manual_target_dids"):
            data["manual_target_dids"] = (legacy_did,)
        loaded = cls(**data)
        if repaired:
            loaded.save()
        return loaded

    def save(self):
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data["coco_keywords"] = list(self.coco_keywords)
        data["selected_dids"] = list(self.selected_dids)
        data["manual_target_dids"] = list(self.manual_target_dids)
        SETTINGS_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def __post_init__(self):
        if self.device_aliases is None:
            self.device_aliases = {}

    def public_dict(self) -> dict:
        data = asdict(self)
        data["account"] = self._mask(self.account)
        data["password"] = "******" if self.password else ""
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
