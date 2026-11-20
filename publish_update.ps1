# ==============================================================
# PUBLISH THIS VERSION OF THE BOT TO YOUR PRIVATE GITHUB REPOSITORY
# Do not run directly: double-click "Publish Update.bat".
#
# Use it on your MAIN laptop after you changed or updated the bot.
# Your other laptops then double-click "Update Audit Bot.bat".
#
# Never uploaded: the Amazon login profile, settings.json (postcode,
# seller), the audit history database, .venv, exports and logs
# (see .gitignore).
# ==============================================================

Set-Location $PSScriptRoot
. (Join-Path $PSScriptRoot "git_helpers.ps1")

Write-Host "==============================================" -ForegroundColor Green
Write-Host "   PUBLISH AMAZON AUDIT BOT UPDATE"             -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green

$git = Get-Git
$url = Get-RepoUrl
Use-Repo $git $url

& $git add -A
Test-NoPersonalData $git

$changes = & $git status --porcelain
if ($changes) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    & $git commit -q -m "Bot update $stamp"
    Write-Host "Saved this version ($stamp)." -ForegroundColor Green
} else {
    Write-Host "No changes since the last publish."
}

Write-Host "Uploading to GitHub (the first time, a GitHub sign-in window opens)..."
& $git push -q -u origin main 2>$null

if ($LASTEXITCODE -ne 0) {

    # GitHub already has files this laptop does not have, e.g. the README
    # that GitHub adds when the repository is created. Join the two, keep
    # THIS laptop's version of any file that exists in both, and upload.
    Write-Host "GitHub already has some files (e.g. a README). Joining them with this version..."

    & $git fetch -q origin main
    if ($LASTEXITCODE -ne 0) {
        Stop-With ("Could not reach the repository. Check the link, that you signed in " +
                   "with the GitHub account that owns it, and the internet.")
    }

    & $git merge -q origin/main --allow-unrelated-histories -X ours -m "Join the GitHub repository"
    if ($LASTEXITCODE -ne 0) {
        & $git merge --abort 2>$null
        Stop-With "The files on GitHub could not be joined automatically. Send a screenshot of this window."
    }

    Test-NoPersonalData $git
    & $git commit -q -m "Keep personal files private" 2>$null

    & $git push -q -u origin main
    if ($LASTEXITCODE -ne 0) {
        Stop-With "Upload failed. Check that you signed in with the GitHub account that owns the repository."
    }
}

Write-Host ""
Write-Host "PUBLISHED. On the other laptops double-click 'Update Audit Bot.bat'." -ForegroundColor Green
exit 0
