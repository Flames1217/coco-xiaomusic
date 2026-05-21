# coco-xiaomusic

coco-xiaomusic is a lightweight Windows desktop controller for routing XiaoAI song requests through a coco-downloader music source.

The app is rebuilt from scratch with:

- Tauri 2 and Rust for the desktop shell
- Svelte and TypeScript for the UI
- A Python FastAPI backend service for XiaoMusic, coco search, playback control, and LAN audio streaming

## Development

Prerequisites:

- Rust stable with the `x86_64-pc-windows-msvc` target
- Visual Studio 2022 Build Tools with **Desktop development with C++** and the Windows 10/11 SDK
- Node.js, pnpm, and Python 3.11+

Install frontend dependencies:

```powershell
pnpm install
```

Install backend service dependencies:

```powershell
python -m pip install -r .\sidecar\requirements.txt
```

Run the desktop app:

```powershell
pnpm tauri:dev
```

Useful checks:

```powershell
pnpm check
pnpm build
cd .\src-tauri
cargo check
cd ..
python -m py_compile (Get-ChildItem .\sidecar -Recurse -Filter *.py).FullName
```

## Runtime Data

Tauri launches the Python backend service with `COCO_XIAOMUSIC_HOME` pointing to `runtime/` inside the project or portable app directory. It also points Python temp, cache, appdata, and pycache variables into that same runtime directory so normal app usage does not write coco-xiaomusic state to the Windows user profile on `C:`.

- `runtime/data/app_settings.json`
- `runtime/conf/`
- `runtime/music/tmp/`
- `runtime/music/cache/`
- `runtime/logs/`
