import asyncio
import os
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

import customtkinter as ctk
from PIL import Image


@dataclass
class RuntimePaths:
    app_root: Path
    runtime_root: Path
    portable: bool


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _runtime_root(root: Path) -> tuple[Path, bool]:
    configured = os.environ.get("COCO_XIAOMUSIC_HOME")
    if configured:
        return Path(configured).expanduser().resolve(), False
    if not getattr(sys, "frozen", False):
        return root, True
    if (root / "portable.flag").exists():
        return root, True
    return Path(os.environ.get("APPDATA", root)).resolve() / "coco-xiaomusic", False


def prepare_runtime_environment() -> RuntimePaths:
    root = _app_root()
    data_root, portable = _runtime_root(root)
    data_root.mkdir(parents=True, exist_ok=True)
    for name in ("data", "conf", "music", "music/tmp", "music/cache", "logs"):
        (data_root / name).mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("COCO_XIAOMUSIC_HOME", str(data_root))
    os.chdir(data_root)
    return RuntimePaths(root, data_root, portable)


def _asset_path(name: str) -> Path:
    return _app_root() / "assets" / name


class Backend:
    def __init__(self, ui_call: Callable[..., None]):
        self.ui_call = ui_call
        from .service import CocoXiaoMusicService
        from .settings import settings

        self.settings = settings
        self.service = CocoXiaoMusicService(settings)
        self.stream_server = None
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, name="coco-native-loop", daemon=True)
        self.thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def call(self, coro, callback: Callable[[Any], None] | None = None):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)

        def done(task):
            try:
                result = task.result()
            except Exception as exc:
                result = {"success": False, "error": repr(exc)}
            if callback:
                self.ui_call(0, callback, result)

        future.add_done_callback(done)
        return future

    def start(self, on_started: Callable[[dict], None]):
        self.call(self._start(), on_started)

    async def _start(self):
        from .stream_server import make_stream_server

        self.stream_server = make_stream_server(self.service, self.settings)
        self.loop.create_task(self.stream_server.server.serve())
        await self.service.start()
        return {"success": True}

    def shutdown(self):
        async def close():
            if self.stream_server:
                self.stream_server.server.should_exit = True
            await self.service.stop()

        try:
            self.call(close()).result(timeout=8)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)

    def snapshot(self) -> tuple[dict, list[dict]]:
        return self.service.status(), self.service.events()

    def search(self, keyword: str, callback: Callable[[dict], None]):
        self.call(self.service.search_preview(keyword), callback)

    def play_keyword(self, keyword: str, callback: Callable[[dict], None]):
        self.call(self.service.play_keyword(self._primary_did(), keyword), callback)

    def play_selected(self, song: dict, callback: Callable[[dict], None]):
        self.call(
            self.service.play_selected_song(
                str(song.get("id", "")),
                str(song.get("provider", "")),
                str(song.get("title", "")),
                str(song.get("artist", "")),
                str(song.get("cover", "")),
                str(song.get("duration", "")),
                str(song.get("album", "")),
                str(song.get("audio_type", "")),
                str(song.get("bitrate", "")),
                list(self.settings.manual_target_dids),
            ),
            callback,
        )

    def pause(self, callback: Callable[[dict], None]):
        self.call(self.service.pause_playback(), callback)

    def resume(self, callback: Callable[[dict], None]):
        self.call(self.service.resume_playback(), callback)

    def stop(self, callback: Callable[[dict], None]):
        self.call(self.service.stop_playback(), callback)

    def seek(self, seconds: float, callback: Callable[[dict], None]):
        self.call(self.service.seek_playback(seconds), callback)

    def volume(self, volume: int, callback: Callable[[dict], None]):
        self.call(self.service.set_volume(volume), callback)

    def save_account(self, account: str, password: str, hostname: str, callback: Callable[[dict], None]):
        self.call(self.service.update_account(account, password, hostname), callback)

    def save_devices(self, selected: list[str], targets: list[str], callback: Callable[[dict], None]):
        self.call(self.service.select_devices(selected, targets), callback)

    def save_alias(self, did: str, alias: str, callback: Callable[[dict], None]):
        self.call(self.service.rename_device(did, alias), callback)

    def save_strategy(
        self,
        coco_base: str,
        delay: float,
        search_tts: str,
        found_tts: str,
        error_tts: str,
        callback: Callable[[dict], None],
    ):
        self.call(self.service.update_runtime_settings(coco_base, delay, search_tts, found_tts, error_tts), callback)

    def clear_logs(self):
        self.service.clear_events()

    def _primary_did(self) -> str:
        status = self.service.status()
        targets = status.get("manual_target_dids") or status.get("selected_dids") or []
        if targets:
            return str(targets[0])
        devices = status.get("devices") or []
        return str(devices[0]["did"]) if devices else ""


