# coco-xiaomusic

🎵 **coco-xiaomusic** 是一个原生 Windows 桌面应用，用来把小爱音箱的点歌请求接入自建的 coco-downloader 音源。

它负责小米账号登录、设备选择、coco 搜索、手动推送、语音接管、实时日志和播放控制。小爱音箱实际播放时，会通过本机内部流服务拉取兼容的 MP3 音频。

## ✨ 主要功能

- 🖥️ 原生 Windows 桌面窗口，不依赖浏览器或 WebView
- 🎙️ 支持小爱语音点歌，命中关键词后优先走 coco 音源
- 🔎 支持搜索 coco 全部结果，并手动推送任意一首
- 🎧 内置底部音乐播放栏，可暂停、继续、停止、调音量
- 📻 支持多设备管理、监听设备、默认推送设备和设备别名
- 🧩 支持配置 coco 服务地址、提示话术和接管策略
- 🔁 内置 MP3 流服务，提升小爱音箱播放兼容性
- 📦 支持便携版和安装版打包

## 🚀 快速开始

### 方式一：直接运行源码

```powershell
python -m pip install -r .\requirements.txt
python .\desktop_app.py
```

`main.py` 和 `desktop_app.py` 都会启动同一个桌面应用入口。

### 方式二：使用便携版

下载 `coco-xiaomusic-portable.zip`，解压后运行：

```text
coco-xiaomusic.exe
```

便携版会把配置、日志和运行数据保存在解压目录内，适合直接复制到任意 Windows 电脑使用。

## 🧰 运行要求

- Windows 10 / Windows 11
- Python 3.11+（源码运行时需要）
- FFmpeg
- 可访问你的 coco-downloader 服务，例如 `https://coco.viper3.top`
- 小米账号下已经绑定目标小爱音箱

FFmpeg 推荐加入系统 `PATH`，或者放到项目内：

```text
ffmpeg/bin/ffmpeg.exe
```

## 🏗️ 本地打包

### 打包便携版

```powershell
.\scripts\build_desktop.ps1
```

输出文件：

```text
release\coco-xiaomusic-portable\
release\coco-xiaomusic-portable.zip
```

### 打包安装版

先安装 Inno Setup 6，然后执行：

```powershell
.\scripts\build_installer.ps1
```

输出文件：

```text
release\coco-xiaomusic-setup.exe
```

## 🪟 Windows 服务

如果你希望后台自启，可以用管理员 PowerShell 注册服务：

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

## 📁 项目结构

```text
coco-xiaomusic
├── desktop_app.py                  # 桌面应用入口
├── main.py                         # 同样启动桌面应用
├── windows_service.py              # Windows 服务入口
├── requirements.txt                # Python 依赖
├── coco_xiaomusic
│   ├── native_app.py               # 原生桌面界面
│   ├── service.py                  # 小爱接管、搜索、推送和播放控制
│   ├── stream_server.py            # 内部 MP3 流服务
│   ├── coco_client.py              # coco-downloader API 封装
│   └── settings.py                 # 本地配置读写
├── scripts
│   ├── build_desktop.ps1           # 构建 EXE 和便携版
│   └── build_installer.ps1         # 构建安装包
└── packaging
    ├── pyinstaller
    │   └── coco-xiaomusic.spec     # PyInstaller 配置
    └── installer
        └── coco-xiaomusic.iss      # Inno Setup 配置
```

## 💡 使用建议

- 第一次启动后，先在「账号」页登录小米账号
- 在「设备」页选择参与监听和默认推送的小爱音箱
- 在「策略」页确认 coco 服务地址和提示话术
- 回到「控制台」页搜索歌曲，或直接对小爱说配置好的点歌关键词

如果音箱提示播放失败，优先检查 FFmpeg、coco 服务地址、本机 IP 是否能被音箱访问，以及音箱和电脑是否在同一局域网。
