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
  $Candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
  )

  $RegistryKeys = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
  )
  foreach ($Key in $RegistryKeys) {
    if (Test-Path $Key) {
      $InstallLocation = (Get-ItemProperty $Key).InstallLocation
      if ($InstallLocation) {
        $Candidates += (Join-Path $InstallLocation "ISCC.exe")
      }
    }
  }

  foreach ($Candidate in $Candidates) {
    if ($Candidate -and (Test-Path $Candidate)) {
      $Iscc = Get-Item $Candidate
      break
    }
  }
}

if (-not $Iscc) {
  throw "Inno Setup 6 not found. Install Inno Setup or use release\coco-xiaomusic-portable.zip."
}

$IsccPath = $Iscc.Source
if (-not $IsccPath) {
  $IsccPath = $Iscc.FullName
}

& $IsccPath ".\packaging\installer\coco-xiaomusic.iss"
Write-Host "Installer generated: $Root\release\coco-xiaomusic-setup.exe"
