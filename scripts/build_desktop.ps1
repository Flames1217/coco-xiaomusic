$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python -m pip install -r requirements.txt
python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name coco-xiaomusic `
  --add-data "assets;assets" `
  --add-data "views;views" `
  --add-data "coco_xiaomusic;coco_xiaomusic" `
  .\desktop_app.py

Write-Host "桌面应用已生成：$Root\dist\coco-xiaomusic\coco-xiaomusic.exe"
