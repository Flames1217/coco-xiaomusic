import asyncio
import logging
import re
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import xiaomusic.xiaomusic as xm_module
from rich.console import Console
from xiaomusic.config import Config
from xiaomusic.xiaomusic import XiaoMusic

from .coco_client import CocoClient, CocoSong
from .settings import AppSettings, repair_text


console = Console()


@dataclass
class PlaybackEvent:
    at: str
    level: str
    message: str
    keyword: str = ""
    song: dict | None = None


@dataclass
class RuntimeState:
    ready: bool = False
    starting: bool = False
    last_keyword: str = ""
    last_song: dict | None = None
    last_error: str = ""
    last_playback_at: str = ""
    startup_error: str = ""
    discovered_devices: list[dict] = field(default_factory=list)
    events: deque[PlaybackEvent] = field(default_factory=lambda: deque(maxlen=80))


class CocoXiaoMusicService:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.coco = CocoClient(settings.coco_base)
        self.state = RuntimeState()
        self.xiaomusic: XiaoMusic | None = None
        self._runner_task: asyncio.Task | None = None
        self._patch_online_play()

    def _log(self, level: str, message: str, keyword: str = "", song: dict | None = None):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.state.events.appendleft(
            PlaybackEvent(at=timestamp, level=level, message=message, keyword=keyword, song=song)
        )
        styles = {
            "ok": ("bold green", "✅"),
            "warn": ("bold yellow", "⚠️"),
            "error": ("bold red", "❌"),
            "info": ("bold cyan", "🎧"),
        }
        style, icon = styles[level]
        if getattr(sys.stdout, "isatty", lambda: False)():
            try:
                console.print(f"[{style}]{icon} {message}[/{style}]")
            except UnicodeEncodeError:
                console.print(f"[{style}]{level.upper()}: {message}[/{style}]")

    def _patch_online_play(self):
        async def coco_online_play(service, did="", arg1="", **kwargs):
            return await self.play_keyword(did, arg1)

        xm_module.OnlineMusicService.online_play = coco_online_play

    @staticmethod
    def _patch_xiaomusic_logger():
        def setup_quiet_logger(instance):
            instance.log = logging.getLogger("xiaomusic")
            instance.log.handlers.clear()
            instance.log.setLevel(logging.ERROR)
            instance.log.addHandler(logging.NullHandler())

        XiaoMusic.setup_logger = setup_quiet_logger

    @staticmethod
    def _clean_keyword(arg: str) -> str:
        return re.sub(r"^(播放歌曲|播放|放|来一首)\s*", "", arg.strip())

    def _build_xiaomusic(self) -> XiaoMusic:
        self._patch_xiaomusic_logger()
        user_keywords = {keyword: "online_play" for keyword in self.settings.coco_keywords}
        user_keywords["闭嘴"] = "stop"
        config = Config(
            account=self.settings.account,
            password=self.settings.password,
            mi_did=",".join(self.settings.selected_dids),
            hostname=self.settings.hostname,
            port=self.settings.xiaomusic_port,
            enable_pull_ask=True,
            enable_force_stop=True,
            pull_ask_sec=1,
            edge_tts_voice=self.settings.edge_tts_voice,
            log_file="xiaomusic.log.txt",
            user_key_word_dict=user_keywords,
        )
        return XiaoMusic(config)

    async def start(self):
        if self._runner_task:
            return
        if not self.settings.account or not self.settings.password:
            self.state.ready = False
            self.state.starting = False
            self.state.startup_error = "请先配置小米账号和密码"
            self._log("warn", self.state.startup_error)
            return
        self.state.starting = True
        self._runner_task = asyncio.create_task(self._run())

    async def stop(self):
        if self._runner_task:
            self._runner_task.cancel()
            self._runner_task = None
        self.state.ready = False
        self.state.starting = False
        self.xiaomusic = None

    async def restart(self):
        await self.stop()
        self.state.startup_error = ""
        await self.start()

    async def _run(self):
        try:
            self.xiaomusic = self._build_xiaomusic()
            await self.xiaomusic.reinit()
            await self._discover_devices()
            self.state.ready = True
            self.state.starting = False
            self.state.startup_error = ""
            self._log("ok", "xiaomusic 服务已就绪")
            await self.xiaomusic.run_forever()
        except Exception as exc:
            self.state.ready = False
            self.state.starting = False
            self.state.startup_error = str(exc)
            self._log("error", f"xiaomusic 启动失败：{exc!r}")

    async def _discover_devices(self):
        self.state.discovered_devices = []
        if not self.xiaomusic:
            return
        auth_manager = getattr(self.xiaomusic, "auth_manager", None)
        mina_service = getattr(auth_manager, "mina_service", None)
        if not mina_service:
            return
        try:
            raw_devices = await mina_service.device_list()
        except Exception as exc:
            self._log("warn", f"拉取原始设备列表失败：{exc!r}")
            return
        for item in raw_devices or []:
            did = str(item.get("miotDID", "") or "")
            if not did:
                continue
            self.state.discovered_devices.append(
                {
                    "did": did,
                    "device_id": str(item.get("deviceID", "") or ""),
                    "raw_name": repair_text(str(item.get("alias") or item.get("name") or "未知设备")),
                    "hardware": str(item.get("hardware", "") or ""),
                }
            )

    async def play_keyword(self, did: str, keyword: str):
        if not self.xiaomusic:
            return {"success": False, "error": "xiaomusic not ready"}

        keyword = self._clean_keyword(keyword)
        if not keyword:
            self.state.last_error = "empty keyword"
            self._log("error", "没拿到歌名，不会回退其他音源")
            return {"success": False, "error": "empty keyword"}

        self.state.last_keyword = keyword
        self.state.last_error = ""
        self._log("info", f"coco 搜索：{keyword}", keyword=keyword)

        search_task = asyncio.get_running_loop().run_in_executor(
            None, self.coco.search_first, keyword
        )
        await asyncio.sleep(self.settings.official_answer_delay_sec)
        device = await self._take_over_device(did)
        if not device:
            self.state.last_error = "device not found"
            return {"success": False, "error": "device not found"}

        await self._speak(device, self.settings.search_tts.format(keyword=keyword))
        try:
            song, url = await search_task
        except Exception as exc:
            self.state.last_error = str(exc)
            self._log("error", f"coco 请求失败：{exc!r}", keyword=keyword)
            await self._speak(device, self.settings.error_tts)
            return {"success": False, "error": str(exc)}

        if not song:
            self.state.last_error = "not found"
            self._log("error", f"coco 没搜到：{keyword}", keyword=keyword)
            await self._speak(device, self.settings.error_tts)
            return {"success": False, "error": "not found"}
        if not url:
            self.state.last_error = "first result has no url"
            self._log(
                "error",
                f"coco 第一条没有直链：{song.title} - {song.artist} [{song.provider}]",
                keyword=keyword,
                song=song.raw,
            )
            await self._speak(device, self.settings.error_tts)
            return {
                "success": False,
                "error": "first result has no url",
                "song": song.raw,
            }

        return await self._play_song(device, did, keyword, song, url)

    async def _play_song(self, device, did: str, keyword: str, song: CocoSong, url: str):
        self.state.last_song = song.raw
        self.state.last_playback_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._log(
            "ok",
            f"coco 第一条：{song.title} - {song.artist} [{song.provider}]",
            keyword=keyword,
            song=song.raw,
        )
        await self._speak(
            device,
            self.settings.found_tts.format(
                title=song.title or keyword,
                artist=song.artist or "歌手",
                keyword=keyword,
            ),
        )
        await self._take_over_device(did)
        await self.xiaomusic.play_url(did, url)
        self._log("ok", "已推送到小爱音箱", keyword=keyword, song=song.raw)
        return {"success": True, "song": song.raw, "url": url}

    async def _take_over_device(self, did: str):
        if not self.xiaomusic:
            return None
        device = self.xiaomusic.device_manager.devices.get(did)
        if not device:
            self._log("warn", f"找不到设备 did={did}")
            return None
        await device.cancel_group_next_timer()
        await device.group_force_stop_xiaoai()
        return device

    async def _speak(self, device, text: str):
        await device.text_to_speech(text)
        await asyncio.sleep(max(1.2, min(4.5, len(text) / 4.5)))
        timer = getattr(device, "_tts_timer", None)
        if timer:
            timer.cancel()
            device._tts_timer = None

    async def search_preview(self, keyword: str):
        songs = await asyncio.get_running_loop().run_in_executor(
            None, self.coco.search_items, keyword, None
        )
        preview = []
        for index, song in enumerate(songs):
            has_url = False
            if index == 0:
                try:
                    has_url = bool(
                        await asyncio.get_running_loop().run_in_executor(
                            None, self.coco.resolve_url, song
                        )
                    )
                except Exception:
                    has_url = False
            preview.append(
                {
                    "item": song.raw,
                    "is_first": index == 0,
                    "has_url": has_url if index == 0 else None,
                }
            )
        return {"items": preview}

    def _manual_targets(self, requested: list[str] | None = None) -> list[str]:
        candidates = requested or list(self.settings.manual_target_dids) or list(self.settings.selected_dids)
        return [did for did in candidates if did]

    async def _play_url_to_targets(self, url: str, target_dids: list[str]):
        results = []
        for did in target_dids:
            device = await self._take_over_device(did)
            if not device:
                results.append({"did": did, "success": False, "error": "device not found"})
                continue
            await self.xiaomusic.play_url(did, url)
            results.append({"did": did, "success": True})
        return results

    async def play_selected_song(
        self,
        song_id: str,
        provider: str,
        title: str,
        artist: str,
        target_dids: list[str] | None = None,
    ):
        if not self.xiaomusic:
            return {"success": False, "error": "xiaomusic not ready"}
        target_dids = self._manual_targets(target_dids)
        if not target_dids:
            return {"success": False, "error": "device not selected"}

        song = CocoSong(
            id=song_id,
            provider=provider,
            title=title,
            artist=artist,
            raw={"id": song_id, "provider": provider, "title": title, "artist": artist},
        )
        try:
            url = await asyncio.get_running_loop().run_in_executor(
                None, self.coco.resolve_url, song
            )
        except Exception as exc:
            self.state.last_error = str(exc)
            self._log("error", f"指定歌曲解析失败：{exc!r}", song=song.raw)
            return {"success": False, "error": str(exc)}
        if not url:
            self.state.last_error = "selected song has no url"
            self._log("error", f"指定歌曲没有直链：{title} - {artist} [{provider}]", song=song.raw)
            return {"success": False, "error": "selected song has no url"}

        results = await self._play_url_to_targets(url, target_dids)
        if not any(item["success"] for item in results):
            return {"success": False, "error": "all target devices failed", "targets": results}
        self.state.last_song = song.raw
        self.state.last_playback_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._log("ok", f"前端手动推送：{title} - {artist} [{provider}]", song=song.raw)
        return {"success": True, "song": song.raw, "url": url, "targets": results}

    async def stop_playback(self, target_dids: list[str] | None = None):
        if not self.xiaomusic:
            return {"success": False, "error": "xiaomusic not ready"}
        targets = self._manual_targets(target_dids)
        results = []
        for did in targets:
            device = await self._take_over_device(did)
            results.append({"did": did, "success": bool(device)})
        return {"success": any(item["success"] for item in results), "targets": results}

    async def update_account(self, account: str, password: str, hostname: str):
        self.settings.account = account.strip()
        self.settings.password = password
        self.settings.hostname = hostname.strip() or self.settings.hostname
        self.settings.selected_dids = ()
        self.settings.manual_target_dids = ()
        self.settings.save()
        await self.restart()
        return {"success": True}

    async def select_devices(self, dids: list[str], manual_targets: list[str] | None = None):
        cleaned_dids = tuple(dict.fromkeys(did.strip() for did in dids if did.strip()))
        if not cleaned_dids:
            return {"success": False, "error": "empty dids"}
        cleaned_manual = tuple(
            did for did in dict.fromkeys((manual_targets or dids)) if did in cleaned_dids
        )
        self.settings.selected_dids = cleaned_dids
        self.settings.manual_target_dids = cleaned_manual or cleaned_dids[:1]
        self.settings.save()
        await self.restart()
        return {
            "success": True,
            "selected_dids": list(self.settings.selected_dids),
            "manual_target_dids": list(self.settings.manual_target_dids),
        }

    async def update_runtime_settings(
        self,
        coco_base: str,
        official_answer_delay_sec: float,
        search_tts: str,
        found_tts: str,
        error_tts: str,
    ):
        self.settings.coco_base = coco_base.strip() or self.settings.coco_base
        self.settings.official_answer_delay_sec = max(0.0, official_answer_delay_sec)
        self.settings.search_tts = search_tts.strip() or self.settings.search_tts
        self.settings.found_tts = found_tts.strip() or self.settings.found_tts
        self.settings.error_tts = error_tts.strip() or self.settings.error_tts
        self.settings.save()
        self.coco = CocoClient(self.settings.coco_base)
        return {"success": True}

    async def rename_device(self, did: str, alias: str):
        did = did.strip()
        alias = alias.strip()
        if not did:
            return {"success": False, "error": "empty did"}
        if alias:
            self.settings.device_aliases[did] = alias
        else:
            self.settings.device_aliases.pop(did, None)
        self.settings.save()
        return {"success": True, "did": did, "alias": alias}

    def status(self) -> dict:
        token_file = Path("conf/.mi.token")
        devices = []
        if self.xiaomusic:
            for device in self.xiaomusic.device_manager.devices.values():
                raw_device = getattr(device, "device", None)
                did = getattr(device, "did", "") or getattr(raw_device, "did", "")
                raw_name = repair_text(
                    getattr(raw_device, "name", "") or getattr(device, "group_name", "")
                )
                devices.append(
                    {
                        "did": did,
                        "device_id": getattr(device, "device_id", "") or getattr(raw_device, "device_id", ""),
                        "name": repair_text(self.settings.device_aliases.get(did) or raw_name),
                        "raw_name": raw_name,
                        "alias": repair_text(self.settings.device_aliases.get(did, "")),
                        "hardware": getattr(device, "hardware", "") or getattr(raw_device, "hardware", ""),
                    }
                )
        if not devices:
            for item in self.state.discovered_devices:
                did = item["did"]
                devices.append(
                    {
                        "did": did,
                        "device_id": item["device_id"],
                        "name": repair_text(self.settings.device_aliases.get(did) or item["raw_name"]),
                        "raw_name": repair_text(item["raw_name"]),
                        "alias": repair_text(self.settings.device_aliases.get(did, "")),
                        "hardware": item["hardware"],
                    }
                )
        selected_device_present = bool(self.settings.selected_dids) and all(
            did in {device["did"] for device in devices} for did in self.settings.selected_dids
        )
        return {
            "ready": self.state.ready,
            "starting": self.state.starting,
            "startup_error": self.state.startup_error,
            "last_keyword": self.state.last_keyword,
            "last_song": self.state.last_song,
            "last_error": self.state.last_error,
            "last_playback_at": self.state.last_playback_at,
            "selected_dids": list(self.settings.selected_dids),
            "manual_target_dids": list(self.settings.manual_target_dids),
            "coco_base": self.settings.coco_base,
            "token_present": token_file.exists(),
            "account_configured": bool(self.settings.account and self.settings.password),
            "selected_device_present": selected_device_present,
            "devices": devices,
        }

    def events(self) -> list[dict]:
        return [
            {
                "at": item.at,
                "level": item.level,
                "message": repair_text(item.message),
                "keyword": item.keyword,
                "song": item.song,
            }
            for item in self.state.events
        ]
