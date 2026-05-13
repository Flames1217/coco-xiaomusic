from dataclasses import dataclass

import requests


@dataclass
class CocoSong:
    id: str
    provider: str
    title: str = ""
    artist: str = ""
    raw: dict | None = None


class CocoClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def search_items(self, keyword: str, limit: int | None = None) -> list[CocoSong]:
        items = requests.get(
            f"{self.base_url}/api/search",
            params={"q": keyword},
            timeout=15,
        ).json().get("items", [])
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
        play_info = requests.get(
            f"{self.base_url}/api/url",
            params={"id": song.id, "provider": song.provider},
            timeout=15,
        ).json()
        return play_info.get("url")

    def search_first(self, keyword: str) -> tuple[CocoSong | None, str | None]:
        songs = self.search_items(keyword, limit=1)
        if not songs:
            return None, None
        song = songs[0]
        return song, self.resolve_url(song)
