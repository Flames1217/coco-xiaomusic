# coco-xiaomusic

把小爱音箱的点歌请求接到自建 coco-downloader，并提供一个本地 Web 控制台。语音点歌默认使用 coco 搜索结果中最适合小爱播放的一条，前端则可以查看 coco 全量结果、筛选渠道并手动推送任意歌曲。

## 主要能力

- 语音触发：支持 `点歌 关键词`、`点一首 关键词`、`搜歌 关键词`、`可可 关键词`、`coco 关键词`。
- coco 优先：语音链路走 coco 搜索与解析，不依赖小爱官方音乐结果。
- 实时转码：coco 返回的音源通过本机 `/stream/{token}.mp3` 实时转成 MP3 推给音箱，避免部分小爱型号无法播放 `.aac` 裸流或带参数直链。
- 不缓存歌曲：歌曲音源不落地到 `music/tmp`，只保留内存中的临时流 token。
- 提示话术：可配置搜索中、命中、失败提示；TTS 临时文件播放后会自动清理。
- 控制台点歌：前端可搜索 coco 全部结果，按渠道筛选，查看封面、歌手、时长、音质信息，并手动推送任意一条。
- 底部播放器：只有真正推送成功并进入播放态后才浮现，支持暂停、继续、停止、进度跳转和音量调整。
- 多设备：可选择多台小爱参与语音监听，也可单独指定后台默认推送目标。
- 从 0 引导：控制台引导用户完成小米账号登录、token 生成、设备识别和最终播放。
- Windows 桌面应用：可用原生窗口打开控制台，自动启动或复用本地后台服务。
- Windows 服务：内置原生 Windows 服务脚本，不依赖 NSSM。

## 前置要求

- Python 3.11+，当前开发环境使用 Python 3.12。
- FFmpeg 可执行文件必须可被找到，用于实时转码和进度跳转。
  - 推荐把 `ffmpeg` 加入 `PATH`。
  - 或放在项目内 `ffmpeg/bin/ffmpeg.exe`。
  - 代码也会尝试查找 `D:/Best/ffmpeg/bin/ffmpeg.exe`。
- 能访问你部署的 coco-downloader 服务，例如 `https://coco.viper3.top`。
- 小米账号能正常登录并拥有目标小爱音箱。

## 安装依赖

```powershell
python -m pip install -r .\requirements.txt
```

`requirements.txt` 只包含 Python 依赖；FFmpeg 是系统依赖，需要单独安装。

## 启动

### 桌面应用启动

推荐 Windows 用户优先使用桌面入口：

```powershell
python .\desktop_app.py
```

或：

```powershell
.\scripts\run_desktop.ps1
```

桌面入口会打开一个原生窗口，并自动检查 `127.0.0.1:8088`：

- 如果已有 coco-xiaomusic 服务在运行，会直接复用。
- 如果没有服务，会在当前进程中启动后台 FastAPI 服务。
- 关闭窗口时，会自动停止由桌面入口启动的后台服务；如果复用的是 Windows 服务，则不会关闭它。

### Web 控制台启动

```powershell
python .\main.py
```

启动后访问：

```text
http://127.0.0.1:8088
```

默认监听地址是 `0.0.0.0:8088`，页面中“本机访问地址”建议填写局域网内音箱可以访问到的地址，例如：

```text
http://192.168.1.13
```

## 首次使用流程

1. 执行 `python .\main.py`。
2. 打开控制台首页。
3. 输入小米账号、密码和本机访问地址。
4. 系统会登录小米账号并生成 `conf/.mi.token`。
5. 登录成功后，在设备区选择参与语音监听的小爱音箱。
6. 选择后台默认推送目标，可一台或多台。
7. 保存设备方案后，对小爱说：`点歌 七朵组合的咏春`。
8. 音箱命中后会走 coco 搜索、提示话术和实时 MP3 推流。

## 语音播放策略

语音触发后，服务会先接管小爱原始指令，避免继续走官方音乐链路。命中关键词后：

