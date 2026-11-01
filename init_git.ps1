<#
.SYNOPSIS
    Turn the Watan-e-Pak portal folder into a single git repository, then
    (optionally) create a GitHub remote and push.

.DESCRIPTION
    Produces ONE repository at the project ROOT (default: the folder this
    script lives in, i.e. ...\WatanePak), containing:

        WatanePak\
          |-- backend\   (MCP + FastAPI portal: server.py, api.py, modules, tests)
          |-- *.docx     (design / requirements docs)
          |-- *.png      (brand assets)
          \-- .gitignore (written by this script)

    Steps performed (all idempotent - safe to re-run):
      1. Removes the stale, commit-less nested repo at backend\.git.
      2. Writes a root .gitignore (only if one does not already exist).
      3. git init on branch 'main'.
      4. Stages everything and makes the initial commit.
      5. If the GitHub CLI (gh) is installed and authenticated, runs
         `gh repo create` and pushes; otherwise it prints exact next steps.

.PARAMETER ProjectRoot
    Folder to initialise. Defaults to the script's own folder.

.PARAMETER Branch
    Initial branch name. Default 'main'.

.PARAMETER CommitMessage
    Message for the initial commit.

.PARAMETER GitHubRepo
    Name of the GitHub repository to create. Default 'watan-e-pak-portal'.

.PARAMETER Visibility
    'private' (default) or 'public'.

.PARAMETER SkipRemote
    Do the local setup only; skip all GitHub steps.

.PARAMETER Force
    Proceed even if backend\server.py is missing, and allow removing a
    nested backend\.git that DOES contain commits.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\init_git.ps1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\init_git.ps1 -GitHubRepo watan-e-pak-portal -Visibility public
#>

[CmdletBinding()]
param(
    [string]$ProjectRoot,
    [string]$Branch         = 'main',
    [string]$CommitMessage  = 'Initial commit: Watan-e-Pak real-estate portal (MCP + FastAPI backend)',
    [string]$GitHubRepo     = 'watan-e-pak-portal',
    [ValidateSet('private', 'public')]
    [string]$Visibility     = 'private',
    [switch]$SkipRemote,
    [switch]$Force
)

# ------------------------------------------------------------------ helpers ---
function Step ($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Info ($m) { Write-Host "    $m" }
function Warn ($m) { Write-Host "    ! $m" -ForegroundColor Yellow }
function Die  ($m) { Write-Host "    x $m" -ForegroundColor Red; exit 1 }

function Run-Git {
    param([Parameter(Mandatory = $true)][string[]]$Command)
    & git @Command
    if ($LASTEXITCODE -ne 0) { Die "git $($Command -join ' ') failed (exit $LASTEXITCODE)" }
}

# ------------------------------------------------------------- resolve root ---
if (-not $ProjectRoot) {
    if ($PSScriptRoot) { $ProjectRoot = $PSScriptRoot } else { $ProjectRoot = (Get-Location).Path }
}
if (-not (Test-Path -LiteralPath $ProjectRoot)) { Die "ProjectRoot not found: $ProjectRoot" }
$root    = (Resolve-Path -LiteralPath $ProjectRoot).Path
$backend = Join-Path $root 'backend'

Write-Host "Watan-e-Pak portal - git bootstrap" -ForegroundColor White
Info "Repository root : $root"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Die "git is not installed or not on PATH." }
if (-not (Test-Path (Join-Path $backend 'server.py'))) {
    if (-not $Force) { Die "backend\server.py not found under '$root'. Pass -ProjectRoot <path>, or -Force to override." }
    Warn "backend\server.py not found - continuing because -Force was given."
}

# --------------------------------------- 1. remove stale nested repo (if any) ---
Step "Checking for a nested repository in backend\"
$nested = Join-Path $backend '.git'
if (Test-Path -LiteralPath $nested) {
    $count = (& git -C $backend rev-list --count --all) 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $count) { $count = 0 }
    $count = [int]$count
    if ($count -eq 0) {
        Info "Found a commit-less nested repo - removing backend\.git (nothing is lost)."
        Remove-Item -LiteralPath $nested -Recurse -Force
    } elseif ($Force) {
        Warn "-Force: removing backend\.git which contains $count commit(s)."
        Remove-Item -LiteralPath $nested -Recurse -Force
    } else {
        Die "backend\.git already contains $count commit(s). Refusing to delete it. Re-run with -Force to discard it, or keep the backend-only layout."
    }
} else {
    Info "No nested repo - good."
}

