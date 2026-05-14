param(
  [string]$Tag = "v0.1.0",
  [string]$Repo = "Flames1217/coco-xiaomusic"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Token = $env:GH_TOKEN
if (-not $Token) {
  $Token = $env:GITHUB_TOKEN
}
if (-not $Token) {
  throw "Missing GH_TOKEN or GITHUB_TOKEN. Cannot publish GitHub Releases."
}

.\scripts\build_desktop.ps1

$Installer = Join-Path $Root "release\coco-xiaomusic-setup.exe"
try {
  .\scripts\build_installer.ps1
} catch {
  Write-Warning "Installer was not generated: $($_.Exception.Message)"
}

$PortableZip = Join-Path $Root "release\coco-xiaomusic-portable.zip"
$Assets = @($PortableZip)
if (Test-Path $Installer) {
  $Assets += $Installer
}

$Headers = @{
  Authorization = "Bearer $Token"
  Accept = "application/vnd.github+json"
  "X-GitHub-Api-Version" = "2022-11-28"
}

$Body = @{
  tag_name = $Tag
  name = "coco-xiaomusic $Tag"
  body = "Native Windows desktop release. Includes portable archive and installer when Inno Setup is available."
  draft = $false
  prerelease = $false
} | ConvertTo-Json

$Release = Invoke-RestMethod `
  -Method Post `
  -Uri "https://api.github.com/repos/$Repo/releases" `
  -Headers $Headers `
  -Body $Body `
  -ContentType "application/json; charset=utf-8"

foreach ($Asset in $Assets) {
  if (-not (Test-Path $Asset)) {
    continue
  }
  $Name = Split-Path $Asset -Leaf
  $UploadUrl = $Release.upload_url -replace "\{\?name,label\}", "?name=$Name"
  Invoke-RestMethod `
    -Method Post `
    -Uri $UploadUrl `
    -Headers $Headers `
    -InFile $Asset `
    -ContentType "application/octet-stream" | Out-Null
  Write-Host "Uploaded: $Name"
}

Write-Host "Release published: $($Release.html_url)"
