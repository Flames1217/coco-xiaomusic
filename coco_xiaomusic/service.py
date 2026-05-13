import asyncio
import hashlib
import logging
import re
import shutil
import sys
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote, urlparse

import xiaomusic.xiaomusic as xm_module
from pypinyin import Style, lazy_pinyin
from rich.console import Console
from xiaomusic.command_handler import CommandHandler
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
    last_duration: float = 0.0
    last_position: float = 0.0
    last_used_url: str = ""
    last_seek_base_url: str = ""
    last_source_url: str = ""
    playback_paused: bool = False
    startup_error: str = ""
    discovered_devices: list[dict] = field(default_factory=list)
    events: deque[PlaybackEvent] = field(default_factory=lambda: deque(maxlen=120))


class CocoXiaoMusicService:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.coco = CocoClient(settings.coco_base)
        self.state = RuntimeState()
        self.xiaomusic: XiaoMusic | None = None
        self._runner_task: asyncio.Task | None = None
        self._mina_watch_task: asyncio.Task | None = None
        self._last_mina_timestamp: dict[str, int] = {}
        self._recent_voice_commands: dict[tuple[str, str], float] = {}
        self._pause_verify_tasks: dict[str, asyncio.Task] = {}
        self._stream_sources: dict[str, dict] = {}
        self._control_version = 0
        self._last_mina_error_log_at: dict[str, float] = {}
        self._patch_online_play()
        self._patch_command_observer()

    @staticmethod
    def _provider_priority(provider: str) -> int:
        table = {
            "gequhai": 1,
            "qq": 2,
            "qqmp3": 3,
            "jianbin-qq": 4,
            "jianbin-kuwo": 5,
            "jianbin-kugou": 6,
            "kuwo": 7,
            "kugou": 8,
            "migu": 9,
            "netease": 10,
            "livepoo": 10,
            "fangyin": 10,
        }
        return table.get((provider or "").lower(), 50)

    def _log(self, level: str, message: str, keyword: str = "", song: dict | None = None):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.state.events.appendleft(
            PlaybackEvent(
                at=timestamp,
                level=level,
                message=repair_text(message),
                keyword=repair_text(keyword),
                song=song,
            )
        )
        styles = {
            "ok": ("bold green", "OK"),
            "warn": ("bold yellow", "WARN"),
            "error": ("bold red", "ERROR"),
            "info": ("bold cyan", "INFO"),
        }
        style, prefix = styles.get(level, styles["info"])
        if getattr(sys.stdout, "isatty", lambda: False)():
            try:
                console.print(f"[{style}]{prefix}[/{style}] {message}")
            except UnicodeEncodeError:
                console.print(f"[{style}]{prefix}[/{style}] {repair_text(message)}")

    def _patch_online_play(self):
        async def coco_online_play(_, did="", arg1="", **kwargs):
            return await self.play_keyword(did, arg1)

        xm_module.OnlineMusicService.online_play = coco_online_play

    def _patch_command_observer(self):
        if getattr(CommandHandler.do_check_cmd, "_coco_observed", False):
            return

        original_do_check_cmd = CommandHandler.do_check_cmd

        async def observed_do_check_cmd(handler, did="", query="", ctrl_panel=True, **kwargs):
            cleaned = str(query or "").strip()
            if not ctrl_panel:
                self._log("info", f"收到语音问句：{cleaned}", keyword=cleaned)
            if cleaned and self._is_coco_command(cleaned):
                keyword = self._extract_coco_keyword(cleaned)
                if not keyword:
                    return
                dedupe_key = (str(did or ""), cleaned)
                now = time.monotonic()
                if now - self._recent_voice_commands.get(dedupe_key, 0) < 6:
                    self._log("info", f"重复语音事件已忽略：{cleaned}", keyword=cleaned)
                    return
                self._recent_voice_commands[dedupe_key] = now
                self._log("info", f"关键词命中，跳过官方处理链路：{cleaned}", keyword=cleaned)
                await self.play_keyword(did, keyword)
                return
            return await original_do_check_cmd(handler, did=did, query=query, ctrl_panel=ctrl_panel, **kwargs)

        observed_do_check_cmd._coco_observed = True
        CommandHandler.do_check_cmd = observed_do_check_cmd

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
        return re.sub(r"^(播放歌曲|播放|放|来一首|点歌|点一首|搜索)\s*", "", arg.strip())

    def _is_coco_command(self, query: str) -> bool:
        text = query.strip()
        lowered = text.lower()
        return any(keyword.lower() in lowered for keyword in self.settings.coco_keywords if keyword)

    def _extract_coco_keyword(self, query: str) -> str:
        text = query.strip()
        for keyword in sorted((item for item in self.settings.coco_keywords if item), key=len, reverse=True):
            index = text.lower().find(keyword.lower())
            if index >= 0:
                return self._clean_keyword(text[index + len(keyword):].strip())
        return self._clean_keyword(text)

    @staticmethod
    def _split_query(keyword: str) -> tuple[str, str]:
        if "的" not in keyword:
            return "", keyword.strip()
        artist, title = keyword.rsplit("的", 1)
        return artist.strip(), title.strip()

    @staticmethod
    def _compact_text(value: str) -> str:
        return re.sub(r"[\W_]+", "", (value or "").lower(), flags=re.UNICODE)

    @classmethod
    def _pinyin(cls, value: str, initials: bool = False) -> str:
        style = Style.FIRST_LETTER if initials else Style.NORMAL
        return "".join(lazy_pinyin(cls._compact_text(value), style=style, errors="ignore"))

    def _search_queries(self, keyword: str) -> list[str]:
        artist, title = self._split_query(keyword)
        queries = [keyword]
        if title:
            title_py = self._pinyin(title)
            title_initials = self._pinyin(title, initials=True)
            queries.extend([title, title_py, title_initials])
        if artist:
            artist_py = self._pinyin(artist)
            queries.extend([artist, artist_py, f"{artist} {title}", f"{title} {artist}"])
        return list(dict.fromkeys(item.strip() for item in queries if item and item.strip()))

    @staticmethod
    def _ratio(left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        return SequenceMatcher(None, left, right).ratio()

    def _song_match_score(self, keyword: str, song: CocoSong, index: int) -> float:
        query_artist, query_title = self._split_query(keyword)
        query_title = query_title or keyword
        title = song.title or ""
        artist = song.artist or ""
        raw_title = self._compact_text(title)
        raw_artist = self._compact_text(artist)
        raw_query_title = self._compact_text(query_title)
        raw_query_artist = self._compact_text(query_artist)
        title_py = self._pinyin(title)
        query_title_py = self._pinyin(query_title)
        title_initials = self._pinyin(title, initials=True)
        query_initials = self._pinyin(query_title, initials=True)
        artist_py = self._pinyin(artist)
        query_artist_py = self._pinyin(query_artist)

        title_score = max(
            self._ratio(raw_query_title, raw_title),
            self._ratio(query_title_py, title_py),
            self._ratio(query_initials, title_initials),
        )
        artist_score = max(
            self._ratio(raw_query_artist, raw_artist),
            self._ratio(query_artist_py, artist_py),
        ) if query_artist else 0.0
        contains_bonus = 0.0
        if raw_query_title and (raw_query_title in raw_title or raw_title in raw_query_title):
            contains_bonus += 0.18
        if query_title_py and (query_title_py in title_py or title_py in query_title_py):
            contains_bonus += 0.22
        if raw_query_artist and (raw_query_artist in raw_artist or raw_artist in raw_query_artist):
            contains_bonus += 0.22
        order_bonus = max(0.0, 0.08 - index * 0.002)
        cover_bonus = 0.03 if song.cover or (song.raw or {}).get("cover") else 0.0
        provider_bonus = 0.03 if song.provider in {"qq", "qqmp3", "jianbin-qq", "jianbin-kuwo", "jianbin-kugou", "kuwo", "kugou"} else 0.0
        score = title_score * 0.62 + artist_score * 0.28 + contains_bonus + order_bonus + cover_bonus + provider_bonus
        if query_artist and artist_score < 0.52:
            score -= 0.35
        return score

    async def _collect_ranked_songs(self, keyword: str) -> list[tuple[float, CocoSong, str]]:
        loop = asyncio.get_running_loop()
        ranked: dict[tuple[str, str], tuple[float, CocoSong, str]] = {}
        queries = self._search_queries(keyword)

        async def search_query(query_index: int, query: str):
            limit = None if query_index == 0 else 80
            try:
                songs = await loop.run_in_executor(None, self.coco.search_items, query, limit)
            except Exception as exc:
                self._log("warn", f"候选检索失败：{query} {exc!r}", keyword=keyword)
                return query_index, query, []
            return query_index, query, songs

        batches = await asyncio.gather(
            *(search_query(query_index, query) for query_index, query in enumerate(queries))
        )
        for query_index, query, songs in batches:
            for index, song in enumerate(songs):
                key = (song.provider, song.id)
                if not song.id or key in ranked:
                    continue
                score = self._song_match_score(keyword, song, index + query_index * 4)
                ranked[key] = (score, song, query)
        results = sorted(ranked.values(), key=lambda item: item[0], reverse=True)
        if len(queries) > 1:
            self._log("info", f"相关度召回：{len(results)} 条候选，使用 {len(queries)} 个搜索词", keyword=keyword)
        return results

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
        if self._mina_watch_task:
            self._mina_watch_task.cancel()
            self._mina_watch_task = None
        self.state.ready = False
        self.state.starting = False
        self.xiaomusic = None

    async def restart(self):
        await self.stop()
        self.state.startup_error = ""
        await self.start()

    async def _run(self):
        try:
            self._cleanup_temp_audio()
            self.xiaomusic = self._build_xiaomusic()
            await self.xiaomusic.reinit()
            await self._discover_devices()
            self.state.ready = True
            self.state.starting = False
            self.state.startup_error = ""
            self._log("ok", "xiaomusic 服务已就绪")
            self._mina_watch_task = asyncio.create_task(self._watch_mina_latest_ask())
            await self.xiaomusic.run_forever()
        except Exception as exc:
            self.state.ready = False
            self.state.starting = False
            self.state.startup_error = str(exc)
            self._log("error", f"xiaomusic 启动失败：{exc!r}")

    def _cleanup_temp_audio(self):
        temp_dir = Path("music/tmp")
        if not temp_dir.exists():
            return
        removed = 0
        cutoff = time.time() - 30
        for item in temp_dir.iterdir():
            if not item.is_file():
                continue
            if item.suffix.lower() not in {".mp3", ".aac", ".m4a", ".audio"}:
                continue
            if item.stat().st_mtime > cutoff and not item.name.startswith("coco-"):
                continue
            try:
                item.unlink()
                removed += 1
            except OSError:
                continue
        if removed:
            self._log("info", f"已清理历史临时语音文件 {removed} 个")

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

    async def _watch_mina_latest_ask(self):
        initialized: set[str] = set()
        while True:
            try:
                if not self.xiaomusic:
                    await asyncio.sleep(1)
                    continue
                auth_manager = getattr(self.xiaomusic, "auth_manager", None)
                mina_service = getattr(auth_manager, "mina_service", None)
                device_manager = getattr(self.xiaomusic, "device_manager", None)
                if not mina_service or not device_manager:
                    await asyncio.sleep(1)
                    continue
                for device_id, did in device_manager.device_id_did.items():
                    try:
                        messages = await mina_service.get_latest_ask(device_id)
                    except Exception as exc:
                        self._log("warn", f"Mina 拉取失败 did={did}：{exc!r}")
                        continue
                    pending: list[tuple[int, str]] = []
                    latest_ts = self._last_mina_timestamp.get(did, 0)
                    for message in messages or []:
                        timestamp = int(getattr(message, "timestamp_ms", 0) or 0)
                        if timestamp <= latest_ts:
                            continue
                        answers = getattr(getattr(message, "response", None), "answer", []) or []
                        if not answers:
                            continue
                        query = str(getattr(answers[0], "question", "") or "").strip()
                        if query:
                            pending.append((timestamp, query))
                    if did not in initialized:
                        if pending:
                            self._last_mina_timestamp[did] = max(item[0] for item in pending)
                        initialized.add(did)
                        continue
                    for timestamp, query in sorted(pending):
                        self._last_mina_timestamp[did] = max(self._last_mina_timestamp.get(did, 0), timestamp)
                        self._log("info", f"Mina 捕获语音：{query}", keyword=query)
                        await self.xiaomusic.do_check_cmd(did=did, query=query, ctrl_panel=False)
                await asyncio.sleep(0.2)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._log("warn", f"Mina 监听循环异常：{exc!r}")
                await asyncio.sleep(2)

    async def play_keyword(self, did: str, keyword: str):
        if not self.xiaomusic:
            return {"success": False, "error": "xiaomusic not ready"}

        keyword = self._clean_keyword(keyword)
        if not keyword:
            self.state.last_error = "empty keyword"
            self._log("error", "没有识别到歌曲关键词")
            return {"success": False, "error": "empty keyword"}

        self.state.last_keyword = keyword
        self.state.last_error = ""
        self._log("info", f"coco 搜索：{keyword}", keyword=keyword)

        search_task = asyncio.create_task(self._collect_ranked_songs(keyword))
        device = await self._take_over_device(did)
        if not device:
            search_task.cancel()
            self.state.last_error = "device not found"
            return {"success": False, "error": "device not found"}

        await self._speak_if_needed(device, self.settings.search_tts, keyword=keyword, artist="", title="")

        try:
            ranked = await search_task
        except Exception as exc:
            self.state.last_error = str(exc)
            self._log("error", f"coco 请求失败：{exc!r}", keyword=keyword)
            await self._speak_if_needed(device, self.settings.error_tts, keyword=keyword, artist="", title="")
            return {"success": False, "error": str(exc)}

        if not ranked:
            self.state.last_error = "not found"
            self._log("error", f"coco 没搜到：{keyword}", keyword=keyword)
            await self._speak_if_needed(device, self.settings.error_tts, keyword=keyword, artist="", title="")
            return {"success": False, "error": "not found"}

        last_error = ""
        for index, (score, song, matched_query) in enumerate(ranked[:80]):
            try:
                url = await asyncio.get_running_loop().run_in_executor(None, self.coco.resolve_url, song)
            except Exception as exc:
                last_error = repr(exc)
                self._log("warn", f"候选解析失败：{song.title} - {song.artist} [{song.provider}] {exc!r}", keyword=keyword, song=song.raw)
                continue
            if not url:
                last_error = "no url"
                self._log("warn", f"候选无直链：{song.title} - {song.artist} [{song.provider}]", keyword=keyword, song=song.raw)
                continue
            local_url = self._stream_url_for_speaker(url, song)
            if index > 0:
                self._log("warn", f"前 {index} 条候选不可用，已切到可推送结果：{song.title} - {song.artist} [{song.provider}]", keyword=keyword, song=song.raw)
            if matched_query != keyword:
                self._log("info", f"相关度命中：{song.title} - {song.artist} [{song.provider}]，搜索词={matched_query}，得分={score:.2f}", keyword=keyword, song=song.raw)
            await self._speak_if_needed(device, self.settings.found_tts, keyword=keyword, artist=song.artist, title=song.title)
            result = await self._play_song(did, keyword, song, url, local_url=local_url)
            if result.get("success"):
                return result
            last_error = result.get("error") or str(result)

        self.state.last_error = last_error or "no playable candidate"
        await self._speak_if_needed(device, self.settings.error_tts, keyword=keyword, artist="", title="")
        return {"success": False, "error": self.state.last_error}

    async def _play_song(self, did: str, keyword: str, song: CocoSong, url: str, local_url: str | None = None):
        self.state.last_song = song.raw
        self.state.last_duration = self._song_duration_seconds(song.raw or {})
        self.state.last_position = 0.0
        self.state.last_playback_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._log("ok", f"coco 第一条：{song.title} - {song.artist} [{song.provider}]", keyword=keyword, song=song.raw)

        suffix = Path(urlparse(url).path).suffix.lower() or "无后缀"
        self._log("info", f"准备推送音源格式：{suffix}", keyword=keyword, song=song.raw)

        self._next_control_version()
        results = await self._play_url_to_targets(url, [did], song, take_over=False, prepared_url=local_url)
        target = results[0] if results else {"success": False}
        if not target.get("success"):
            self.state.last_error = f"target failed: {target!r}"
            self._log("error", f"推送失败：did={did}，状态={target.get('status')!r}", keyword=keyword, song=song.raw)
            return {"success": False, "song": song.raw, "url": url, "targets": results}

        status = target.get("status", {})
        volume = status.get("volume")
        self.state.last_used_url = target.get("used_url") or local_url or url
        self.state.last_seek_base_url = url
        self.state.last_source_url = url
        self.state.playback_paused = False
        self._log("ok", f"已推送并确认音箱进入播放态（did={did}，音量={volume}）", keyword=keyword, song=song.raw)
        return {"success": True, "song": song.raw, "url": url, "targets": results}

    @staticmethod
    def _find_ffmpeg() -> str:
        candidates = [
            Path("ffmpeg/bin/ffmpeg.exe"),
            Path("ffmpeg.exe"),
            Path("D:/Best/ffmpeg/bin/ffmpeg.exe"),
            Path("D:/Best/ffmpeg/ffmpeg.exe"),
        ]
        found = shutil.which("ffmpeg")
        if found:
            return found
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        raise RuntimeError("ffmpeg not found")

    @staticmethod
    def _song_duration_seconds(raw: dict) -> float:
        value = (
            raw.get("duration")
            or raw.get("interval")
            or raw.get("time")
            or raw.get("songTimeMinutes")
            or raw.get("song_time")
            or raw.get("extra", {}).get("duration")
            or 0
        )
        if isinstance(value, (int, float)):
            seconds = float(value)
            return seconds / 1000 if seconds > 10000 else seconds
        text = str(value).strip()
        if not text:
            return 0.0
        parts = text.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            seconds = float(text)
            return seconds / 1000 if seconds > 10000 else seconds
        except ValueError:
            return 0.0

    def _current_position_seconds(self) -> float:
        if self.state.playback_paused:
            return max(0.0, self.state.last_position)
        if not self.state.last_playback_at:
            return 0.0
        try:
            started = datetime.strptime(self.state.last_playback_at, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return max(0.0, self.state.last_position)
        elapsed = max(0.0, (datetime.now() - started).total_seconds())
        if self.state.last_duration > 0:
            elapsed = min(elapsed, self.state.last_duration)
        return elapsed

    def _media_url_for(self, filepath: Path) -> str:
        media_root = Path("music/tmp").resolve()
        relative = filepath.resolve().relative_to(media_root).as_posix()
        base = self.settings.hostname.rstrip("/")
        return f"{base}:{self.settings.admin_port}/media/{quote(relative)}"

    def _stream_url_for_speaker(self, url: str, song: CocoSong | None = None, offset: float = 0.0) -> str:
        now = time.time()
        for token, entry in list(self._stream_sources.items()):
            if now - float(entry.get("created", 0)) > 3600:
                self._stream_sources.pop(token, None)
        key = f"{url}:{offset:.3f}:{now:.6f}"
        token = hashlib.sha1(key.encode("utf-8")).hexdigest()[:28]
        self._stream_sources[token] = {
            "url": url,
            "offset": max(0.0, float(offset or 0)),
            "created": now,
            "song": song.raw if song and isinstance(song.raw, dict) else {},
        }
        base = self.settings.hostname.rstrip("/")
        return f"{base}:{self.settings.admin_port}/stream/{token}.mp3"

    def has_stream_source(self, token: str) -> bool:
        return token in self._stream_sources

    def stream_audio_chunks(self, token: str):
        entry = self._stream_sources.get(token)
        if not entry:
            raise KeyError(token)
        url = str(entry["url"])
        offset = max(0.0, float(entry.get("offset") or 0))
        headers = "\r\n".join(
            [
                "User-Agent: Mozilla/5.0",
                "Accept: */*",
                f"Referer: {self.settings.coco_base.rstrip('/')}/",
                f"Origin: {self.settings.coco_base.rstrip('/')}",
                "",
            ]
        )
        command = [
            self._find_ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-reconnect",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            "5",
            "-headers",
            headers,
        ]
        if offset > 0:
            command.extend(["-ss", f"{offset:.3f}"])
        command.extend(
            [
                "-i",
                url,
                "-vn",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "128k",
                "-ar",
                "44100",
                "-f",
                "mp3",
                "pipe:1",
            ]
        )
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        try:
            if not process.stdout:
                return
            while True:
                chunk = process.stdout.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    def _make_seek_audio(self, seconds: float) -> str:
        source_url = self.state.last_source_url or self.state.last_seek_base_url or self.state.last_used_url
        if not source_url:
            raise RuntimeError("current stream does not support seeking")
        duration = max(0.0, self.state.last_duration)
        offset = max(0.0, float(seconds))
        if duration > 0:
            offset = min(offset, max(0.0, duration - 1))
        return self._stream_url_for_speaker(source_url, offset=offset)

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

    async def _speak_if_needed(self, device, template: str, keyword: str, artist: str, title: str):
        text = (template or "").strip()
        if not text:
            return
        text = text.format(keyword=keyword, artist=artist or "未知歌手", title=title or "未知歌曲")
        try:
            from xiaomusic.utils.network_utils import text_to_mp3

            mp3_path = await text_to_mp3(
                text=text,
                save_dir=self.xiaomusic.config.temp_dir,
                voice=self.settings.edge_tts_voice,
            )
            tts_url = self._media_url_for(Path(mp3_path))
            await device.group_player_play(tts_url)
            speech_seconds = max(1.2, min(5.5, len(text) / 4.5))
            asyncio.create_task(self._delete_temp_file_later(Path(mp3_path), delay=int(speech_seconds + 6)))
            await asyncio.sleep(speech_seconds)
            if self.settings.official_answer_delay_sec > 0:
                await asyncio.sleep(self.settings.official_answer_delay_sec)
            self._log("info", f"提示话术：{text}")
        except Exception as exc:
            self._log("warn", f"提示话术失败：{exc!r}")

    async def _delete_temp_file_later(self, filepath: Path, delay: int = 90):
        await asyncio.sleep(delay)
        for _ in range(6):
            try:
                if filepath.exists():
                    filepath.unlink()
                return
            except OSError:
                await asyncio.sleep(2)

    async def search_preview(self, keyword: str):
        songs = await asyncio.get_running_loop().run_in_executor(None, self.coco.search_items, keyword, None)
        loop = asyncio.get_running_loop()
        enrich_count = min(len(songs), 80)
        enrich_tasks = [loop.run_in_executor(None, self.coco.resolve_info, song) for song in songs[:enrich_count]]
        enrich_results = await asyncio.gather(*enrich_tasks, return_exceptions=True)
        preview = []
        for index, song in enumerate(songs):
            has_url = None
            if index < enrich_count:
                result = enrich_results[index]
                has_url = isinstance(result, dict) and bool(result.get("url"))
            preview.append(
                {
                    "item": song.raw,
                    "is_first": index == 0,
                    "has_url": has_url,
                }
            )
        return {"items": preview}

    def _manual_targets(self, requested: list[str] | None = None) -> list[str]:
        candidates = requested or list(self.settings.manual_target_dids) or list(self.settings.selected_dids)
        return [did for did in candidates if did]

    async def _play_url_to_targets(
        self,
        url: str,
        target_dids: list[str],
        song: CocoSong,
        take_over: bool = True,
        prepared_url: str | None = None,
    ):
        results = []
        local_url = prepared_url
        if not local_url:
            local_url = self._stream_url_for_speaker(url, song)

        for did in target_dids:
            if take_over:
                device = await self._take_over_device(did)
                if not device:
                    results.append({"did": did, "success": False, "error": "device not found"})
                    continue
            push_ret = await self.xiaomusic.play_url(did, local_url)
            status = await self._poll_player_status(did, max_tries=3, assume_playing=self._extract_code(push_ret) == 0)
            results.append(
                {
                    "did": did,
                    "success": status.get("status") == 1,
                    "status": status,
                    "push_result": push_ret,
                    "used_url": local_url,
                }
            )
            self._log(
                "info",
                f"播放下发结果：did={did} code={self._extract_code(push_ret)} status={status.get('status')}",
                song=song.raw,
            )
        return results

    async def _poll_player_status(self, did: str, max_tries: int = 3, assume_playing: bool = False):
        status = {}
        for index in range(max_tries):
            try:
                status = await self.xiaomusic.get_player_status(did=did)
            except Exception as exc:
                return self._fallback_player_status(did, exc, assume_playing=assume_playing)
            if status.get("status") == 1:
                return status
            if index + 1 < max_tries:
                await asyncio.sleep(1.0)
        return status

    def _fallback_player_status(self, did: str, exc: Exception | None = None, assume_playing: bool = False) -> dict:
        if exc is not None:
            now = time.monotonic()
            last = self._last_mina_error_log_at.get(did, 0)
            if now - last > 30:
                self._last_mina_error_log_at[did] = now
                self._log("warn", f"Mina 拉取失败 did={did}，播放器使用本地状态兜底：{exc!r}")
        return {
            "status": 2 if self.state.playback_paused else (1 if (assume_playing or self.state.last_used_url) else 0),
            "volume": None,
            "loop_type": 1,
            "local_fallback": True,
        }

    def _cancel_pause_verify(self, did: str):
        task = self._pause_verify_tasks.pop(did, None)
        if task and not task.done():
            task.cancel()

    def _next_control_version(self) -> int:
        self._control_version += 1
        return self._control_version

    async def _verify_pause_or_stop(self, did: str, paused_at: float, version: int, delay: float = 0.8):
        try:
            await asyncio.sleep(delay)
            if version != self._control_version or not self.state.playback_paused:
                return
            device = self.xiaomusic.device_manager.devices.get(did) if self.xiaomusic else None
            if not device:
                return
            status = await self._poll_player_status(did, max_tries=1)
            if status.get("status") != 1 or version != self._control_version or not self.state.playback_paused:
                return
            device_ids = self.xiaomusic.device_manager.get_group_device_id_list(device.group_name)
            for device_id in device_ids:
                await device.auth_manager.mina_service.player_stop(device_id)
            if version == self._control_version and self.state.playback_paused:
                self.state.last_position = paused_at
                self._log("info", "设备未响应 pause，已后台静默 stop 并保留进度")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._log("warn", f"后台暂停确认失败：{exc!r}")

    async def _verify_resume_or_replay(self, did: str, version: int, resumed_from: float, delay: float = 0.7):
        try:
            await asyncio.sleep(delay)
            if version != self._control_version or self.state.playback_paused:
                return
            status = await self._poll_player_status(did, max_tries=1)
            if status.get("status") == 1 or version != self._control_version or self.state.playback_paused:
                return
            replay_url = self._make_seek_audio(resumed_from) if resumed_from > 1 else self.state.last_used_url
            await self.xiaomusic.play_url(did, replay_url)
            if version == self._control_version and not self.state.playback_paused:
                self.state.last_used_url = replay_url
                self._log("info", "设备未响应 play，已后台从保留进度重推")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._log("warn", f"后台续播确认失败：{exc!r}")

    @staticmethod
    def _extract_code(push_ret):
        if isinstance(push_ret, dict):
            data = push_ret.get("data")
            if isinstance(data, dict) and "code" in data:
                return data["code"]
            if "code" in push_ret:
                return push_ret["code"]
        if isinstance(push_ret, list) and push_ret:
            return CocoXiaoMusicService._extract_code(push_ret[0])
        return "?"

    async def play_selected_song(
        self,
        song_id: str,
        provider: str,
        title: str,
        artist: str,
        cover: str = "",
        duration: str = "",
        album: str = "",
        audio_type: str = "",
        bitrate: str = "",
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
            album=album,
            cover=cover,
            duration=duration,
            audio_type=audio_type,
            bitrate=bitrate,
            raw={
                "id": song_id,
                "provider": provider,
                "title": title,
                "artist": artist,
                "album": album,
                "cover": cover,
                "duration": duration,
                "audio_type": audio_type,
                "bitrate": bitrate,
            },
        )
        try:
            url = await asyncio.get_running_loop().run_in_executor(None, self.coco.resolve_url, song)
        except Exception as exc:
            self.state.last_error = str(exc)
            self._log("error", f"指定歌曲解析失败：{exc!r}", song=song.raw)
            return {"success": False, "error": str(exc)}
        if not url:
            self.state.last_error = "selected song has no url"
            self._log("error", f"指定歌曲没有直链：{title} - {artist} [{provider}]", song=song.raw)
            return {"success": False, "error": "selected song has no url"}

        self._next_control_version()
        results = await self._play_url_to_targets(url, target_dids, song)
        if not any(item["success"] for item in results):
            return {"success": False, "error": "all target devices failed", "targets": results}
        self.state.last_song = song.raw
        self.state.last_duration = self._song_duration_seconds(song.raw or {})
        self.state.last_position = 0.0
        self.state.last_playback_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        first_success = next((item for item in results if item.get("success")), {})
        self.state.last_used_url = first_success.get("used_url", "")
        self.state.last_seek_base_url = url
        self.state.last_source_url = url
        self.state.playback_paused = False
        self._log("ok", f"前端手动推送：{title} - {artist} [{provider}]", song=song.raw)
        return {"success": True, "song": song.raw, "url": url, "targets": results}

    async def stop_playback(self, target_dids: list[str] | None = None):
        if not self.xiaomusic:
            return {"success": False, "error": "xiaomusic not ready"}
        targets = self._manual_targets(target_dids)
        self._next_control_version()
        results = []
        for did in targets:
            device = await self._take_over_device(did)
            results.append({"did": did, "success": bool(device)})
        if any(item["success"] for item in results):
            self.state.last_position = self._current_position_seconds()
            self.state.playback_paused = True
            self._log("ok", "已停止当前推流")
        return {"success": any(item["success"] for item in results), "targets": results}

    async def pause_playback(self, target_dids: list[str] | None = None):
        if not self.xiaomusic:
            return {"success": False, "error": "xiaomusic not ready"}
        targets = self._manual_targets(target_dids)
        results = []
        paused_at = self._current_position_seconds()
        version = self._next_control_version()
        for did in targets:
            self._cancel_pause_verify(did)
            device = self.xiaomusic.device_manager.devices.get(did)
            if not device:
                results.append({"did": did, "success": False, "error": "device not found"})
                continue
            try:
                device_ids = self.xiaomusic.device_manager.get_group_device_id_list(device.group_name)
                ret = []
                for device_id in device_ids:
                    ret.append(await device.auth_manager.mina_service.player_pause(device_id))
                results.append({"did": did, "success": True, "ret": ret})
            except Exception as exc:
                results.append({"did": did, "success": False, "error": repr(exc)})
        if any(item["success"] for item in results):
            self.state.last_position = paused_at
            self.state.playback_paused = True
            for item in results:
                if item.get("success") and item.get("did"):
                    self._pause_verify_tasks[item["did"]] = asyncio.create_task(self._verify_pause_or_stop(item["did"], paused_at, version))
            self._log("ok", "已暂停当前推流")
        return {"success": any(item["success"] for item in results), "targets": results}

    async def resume_playback(self, target_dids: list[str] | None = None):
        if not self.xiaomusic:
            return {"success": False, "error": "xiaomusic not ready"}
        if not self.state.last_used_url:
            return {"success": False, "error": "no previous stream url"}
        targets = self._manual_targets(target_dids)
        results = []
        resumed_from = max(0.0, self.state.last_position)
        version = self._next_control_version()
        for did in targets:
            self._cancel_pause_verify(did)
            device = self.xiaomusic.device_manager.devices.get(did)
            if not device:
                results.append({"did": did, "success": False, "error": "device not found"})
                continue
            try:
                device_ids = self.xiaomusic.device_manager.get_group_device_id_list(device.group_name)
                ret = []
                for device_id in device_ids:
                    ret.append(await device.auth_manager.mina_service.player_play(device_id))
                asyncio.create_task(self._verify_resume_or_replay(did, version, resumed_from))
                results.append({"did": did, "success": True, "ret": ret})
            except Exception as exc:
                results.append({"did": did, "success": False, "error": repr(exc)})
        if any(item["success"] for item in results):
            self.state.playback_paused = False
            self.state.last_playback_at = (datetime.now() - timedelta(seconds=resumed_from)).strftime("%Y-%m-%d %H:%M:%S")
            self._log("ok", "已继续播放上一次推流")
        return {"success": any(item["success"] for item in results), "targets": results}

    async def seek_playback(self, position: float, target_dids: list[str] | None = None):
        if not self.xiaomusic:
            return {"success": False, "error": "xiaomusic not ready"}
        targets = self._manual_targets(target_dids)
        try:
            seek_url = await asyncio.get_running_loop().run_in_executor(None, self._make_seek_audio, position)
        except Exception as exc:
            self.state.last_error = repr(exc)
            self._log("error", f"进度跳转失败：{exc!r}")
            return {"success": False, "error": repr(exc)}
        results = []
        for did in targets:
            try:
                ret = await self.xiaomusic.play_url(did, seek_url)
                status = await self._poll_player_status(did, max_tries=3, assume_playing=self._extract_code(ret) == 0)
                results.append({"did": did, "success": status.get("status") == 1, "ret": ret, "status": status})
            except Exception as exc:
                results.append({"did": did, "success": False, "error": repr(exc)})
        if any(item["success"] for item in results):
            self.state.last_position = max(0.0, float(position))
            self.state.last_playback_at = (datetime.now() - timedelta(seconds=self.state.last_position)).strftime("%Y-%m-%d %H:%M:%S")
            self.state.last_used_url = seek_url
            self.state.playback_paused = False
            self._log("ok", f"已跳转到 {self.state.last_position:.1f}s 继续播放")
        return {"success": any(item["success"] for item in results), "targets": results}

    async def set_volume(self, volume: int, target_dids: list[str] | None = None):
        if not self.xiaomusic:
            return {"success": False, "error": "xiaomusic not ready"}
        volume = max(0, min(100, int(volume)))
        targets = self._manual_targets(target_dids)
        results = []
        for did in targets:
            device = self.xiaomusic.device_manager.devices.get(did)
            if not device:
                results.append({"did": did, "success": False, "error": "device not found"})
                continue
            try:
                device_ids = self.xiaomusic.device_manager.get_group_device_id_list(device.group_name)
                ret = []
                for device_id in device_ids:
                    ret.append(await device.auth_manager.mina_service.player_set_volume(device_id, volume))
                results.append({"did": did, "success": True, "ret": ret, "volume": volume})
            except Exception as exc:
                results.append({"did": did, "success": False, "error": repr(exc)})
        return {"success": any(item["success"] for item in results), "targets": results}

    async def player_status(self, target_dids: list[str] | None = None):
        if not self.xiaomusic:
            return {"success": False, "error": "xiaomusic not ready", "targets": []}
        targets = self._manual_targets(target_dids)
        results = []
        for did in targets:
            try:
                status = await self.xiaomusic.get_player_status(did=did)
                results.append({"did": did, "success": True, "status": status})
            except Exception as exc:
                results.append(
                    {
                        "did": did,
                        "success": True,
                        "warning": repr(exc),
                        "status": self._fallback_player_status(did, exc),
                    }
                )
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
        cleaned_manual = tuple(did for did in dict.fromkeys((manual_targets or dids)) if did in cleaned_dids)
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
        self.settings.search_tts = search_tts.strip()
        self.settings.found_tts = found_tts.strip()
        self.settings.error_tts = error_tts.strip()
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
                raw_name = repair_text(getattr(raw_device, "name", "") or getattr(device, "group_name", ""))
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
            "last_duration": self.state.last_duration,
            "last_position": self._current_position_seconds(),
            "last_used_url": self.state.last_used_url,
            "last_seek_base_url": self.state.last_seek_base_url,
            "last_source_url": self.state.last_source_url,
            "playback_paused": self.state.playback_paused,
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

    def clear_events(self) -> dict:
        self.state.events.clear()
        return {"success": True}
