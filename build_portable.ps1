param(
    [string]$PythonExe = "E:\anaconda\python.exe"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$distRoot = Join-Path $projectRoot "dist"
$buildRoot = Join-Path $projectRoot "build"
$appName = "AttendanceRebuild"
$portableAssetsDir = Join-Path $projectRoot "portable_assets"

Set-Location $projectRoot

& $PythonExe -m pip install --upgrade pyinstaller

if (Test-Path $buildRoot) {
    Remove-Item -Recurse -Force $buildRoot
}

$packageDir = Join-Path $distRoot $appName
if (Test-Path $packageDir) {
    Remove-Item -Recurse -Force $packageDir
}

& $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name $appName `
    --paths $projectRoot `
    --add-data "rebuild_login\web;rebuild_login\web" `
    rebuild_login\server.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$launcherPath = Join-Path $packageDir "Launch-AttendanceRebuild.bat"
$launcherContent = @'
@echo off
setlocal
cd /d "%~dp0"
start "" "AttendanceRebuild.exe"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8765"
endlocal
'@
Set-Content -LiteralPath $launcherPath -Value $launcherContent -Encoding Ascii

$backgroundLauncherSource = Join-Path $portableAssetsDir "Launch-AttendanceRebuild-Background.vbs"
$backgroundLauncherPath = Join-Path $packageDir "Launch-AttendanceRebuild-Background.vbs"
Copy-Item -LiteralPath $backgroundLauncherSource -Destination $backgroundLauncherPath -Force

$autostartManagerSource = Join-Path $portableAssetsDir "Manage-AttendanceRebuild-Autostart.ps1"
$autostartManagerPath = Join-Path $packageDir "Manage-AttendanceRebuild-Autostart.ps1"
Copy-Item -LiteralPath $autostartManagerSource -Destination $autostartManagerPath -Force

$readmePath = Join-Path $packageDir "README.txt"
$readmeContent = @'
AttendanceRebuild portable package

1. Double-click Launch-AttendanceRebuild.bat
2. Wait 2 seconds and your browser should open http://127.0.0.1:8765
3. Runtime data will be created in .attendance_auth next to the executable
4. To enable backend autostart without opening the browser, run:
   powershell -ExecutionPolicy Bypass -File .\Manage-AttendanceRebuild-Autostart.ps1 -Mode Install

Notes:
- Copy the whole AttendanceRebuild folder to another device, not only the exe.
- Put it in a writable folder such as Desktop or D:\Work.
- If port 8765 is already occupied, run AttendanceRebuild.exe --port 8876 from a terminal.
'@
Set-Content -LiteralPath $readmePath -Value $readmeContent -Encoding UTF8

$zipPath = Join-Path $distRoot "AttendanceRebuild-portable.zip"
if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}
Compress-Archive -Path $packageDir -DestinationPath $zipPath

Write-Host "Portable package ready:"
Write-Host $packageDir
Write-Host $zipPath
