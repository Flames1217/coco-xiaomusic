import asyncio
import os
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

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

    def save_strategy(self, coco_base: str, delay: float, search_tts: str, found_tts: str, error_tts: str, callback: Callable[[dict], None]):
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


class CocoDesktopApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("coco-xiaomusic")
        self.geometry("1280x820")
        self.minsize(1100, 720)
        self.configure(bg="#0b0f1a")
        self.results: list[dict] = []
        self.device_vars: dict[str, tuple[tk.BooleanVar, tk.BooleanVar, tk.StringVar]] = {}
        self.dragging_progress = False
        self.duration = 0.0
        self.backend = Backend(self.after)
        self.settings = self.backend.settings
        self._build_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.backend.start(self._started)
        self.after(800, self._poll)

    def _build_style(self):
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.style.configure(".", background="#0b0f1a", foreground="#e9eef8", fieldbackground="#151c2e", font=("SFMono-Regular", 10))
        self.style.configure("TFrame", background="#0b0f1a")
        self.style.configure("Panel.TFrame", background="#111827", bordercolor="#263248", relief="solid", borderwidth=1)
        self.style.configure("TLabel", background="#0b0f1a", foreground="#e9eef8")
        self.style.configure("Muted.TLabel", foreground="#97a4ba")
        self.style.configure("Accent.TLabel", foreground="#ffb020", font=("SFMono-Regular", 10, "bold"))
        self.style.configure("Title.TLabel", font=("SFMono-Regular", 22, "bold"))
        self.style.configure("CardValue.TLabel", background="#111827", foreground="#ffffff", font=("SFMono-Regular", 15, "bold"))
        self.style.configure("CardTitle.TLabel", background="#111827", foreground="#ffb020", font=("SFMono-Regular", 9, "bold"))
        self.style.configure("TButton", background="#1b2336", foreground="#e9eef8", bordercolor="#34425f", padding=(12, 8), font=("SFMono-Regular", 10, "bold"))
        self.style.map("TButton", background=[("active", "#ffb020")], foreground=[("active", "#07111f")])
        self.style.configure("Accent.TButton", background="#ffb020", foreground="#07111f")
        self.style.configure("Treeview", background="#111827", fieldbackground="#111827", foreground="#e9eef8", rowheight=34, bordercolor="#263248")
        self.style.configure("Treeview.Heading", background="#151c2e", foreground="#97a4ba", font=("SFMono-Regular", 9, "bold"))
        self.style.configure("TNotebook", background="#0b0f1a", borderwidth=0)
        self.style.configure("TNotebook.Tab", background="#111827", foreground="#97a4ba", padding=(18, 10), font=("SFMono-Regular", 10, "bold"))
        self.style.map("TNotebook.Tab", background=[("selected", "#ffb020")], foreground=[("selected", "#07111f")])

    def _build_ui(self):
        root = ttk.Frame(self)
        root.pack(fill=tk.BOTH, expand=True, padx=18, pady=14)

        header = ttk.Frame(root)
        header.pack(fill=tk.X)
        ttk.Label(header, text="coco-xiaomusic", style="Accent.TLabel").pack(anchor=tk.W)
        ttk.Label(header, text="小爱音箱播放控制台", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(header, text="原生 Windows 桌面应用，内部流服务只用于给音箱拉取转码音频。", style="Muted.TLabel").pack(anchor=tk.W)

        self.cards = ttk.Frame(root)
        self.cards.pack(fill=tk.X, pady=(14, 10))
        self.card_values = {}
        for key, title in (("xiao", "XIAOMUSIC 服务"), ("coco", "COCO 服务"), ("devices", "监听设备"), ("recent", "最近口令")):
            card = ttk.Frame(self.cards, style="Panel.TFrame", padding=14)
            card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor=tk.W)
            value = ttk.Label(card, text="--", style="CardValue.TLabel")
            value.pack(anchor=tk.W, pady=(6, 0))
            self.card_values[key] = value

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.console_page = ttk.Frame(self.notebook, padding=12)
        self.devices_page = ttk.Frame(self.notebook, padding=12)
        self.strategy_page = ttk.Frame(self.notebook, padding=12)
        self.account_page = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.console_page, text="控制台")
        self.notebook.add(self.devices_page, text="设备")
        self.notebook.add(self.strategy_page, text="策略")
        self.notebook.add(self.account_page, text="账号")
        self._build_console()
        self._build_devices()
        self._build_strategy()
        self._build_account()
        self._build_player(root)

    def _build_console(self):
        search = ttk.Frame(self.console_page)
        search.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(search, text="歌曲关键词", style="Accent.TLabel").pack(anchor=tk.W)
        row = ttk.Frame(search)
        row.pack(fill=tk.X, pady=(5, 0))
        self.keyword = ttk.Entry(row)
        self.keyword.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.keyword.insert(0, "宿 廖静媛")
        ttk.Button(row, text="播放第一条", style="Accent.TButton", command=self._play_first).pack(side=tk.LEFT, padx=8)
        ttk.Button(row, text="搜索全部", command=self._search).pack(side=tk.LEFT)
        self.keyword.bind("<Return>", lambda _: self._search())

        body = ttk.PanedWindow(self.console_page, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)
        results_frame = ttk.Frame(body, style="Panel.TFrame", padding=10)
        logs_frame = ttk.Frame(body, style="Panel.TFrame", padding=10)
        body.add(results_frame, weight=3)
        body.add(logs_frame, weight=1)

        ttk.Label(results_frame, text="搜索结果", style="Accent.TLabel").pack(anchor=tk.W)
        columns = ("index", "title", "artist", "provider", "duration", "format")
        self.results_tree = ttk.Treeview(results_frame, columns=columns, show="headings", selectmode="browse")
        for column, title, width in (
            ("index", "#", 42),
            ("title", "歌名", 260),
            ("artist", "歌手", 160),
            ("provider", "渠道", 100),
            ("duration", "时长", 80),
            ("format", "格式", 90),
        ):
            self.results_tree.heading(column, text=title)
            self.results_tree.column(column, width=width, anchor=tk.W)
        self.results_tree.pack(fill=tk.BOTH, expand=True, pady=(8, 8))
        ttk.Button(results_frame, text="推送选中歌曲", style="Accent.TButton", command=self._push_selected).pack(anchor=tk.E)

        log_header = ttk.Frame(logs_frame)
        log_header.pack(fill=tk.X)
        ttk.Label(log_header, text="实时日志", style="Accent.TLabel").pack(side=tk.LEFT)
        ttk.Button(log_header, text="清理日志", command=self._clear_logs).pack(side=tk.RIGHT)
        self.logs = tk.Listbox(logs_frame, bg="#111827", fg="#e9eef8", bd=0, highlightthickness=0, activestyle="none", font=("SFMono-Regular", 9))
        self.logs.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

    def _build_devices(self):
        ttk.Label(self.devices_page, text="设备接入", style="Title.TLabel").pack(anchor=tk.W)
        self.device_list = ttk.Frame(self.devices_page)
        self.device_list.pack(fill=tk.BOTH, expand=True, pady=10)
        ttk.Button(self.devices_page, text="保存设备方案", style="Accent.TButton", command=self._save_devices).pack(anchor=tk.E)

    def _build_strategy(self):
        ttk.Label(self.strategy_page, text="策略", style="Title.TLabel").pack(anchor=tk.W)
        self.coco_base = self._field(self.strategy_page, "coco 服务地址", self.settings.coco_base)
        self.delay = self._field(self.strategy_page, "静默接管延迟秒数", str(self.settings.official_answer_delay_sec))
        self.search_tts = self._field(self.strategy_page, "搜索提示话术", self.settings.search_tts)
        self.found_tts = self._field(self.strategy_page, "命中提示话术", self.settings.found_tts)
        self.error_tts = self._field(self.strategy_page, "失败提示话术", self.settings.error_tts)
        ttk.Button(self.strategy_page, text="保存策略", style="Accent.TButton", command=self._save_strategy).pack(anchor=tk.E, pady=10)

    def _build_account(self):
        ttk.Label(self.account_page, text="小米账号", style="Title.TLabel").pack(anchor=tk.W)
        self.account = self._field(self.account_page, "小米账号", self.settings.account)
        self.password = self._field(self.account_page, "小米密码", self.settings.password, show="*")
        self.hostname = self._field(self.account_page, "本机访问地址", self.settings.hostname)
        ttk.Button(self.account_page, text="保存账号并登录", style="Accent.TButton", command=self._save_account).pack(anchor=tk.E, pady=10)

    def _build_player(self, parent):
        self.player = ttk.Frame(parent, style="Panel.TFrame", padding=(16, 10))
        self.player.pack(fill=tk.X, pady=(12, 0))
        self.cover = tk.Label(self.player, text="暂无", width=5, height=2, bg="#172033", fg="#ffb020", font=("SFMono-Regular", 14, "bold"))
        self.cover.pack(side=tk.LEFT, padx=(0, 12))
        meta = ttk.Frame(self.player)
        meta.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.player_title = ttk.Label(meta, text="暂无歌曲", font=("SFMono-Regular", 12, "bold"))
        self.player_title.pack(anchor=tk.W)
        self.player_artist = ttk.Label(meta, text="--", style="Muted.TLabel")
        self.player_artist.pack(anchor=tk.W)

        controls = ttk.Frame(self.player)
        controls.pack(side=tk.LEFT, padx=18)
        self.play_button = ttk.Button(controls, text="▶", style="Accent.TButton", width=4, command=self._toggle_play)
        self.play_button.grid(row=0, column=1, padx=4)
        ttk.Button(controls, text="‹", width=3).grid(row=0, column=0, padx=4)
        ttk.Button(controls, text="›", width=3).grid(row=0, column=2, padx=4)
        ttk.Button(controls, text="↻", width=3).grid(row=0, column=3, padx=4)
        ttk.Button(controls, text="■", width=3, command=lambda: self.backend.stop(self._operation)).grid(row=0, column=4, padx=4)
        progress = ttk.Frame(controls)
        progress.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(6, 0))
        self.current_time = ttk.Label(progress, text="0:00", style="Muted.TLabel")
        self.current_time.pack(side=tk.LEFT)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Scale(progress, from_=0, to=1000, variable=self.progress_var, orient=tk.HORIZONTAL)
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.progress.bind("<ButtonPress-1>", lambda _: setattr(self, "dragging_progress", True))
        self.progress.bind("<ButtonRelease-1>", self._seek_from_slider)
        self.total_time = ttk.Label(progress, text="--:--", style="Muted.TLabel")
        self.total_time.pack(side=tk.LEFT)

        volume = ttk.Frame(self.player)
        volume.pack(side=tk.RIGHT)
        ttk.Label(volume, text="音量").pack(side=tk.LEFT)
        self.volume_var = tk.IntVar(value=8)
        self.volume_scale = ttk.Scale(volume, from_=0, to=100, variable=self.volume_var, orient=tk.HORIZONTAL)
        self.volume_scale.pack(side=tk.LEFT, padx=8)
        self.volume_scale.bind("<ButtonRelease-1>", lambda _: self.backend.volume(self.volume_var.get(), self._operation))
        self.volume_spin = ttk.Spinbox(volume, from_=0, to=100, textvariable=self.volume_var, width=5, command=lambda: self.backend.volume(self.volume_var.get(), self._operation))
        self.volume_spin.pack(side=tk.LEFT)
        self.player.pack_forget()

    def _field(self, parent, label: str, value: str, show: str = ""):
        ttk.Label(parent, text=label, style="Accent.TLabel").pack(anchor=tk.W, pady=(12, 4))
        entry = ttk.Entry(parent, show=show)
        entry.insert(0, value or "")
        entry.pack(fill=tk.X)
        return entry

    def _started(self, result: dict):
        if result.get("success"):
            self.status_msg("服务已启动")
        else:
            messagebox.showerror("启动失败", str(result.get("error") or "未知错误"))

    def _poll(self):
        try:
            status, events = self.backend.snapshot()
            self._apply_status(status)
            self._apply_events(events)
        finally:
            self.after(1000, self._poll)

    def _apply_status(self, status: dict):
        self.card_values["xiao"].configure(text="在线" if status.get("ready") else "启动中")
        self.card_values["coco"].configure(text=status.get("coco_base") or self.settings.coco_base)
        self.card_values["devices"].configure(text=f"{len(status.get('devices') or [])} 台")
        self.card_values["recent"].configure(text=status.get("last_keyword") or "暂无")
        self._apply_devices(status)
        self._apply_player(status)

    def _apply_events(self, events: list[dict]):
        self.logs.delete(0, tk.END)
        for item in events[:100]:
            self.logs.insert(tk.END, f"{item.get('at', '')[-8:]}  {str(item.get('level', '')).upper()}  {item.get('message', '')}")

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
        for device in devices:
            did = device["did"]
            frame = ttk.Frame(self.device_list, style="Panel.TFrame", padding=12)
            frame.pack(fill=tk.X, pady=(0, 8))
            ttk.Label(frame, text=f"{device.get('name')}  DID: {did}  {device.get('hardware')}", font=("SFMono-Regular", 11, "bold")).pack(anchor=tk.W)
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, pady=(8, 0))
            listen = tk.BooleanVar(value=did in selected)
            push = tk.BooleanVar(value=did in targets)
            alias = tk.StringVar(value=device.get("alias") or "")
            ttk.Checkbutton(row, text="语音监听", variable=listen).pack(side=tk.LEFT)
            ttk.Checkbutton(row, text="默认推送", variable=push).pack(side=tk.LEFT, padx=12)
            ttk.Entry(row, textvariable=alias, width=24).pack(side=tk.LEFT, padx=12)
            ttk.Button(row, text="命名", command=lambda d=did, a=alias: self.backend.save_alias(d, a.get(), self._operation)).pack(side=tk.LEFT)
            self.device_vars[did] = (listen, push, alias)

    def _apply_player(self, status: dict):
        song = status.get("last_song") or {}
        if song or status.get("last_used_url"):
            self.player.pack(fill=tk.X, pady=(12, 0))
        title = str(song.get("title") or "暂无歌曲")
        artist = str(song.get("artist") or "--")
        self.player_title.configure(text=title)
        self.player_artist.configure(text=artist)
        self.cover.configure(text=title[:2] if title else "暂无")
        self.duration = float(status.get("last_duration") or 0)
        position = float(status.get("last_position") or 0)
        paused = bool(status.get("playback_paused") or not status.get("last_used_url"))
        self.play_button.configure(text="▶" if paused else "Ⅱ")
        self.current_time.configure(text=self._fmt(position))
        self.total_time.configure(text=self._fmt(self.duration) if self.duration else "--:--")
        if self.duration > 0 and not self.dragging_progress:
            self.progress_var.set(min(1000, position / self.duration * 1000))

    def _search(self):
        keyword = self.keyword.get().strip()
        if keyword:
            self.backend.search(keyword, self._set_results)

    def _play_first(self):
        keyword = self.keyword.get().strip()
        if keyword:
            self.backend.play_keyword(keyword, self._operation)

    def _set_results(self, result: dict):
        self.results = [item.get("item") or {} for item in result.get("items", [])]
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
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
                    song.get("duration") or "--",
                    song.get("audio_type") or song.get("quality") or "",
                ),
            )

    def _push_selected(self):
        selected = self.results_tree.selection()
        if not selected:
            return
        self.backend.play_selected(self.results[int(selected[0])], self._operation)

    def _toggle_play(self):
        if self.play_button.cget("text") == "▶":
            self.backend.resume(self._operation)
        else:
            self.backend.pause(self._operation)

    def _seek_from_slider(self, _event):
        self.dragging_progress = False
        if self.duration > 0:
            self.backend.seek(float(self.progress_var.get()) / 1000 * self.duration, self._operation)

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
        self.logs.delete(0, tk.END)

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

    def _close(self):
        self.backend.shutdown()
        self.destroy()


def main():
    prepare_runtime_environment()
    app = CocoDesktopApp()
    app.mainloop()
