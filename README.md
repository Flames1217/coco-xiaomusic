<p align="center">
  <img src="./assets/logo.png" width="112" alt="coco-xiaomusic logo" />
</p>

<h1 align="center">🎵 coco-xiaomusic</h1>

<p align="center">
  轻量的小爱音箱 coco 音乐控制台。把小爱音箱的点歌、搜歌、播放控制接到 coco 音乐搜索服务。
</p>

<p align="center">
  <img src="./assets/readme/tech/windows11.svg" width="18" height="18" align="absmiddle" alt="Windows" />
  <b>Windows 10/11</b>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <img src="./assets/readme/tech/tauri.svg" width="18" height="18" align="absmiddle" alt="Tauri" />
  <b>Tauri 2</b>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <img src="./assets/readme/tech/react.svg" width="18" height="18" align="absmiddle" alt="React" />
  <b>React</b>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <img src="./assets/readme/tech/fastapi.svg" width="18" height="18" align="absmiddle" alt="FastAPI" />
  <b>FastAPI</b>
</p>

## <img src="./assets/readme/sparkles.svg" width="22" height="22" align="absmiddle" alt="" /> 鸣谢与灵感来源

<p>
  <img src="./assets/readme/projects/coco-cherry-logo.svg" width="18" height="18" align="absmiddle" alt="COCO Downloader" />
  <b>coco 音乐下载站 / COCO Downloader</b>：本项目默认对接用户自建的 coco 音乐服务。项目地址：
  <a href="https://github.com/markcxx/coco-downloader">markcxx/coco-downloader</a>
</p>

<p>
  <img src="https://github.com/hanxi.png?size=36" width="18" height="18" align="absmiddle" alt="hanxi/xiaomusic" />
  <b>XiaoMusic</b>：本项目的小爱音箱登录、设备控制和播放链路参考并集成 XiaoMusic 能力。项目地址：
  <a href="https://github.com/hanxi/xiaomusic">hanxi/xiaomusic</a>
</p>

> <img src="./assets/readme/alert-triangle.svg" width="16" height="16" align="absmiddle" alt="" /> coco 服务需要用户自行搭建并在应用内填写服务地址。本仓库不包含、不托管、不分发 coco 服务端或任何敏感音源服务代码。

## ✨ 主要能力

- 🔐 小米账号登录、授权验证、设备发现和设备别名。
- 🔎 coco 多渠道搜索、渠道预选、搜索结果筛选、封面展示。
- 🎶 手动推送、播放列表、上一首、下一首、暂停、继续、停止、进度和音量控制。
- 🗣️ 小爱音箱语音接管，可按关键词接管或全量接管。
- 🖥️ 右下角系统托盘控制：打开主窗口、播放/暂停、上一首、下一首、播放列表点歌、退出应用并关闭服务。
- 🚀 应用内检查 GitHub Release 新版本，显示更新日志，下载便携更新包后自动覆盖并重启。
- 🧼 所有运行数据、缓存、日志、临时更新文件都保存在应用目录内的 `runtime/`，不主动写入用户的 C 盘配置目录。

## 🧱 技术栈

- 🦀 **Tauri 2 + Rust**：桌面窗口、托盘、进程管理、更新下载和本地命令。
- ⚛️ **React + TypeScript**：桌面控制台界面。
- 🐍 **Python FastAPI**：XiaoMusic 集成、coco 搜索、播放控制和局域网音频流服务。

## 📁 目录说明

- `src-tauri/`：Rust/Tauri 主程序。
- `src/`：前端界面。
- `sidecar/`：Python 后台服务。
- `assets/`：应用图标和 logo。
- `runtime/`：运行时数据目录，首次启动自动创建。

## 🧳 运行时数据

应用启动时会把以下环境变量指向应用目录内的 `runtime/`，避免把状态、缓存和临时文件写到系统盘用户目录：

- `COCO_XIAOMUSIC_HOME`
- `TEMP`
- `TMP`
- `HOME`
- `USERPROFILE`
- `APPDATA`
- `LOCALAPPDATA`
- `XDG_CACHE_HOME`
- `PIP_CACHE_DIR`
- `PYTHONPYCACHEPREFIX`

常见数据位置：

- `runtime/data/app_settings.json`：账号、设备、策略、音量、关闭偏好等配置。
- `runtime/data/app_prefs.json`：应用级偏好。
- `runtime/conf/`：小米登录 token。
- `runtime/music/tmp/`：临时音频。
- `runtime/music/cache/`：音频缓存。
- `runtime/logs/`：后台日志。
- `runtime/update/`：应用内更新下载和临时解压目录。
- `runtime/webview/`：Tauri WebView 本地数据。

## 🛠️ 开发环境

需要：

- Rust stable，Windows MSVC 工具链。
- Node.js、pnpm。
- Python 3.11+。
- Windows 上可用的 C++ 构建工具。

安装依赖：

```powershell
pnpm install
python -m pip install -r .\sidecar\requirements.txt
```

开发运行：

```powershell
pnpm tauri:dev
```

常用检查：

```powershell
pnpm check
pnpm build
cd .\src-tauri
cargo check
cd ..
python -m py_compile (Get-ChildItem .\sidecar -Recurse -Filter *.py).FullName
```

## 📦 打包发布

生成 release 可执行文件：

```powershell
pnpm tauri build --no-bundle
```

生成安装包：

```powershell
pnpm tauri build --bundles nsis
```

便携版发布包需要包含：

- `coco-xiaomusic.exe`
- `sidecar/`
- `assets/`
- `README.md`

应用内自动更新会优先下载 GitHub Release 中名称包含 `portable` 的 zip 包，并在应用目录内完成覆盖和重启。

## 🧭 使用提示

- 首次使用先到 **账号授权** 填写小米账号密码并完成安全验证。
- 登录后到 **设备管理** 刷新设备，选择监听设备和推送设备。
- 到 **搜索与推送** 搜歌，加入播放列表或直接推送到小爱音箱。
- 点击窗口右上角关闭时，可以选择最小化到右下角托盘，也可以退出并关闭后台服务。
