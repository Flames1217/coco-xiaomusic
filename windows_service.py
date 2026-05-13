from __future__ import annotations

import os
import sys
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
    _svc_description_ = "coco-xiaomusic local dashboard and XiaoAI bridge service"

    def __init__(self, args):
        super().__init__(args)
        self._stop_event = win32event.CreateEvent(None, 0, 0, None)
        self._server: uvicorn.Server | None = None
        self._server_thread: threading.Thread | None = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        servicemanager.LogInfoMsg("coco-xiaomusic service stopping")
        if self._server is not None:
            self._server.should_exit = True
        win32event.SetEvent(self._stop_event)

    def SvcDoRun(self):
        os.chdir(PROJECT_ROOT)
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))

        from coco_xiaomusic.settings import settings
        from coco_xiaomusic.web import app

        config = uvicorn.Config(
            app,
            host=settings.admin_host,
            port=settings.admin_port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        self._server_thread = threading.Thread(
            target=self._server.run,
            name="coco-xiaomusic-uvicorn",
            daemon=True,
        )
        self._server_thread.start()
        servicemanager.LogInfoMsg(
            f"coco-xiaomusic service started on {settings.admin_host}:{settings.admin_port}"
        )

        win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)

        if self._server_thread is not None:
            self._server_thread.join(timeout=20)
        servicemanager.LogInfoMsg("coco-xiaomusic service stopped")


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(CocoXiaoMusicWindowsService)
