# coco-xiaomusic

把小爱音箱语音播放接到 coco-downloader，并内置一个本地后台控制台。

## 启动

```powershell
pip install -r .\requirements.txt
```

然后运行：

```powershell
python .\main.py
```

启动后访问：

```text
http://127.0.0.1:8088
```

## 功能

- 监听小爱语音口令：`点歌 关键词`、`点一首 关键词`、`搜歌 关键词`
- 语音口令严格使用 coco 搜索结果第一条
- 语音第一条没有直链时不回退其他音源
- 保留官方原本应答，再播 coco 搜索提示与命中提示
- 后台手动推送播放，并可指定多个目标设备
- 后台接收 coco 全量搜索结果，任意结果可单独推送
- 后台静默停止小爱当前播放
- 后台显示运行状态、最近命令、最近播放和事件流
- 首次使用引导：账号、token、设备、服务就绪状态
- 多设备接入：多台小爱参与语音监听
- 多目标推送：后台默认目标可选一台或多台
- 后台可编辑 coco 服务地址、应答延迟和 TTS 话术

## 首次启动

1. 执行 `python .\main.py`。
2. 打开后台首页。
3. 在“从 0 到可播放”区域输入小米账号、密码和本机访问地址。
4. 系统会自动尝试登录，并在 `conf/.mi.token` 生成 token。
5. 登录成功后，勾选参与语音监听的音箱，并选择后台默认推送目标。
6. 四步状态都完成后，再测试语音口令或后台手动推送。

## 项目结构

- `main.py`：唯一启动入口
- `coco_xiaomusic/`：服务端代码
- `views/`：后台页面
- `assets/`：后台样式与脚本

## 配置

首次启动直接在后台页面填写账号、密码并选择设备。

运行后配置会保存到：

```text
data/app_settings.json
```

当前按你的要求不依赖环境变量。

## 注册为 Windows 服务

Windows 上可以直接用项目自带的原生服务入口，不依赖 NSSM。

先安装依赖：

```powershell
python -m pip install -r .\requirements.txt
```

然后用管理员 PowerShell 执行：

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

服务默认读取项目目录内的 `data/`、`conf/`、`music/`，所以请保持整个项目目录可访问。`pywin32` 官方也提醒，Windows 服务运行账号必须能访问 Python 安装目录及相关 DLL；如果你的 Python 装在个人用户目录，建议把服务账号改成你自己的 Windows 账号，或者使用系统可访问的 Python 安装路径。