1. 清理或接管当前小爱播放状态。
2. 调用 coco 搜索关键词。
3. 根据标题、歌手、封面、渠道和可解析程度选择候选。
4. 解析 coco 直链。
5. 通过本机 `/stream/{token}.mp3` 使用 FFmpeg 实时转 MP3。
6. 将 MP3 流地址推给小爱音箱。
7. 后端确认推送成功后，前端底部播放器才从底部浮现。

注意：小爱音箱的 Mina 状态接口偶尔会返回 `code=101`。项目会在这种情况下使用本地播放状态兜底，避免按钮、时长和日志被 Mina 抖动打乱。

## 控制台功能

- 账号与设备：保存账号、生成 token、选择监听设备和推送目标。
- 搜索与推送：获取 coco 全量搜索结果，按渠道筛选，手动推送指定歌曲。
- 播放器：暂停、继续、停止、跳转进度、调整音量。
- 运行日志：查看语音命中、搜索、解析、推送、Mina 状态等事件，并可一键清空。
- 运行策略：配置 coco 服务地址、静默接管延迟和 TTS 文案。

## Windows 服务

用管理员 PowerShell 执行：

```powershell
python .\windows_service.py --startup auto install
python .\windows_service.py start --wait 10
```

常用维护命令：

```powershell
python .\windows_service.py stop
python .\windows_service.py restart
python .\windows_service.py remove
```

如果服务启动后浏览器访问不了，先检查：

- `sc.exe query CocoXiaoMusic` 是否为 `RUNNING`。
- `python`、项目目录、FFmpeg 是否对服务运行账号可访问。
- `data/app_settings.json` 中 `admin_port` 是否仍为 `8088`。
- 防火墙是否允许局域网访问该端口。

## 打包 Windows 桌面版

如果要生成可分发的 `.exe`，执行：

```powershell
.\scripts\build_desktop.ps1
```

生成结果位于：

```text
dist\coco-xiaomusic\coco-xiaomusic.exe
```

打包版会把 Python 桌面入口、前端资源和后端代码放进同一个目录。FFmpeg 仍建议放到系统 `PATH`，或者随安装包一起放到项目可识别的位置，例如 `ffmpeg/bin/ffmpeg.exe`。

## 敏感数据与本地文件

以下路径包含账号、密码、token、设备 DID、缓存、临时 TTS 或日志，不应提交到 Git：

- `data/`
- `conf/`
- `music/`
- `.env`
- `*.log`
- `*.token`
- `*.cookie`
- `cookies.txt`

项目已经在 `.gitignore` 中忽略这些路径。当前仓库只应提交源码、前端资源、文档和依赖清单。

## 项目结构

```text
desktop_app.py               Windows 桌面应用入口
main.py                      Web 控制台启动入口
windows_service.py           Windows 服务入口
coco_xiaomusic/
  coco_client.py             coco-downloader API 封装
  service.py                 小爱接管、搜索、推流、播放器控制
  settings.py                本地配置读写与脱敏
  web.py                     FastAPI 路由与实时转码流端点
views/dashboard.html         控制台页面
assets/dashboard.css         控制台样式
assets/dashboard.js          控制台交互
scripts/run_desktop.ps1      启动桌面应用
scripts/build_desktop.ps1    打包桌面应用
requirements.txt             Python 依赖
```

## 常见问题

### 小爱提示播放失败或换一个试试

优先确认本机访问地址是音箱能访问到的局域网 IP，而不是 `127.0.0.1`。例如后台里应填 `http://192.168.1.13`。还要确认 FFmpeg 可用，因为所有 coco 直链都会通过 `/stream/{token}.mp3` 实时转码。

### 为什么还会看到 `music/tmp` 里短暂出现 MP3

歌曲音源不会落地缓存。`music/tmp` 里短暂出现的通常是 edge-tts 生成的提示话术文件，播放后会自动重试删除。

### 暂停和继续为什么偶尔和真实音箱状态不同步

小爱 Mina 状态接口偶尔会超时或返回 `code=101`。控制台会优先采用本地状态兜底，并在后台补一次确认或重推，避免 UI 因 Mina 抖动频繁跳变。
