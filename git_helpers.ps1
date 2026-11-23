# ==============================================================
# Shared helpers for "Publish Update.bat" and "Update Audit Bot.bat".
# Not run on its own.
# ==============================================================

$ErrorActionPreference = "Continue"

$SourceFile = Join-Path $PSScriptRoot "config\update_source.txt"

function Stop-With($message) {
    Write-Host ""
    Write-Host "STOPPED: $message" -ForegroundColor Red
    exit 1
}

function Find-Git {
    $git = Get-Command git -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1
    if ($git) { return $git }
    foreach ($path in @("$env:ProgramFiles\Git\cmd\git.exe", "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe")) {
        if (Test-Path $path) { return $path }
    }
    return $null
}

function Get-Git {
    # Returns the path of git.exe, installing Git for Windows if needed.
    $git = Find-Git
    if ($git) { return $git }

    Write-Host "Git is not installed. Installing it (one time, needs internet)..." -ForegroundColor Cyan

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Start-Process "https://git-scm.com/download/win"
        Stop-With "Please install Git from the page that opened, then try again."
    }

    winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements

    $git = Find-Git
    if (-not $git) { Stop-With "Git could not be installed automatically. Install it from git-scm.com." }
    return $git
}

$DefaultRepo = "https://github.com/M-Shameer/Amazon-Listing-Audit-Bot.git"

function Clean-RepoUrl($text) {
    # Accepts a link pasted with quotes, spaces, "www.", a trailing "/" or a
    # page inside the repository (e.g. .../tree/main) and returns owner/repo.git.
    if (-not $text) { return $null }
    $text = $text.Trim().Trim('"', "'", '<', '>').Trim()
    $text = $text -replace '^(https?://)?(www\.)?', 'https://'
    if ($text -match '^https://github\.com/([^/\s]+)/([^/\s]+)') {
        $repo = $Matches[2] -replace '\.git$', ''
        return "https://github.com/$($Matches[1])/$repo.git"
    }
    return $null
}

function Get-RepoUrl {
    # The bot's public GitHub repository. Built in, so nothing needs pasting.
    # A different link can still be saved in config\update_source.txt.
    if (Test-Path $SourceFile) {
        $saved = Clean-RepoUrl (Get-Content $SourceFile -Raw)
        if ($saved) { return $saved }
    }
    return $DefaultRepo
}

function Use-Repo($git, $url) {
    # Makes this folder a Git folder linked to the repository.
    if (-not (Test-Path (Join-Path $PSScriptRoot ".git"))) {
        & $git init -q
        & $git branch -M main
    }
    $current = & $git remote get-url origin 2>$null
    if ($LASTEXITCODE -ne 0) {
        & $git remote add origin $url
    } elseif ($current -ne $url) {
        & $git remote set-url origin $url
    }
    # Keep files exactly as they are (no line-ending warnings).
    & $git config core.autocrlf false
    # A name for the saved versions (only inside this repository).
    if (-not (& $git config user.name)) { & $git config user.name "Amazon Audit Bot" }
    if (-not (& $git config user.email)) { & $git config user.email "audit-bot@localhost" }
}

function Test-NoPersonalData($git) {
    # Never publish Amazon cookies, settings or audit history.
    $tracked = & $git ls-files
    $blocked = $tracked | Where-Object {
        $_ -like "data/amazon_uk_profile/*" -or $_ -like "*.db" -or
        $_ -eq "config/settings.json" -or $_ -like ".venv/*" -or $_ -eq ".env"
    }
    if ($blocked) {
        & $git rm -r -q --cached -- $blocked 2>$null
        Write-Host "Personal files were removed from the upload list." -ForegroundColor Yellow
    }
}