# ------------------------------------------------- 2. root .gitignore (once) ---
Step "Root .gitignore"
$gitignorePath = Join-Path $root '.gitignore'
if (Test-Path -LiteralPath $gitignorePath) {
    Info ".gitignore already exists - leaving it untouched."
} else {
    $gitignore = @'
# ===========================================================================
# Watan-e-Pak portal - repository ignore rules
# ===========================================================================

# ---- OS / editor cruft ----
Thumbs.db
ehthumbs.db
desktop.ini
.DS_Store
*~
*.swp
*.swo
.vscode/
.idea/

# ---- Office / Word temp + lock files ----
~$*
~WRL*.tmp
*.tmp

# ---- Python ----
__pycache__/
*.py[cod]
*$py.class
*.so
*.egg
*.egg-info/
.eggs/
build/
dist/
wheels/
.installed.cfg
.pytest_cache/
.mypy_cache/
.pyre/
.ruff_cache/
.coverage
coverage.xml
htmlcov/

# ---- Virtual environments ----
.venv/
venv/
env/
ENV/

# ---- Secrets / local environment (never commit) ----
.env
.env.*
!.env.example
*.local
*.pem
*.key
secrets.*

# ---- Logs ----
*.log
logs/
'@
    # Write as UTF-8 without a BOM so git treats it as plain text.
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($gitignorePath, $gitignore, $utf8NoBom)
    Info "Created .gitignore"
}

# ---------------------------------------------------------- 3. init the repo ---
Step "Initialising the repository"
if (Test-Path -LiteralPath (Join-Path $root '.git')) {
    Info "Already a git repository - skipping init."
    $currentBranch = (& git -C $root rev-parse --abbrev-ref HEAD) 2>$null
    if ($currentBranch -eq 'master') {
        Run-Git -Command @('-C', $root, 'branch', '-M', $Branch)
        Info "Renamed branch 'master' to '$Branch'."
    }
} else {
    Run-Git -Command @('init', '-b', $Branch, $root)
    Info "git init on branch '$Branch'."
}

# ------------------------------------------------------- 4. stage and commit ---
Step "Staging files"
Run-Git -Command @('-C', $root, 'add', '-A')

$staged = @(& git -C $root diff --cached --name-only)
$stagedCount = if ($staged) { $staged.Count } else { 0 }
Info "$stagedCount file(s) staged."

if ($stagedCount -eq 0) {
    Info "Nothing to commit."
} else {
    Run-Git -Command @('-C', $root, 'commit', '-m', $CommitMessage)
    $short = (& git -C $root rev-parse --short HEAD) 2>$null
    Info "Initial commit created ($short)."
}

# --------------------------------------------------------------- 5. GitHub ---
Step "GitHub remote"
if ($SkipRemote) { Info "Skipped (-SkipRemote)."; Write-Host ""; exit 0 }

$origin = (& git -C $root remote get-url origin) 2>$null
if ($LASTEXITCODE -eq 0 -and $origin) {
    Info "remote 'origin' already set to $origin"
    Run-Git -Command @('-C', $root, 'push', '-u', 'origin', $Branch)
    Info "Pushed branch '$Branch'."
    Write-Host ""
    exit 0
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Warn "GitHub CLI (gh) is not installed - cannot create the remote automatically."
    Write-Host ""
    Write-Host "  Option A - install gh, then re-run this script:" -ForegroundColor White
    Write-Host "      winget install --id GitHub.cli -e" -ForegroundColor Gray
    Write-Host "      gh auth login" -ForegroundColor Gray
    Write-Host "      powershell -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Option B - create an empty repo on github.com, then run:" -ForegroundColor White
    Write-Host "      git -C `"$root`" remote add origin https://github.com/<you>/$GitHubRepo.git" -ForegroundColor Gray
    Write-Host "      git -C `"$root`" push -u origin $Branch" -ForegroundColor Gray
    Write-Host ""
    exit 0
}

& gh auth status *> $null
if ($LASTEXITCODE -ne 0) {
    Warn "gh is installed but not signed in. Run:  gh auth login"
    Write-Host "      then re-run this script." -ForegroundColor Gray
    Write-Host ""
    exit 0
}

Info "Creating GitHub repo '$GitHubRepo' ($Visibility) and pushing..."
$visFlag = "--$Visibility"
& gh repo create $GitHubRepo --source $root --remote origin --push $visFlag
if ($LASTEXITCODE -ne 0) { Die "gh repo create failed. Create the repo manually and run: git push -u origin $Branch" }

$url = (& gh repo view $GitHubRepo --json url --jq .url) 2>$null
Info "Done. Remote: $url"
Write-Host ""
