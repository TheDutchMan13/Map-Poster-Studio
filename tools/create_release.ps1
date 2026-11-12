# create_release.ps1
# Builds the installer, tags the current version, pushes the tag and creates
# the GitHub release with the installer attached. The release notes come from
# the "## What's new in X.Y" section of README.md.
#
# This is the "build on this PC" route: push_release.ps1 -Local calls it.
# (Normally GitHub builds the installer; see .github\workflows\release.yml.)
# To run it on its own (main must already match origin/main):
#     powershell -ExecutionPolicy Bypass -File C:\MapPosterStudio\tools\create_release.ps1
# Optional:
#     -Draft     create the release as a draft (you publish it on GitHub later)
#
# Needs: git, GitHub CLI (gh) logged in, and Inno Setup 7 or 6 (for the build).

param(
    [string]$Root = "",
    [switch]$Draft
)
if (-not $Root) {
    # tools\ inside the project -> the project; anywhere else -> C:\MapPosterStudio
    $parent = Split-Path $PSScriptRoot -Parent
    $Root = if (Test-Path (Join-Path $parent "mapposter\__init__.py")) { $parent } else { "C:\MapPosterStudio" }
}

# Native programs (git, gh) write progress to stderr; Windows PowerShell 5.1 would treat
# that as a fatal error under "Stop". Exit codes are checked explicitly instead.
$ErrorActionPreference = "Continue"
if (-not (Test-Path (Join-Path $Root "mapposter\__init__.py"))) {
    Write-Host "ERROR: project not found in $Root. Pass -Root <folder> if it lives elsewhere." -ForegroundColor Red
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

# ---- 1. tools -------------------------------------------------------------
Step "Checking tools"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail "git was not found." }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Fail "GitHub CLI (gh) was not found. Install it with: winget install GitHub.cli   then run: gh auth login"
}
gh auth status *> $null
if ($LASTEXITCODE -ne 0) { Fail "gh is not logged in. Run: gh auth login" }
Write-Host "git and gh are ready."

# ---- 2. version -----------------------------------------------------------
Step "Reading version"
$initText = Get-Content "mapposter\__init__.py" -Raw
$m = [regex]::Match($initText, '__version__\s*=\s*"([^"]+)"')
if (-not $m.Success) { Fail "Could not read __version__ from mapposter\__init__.py" }
$Version = $m.Groups[1].Value
$Tag = "v$Version"
$Installer = "dist\MapPosterStudio-Setup-$Version.exe"
Write-Host "Version $Version  (tag $Tag)"

# ---- 3. repo must be clean and pushed ------------------------------------
Step "Checking the repository"
$dirty = git status --porcelain
if ($dirty) { Fail "You have uncommitted changes. Commit and push them first:`n$dirty" }

git fetch origin --quiet
if ($LASTEXITCODE -ne 0) { Fail "Could not reach GitHub (git fetch failed)." }
$head = (git rev-parse HEAD).Trim()
$remote = (git rev-parse origin/main).Trim()
if ($head -ne $remote) { Fail "Your local main is not the same as origin/main. Run push_release.ps1, or: git push" }

gh release view $Tag *> $null
if ($LASTEXITCODE -eq 0) { Fail "A release called $Tag already exists on GitHub. Delete it there first, or change the version." }
Write-Host "Repository is clean and pushed."

# ---- 4. build the installer ----------------------------------------------
Step "Building the installer"
cmd /c build_installer.bat
if ($LASTEXITCODE -ne 0) { Fail "build_installer.bat failed. Scroll up for the error." }
if (-not (Test-Path $Installer)) { Fail "Expected installer not found: $Installer" }
$hash = (Get-FileHash $Installer -Algorithm SHA256).Hash
Write-Host "Built $Installer"
Write-Host "SHA256 $hash"

# ---- 5. tag and push -------------------------------------------------------
Step "Tagging $Tag"
$localTag = git tag -l $Tag
if ($localTag) {
    $tagCommit = (git rev-list -n 1 $Tag).Trim()
    if ($tagCommit -ne $head) {
        Fail "Local tag $Tag points at another commit. Delete it with: git tag -d $Tag"
    }
    Write-Host "Local tag $Tag already points at HEAD, reusing it."
} else {
    git tag -a $Tag -m "Map Poster Studio $Version"
    if ($LASTEXITCODE -ne 0) { Fail "Could not create the tag." }
}
git push origin $Tag
if ($LASTEXITCODE -ne 0) { Fail "Could not push the tag $Tag to GitHub." }

# ---- 6. release notes (from README "What's new in X.Y") -------------------
Step "Writing release notes"
$mm = ($Version -split '\.')[0..1] -join '.'
$body = "Map Poster Studio $Version."
if (Test-Path "README.md") {
    $readme = Get-Content "README.md" -Raw
    $rx = '(?ms)^## What''s new in ' + [regex]::Escape($mm) + '\s*\r?\n(.*?)(?=^## |\z)'
    $section = [regex]::Match($readme, $rx)
    if ($section.Success) { $body = $section.Groups[1].Value.Trim() }
    else { Write-Host "(no 'What's new in $mm' section in README.md; using a short note)" }
}
$notesFile = Join-Path $env:TEMP "mps_release_notes_$Version.md"
$notes = @"
## Map Poster Studio $Version

$body

Install: download **MapPosterStudio-Setup-$Version.exe** and run it. It installs for your user only; no admin rights needed.

SHA256 of the installer: ``$hash``
"@
Set-Content -Path $notesFile -Value $notes -Encoding UTF8

# ---- 7. create the release -------------------------------------------------
Step "Creating the GitHub release"
$args = @("release", "create", $Tag, $Installer,
          "--title", "Map Poster Studio $Version",
          "--notes-file", $notesFile)
if ($Draft) { $args += "--draft" } else { $args += "--latest" }
gh @args
if ($LASTEXITCODE -ne 0) { Fail "gh release create failed. The tag was pushed; you can finish the release on GitHub." }

Step "Done"
gh release view $Tag --web
Write-Host "Release $Tag is up." -ForegroundColor Green
