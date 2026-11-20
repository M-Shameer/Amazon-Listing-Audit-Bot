# ==============================================================
# MAKE A SMALL COPY OF THE BOT FOR ANOTHER LAPTOP
# Do not run directly: double-click "Make Portable Copy.bat".
#
# Leaves OUT: .venv (rebuilt by the installer), the bot's Chrome
# profile (contains Amazon cookies - never copy it), exports, logs,
# caches and git history.
# Keeps: all code, your settings, specification templates and your
# audit history database.
#
# On the other laptop: unzip, then double-click "Install Audit Bot.bat".
# ==============================================================

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$stamp = Get-Date -Format "yyyyMMdd_HHmm"
$temp = Join-Path $env:TEMP "audit_bot_copy_$stamp"
$out = Join-Path (Split-Path $PSScriptRoot -Parent) "Amazon_Listing_Audit_Bot_portable_$stamp.zip"

Write-Host "Copying the bot (without the Amazon login profile)..." -ForegroundColor Cyan

robocopy . $temp /E /XD .venv __pycache__ exports logs amazon_uk_profile .git /XF *.pyc | Out-Null

# The Amazon profile must never travel; check once more.
if (Test-Path (Join-Path $temp "data\amazon_uk_profile")) {
    Remove-Item (Join-Path $temp "data\amazon_uk_profile") -Recurse -Force
}

Compress-Archive -Path "$temp\*" -DestinationPath $out -Force
Remove-Item $temp -Recurse -Force

$sizeMb = [math]::Round((Get-Item $out).Length / 1MB, 2)

Write-Host ""
Write-Host "Created: $out ($sizeMb MB)" -ForegroundColor Green
Write-Host "Copy this .zip to the other laptop, unzip it, then double-click"
Write-Host "'Install Audit Bot.bat' inside the unzipped folder."
