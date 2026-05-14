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
  throw "Inno Setup 6 not found. Install Inno Setup or use release\coco-xiaomusic-portable.zip."
}

& $Iscc.Source ".\packaging\installer\coco-xiaomusic.iss"
Write-Host "Installer generated: $Root\release\coco-xiaomusic-setup.exe"
