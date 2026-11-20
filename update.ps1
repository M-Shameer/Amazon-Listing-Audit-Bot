# ==============================================================
# GET THE LATEST VERSION OF THE BOT FROM YOUR PRIVATE GITHUB
# Do not run directly: double-click "Update Audit Bot.bat".
#
# Replaces the bot's CODE with the latest published version.
# Kept untouched: your postcode and seller (settings.json), audit
# history, specification templates, the Amazon login profile and .venv.
#
# Do NOT use it on the laptop where you make changes before publishing
# them: unpublished code changes on this laptop would be replaced.
# ==============================================================

Set-Location $PSScriptRoot
. (Join-Path $PSScriptRoot "git_helpers.ps1")

Write-Host "==============================================" -ForegroundColor Green
Write-Host "   UPDATE AMAZON AUDIT BOT"                     -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green

$git = Get-Git
$url = Get-RepoUrl
Use-Repo $git $url

$before = & $git rev-parse --short HEAD 2>$null

Write-Host "Downloading the latest version (the first time, a GitHub sign-in window opens)..."
& $git fetch -q origin main

if ($LASTEXITCODE -ne 0) {
    Stop-With "Could not download. Check the internet and that you signed in with the right GitHub account."
}

& $git reset -q --hard origin/main
$after = & $git rev-parse --short HEAD

if ($before -eq $after) {
    Write-Host "You already have the latest version." -ForegroundColor Green
} else {
    Write-Host "Updated to the latest version." -ForegroundColor Green
}

# New libraries, if an update needs them (quick when nothing changed).
$venv = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venv) {
    Write-Host "Checking libraries..."
    & $venv -m pip install -q -r requirements.txt
    & $venv -m pip install -q -r requirements-ocr.txt
} else {
    Write-Host "Not installed yet: double-click 'Install Audit Bot.bat'." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "DONE. Close the bot's window (if open) and start it again from the desktop icon." -ForegroundColor Green
exit 0
