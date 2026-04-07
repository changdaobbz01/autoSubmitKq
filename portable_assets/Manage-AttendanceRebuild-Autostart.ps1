param(
    [ValidateSet("Install", "Remove", "Status")]
    [string]$Mode = "Install"
)

$ErrorActionPreference = "Stop"

$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "AttendanceRebuild Backend.lnk"
$vbsPath = Join-Path $PSScriptRoot "Launch-AttendanceRebuild-Background.vbs"
$exePath = Join-Path $PSScriptRoot "AttendanceRebuild.exe"
$wscriptExe = Join-Path $env:SystemRoot "System32\wscript.exe"

function Get-AutostartStatus {
    if (-not (Test-Path $shortcutPath)) {
        return [pscustomobject]@{
            Installed = $false
            ShortcutPath = $shortcutPath
            Target = ""
        }
    }

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    return [pscustomobject]@{
        Installed = $true
        ShortcutPath = $shortcutPath
        Target = $shortcut.TargetPath
        Arguments = $shortcut.Arguments
        WorkingDirectory = $shortcut.WorkingDirectory
    }
}

switch ($Mode) {
    "Install" {
        if (-not (Test-Path $exePath)) {
            throw "AttendanceRebuild.exe not found: $exePath"
        }
        if (-not (Test-Path $vbsPath)) {
            throw "Launch-AttendanceRebuild-Background.vbs not found: $vbsPath"
        }

        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $wscriptExe
        $shortcut.Arguments = '"' + $vbsPath + '"'
        $shortcut.WorkingDirectory = $PSScriptRoot
        $shortcut.WindowStyle = 7
        $shortcut.IconLocation = "$exePath,0"
        $shortcut.Description = "Start AttendanceRebuild backend at Windows sign-in"
        $shortcut.Save()

        Write-Output "Autostart installed."
        Get-AutostartStatus | ConvertTo-Json
    }
    "Remove" {
        if (Test-Path $shortcutPath) {
            Remove-Item -Force $shortcutPath
            Write-Output "Autostart removed."
        } else {
            Write-Output "Autostart was not installed."
        }
        Get-AutostartStatus | ConvertTo-Json
    }
    "Status" {
        Get-AutostartStatus | ConvertTo-Json
    }
}
