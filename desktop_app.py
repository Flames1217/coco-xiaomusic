import socket
import sys
import threading
import time
from dataclasses import dataclass

import requests
import uvicorn

from coco_xiaomusic.settings import settings
from coco_xiaomusic.web import app


@dataclass
class DesktopServer:
    url: str
    server: uvicorn.Server | None = None
    thread: threading.Thread | None = None
    reused_existing: bool = False


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.6):
            return True
    except OSError:
        return False


def _is_coco_server(url: str) -> bool:
    try:
        response = requests.get(f"{url}/api/status", timeout=1.5)
        return response.ok and "status" in response.json()
    except (requests.RequestException, ValueError):
        return False


def _wait_for_server(url: str, timeout: float = 35.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_coco_server(url):
            return True
        time.sleep(0.35)
    return False


def start_desktop_server() -> DesktopServer:
    host = "127.0.0.1"
    port = int(settings.admin_port)
    url = f"http://{host}:{port}"

    if _is_coco_server(url):
        return DesktopServer(url=url, reused_existing=True)
    if _is_port_open(host, port):
        raise RuntimeError(f"端口 {port} 已被其他程序占用，无法启动 coco-xiaomusic 桌面服务。")

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="coco-xiaomusic-server", daemon=True)
    thread.start()

    if not _wait_for_server(url):
        server.should_exit = True
        raise RuntimeError("coco-xiaomusic 后台服务启动超时，请检查小米账号、端口和日志。")
    return DesktopServer(url=url, server=server, thread=thread)


def stop_desktop_server(server: DesktopServer):
    if server.reused_existing or not server.server:
        return
    server.server.should_exit = True
    if server.thread:
        server.thread.join(timeout=5)


def main():
    try:
        import webview
    except ImportError:
        print("缺少桌面依赖 pywebview，请先执行：pip install -r requirements.txt", file=sys.stderr)
        raise SystemExit(1)

    server = start_desktop_server()

    def on_closed():
        stop_desktop_server(server)

    window = webview.create_window(
        "coco-xiaomusic 控制台",
        server.url,
        width=1280,
        height=860,
        min_size=(1060, 720),
        text_select=True,
    )
    window.events.closed += on_closed
    webview.start(gui="edgechromium")


if __name__ == "__main__":
    main()
