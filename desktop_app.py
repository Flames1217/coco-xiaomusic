import os
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import requests
import uvicorn


@dataclass
class DesktopServer:
    url: str
    server: uvicorn.Server | None = None
    thread: threading.Thread | None = None
    reused_existing: bool = False


@dataclass
class RuntimePaths:
    app_root: Path
    runtime_root: Path
    portable: bool


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _resource_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parent


def _runtime_root(app_root: Path) -> tuple[Path, bool]:
    configured = os.environ.get("COCO_XIAOMUSIC_HOME")
    if configured:
        return Path(configured).expanduser().resolve(), False
    if not getattr(sys, "frozen", False):
        return app_root, True
    portable = (app_root / "portable.flag").exists()
    if portable:
        return app_root, True
    return Path(os.environ.get("APPDATA", app_root)).resolve() / "coco-xiaomusic", False


def prepare_runtime_environment() -> RuntimePaths:
    app_root = _app_root()
    resource_root = _resource_root()
    runtime_root, portable = _runtime_root(app_root)
    runtime_root.mkdir(parents=True, exist_ok=True)
    for name in ("data", "conf", "music", "music/tmp", "music/cache", "logs"):
        (runtime_root / name).mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("COCO_XIAOMUSIC_RESOURCE_ROOT", str(resource_root))
    os.environ.setdefault("COCO_XIAOMUSIC_HOME", str(runtime_root))
    if str(resource_root) not in sys.path:
        sys.path.insert(0, str(resource_root))
    os.chdir(runtime_root)
    return RuntimePaths(app_root=app_root, runtime_root=runtime_root, portable=portable)


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
    prepare_runtime_environment()
    from coco_xiaomusic.settings import settings
    from coco_xiaomusic.web import app

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
    runtime = prepare_runtime_environment()
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
    if runtime.portable:
        print(f"coco-xiaomusic portable data: {runtime.runtime_root}")
    else:
        print(f"coco-xiaomusic user data: {runtime.runtime_root}")
    window.events.closed += on_closed
    webview.start(gui="edgechromium")


if __name__ == "__main__":
    main()
