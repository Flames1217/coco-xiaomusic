$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".\dist\coco-xiaomusic\coco-xiaomusic.exe")) {
  .\scripts\build_desktop.ps1
}

$Iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
if (-not $Iscc) {
  $Candidate = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
  if (Test-Path $Candidate) {
    $Iscc = Get-Item $Candidate
  }
}

if (-not $Iscc) {
  throw "未找到 Inno Setup 6。请先安装 Inno Setup，或只使用 release\coco-xiaomusic-portable 便携版。"
}

& $Iscc.Source ".\packaging\installer\coco-xiaomusic.iss"
Write-Host "安装包已生成：$Root\release\coco-xiaomusic-setup.exe"
