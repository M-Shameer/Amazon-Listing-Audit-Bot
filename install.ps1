# ==============================================================
# AMAZON AUDIT BOT - ONE-TIME INSTALL ON A WINDOWS 10/11 LAPTOP
#
# Do not run this file directly: double-click "Install Audit Bot.bat".
#
# What it does:
#   1. Finds Python 3.10 or newer. If none, installs Python 3.13 with
#      Windows' own installer (winget). No admin rights needed.
#   2. Creates the bot's private Python folder (.venv).
#   3. Installs the libraries (requirements.txt).
#   4. Installs the Chromium browser the bot uses.
#   5. Installs OCR (requirements-ocr.txt) and downloads its text
#      models once (then works offline). Optional: if it fails, the
#      rest of the bot still works.
#   6. Puts an "Amazon Audit Bot" icon on the desktop.
#
# Safe to run again at any time (it repairs or updates the install).
# ==============================================================

# "Continue": Python and pip print normal warnings that Windows
# PowerShell 5.1 would otherwise treat as fatal. Each step is checked
# with its exit code instead.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$Venv = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Write-Step($number, $text) {
    Write-Host ""
    Write-Host "[$number/6] $text" -ForegroundColor Cyan
}

function Stop-Install($message) {
    Write-Host ""
    Write-Host "INSTALL STOPPED: $message" -ForegroundColor Red
    Write-Host "Nothing on this laptop was damaged. Fix the problem above and"
    Write-Host "double-click Install Audit Bot.bat again."
    exit 1
}

function Test-Python($path) {
    # True if $path is Python 3.10 or newer (and not the Microsoft Store stub).
    if (-not $path -or -not (Test-Path $path)) { return $false }
    if ($path -like "*\WindowsApps\*") { return $false }
    try {
        & $path -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Find-Python {
    # 1. The "py" launcher (installed with Python from python.org / winget).
    $launchers = @(
        (Get-Command py -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        "$env:LOCALAPPDATA\Programs\Python\Launcher\py.exe",
        "$env:WINDIR\py.exe"
    )
    foreach ($launcher in $launchers) {
        if ($launcher -and (Test-Path $launcher)) {
            try {
                $exe = & $launcher -3 -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and (Test-Python $exe.Trim())) { return $exe.Trim() }
            } catch { }
        }
    }

    # 2. The usual install folders (newest first).
    $found = Get-ChildItem -Path @(
        "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
        "$env:ProgramFiles\Python3*\python.exe"
    ) -ErrorAction SilentlyContinue | Sort-Object FullName -Descending
    foreach ($item in $found) {
        if (Test-Python $item.FullName) { return $item.FullName }
    }

    # 3. "python" on PATH, but not the Microsoft Store shortcut.
    $onPath = Get-Command python -All -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    foreach ($candidate in $onPath) {
        if (Test-Python $candidate) { return $candidate }
    }

    return $null
}

Write-Host "==============================================" -ForegroundColor Green
Write-Host "   AMAZON UK LISTING AUDIT BOT - INSTALL"       -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
Write-Host "This takes 5 to 15 minutes the first time and needs internet."

# ---------- 1. Python ----------
Write-Step 1 "Looking for Python..."

$Python = Find-Python

if (-not $Python) {

    Write-Host "Python was not found. Installing Python 3.13 (Windows installer)..."

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Start-Process "https://www.python.org/downloads/windows/"
        Stop-Install ("Windows' installer (winget) is missing. The Python download page " +
                      "has opened: install Python 3.13 (tick 'Add python.exe to PATH').")
    }

    winget install --id Python.Python.3.13 -e --scope user --silent `
        --accept-package-agreements --accept-source-agreements

    $Python = Find-Python

    if (-not $Python) {
        Stop-Install "Python could not be installed automatically. Install Python 3.13 from python.org."
    }
}

Write-Host "Using Python: $Python" -ForegroundColor Green

# ---------- 2. Private Python folder ----------
Write-Step 2 "Preparing the bot's Python folder (.venv)..."

$venvOk = $false
if (Test-Path $Venv) {
    try {
        & $Venv -c "import sys" 2>$null
        $venvOk = ($LASTEXITCODE -eq 0)
    } catch {
        $venvOk = $false
    }
}

if (-not $venvOk) {
    if (Test-Path ".venv") {
        Write-Host "The old .venv folder does not work on this laptop. Rebuilding it..."
        Remove-Item ".venv" -Recurse -Force
    }
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Stop-Install "The .venv folder could not be created." }
}

# ---------- 3. Libraries ----------
Write-Step 3 "Installing the libraries (a few minutes)..."

& $Venv -m pip install --upgrade pip --quiet
& $Venv -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Stop-Install "The libraries could not be installed. Check the internet connection." }

# ---------- 4. Browser ----------
Write-Step 4 "Installing the Chromium browser for the bot..."

& $Venv -m playwright install chromium
if ($LASTEXITCODE -ne 0) { Stop-Install "Chromium could not be installed. Check the internet connection." }

# ---------- 5. OCR models (optional - the bot works without them) ----------
Write-Step 5 "Preparing text reading inside images (OCR)..."

# Installed separately: if OCR cannot install on this Python version,
# everything else still works.
& $Venv -m pip install -r requirements-ocr.txt

if ($LASTEXITCODE -eq 0) {
    & $Venv -c "from modules.image_text import warm_up; print(warm_up())"
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "OCR is not ready on this laptop. The bot still works; image text will show 'not installed'." -ForegroundColor Yellow
}

# ---------- 6. Desktop icon ----------
Write-Step 6 "Creating the desktop icon..."

try {
    $shell = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath("Desktop")
    $link = $shell.CreateShortcut((Join-Path $desktop "Amazon Audit Bot.lnk"))
    $link.TargetPath = Join-Path $PSScriptRoot "Start Audit Bot.bat"
    $link.WorkingDirectory = $PSScriptRoot
    $link.WindowStyle = 7
    $link.IconLocation = "$env:SystemRoot\System32\shell32.dll,22"
    $link.Description = "Start the Amazon UK Listing Audit Bot"
    $link.Save()
    Write-Host "Desktop icon created: Amazon Audit Bot" -ForegroundColor Green
} catch {
    Write-Host "The desktop icon could not be created. Use 'Start Audit Bot.bat' instead." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host " INSTALL FINISHED"                               -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
Write-Host "1. Double-click 'Amazon Audit Bot' on the desktop."
Write-Host "2. First time on this laptop: open Delivery Location and click"
Write-Host "   'Verify Location in Chrome'."
exit 0
