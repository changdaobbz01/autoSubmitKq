@echo off
setlocal

set "APP_DIR=%~dp0"
set "APP_EXE=%~dp0AttendanceTokenCollector.exe"

if not exist "%APP_EXE%" (
    echo AttendanceTokenCollector.exe was not found in this folder.
    echo Please keep this script beside the application executable.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference = 'Stop';" ^
    "$appDir = $env:APP_DIR.TrimEnd([char]92);" ^
    "$target = Join-Path $appDir 'AttendanceTokenCollector.exe';" ^
    "$desktop = if ([string]::IsNullOrWhiteSpace($env:ATTENDANCE_SHORTCUT_DESKTOP)) { [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory) } else { $env:ATTENDANCE_SHORTCUT_DESKTOP };" ^
    "[IO.Directory]::CreateDirectory($desktop) | Out-Null;" ^
    "$shortcutName = -join @([char]0x8003, [char]0x52e4, ' Token ', [char]0x91c7, [char]0x96c6, [char]0x5668, '.lnk');" ^
    "$description = -join @([char]0x8003, [char]0x52e4, ' Token ', [char]0x91c7, [char]0x96c6, [char]0x5668);" ^
    "$linkPath = Join-Path $desktop $shortcutName;" ^
    "$shell = New-Object -ComObject WScript.Shell;" ^
    "$shortcut = $shell.CreateShortcut($linkPath);" ^
    "$shortcut.TargetPath = $target;" ^
    "$shortcut.WorkingDirectory = $appDir;" ^
    "$shortcut.IconLocation = $target + ',0';" ^
    "$shortcut.Description = $description;" ^
    "$shortcut.Save();"

if errorlevel 1 (
    echo Failed to create the desktop shortcut.
    pause
    exit /b 1
)

echo Desktop shortcut created successfully.
exit /b 0
