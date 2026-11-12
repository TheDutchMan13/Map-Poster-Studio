# push_release.ps1
# One command to publish a release of the version in mapposter\__init__.py:
#   1. refuses to continue with uncommitted changes,
#   2. runs the theme regression test (if build.bat has made the .venv),
#   3. moves main to your current branch (fast-forward only) and pushes main,
#   4. tags vX.Y.Z and pushes the tag. GitHub then builds the exe and installer
#      and publishes the release (.github\workflows\release.yml); this script
#      follows that build and opens the release page when it is up.
#
# Run from PowerShell:
#     powershell -ExecutionPolicy Bypass -File C:\MapPosterStudio\tools\push_release.ps1
# Options:
#     -Local      build the installer on this PC instead (runs create_release.ps1)
#     -Draft      with -Local: create the release as a draft
#     -NoWait     push the tag and stop; don't follow the GitHub build
#     -SkipTests  skip the local regression test (GitHub still runs it)
#
# Needs: git, and GitHub CLI (gh) logged in.

param(
    [string]$Root = "",
    [switch]$Local,
    [switch]$Draft,
    [switch]$NoWait,
    [switch]$SkipTests
)

$ErrorActionPreference = "Continue"
if (-not $Root) {
    $parent = Split-Path $PSScriptRoot -Parent
    $Root = if (Test-Path (Join-Path $parent "mapposter\__init__.py")) { $parent } else { "C:\MapPosterStudio" }
}
if (-not (Test-Path (Join-Path $Root "mapposter\__init__.py"))) {
    Write-Host "ERROR: project not found in $Root. Pass -Root <folder>." -ForegroundColor Red
    exit 1
}
Set-Location $Root

function Fail($msg) {
    Write-Host "ERROR: $msg" -ForegroundColor Red
    exit 1
}

function Step($msg) {
    Write-Host ""
    Write-Host "== $msg" -ForegroundColor Cyan
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail "git was not found." }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Fail "GitHub CLI (gh) was not found. Install it from https://cli.github.com, then run: gh auth login"
}
gh auth status *> $null
if ($LASTEXITCODE -ne 0) { Fail "gh is not logged in. Run: gh auth login" }

# ---- version ----------------------------------------------------------------
$initText = Get-Content "mapposter\__init__.py" -Raw
$m = [regex]::Match($initText, '__version__\s*=\s*"([^"]+)"')
if (-not $m.Success) { Fail "Could not read __version__ from mapposter\__init__.py" }
$Version = $m.Groups[1].Value
$Tag = "v$Version"
Write-Host "Releasing Map Poster Studio $Version  (tag $Tag)"

# ---- 1. clean working tree ---------------------------------------------------
Step "Checking the working tree"
$dirty = git status --porcelain
if ($dirty) {
    Fail "You have uncommitted changes. Commit them first (git add -A; git commit -m ""...""), then run this again:`n$dirty"
}
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
Write-Host "On branch $branch, working tree clean."

gh release view $Tag *> $null
if ($LASTEXITCODE -eq 0) {
    Fail "Release $Tag already exists on GitHub. Raise __version__ in mapposter\__init__.py (and installer\MapPosterStudio.iss) for a new release."
}

# ---- 2. regression test --------------------------------------------------------
if (-not $SkipTests) {
    Step "Theme regression test"
    if (Test-Path ".venv\Scripts\python.exe") {
        & .venv\Scripts\python.exe tests\regress.py
        if ($LASTEXITCODE -ne 0) {
            Fail "Theme regression test found changes (see tests\output\*_diff.png). If they are intended: run_tests.bat --update, commit, and run this again."
        }
    } else {
        Write-Host "(no .venv yet, skipping; GitHub runs the test anyway)"
    }
}

# ---- 3. main ------------------------------------------------------------------
Step "Updating main"
git fetch origin --tags --quiet
if ($LASTEXITCODE -ne 0) { Fail "Could not reach GitHub (git fetch failed)." }
if ($branch -ne "main") {
    git checkout main --quiet
    if ($LASTEXITCODE -ne 0) { Fail "Could not switch to main." }
    git merge --ff-only $branch --quiet
    if ($LASTEXITCODE -ne 0) {
        Fail "main cannot fast-forward to $branch. Rebase $branch onto main first, then run this again."
    }
    Write-Host "main now includes everything on $branch."
}
$behind = [int](git rev-list --count "main..origin/main")
if ($behind -gt 0) { Fail "origin/main has $behind commit(s) you don't have. Run: git pull --ff-only, then this again." }
$ahead = [int](git rev-list --count "origin/main..main")
if ($ahead -gt 0) {
    Write-Host "Pushing $ahead commit(s)..."
    git push origin main
    if ($LASTEXITCODE -ne 0) { Fail "git push origin main failed. Scroll up for the reason." }
} else {
    Write-Host "main is already on GitHub."
}

# ---- 4a. build on this PC ------------------------------------------------------
if ($Local) {
    Step "Building and releasing on this PC"
    $rel = @{ Root = $Root }
    if ($Draft) { $rel.Draft = $true }
    & (Join-Path $PSScriptRoot "create_release.ps1") @rel
    if ($LASTEXITCODE -ne 0) { Fail "create_release.ps1 did not finish. See the messages above." }
    Write-Host ""
    Write-Host "All done." -ForegroundColor Green
    exit 0
}

# ---- 4b. tag; GitHub builds and publishes ---------------------------------------
if (-not (Test-Path ".github\workflows\release.yml")) {
    Fail ".github\workflows\release.yml is missing. Use -Local to build on this PC."
}
Step "Tagging $Tag"
$head = (git rev-parse HEAD).Trim()
if (git tag -l $Tag) {
    if ((git rev-list -n 1 $Tag).Trim() -ne $head) { Fail "Tag $Tag points at another commit. Delete it with: git tag -d $Tag" }
} else {
    git tag -a $Tag -m "Map Poster Studio $Version"
    if ($LASTEXITCODE -ne 0) { Fail "Could not create the tag." }
}
git push origin $Tag
if ($LASTEXITCODE -ne 0) { Fail "Could not push the tag $Tag." }
Write-Host "Tag pushed. GitHub is now building the installer (about 10 minutes)."

if ($NoWait) {
    Write-Host "Follow it at: gh run list --workflow release.yml"
    exit 0
}

Step "Following the GitHub build"
$runId = $null
for ($i = 0; $i -lt 30 -and -not $runId; $i++) {
    Start-Sleep -Seconds 4
    $runId = gh run list --workflow release.yml --branch $Tag --limit 1 --json databaseId --jq ".[0].databaseId" 2>$null
}
if (-not $runId) { Fail "Could not find the GitHub build. Look under the Actions tab of the repository." }
gh run watch $runId --exit-status
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "The GitHub build failed. Details: gh run view $runId --log-failed" -ForegroundColor Red
    Write-Host "If the theme test failed only on GitHub, its images are under the run's artifacts."
    Write-Host "You can still build here: delete the tag (git push origin :refs/tags/$Tag; git tag -d $Tag), then run with -Local."
    exit 1
}

Step "Done"
gh release view $Tag --web
Write-Host "Release $Tag is up." -ForegroundColor Green
