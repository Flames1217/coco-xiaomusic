import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .service import CocoXiaoMusicService
from .settings import settings


def _resource_root() -> Path:
    configured = os.environ.get("COCO_XIAOMUSIC_RESOURCE_ROOT")
    if configured:
        return Path(configured).resolve()
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parent.parent


BASE_DIR = _resource_root()
MEDIA_DIR = Path.cwd() / "music" / "tmp"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
service = CocoXiaoMusicService(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await service.start()
    yield
    await service.stop()


app = FastAPI(title="coco-xiaomusic", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=BASE_DIR / "assets"), name="assets")
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (BASE_DIR / "views" / "dashboard.html").read_text(encoding="utf-8")
    return html


@app.get("/api/status")
async def api_status():
    return {"status": service.status(), "settings": settings.public_dict()}


@app.get("/api/events")
async def api_events():
    return {"items": service.events()}


@app.post("/api/events/clear")
async def api_clear_events():
    return service.clear_events()


@app.get("/api/search-preview")
async def api_search_preview(keyword: str):
    return await service.search_preview(keyword)


@app.get("/stream/{token}.mp3")
async def api_stream_audio(token: str):
    if not service.has_stream_source(token):
        raise HTTPException(status_code=404, detail="stream expired")
    chunks = service.stream_audio_chunks(token)
    return StreamingResponse(
        chunks,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "inline; filename=coco.mp3",
            "Cache-Control": "no-store",
            "Accept-Ranges": "none",
        },
    )


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@app.post("/api/play")
async def api_play(keyword: str = Form(...), target_dids: str = Form("")):
    if not service.state.ready:
        raise HTTPException(status_code=503, detail="service is still starting")
    targets = _parse_csv(target_dids) or list(settings.manual_target_dids) or list(settings.selected_dids)
    if not targets:
        raise HTTPException(status_code=409, detail="请先选择至少一台目标音箱")
    return await service.play_keyword(targets[0], keyword)


@app.post("/api/stop")
async def api_stop(target_dids: str = Form("")):
    return await service.stop_playback(_parse_csv(target_dids))


@app.post("/api/pause")
async def api_pause(target_dids: str = Form("")):
    return await service.pause_playback(_parse_csv(target_dids))


@app.post("/api/resume")
async def api_resume(target_dids: str = Form("")):
    return await service.resume_playback(_parse_csv(target_dids))


@app.post("/api/seek")
async def api_seek(position: float = Form(...), target_dids: str = Form("")):
    return await service.seek_playback(position, _parse_csv(target_dids))


@app.post("/api/volume")
async def api_volume(volume: int = Form(...), target_dids: str = Form("")):
    return await service.set_volume(volume, _parse_csv(target_dids))


@app.get("/api/player-status")
async def api_player_status(target_dids: str = ""):
    return await service.player_status(_parse_csv(target_dids))


@app.post("/api/setup/account")
async def api_setup_account(
    account: str = Form(...),
    password: str = Form(...),
    hostname: str = Form("http://192.168.1.13"),
):
    return await service.update_account(account, password, hostname)


@app.post("/api/setup/devices")
async def api_setup_devices(
    dids: str = Form(...),
    manual_target_dids: str = Form(""),
):
    return await service.select_devices(
        _parse_csv(dids),
        _parse_csv(manual_target_dids),
    )


@app.post("/api/setup/device-alias")
async def api_setup_device_alias(
    did: str = Form(...),
    alias: str = Form(""),
):
    return await service.rename_device(did, alias)


@app.post("/api/play-selected")
async def api_play_selected(
    song_id: str = Form(...),
    provider: str = Form(...),
    title: str = Form(""),
    artist: str = Form(""),
    cover: str = Form(""),
    duration: str = Form(""),
    album: str = Form(""),
    audio_type: str = Form(""),
    bitrate: str = Form(""),
    target_dids: str = Form(""),
):
    if not service.state.ready:
        raise HTTPException(status_code=503, detail="service is still starting")
    targets = _parse_csv(target_dids) or list(settings.manual_target_dids) or list(settings.selected_dids)
    if not targets:
        raise HTTPException(status_code=409, detail="请先选择至少一台目标音箱")
    return await service.play_selected_song(
        song_id,
        provider,
        title,
        artist,
        cover,
        duration,
        album,
        audio_type,
        bitrate,
        targets,
    )


@app.post("/api/setup/runtime")
async def api_setup_runtime(
    coco_base: str = Form(...),
    official_answer_delay_sec: float = Form(...),
    search_tts: str = Form(...),
    found_tts: str = Form(...),
    error_tts: str = Form(...),
):
    return await service.update_runtime_settings(
        coco_base,
        official_answer_delay_sec,
        search_tts,
        found_tts,
        error_tts,
    )