class CocoDesktopApp(ctk.CTk):
    BG = "#0b1020"
    PANEL = "#111827"
    PANEL_SOFT = "#151d2f"
    LINE = "#263247"
    TEXT = "#eef4ff"
    MUTED = "#91a0b8"
    ACCENT = "#ffb020"
    BLUE = "#33a6ff"
    GREEN = "#23d18b"
    RED = "#ff5573"

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("coco-xiaomusic")
        self.geometry("1320x860")
        self.minsize(1120, 720)
        self.configure(fg_color=self.BG)

        icon = _asset_path("logo.ico")
        if icon.exists():
            try:
                self.iconbitmap(str(icon))
            except tk.TclError:
                pass

        self.results: list[dict] = []
        self.device_vars: dict[str, tuple[tk.BooleanVar, tk.BooleanVar, tk.StringVar]] = {}
        self.page_frames: dict[str, ctk.CTkFrame] = {}
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.log_rows: list[ctk.CTkFrame] = []
        self.dragging_progress = False
        self.dragging_volume = False
        self.duration = 0.0
        self.current_status: dict = {}
        self.logo_image = self._load_image("logo.png", (44, 44))
        self.player_image = self._load_image("logo.png", (48, 48))

        self.backend = Backend(self.after)
        self.settings = self.backend.settings
        self._build_ttk_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.backend.start(self._started)
        self.after(700, self._poll)

    def _load_image(self, name: str, size: tuple[int, int]) -> ctk.CTkImage | None:
        path = _asset_path(name)
        if not path.exists():
            return None
        try:
            image = Image.open(path)
            return ctk.CTkImage(light_image=image, dark_image=image, size=size)
        except Exception:
            return None

    def _build_ttk_style(self):
        self.ttk_style = ttk.Style(self)
        self.ttk_style.theme_use("clam")
        self.ttk_style.configure(
            "Results.Treeview",
            background=self.PANEL_SOFT,
            fieldbackground=self.PANEL_SOFT,
            foreground=self.TEXT,
            borderwidth=0,
            rowheight=42,
            font=("Microsoft YaHei UI", 10),
        )
        self.ttk_style.map("Results.Treeview", background=[("selected", "#22385d")], foreground=[("selected", self.TEXT)])
        self.ttk_style.configure(
            "Results.Treeview.Heading",
            background="#0f172a",
            foreground=self.MUTED,
            borderwidth=0,
            relief="flat",
            font=("Microsoft YaHei UI", 9, "bold"),
        )

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=236, fg_color="#080d18", corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self._build_sidebar()

        self.main = ctk.CTkFrame(self, fg_color=self.BG, corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_cards()
        self._build_pages()
        self._build_player()
        self._show_page("console")

    def _build_sidebar(self):
        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.pack(fill=tk.X, padx=18, pady=(22, 18))
        if self.logo_image:
            ctk.CTkLabel(brand, text="", image=self.logo_image).pack(side=tk.LEFT, padx=(0, 12))
        else:
            ctk.CTkLabel(brand, text="♪", width=44, height=44, fg_color="#17233a", corner_radius=14).pack(side=tk.LEFT, padx=(0, 12))
        text_box = ctk.CTkFrame(brand, fg_color="transparent")
        text_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ctk.CTkLabel(text_box, text="coco", anchor="w", text_color=self.ACCENT, font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        ctk.CTkLabel(text_box, text="xiaomusic", anchor="w", text_color=self.MUTED, font=("Microsoft YaHei UI", 11)).pack(anchor="w")

        ctk.CTkLabel(
            self.sidebar,
            text="导航",
            text_color="#66738b",
            font=("Microsoft YaHei UI", 11, "bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=22, pady=(10, 8))

        for key, label in (
            ("console", "控制台"),
            ("devices", "设备"),
            ("strategy", "策略"),
            ("account", "账号"),
        ):
            btn = ctk.CTkButton(
                self.sidebar,
                text=label,
                height=42,
                corner_radius=14,
                anchor="w",
                fg_color="transparent",
                hover_color="#16233a",
                text_color=self.MUTED,
                font=("Microsoft YaHei UI", 13, "bold"),
                command=lambda page=key: self._show_page(page),
            )
            btn.pack(fill=tk.X, padx=14, pady=4)
            self.nav_buttons[key] = btn

        self.sidebar_footer = ctk.CTkFrame(self.sidebar, fg_color="#0d1526", corner_radius=18)
        self.sidebar_footer.pack(side=tk.BOTTOM, fill=tk.X, padx=14, pady=16)
        ctk.CTkLabel(self.sidebar_footer, text="运行模式", text_color=self.MUTED, font=("Microsoft YaHei UI", 11)).pack(anchor="w", padx=14, pady=(12, 0))
        self.runtime_label = ctk.CTkLabel(self.sidebar_footer, text="桌面应用", text_color=self.TEXT, font=("Microsoft YaHei UI", 13, "bold"))
        self.runtime_label.pack(anchor="w", padx=14, pady=(3, 12))

    def _build_header(self):
        header = ctk.CTkFrame(self.main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=26, pady=(22, 12))
        header.grid_columnconfigure(0, weight=1)

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(title_box, text="小爱音箱播放控制台", text_color=self.TEXT, font=("Microsoft YaHei UI", 28, "bold")).pack(anchor="w")
        ctk.CTkLabel(
            title_box,
            text="点歌接管、coco 搜索、设备推流与运行状态集中在一个桌面应用里。",
            text_color=self.MUTED,
            font=("Microsoft YaHei UI", 12),
        ).pack(anchor="w", pady=(4, 0))

        self.status_pill = ctk.CTkFrame(header, fg_color="#0f1a2b", corner_radius=18, border_width=1, border_color=self.LINE)
        self.status_pill.grid(row=0, column=1, sticky="e")
        self.status_dot = ctk.CTkLabel(self.status_pill, text="●", text_color=self.ACCENT, font=("Microsoft YaHei UI", 18))
        self.status_dot.pack(side=tk.LEFT, padx=(16, 6), pady=14)
        self.status_text = ctk.CTkLabel(self.status_pill, text="启动中", text_color=self.TEXT, font=("Microsoft YaHei UI", 13, "bold"))
        self.status_text.pack(side=tk.LEFT, padx=(0, 16), pady=14)

    def _build_cards(self):
        cards = ctk.CTkFrame(self.main, fg_color="transparent")
        cards.grid(row=1, column=0, sticky="ew", padx=26, pady=(0, 16))
        cards.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="cards")
        self.card_values: dict[str, ctk.CTkLabel] = {}
        for index, (key, title) in enumerate(
            (
                ("xiao", "XIAOMUSIC 服务"),
                ("coco", "COCO 服务"),
                ("devices", "监听设备"),
                ("recent", "最近口令"),
            )
        ):
            card = ctk.CTkFrame(cards, fg_color=self.PANEL, corner_radius=18, border_width=1, border_color=self.LINE)
            card.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 8, 0 if index == 3 else 8))
            ctk.CTkLabel(card, text=title, text_color=self.ACCENT, font=("Microsoft YaHei UI", 11, "bold"), anchor="w").pack(fill=tk.X, padx=16, pady=(14, 0))
            value = ctk.CTkLabel(card, text="--", text_color=self.TEXT, font=("Microsoft YaHei UI", 18, "bold"), anchor="w")
            value.pack(fill=tk.X, padx=16, pady=(6, 16))
            self.card_values[key] = value

    def _build_pages(self):
        self.page_host = ctk.CTkFrame(self.main, fg_color="transparent")
        self.page_host.grid(row=2, column=0, sticky="nsew", padx=26, pady=(0, 98))
        self.page_host.grid_columnconfigure(0, weight=1)
        self.page_host.grid_rowconfigure(0, weight=1)

        for key in ("console", "devices", "strategy", "account"):
            frame = ctk.CTkFrame(self.page_host, fg_color="transparent")
            frame.grid(row=0, column=0, sticky="nsew")
            self.page_frames[key] = frame

        self._build_console(self.page_frames["console"])
        self._build_devices(self.page_frames["devices"])
        self._build_strategy(self.page_frames["strategy"])
        self._build_account(self.page_frames["account"])

    def _build_console(self, page: ctk.CTkFrame):
        page.grid_columnconfigure(0, weight=3)
        page.grid_columnconfigure(1, weight=1)
        page.grid_rowconfigure(0, weight=1)

        left = self._panel(page)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(3, weight=1)
        self._section_title(left, "CONSOLE", "点歌与搜索").grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 12))

        ctk.CTkLabel(left, text="歌曲关键词", text_color=self.ACCENT, font=("Microsoft YaHei UI", 12, "bold"), anchor="w").grid(row=1, column=0, sticky="ew", padx=18)
        search_row = ctk.CTkFrame(left, fg_color="transparent")
        search_row.grid(row=2, column=0, sticky="ew", padx=18, pady=(8, 14))
        search_row.grid_columnconfigure(0, weight=1)
        self.keyword = ctk.CTkEntry(search_row, height=42, placeholder_text="例如：宿 廖静媛", fg_color=self.PANEL_SOFT, border_color=self.LINE)
        self.keyword.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.keyword.bind("<Return>", lambda _: self._search())
        ctk.CTkButton(search_row, text="播放第一条", width=112, height=42, fg_color=self.ACCENT, hover_color="#ffc04d", text_color="#111827", command=self._play_first).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(search_row, text="搜索全部", width=104, height=42, fg_color="#1b2941", hover_color="#243755", command=self._search).grid(row=0, column=2)

        results = ctk.CTkFrame(left, fg_color=self.PANEL_SOFT, corner_radius=16, border_width=1, border_color=self.LINE)
        results.grid(row=3, column=0, sticky="nsew", padx=18, pady=(0, 18))
        results.grid_columnconfigure(0, weight=1)
        results.grid_rowconfigure(1, weight=1)
        result_header = ctk.CTkFrame(results, fg_color="transparent")
        result_header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        result_header.grid_columnconfigure(0, weight=1)
        self.result_count_label = ctk.CTkLabel(result_header, text="搜索结果：等待搜索", text_color=self.TEXT, font=("Microsoft YaHei UI", 14, "bold"), anchor="w")
        self.result_count_label.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(result_header, text="推送选中", width=94, height=32, fg_color=self.ACCENT, hover_color="#ffc04d", text_color="#111827", command=self._push_selected).grid(row=0, column=1, sticky="e")

        columns = ("index", "title", "artist", "provider", "duration", "format")
        self.results_tree = ttk.Treeview(results, columns=columns, show="headings", selectmode="browse", style="Results.Treeview")
        for column, title, width in (
            ("index", "#", 46),
            ("title", "歌名", 300),
            ("artist", "歌手", 180),
            ("provider", "渠道", 120),
            ("duration", "时长", 90),
            ("format", "格式", 100),
        ):
            self.results_tree.heading(column, text=title)
            self.results_tree.column(column, width=width, anchor=tk.W, stretch=column in {"title", "artist"})
        self.results_tree.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.results_tree.bind("<Double-1>", lambda _: self._push_selected())

        right = self._panel(page)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        log_title = self._section_title(right, "LOGS", "实时日志")
        log_title.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        ctk.CTkButton(log_title, text="清理日志", width=88, height=32, fg_color="#1b2941", hover_color="#243755", command=self._clear_logs).grid(row=0, column=1, padx=(10, 0))
        self.logs_frame = ctk.CTkScrollableFrame(right, fg_color="#0f172a", corner_radius=16, border_width=1, border_color=self.LINE)
        self.logs_frame.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))

    def _build_devices(self, page: ctk.CTkFrame):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        header = self._section_title(page, "DEVICES", "设备接入")
        header.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 12))
        ctk.CTkButton(header, text="保存设备方案", width=124, height=34, fg_color=self.ACCENT, hover_color="#ffc04d", text_color="#111827", command=self._save_devices).grid(row=0, column=1)
        self.device_list = ctk.CTkScrollableFrame(page, fg_color="transparent")
        self.device_list.grid(row=1, column=0, sticky="nsew")

    def _build_strategy(self, page: ctk.CTkFrame):
        page.grid_columnconfigure(0, weight=1)
        content = self._panel(page)
        content.grid(row=0, column=0, sticky="new")
        content.grid_columnconfigure(0, weight=1)
        self._section_title(content, "SIGNALS", "接管策略").grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 12))
        self.coco_base = self._field(content, "coco 服务地址", self.settings.coco_base, 1)
        self.delay = self._field(content, "静默接管延迟秒数", str(self.settings.official_answer_delay_sec), 2)
        self.search_tts = self._field(content, "搜索提示话术", self.settings.search_tts, 3)
        self.found_tts = self._field(content, "命中提示话术", self.settings.found_tts, 4)
        self.error_tts = self._field(content, "失败提示话术", self.settings.error_tts, 5)
        ctk.CTkButton(content, text="保存策略", height=40, fg_color=self.ACCENT, hover_color="#ffc04d", text_color="#111827", command=self._save_strategy).grid(row=6, column=0, sticky="e", padx=18, pady=(6, 18))

    def _build_account(self, page: ctk.CTkFrame):
        page.grid_columnconfigure(0, weight=1)
        content = self._panel(page)
        content.grid(row=0, column=0, sticky="new")
        content.grid_columnconfigure(0, weight=1)
        self._section_title(content, "ACCOUNT", "小米账号").grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 12))
        self.account = self._field(content, "小米账号", self.settings.account, 1)
        self.password = self._field(content, "小米密码", self.settings.password, 2, show="*")
        self.hostname = self._field(content, "本机访问地址", self.settings.hostname, 3)
        ctk.CTkButton(content, text="保存账号并登录", height=40, fg_color=self.ACCENT, hover_color="#ffc04d", text_color="#111827", command=self._save_account).grid(row=4, column=0, sticky="e", padx=18, pady=(6, 18))

    def _build_player(self):
        self.player = ctk.CTkFrame(self.main, height=86, fg_color="#090f1c", corner_radius=0, border_width=1, border_color="#1c2638")
        self.player.grid(row=3, column=0, sticky="ew")
        self.player.grid_columnconfigure(1, weight=1)

        cover_box = ctk.CTkFrame(self.player, width=52, height=52, fg_color="#17233a", corner_radius=18)
        cover_box.grid(row=0, column=0, padx=(28, 12), pady=16)
        cover_box.grid_propagate(False)
        self.cover = ctk.CTkLabel(cover_box, text="", image=self.player_image)
        self.cover.place(relx=0.5, rely=0.5, anchor="center")

        meta = ctk.CTkFrame(self.player, fg_color="transparent")
        meta.grid(row=0, column=1, sticky="w", pady=12)
        self.player_title = ctk.CTkLabel(meta, text="暂无歌曲", text_color=self.TEXT, font=("Microsoft YaHei UI", 14, "bold"), anchor="w")
        self.player_title.pack(anchor="w")
        self.player_artist = ctk.CTkLabel(meta, text="--", text_color=self.MUTED, font=("Microsoft YaHei UI", 11), anchor="w")
        self.player_artist.pack(anchor="w", pady=(2, 0))

        center = ctk.CTkFrame(self.player, fg_color="transparent")
        center.grid(row=0, column=2, padx=28, sticky="ew")
        for idx in range(5):
            center.grid_columnconfigure(idx, weight=0)
        self.prev_button = self._icon_button(center, "‹", 0)
        self.play_button = ctk.CTkButton(
            center,
            text="▶",
            width=48,
            height=48,
            corner_radius=24,
            fg_color=self.ACCENT,
            hover_color="#ffc04d",
            text_color="#111827",
            font=("Segoe UI Symbol", 20, "bold"),
            command=self._toggle_play,
        )
        self.play_button.grid(row=0, column=1, padx=8)
        self.next_button = self._icon_button(center, "›", 2)
        self.loop_button = self._icon_button(center, "↻", 3)
        self.stop_button = self._icon_button(center, "■", 4, command=lambda: self.backend.stop(self._operation))

        progress = ctk.CTkFrame(center, fg_color="transparent")
        progress.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(4, 0))
        progress.grid_columnconfigure(1, weight=1)
        self.current_time = ctk.CTkLabel(progress, text="0:00", width=44, text_color=self.MUTED, font=("SFMono-Regular", 10))
        self.current_time.grid(row=0, column=0)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ctk.CTkSlider(
            progress,
            from_=0,
            to=1000,
            variable=self.progress_var,
            width=320,
            height=16,
            progress_color=self.ACCENT,
            button_color=self.ACCENT,
            button_hover_color="#ffd47a",
            fg_color="#2a3244",
            command=lambda _: None,
        )
        self.progress.grid(row=0, column=1, sticky="ew", padx=8)
        self.progress.bind("<ButtonPress-1>", lambda _: setattr(self, "dragging_progress", True))
        self.progress.bind("<ButtonRelease-1>", self._seek_from_slider)
        self.total_time = ctk.CTkLabel(progress, text="--:--", width=44, text_color=self.MUTED, font=("SFMono-Regular", 10))
        self.total_time.grid(row=0, column=2)

        volume = ctk.CTkFrame(self.player, fg_color="transparent")
        volume.grid(row=0, column=3, padx=(8, 28), sticky="e")
        ctk.CTkLabel(volume, text="音量", text_color=self.MUTED, font=("Microsoft YaHei UI", 11)).pack(side=tk.LEFT, padx=(0, 8))
        self.volume_var = tk.IntVar(value=8)
        self.volume_scale = ctk.CTkSlider(
            volume,
            from_=0,
            to=100,
            variable=self.volume_var,
            width=130,
            progress_color=self.ACCENT,
            button_color=self.ACCENT,
            button_hover_color="#ffd47a",
            fg_color="#2a3244",
            command=lambda _: None,
        )
        self.volume_scale.pack(side=tk.LEFT, padx=(0, 8))
        self.volume_scale.bind("<ButtonPress-1>", lambda _: setattr(self, "dragging_volume", True))
        self.volume_scale.bind("<ButtonRelease-1>", self._volume_from_slider)
        self.volume_spin = ctk.CTkEntry(volume, width=52, height=32, textvariable=self.volume_var, fg_color=self.PANEL_SOFT, border_color=self.LINE)
        self.volume_spin.pack(side=tk.LEFT)
        self.volume_spin.bind("<Return>", lambda _: self._volume_from_entry())
        self.player.grid_remove()

    def _panel(self, parent) -> ctk.CTkFrame:
        return ctk.CTkFrame(parent, fg_color=self.PANEL, corner_radius=18, border_width=1, border_color=self.LINE)

    def _section_title(self, parent, eyebrow: str, title: str) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        box = ctk.CTkFrame(frame, fg_color="transparent")
        box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(box, text=eyebrow, text_color=self.ACCENT, font=("SFMono-Regular", 10, "bold"), anchor="w").pack(anchor="w")
        ctk.CTkLabel(box, text=title, text_color=self.TEXT, font=("Microsoft YaHei UI", 18, "bold"), anchor="w").pack(anchor="w", pady=(2, 0))
        return frame

    def _field(self, parent, label: str, value: str, row: int, show: str = "") -> ctk.CTkEntry:
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.grid(row=row, column=0, sticky="ew", padx=18, pady=(0, 12))
        block.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(block, text=label, text_color=self.MUTED, font=("Microsoft YaHei UI", 12), anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 5))
        entry = ctk.CTkEntry(block, height=40, fg_color=self.PANEL_SOFT, border_color=self.LINE, show=show)
        entry.insert(0, value or "")
        entry.grid(row=1, column=0, sticky="ew")
        return entry

    def _icon_button(self, parent, text: str, col: int, command: Callable[[], None] | None = None) -> ctk.CTkButton:
        button = ctk.CTkButton(
            parent,
            text=text,
            width=34,
            height=34,
            corner_radius=17,
            fg_color="transparent",
            hover_color="#17233a",
            text_color=self.MUTED,
            font=("Segoe UI Symbol", 17, "bold"),
            command=command,
        )
        button.grid(row=0, column=col, padx=3)
        return button

    def _show_page(self, page: str):
        for key, frame in self.page_frames.items():
            if key == page:
                frame.tkraise()
            button = self.nav_buttons.get(key)
            if button:
                active = key == page
                button.configure(
                    fg_color=self.ACCENT if active else "transparent",
                    hover_color="#ffc04d" if active else "#16233a",
                    text_color="#111827" if active else self.MUTED,
                )

    def _started(self, result: dict):
        if result.get("success"):
            self.status_msg("服务已启动")
        else:
            messagebox.showerror("启动失败", str(result.get("error") or "未知错误"))

    def _poll(self):
        try:
            status, events = self.backend.snapshot()
            self.current_status = status
            self._apply_status(status)
            self._apply_events(events)
        finally:
            self.after(1000, self._poll)

    def _apply_status(self, status: dict):
        ready = bool(status.get("ready"))
        self.status_dot.configure(text_color=self.GREEN if ready else self.ACCENT)
        self.status_text.configure(text="服务在线" if ready else "启动中")
        self.card_values["xiao"].configure(text="在线" if ready else "启动中")
        self.card_values["coco"].configure(text=status.get("coco_base") or self.settings.coco_base)
        self.card_values["devices"].configure(text=f"{len(status.get('devices') or [])} 台")
        self.card_values["recent"].configure(text=status.get("last_keyword") or "暂无")
        self._apply_devices(status)
        self._apply_player(status)

    def _apply_events(self, events: list[dict]):
        for row in self.log_rows:
            row.destroy()
        self.log_rows.clear()
        for item in events[:80]:
            row = ctk.CTkFrame(self.logs_frame, fg_color="#111a2d", corner_radius=12, border_width=1, border_color="#22304a")
            row.pack(fill=tk.X, pady=5)
            row.grid_columnconfigure(2, weight=1)
            time_text = str(item.get("at", ""))[-8:]
            level = str(item.get("level", "")).upper()
            color = {"OK": self.GREEN, "ERROR": self.RED, "WARN": self.ACCENT, "INFO": self.BLUE}.get(level, self.MUTED)
            ctk.CTkLabel(row, text=time_text, width=58, text_color=self.MUTED, font=("SFMono-Regular", 10)).grid(row=0, column=0, padx=(10, 4), pady=8)
            ctk.CTkLabel(row, text=level, width=54, text_color=color, font=("SFMono-Regular", 10, "bold")).grid(row=0, column=1, padx=4, pady=8)
            ctk.CTkLabel(row, text=str(item.get("message", "")), text_color=self.TEXT, font=("Microsoft YaHei UI", 11), anchor="w", justify="left", wraplength=330).grid(row=0, column=2, sticky="ew", padx=(4, 10), pady=8)
            self.log_rows.append(row)

    def _apply_devices(self, status: dict):
        devices = status.get("devices") or []
        wanted = {device["did"] for device in devices}
        if set(self.device_vars) == wanted:
            return
        for child in self.device_list.winfo_children():
            child.destroy()
        self.device_vars.clear()
        selected = set(status.get("selected_dids") or [])
        targets = set(status.get("manual_target_dids") or [])
        if not devices:
            ctk.CTkLabel(self.device_list, text="暂无设备，先到账号页登录并等待设备列表刷新。", text_color=self.MUTED).pack(anchor="w", padx=10, pady=10)
            return
        for device in devices:
            did = device["did"]
            frame = ctk.CTkFrame(self.device_list, fg_color=self.PANEL, corner_radius=16, border_width=1, border_color=self.LINE)
            frame.pack(fill=tk.X, padx=4, pady=(0, 10))
            frame.grid_columnconfigure(0, weight=1)
            name = device.get("alias") or device.get("name") or "未命名设备"
            ctk.CTkLabel(frame, text=name, text_color=self.TEXT, font=("Microsoft YaHei UI", 15, "bold"), anchor="w").grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))
            ctk.CTkLabel(frame, text=f"DID: {did}   硬件: {device.get('hardware') or '--'}", text_color=self.MUTED, anchor="w").grid(row=1, column=0, sticky="ew", padx=16)
            listen = tk.BooleanVar(value=did in selected)
            push = tk.BooleanVar(value=did in targets)
            alias = tk.StringVar(value=device.get("alias") or "")
            ctk.CTkCheckBox(frame, text="参与语音监听", variable=listen, fg_color=self.ACCENT, hover_color="#ffc04d").grid(row=0, column=1, sticky="w", padx=16, pady=(14, 4))
            ctk.CTkCheckBox(frame, text="后台默认推送", variable=push, fg_color=self.ACCENT, hover_color="#ffc04d").grid(row=1, column=1, sticky="w", padx=16, pady=4)
            alias_entry = ctk.CTkEntry(frame, textvariable=alias, width=220, height=36, placeholder_text="本地别名", fg_color=self.PANEL_SOFT, border_color=self.LINE)
            alias_entry.grid(row=2, column=0, sticky="w", padx=16, pady=(12, 16))
            ctk.CTkButton(frame, text="命名", width=86, height=36, fg_color=self.ACCENT, hover_color="#ffc04d", text_color="#111827", command=lambda d=did, a=alias: self.backend.save_alias(d, a.get(), self._operation)).grid(row=2, column=1, sticky="w", padx=16, pady=(12, 16))
            self.device_vars[did] = (listen, push, alias)

    def _apply_player(self, status: dict):
        song = status.get("last_song") or {}
        if song or status.get("last_used_url"):
            self.player.grid()
        title = str(song.get("title") or "暂无歌曲")
        artist = str(song.get("artist") or "--")
        self.player_title.configure(text=title)
        self.player_artist.configure(text=artist)
        self.duration = float(status.get("last_duration") or 0)
        position = float(status.get("last_position") or 0)
        paused = bool(status.get("playback_paused") or not status.get("last_used_url"))
        self.play_button.configure(text="▶" if paused else "Ⅱ")
        self.current_time.configure(text=self._fmt(position))
        self.total_time.configure(text=self._fmt(self.duration) if self.duration else "--:--")
        if self.duration > 0 and not self.dragging_progress:
            self.progress_var.set(min(1000, position / self.duration * 1000))
        volume = status.get("volume") or (status.get("player_status") or {}).get("volume")
        if volume is not None and not self.dragging_volume:
            try:
                self.volume_var.set(int(volume))
            except (TypeError, ValueError):
                pass

    def _search(self):
        keyword = self.keyword.get().strip()
        if keyword:
            self.result_count_label.configure(text="搜索结果：搜索中...")
            self.backend.search(keyword, self._set_results)

    def _play_first(self):
        keyword = self.keyword.get().strip()
        if keyword:
            self.backend.play_keyword(keyword, self._operation)

    def _set_results(self, result: dict):
        self.results = [item.get("item") or {} for item in result.get("items", [])]
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.result_count_label.configure(text=f"搜索结果：{len(self.results)} 条")
        for index, song in enumerate(self.results, start=1):
            self.results_tree.insert(
                "",
                tk.END,
                iid=str(index - 1),
                values=(
                    index,
                    song.get("title") or "",
                    song.get("artist") or "",
                    song.get("provider") or "",
                    self._duration_text(song),
                    song.get("audio_type") or song.get("quality") or "",
                ),
            )

    def _push_selected(self):
        selected = self.results_tree.selection()
        if not selected:
            return
        self.backend.play_selected(self.results[int(selected[0])], self._operation)

    def _toggle_play(self):
        paused = bool(self.current_status.get("playback_paused") or not self.current_status.get("last_used_url"))
        if paused:
            self.backend.resume(self._operation)
        else:
            self.backend.pause(self._operation)

    def _seek_from_slider(self, _event):
        self.dragging_progress = False
        if self.duration > 0:
            self.backend.seek(float(self.progress_var.get()) / 1000 * self.duration, self._operation)

    def _volume_from_slider(self, _event):
        self.dragging_volume = False
        self._volume_from_entry()

    def _volume_from_entry(self):
        try:
            volume = int(float(self.volume_var.get()))
        except (TypeError, ValueError, tk.TclError):
            return
        volume = max(0, min(100, volume))
        self.volume_var.set(volume)
        self.backend.volume(volume, self._operation)

    def _save_devices(self):
        selected = [did for did, values in self.device_vars.items() if values[0].get()]
        targets = [did for did, values in self.device_vars.items() if values[1].get()]
        self.backend.save_devices(selected, targets, self._operation)

    def _save_strategy(self):
        try:
            delay = float(self.delay.get() or 0)
        except ValueError:
            delay = 0.0
        self.backend.save_strategy(
            self.coco_base.get(),
            delay,
            self.search_tts.get(),
            self.found_tts.get(),
            self.error_tts.get(),
            self._operation,
        )

    def _save_account(self):
        self.backend.save_account(self.account.get(), self.password.get(), self.hostname.get(), self._operation)

    def _clear_logs(self):
        self.backend.clear_logs()
        for row in self.log_rows:
            row.destroy()
        self.log_rows.clear()

    def _operation(self, result: dict):
        if result.get("success"):
            self.status_msg("操作完成")
        else:
            self.status_msg(f"操作失败：{result.get('error') or result}")

    def status_msg(self, text: str):
        self.title(f"coco-xiaomusic - {text}")

    @staticmethod
    def _fmt(seconds: float) -> str:
        seconds = max(0, int(seconds or 0))
        return f"{seconds // 60}:{seconds % 60:02d}"

    def _duration_text(self, song: dict) -> str:
        value = song.get("duration") or song.get("interval") or song.get("time") or ""
        if isinstance(value, (int, float)):
            seconds = float(value)
            if seconds > 10000:
                seconds = seconds / 1000
            return self._fmt(seconds) if seconds > 0 else "--:--"
        text = str(value).strip()
        return text or "--:--"

    def _close(self):
        self.backend.shutdown()
        self.destroy()


def main():
    prepare_runtime_environment()
    app = CocoDesktopApp()
    app.mainloop()
