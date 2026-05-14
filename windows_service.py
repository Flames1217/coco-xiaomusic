from __future__ import annotations

import os
import sys
import asyncio
import threading
from pathlib import Path

import servicemanager
import uvicorn
import win32event
import win32service
import win32serviceutil


PROJECT_ROOT = Path(__file__).resolve().parent


class CocoXiaoMusicWindowsService(win32serviceutil.ServiceFramework):
    _svc_name_ = "CocoXiaoMusic"
    _svc_display_name_ = "coco-xiaomusic"
    _svc_description_ = "coco-xiaomusic native app companion and XiaoAI stream service"

    def __init__(self, args):
        super().__init__(args)
        self._stop_event = win32event.CreateEvent(None, 0, 0, None)
        self._server: uvicorn.Server | None = None
        self._server_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._service = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        servicemanager.LogInfoMsg("coco-xiaomusic service stopping")
        if self._server is not None:
            self._server.should_exit = True
        if self._loop and self._service:
            try:
                asyncio.run_coroutine_threadsafe(self._service.stop(), self._loop).result(timeout=10)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
        win32event.SetEvent(self._stop_event)

    def SvcDoRun(self):
        os.chdir(PROJECT_ROOT)
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))

        from coco_xiaomusic.service import CocoXiaoMusicService
        from coco_xiaomusic.settings import settings
        from coco_xiaomusic.stream_server import make_stream_server

        self._loop = asyncio.new_event_loop()

        def run_loop():
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._loop_thread = threading.Thread(target=run_loop, name="coco-xiaomusic-loop", daemon=True)
        self._loop_thread.start()
        self._service = CocoXiaoMusicService(settings)
        handle = make_stream_server(self._service, settings)

        self._server = handle.server
        self._server_thread = threading.Thread(
            target=self._server.run,
            name="coco-xiaomusic-uvicorn",
            daemon=True,
        )
        self._server_thread.start()
        asyncio.run_coroutine_threadsafe(self._service.start(), self._loop).result(timeout=60)
        servicemanager.LogInfoMsg(
            f"coco-xiaomusic service started on {settings.admin_host}:{settings.admin_port}"
        )

        win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)

        if self._server_thread is not None:
            self._server_thread.join(timeout=20)
        if self._loop_thread is not None:
            self._loop_thread.join(timeout=20)
        servicemanager.LogInfoMsg("coco-xiaomusic service stopped")


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(CocoXiaoMusicWindowsService)
