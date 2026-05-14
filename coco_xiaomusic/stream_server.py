from dataclasses import dataclass
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .service import CocoXiaoMusicService
from .settings import AppSettings


@dataclass
class StreamServerHandle:
    server: uvicorn.Server
    url: str


def create_stream_app(service: CocoXiaoMusicService) -> FastAPI:
    media_dir = Path.cwd() / "music" / "tmp"
    media_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="coco-xiaomusic-stream")
    app.mount("/media", StaticFiles(directory=media_dir), name="media")

    @app.get("/health")
    async def health():
        return {"ok": True, "ready": service.state.ready}

    @app.get("/stream/{token}.mp3")
    async def stream_audio(token: str):
        if not service.has_stream_source(token):
            raise HTTPException(status_code=404, detail="stream expired")
        return StreamingResponse(
            service.stream_audio_chunks(token),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=coco.mp3",
                "Cache-Control": "no-store",
                "Accept-Ranges": "none",
            },
        )

    return app


def make_stream_server(service: CocoXiaoMusicService, settings: AppSettings) -> StreamServerHandle:
    port = int(settings.admin_port)
    config = uvicorn.Config(
        create_stream_app(service),
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False,
    )
    return StreamServerHandle(server=uvicorn.Server(config), url=f"http://127.0.0.1:{port}")
