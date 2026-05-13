from dataclasses import dataclass
import re
import time

import requests


@dataclass
class CocoSong:
    id: str
    provider: str
    title: str = ""
    artist: str = ""
    album: str = ""
    cover: str = ""
    duration: str | int | float = ""
    audio_type: str = ""
    bitrate: str = ""
    raw: dict | None = None


class CocoClient:
    SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".wav", ".ape", ".ogg", ".m4a", ".wma"}
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def _get_json(self, path: str, *, params: dict, timeout: int = 15, attempts: int = 2) -> dict:
        last_error = None
        for attempt in range(attempts):
            try:
                response = requests.get(
                    f"{self.base_url}{path}",
                    params=params,
                    timeout=timeout,
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(0.6 * (attempt + 1))
        raise last_error

    def search_items(self, keyword: str, limit: int | None = None) -> list[CocoSong]:
        items = self._get_json(
            "/api/search",
            params={"q": keyword},
            timeout=15,
            attempts=2,
        ).get("items", [])
        songs = []
        source_items = items if limit is None else items[:limit]
        for item in source_items:
            cover = str(item.get("cover") or item.get("extra", {}).get("cover") or "")
            duration = (
                item.get("duration")
                or item.get("interval")
                or item.get("time")
                or item.get("songTimeMinutes")
                or item.get("song_time")
                or item.get("extra", {}).get("duration")
                or ""
            )
            songs.append(
                CocoSong(
                    id=str(item.get("id", "")),
                    provider=str(item.get("provider", "")),
                    title=str(item.get("title", "")),
                    artist=str(item.get("artist", "")),
                    album=str(item.get("album", "")),
                    cover=cover,
                    duration=duration,
                    raw=item,
                )
            )
        return songs

    def resolve_info(self, song: CocoSong) -> dict:
        play_info = self._get_json(
            "/api/url",
            params={"id": song.id, "provider": song.provider},
            timeout=8,
            attempts=1,
        )
        cover = play_info.get("cover")
        if cover and song.raw is not None and not song.raw.get("cover"):
            song.raw["cover"] = cover
            song.cover = str(cover)
        audio_type = play_info.get("type") or play_info.get("format")
        bitrate = play_info.get("bitrate") or play_info.get("quality")
        duration = play_info.get("duration") or play_info.get("interval") or play_info.get("time")
        if not duration and play_info.get("url") and bitrate:
            duration = self._estimate_duration(play_info["url"], str(bitrate))
        if song.raw is not None:
            if audio_type:
                song.raw["audio_type"] = str(audio_type)
            if bitrate:
                song.raw["bitrate"] = str(bitrate)
            if duration and not song.raw.get("duration"):
                song.raw["duration"] = duration
        song.audio_type = str(audio_type or song.audio_type or "")
        song.bitrate = str(bitrate or song.bitrate or "")
        if duration and not song.duration:
            song.duration = duration
        return play_info

    @staticmethod
    def _bitrate_to_bps(value: str) -> int:
        match = re.search(r"(\d+(?:\.\d+)?)\s*k", value.lower())
        if match:
            return int(float(match.group(1)) * 1000)
        match = re.search(r"(\d+(?:\.\d+)?)\s*m", value.lower())
        if match:
            return int(float(match.group(1)) * 1000 * 1000)
        return 0

    def _estimate_duration(self, url: str, bitrate: str) -> int | None:
        bits_per_second = self._bitrate_to_bps(bitrate)
        if not bits_per_second:
            return None
        try:
            response = requests.head(
                url,
                allow_redirects=True,
                timeout=5,
                headers={"User-Agent": "coco-xiaomusic/1.0"},
            )
            size = int(response.headers.get("content-length") or 0)
        except (requests.RequestException, ValueError):
            return None
        if size <= 0:
            return None
        return max(1, round(size * 8 / bits_per_second))

    def resolve_url(self, song: CocoSong) -> str | None:
        return self.resolve_info(song).get("url")

    def is_playable_url(self, url: str) -> bool:
        try:
            response = requests.get(
                url,
                headers={"Range": "bytes=0-31", "User-Agent": "coco-xiaomusic/1.0"},
                stream=True,
                timeout=8,
            )
            if response.status_code >= 400:
                return False
            content_type = response.headers.get("content-type", "").lower()
            chunk = next(response.iter_content(32), b"")
            if chunk.lstrip().startswith((b"{", b"<")):
                return False
            return (
                "audio" in content_type
                or chunk.startswith((b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"fLaC", b"OggS", b"RIFF"))
            )
        except requests.RequestException:
            return False

    def search_first(self, keyword: str) -> tuple[CocoSong | None, str | None]:
        songs = self.search_items(keyword, limit=1)
        if not songs:
            return None, None
        song = songs[0]
        return song, self.resolve_url(song)
