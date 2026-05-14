$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean .\packaging\pyinstaller\coco-xiaomusic.spec

$Portable = Join-Path $Root "release\coco-xiaomusic-portable"
if (Test-Path $Portable) {
  Remove-Item $Portable -Recurse -Force
}
New-Item -ItemType Directory -Force $Portable | Out-Null
Copy-Item (Join-Path $Root "dist\coco-xiaomusic\*") $Portable -Recurse -Force
New-Item -ItemType File -Force (Join-Path $Portable "portable.flag") | Out-Null
New-Item -ItemType Directory -Force `
  (Join-Path $Portable "data"), `
  (Join-Path $Portable "conf"), `
  (Join-Path $Portable "music"), `
  (Join-Path $Portable "music\tmp"), `
  (Join-Path $Portable "music\cache"), `
  (Join-Path $Portable "logs") | Out-Null

$Launcher = Join-Path $Portable "启动 coco-xiaomusic.bat"
Set-Content -Path $Launcher -Encoding ASCII -Value '@echo off
cd /d "%~dp0"
start "" "%~dp0coco-xiaomusic.exe"
'

Write-Host "桌面应用已生成：$Root\dist\coco-xiaomusic\coco-xiaomusic.exe"
Write-Host "便携版已生成：$Portable"
