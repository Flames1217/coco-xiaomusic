# coco-xiaomusic

coco-xiaomusic 是一个原生 Windows 桌面应用，用来把小爱音箱的点歌请求接入自建 coco-downloader 音源。桌面端负责账号登录、设备选择、点歌搜索、手动推送、运行日志和播放器控制；后台只保留给音箱拉取 MP3 转码流的本机 HTTP 服务，不再提供浏览器控制台。

## 功能

- 原生 Windows 桌面窗口，不依赖浏览器或 WebView。
- 语音点歌命中关键词后优先走 coco 搜索与解析。
- 前台可搜索 coco 全量结果，并手动推送任意一条。
- 支持多设备监听、默认推送目标、设备别名。
- 支持提示话术、coco 地址、接管策略配置。
- 内置实时转码流 `/stream/{token}.mp3`，用于兼容小爱音箱播放 MP3。
- 支持便携版和安装版打包。

## 开发运行

```powershell
python -m pip install -r .\requirements.txt
python .\desktop_app.py
```

`main.py` 和 `desktop_app.py` 都会启动同一个原生桌面应用入口。

## 运行要求

- Windows 10/11
- Python 3.11+
- FFmpeg 可执行文件可被找到：
  - 推荐加入系统 `PATH`
  - 或放到项目内 `ffmpeg/bin/ffmpeg.exe`
- 可访问你的 coco-downloader 服务，例如 `https://coco.viper3.top`
- 小米账号下已有目标小爱音箱

## 打包便携版

```powershell
.\scripts\build_desktop.ps1
```

输出：

```text
dist\coco-xiaomusic\coco-xiaomusic.exe
release\coco-xiaomusic-portable\
release\coco-xiaomusic-portable.zip
```

便携版目录中包含 `portable.flag`，所以账号配置、token、日志、缓存都会留在便携目录里，适合直接发给用户解压使用。

## 打包安装版

先安装 Inno Setup 6，然后执行：

```powershell
.\scripts\build_installer.ps1
```

输出：

```text
release\coco-xiaomusic-setup.exe
```

安装版程序默认进入 `Program Files`，运行数据默认放到 `%APPDATA%\coco-xiaomusic`。如需强制指定数据目录，可设置环境变量 `COCO_XIAOMUSIC_HOME`。

## 发布 GitHub Releases

本机没有 `gh` CLI 时也可以用脚本通过 GitHub API 发布：

```powershell
$env:GH_TOKEN="你的 GitHub Token"
.\scripts\publish_release.ps1 -Tag v0.1.0
```

脚本会先打包便携版，尝试生成安装版，然后上传到 `Flames1217/coco-xiaomusic` 的 Releases。

## Windows 服务

桌面版是推荐使用方式。如果仍需要服务后台运行，可以用管理员 PowerShell：

```powershell
python .\windows_service.py --startup auto install
python .\windows_service.py start --wait 10
```

维护命令：

```powershell
python .\windows_service.py stop
python .\windows_service.py restart
python .\windows_service.py remove
```

## 敏感数据

以下内容不要提交到 Git：

- `data/`
- `conf/`
- `music/`
- `logs/`
- `.env`
- `*.log`
- `*.token`
- `*.cookie`
- `cookies.txt`

`.gitignore` 已经忽略这些路径，以及 `build/`、`dist/`、`release/` 等打包产物。

## 项目结构

```text
desktop_app.py                     原生桌面应用入口
main.py                            同样启动桌面应用
windows_service.py                 Windows 服务入口
coco_xiaomusic/
  native_app.py                    Tk/Ttk 原生桌面界面
  stream_server.py                 给音箱使用的内部 MP3 流服务
  service.py                       小爱接管、coco 搜索、推流和播放器控制
  coco_client.py                   coco-downloader API 封装
  settings.py                      本地配置读写
scripts/
  build_desktop.ps1                构建 EXE 和便携版
  build_installer.ps1              构建安装包
  publish_release.ps1              发布 GitHub Releases
packaging/
  pyinstaller/coco-xiaomusic.spec  PyInstaller 配置
  installer/coco-xiaomusic.iss     Inno Setup 配置
```
