from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .runtime import prepare_runtime

prepare_runtime()

from .service import CocoXiaoMusicService
from .settings import settings
from .stream_server import make_stream_server


class AccountRequest(BaseModel):
    account: str = ""
    password: str = ""
    hostname: str = ""


class DevicesRequest(BaseModel):
    selected_dids: list[str] = Field(default_factory=list)
    manual_target_dids: list[str] = Field(default_factory=list)


class KeywordRequest(BaseModel):
    keyword: str = ""
    providers: list[str] = Field(default_factory=list)


class PlaySelectedRequest(BaseModel):
    song: dict[str, Any] = Field(default_factory=dict)


class StrategyRequest(BaseModel):
    coco_base: str = ""
    admin_port: int = 8088
    takeover_mode: str = "keyword"
    delay: float = 0.0
    search_tts: str = ""
    found_tts: str = ""
    error_tts: str = ""
    coco_keywords: list[str] = Field(default_factory=list)


class CocoTestRequest(BaseModel):
    coco_base: str = ""


class SeekRequest(BaseModel):
    seconds: float = 0.0


class VolumeRequest(BaseModel):
    volume: int = 0


class AliasRequest(BaseModel):
    alias: str = ""


service = CocoXiaoMusicService(settings)
stream_handle = None
stream_task: asyncio.Task | None = None


def expected_token() -> str:
    return os.environ.get("COCO_XIAOMUSIC_API_TOKEN", "")


def require_token(authorization: str = Header(default="")):
    token = expected_token()
    if not token:
        return
    if authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="invalid token")


def primary_did() -> str:
    status = service.status()
    targets = status.get("manual_target_dids") or status.get("selected_dids") or []
    if targets:
        return str(targets[0])
    devices = status.get("devices") or []
    return str(devices[0]["did"]) if devices else ""


@asynccontextmanager
async def lifespan(_: FastAPI):
    global stream_handle, stream_task
    stream_handle = make_stream_server(service, settings)
    stream_task = asyncio.create_task(stream_handle.server.serve())
    await service.start()
    try:
        yield
    finally:
        if stream_handle:
            stream_handle.server.should_exit = True
        if stream_task:
            stream_task.cancel()
        await service.stop()


app = FastAPI(title="coco-xiaomusic-backend-service", lifespan=lifespan)


@app.get("/health", dependencies=[Depends(require_token)])
async def health():
    return {
        "ok": True,
        "ready": service.state.ready,
        "starting": service.state.starting,
        "stream_url": getattr(stream_handle, "url", ""),
    }


@app.get("/status", dependencies=[Depends(require_token)])
async def status():
    data = service.status()
    data["settings"] = settings.public_dict()
    data["sidecar_ready"] = True
    data["stream_url"] = getattr(stream_handle, "url", "")
    return data


@app.get("/events", dependencies=[Depends(require_token)])
async def events(limit: int = Query(default=120, ge=1, le=500)):
    return {"items": service.events()[:limit]}


@app.post("/search", dependencies=[Depends(require_token)])
async def search(request: KeywordRequest):
    keyword = request.keyword.strip()
    if not keyword:
        return {"items": []}
    return await service.search_preview(keyword, request.providers)


@app.post("/play/keyword", dependencies=[Depends(require_token)])
async def play_keyword(request: KeywordRequest):
    return await service.play_keyword(primary_did(), request.keyword)


@app.post("/play/selected", dependencies=[Depends(require_token)])
async def play_selected(request: PlaySelectedRequest):
    song = request.song
    return await service.play_selected_song(
        str(song.get("id", "")),
        str(song.get("provider", "")),
        str(song.get("title", "")),
        str(song.get("artist", "")),
        str(song.get("cover", "")),
        str(song.get("duration", "")),
        str(song.get("album", "")),
        str(song.get("audio_type", "")),
        str(song.get("bitrate", "")),
        list(settings.manual_target_dids),
    )


@app.post("/playback/pause", dependencies=[Depends(require_token)])
async def pause_playback():
    return await service.pause_playback()


@app.post("/playback/resume", dependencies=[Depends(require_token)])
async def resume_playback():
    return await service.resume_playback()


@app.post("/playback/stop", dependencies=[Depends(require_token)])
async def stop_playback():
    return await service.stop_playback()


@app.post("/playback/seek", dependencies=[Depends(require_token)])
async def seek_playback(request: SeekRequest):
    return await service.seek_playback(request.seconds)


@app.post("/playback/volume", dependencies=[Depends(require_token)])
async def set_volume(request: VolumeRequest):
    return await service.set_volume(request.volume)


@app.post("/account", dependencies=[Depends(require_token)])
async def save_account(request: AccountRequest):
    return await service.update_account(request.account, request.password, request.hostname)


@app.post("/devices", dependencies=[Depends(require_token)])
async def save_devices(request: DevicesRequest):
    return await service.select_devices(request.selected_dids, request.manual_target_dids)


@app.post("/devices/refresh", dependencies=[Depends(require_token)])
async def refresh_devices():
    return await service.refresh_devices()


@app.post("/devices/{did}/alias", dependencies=[Depends(require_token)])
async def rename_device(did: str, request: AliasRequest):
    return await service.rename_device(did, request.alias)


@app.post("/strategy", dependencies=[Depends(require_token)])
async def save_strategy(request: StrategyRequest):
    return await service.update_runtime_settings(
        request.coco_base,
        request.admin_port,
        request.takeover_mode,
        request.delay,
        request.search_tts,
        request.found_tts,
        request.error_tts,
        request.coco_keywords,
    )


@app.post("/test/coco", dependencies=[Depends(require_token)])
async def test_coco(request: CocoTestRequest):
    return await service.test_coco_connection(request.coco_base)


@app.delete("/events", dependencies=[Depends(require_token)])
async def clear_events():
    return service.clear_events()


def main():
    host = os.environ.get("COCO_XIAOMUSIC_CONTROL_HOST", "127.0.0.1")
    port = int(os.environ.get("COCO_XIAOMUSIC_CONTROL_PORT", "0") or "0")
    if port <= 0:
        port = 18731
    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
