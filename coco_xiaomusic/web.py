from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .service import CocoXiaoMusicService
from .settings import settings


BASE_DIR = Path(__file__).resolve().parent.parent
service = CocoXiaoMusicService(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await service.start()
    yield
    await service.stop()


app = FastAPI(title="coco-xiaomusic", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=BASE_DIR / "assets"), name="assets")


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


@app.get("/api/search-preview")
async def api_search_preview(keyword: str):
    return await service.search_preview(keyword)


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@app.post("/api/play")
async def api_play(keyword: str = Form(...), target_dids: str = Form("")):
    if not service.state.ready:
        raise HTTPException(status_code=503, detail="service is still starting")
    targets = _parse_csv(target_dids) or list(settings.manual_target_dids) or list(settings.selected_dids)
    if not targets:
        raise HTTPException(status_code=409, detail="请先选择目标音箱")
    return await service.play_keyword(targets[0], keyword)


@app.post("/api/stop")
async def api_stop(target_dids: str = Form("")):
    return await service.stop_playback(_parse_csv(target_dids))


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
    target_dids: str = Form(""),
):
    if not service.state.ready:
        raise HTTPException(status_code=503, detail="service is still starting")
    targets = _parse_csv(target_dids) or list(settings.manual_target_dids) or list(settings.selected_dids)
    if not targets:
        raise HTTPException(status_code=409, detail="请先选择目标音箱")
    return await service.play_selected_song(song_id, provider, title, artist, targets)


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
