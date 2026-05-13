from dataclasses import dataclass
from difflib import SequenceMatcher
import time
from urllib.parse import urlparse

import requests


@dataclass
class CocoSong:
    id: str
    provider: str
    title: str = ""
    artist: str = ""
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
            songs.append(
                CocoSong(
                    id=str(item.get("id", "")),
                    provider=str(item.get("provider", "")),
                    title=str(item.get("title", "")),
                    artist=str(item.get("artist", "")),
                    raw=item,
                )
            )
        return songs

    def resolve_url(self, song: CocoSong) -> str | None:
        play_info = self._get_json(
            "/api/url",
            params={"id": song.id, "provider": song.provider},
            timeout=15,
            attempts=2,
        )
        return play_info.get("url")

    def search_first(self, keyword: str) -> tuple[CocoSong | None, str | None]:
        songs = self.search_items(keyword, limit=1)
        if not songs:
            return None, None
        song = songs[0]
        return song, self.resolve_url(song)

    def search_best(self, keyword: str, alternatives: list[str] | None = None) -> tuple[CocoSong | None, str | None, str]:
        queries = [keyword, *(alternatives or [])]
        seen = set()
        candidates: list[tuple[float, CocoSong, str]] = []
        last_error = None
        for query in queries:
            query = query.strip()
            if not query or query in seen:
                continue
            seen.add(query)
            try:
                songs = self.search_items(query, limit=5)
            except requests.RequestException as exc:
                last_error = exc
                continue
            for song in songs:
                haystack = f"{song.artist}{song.title}"
                score = SequenceMatcher(None, query, haystack).ratio()
                candidates.append((score, song, query))
        if not candidates:
            if last_error is not None:
                raise last_error
            return None, None, keyword
        candidates.sort(key=lambda item: item[0], reverse=True)
        fallback: tuple[CocoSong, str, str] | None = None
        for _, song, query in candidates:
            url = self.resolve_url(song)
            if not url:
                continue
            if fallback is None:
                fallback = (song, url, query)
            suffix = urlparse(url).path.lower()
            extension = next((ext for ext in self.SUPPORTED_EXTENSIONS if suffix.endswith(ext)), "")
            if extension or "." not in suffix.rsplit("/", 1)[-1]:
                return song, url, query
        if fallback is not None:
            return fallback
        return None, None, keyword
