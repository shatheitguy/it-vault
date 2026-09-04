# IT-Vault uninstaller for Windows.
#
#   irm https://raw.githubusercontent.com/shatheitguy/it-vault/main/uninstall.ps1 | iex
#
# From cmd.exe:
#
#   powershell -NoProfile -c "irm https://raw.githubusercontent.com/shatheitguy/it-vault/main/uninstall.ps1 | iex"
#
# Removes the IT-Vault container and image. Your data is NOT touched unless you
# ask for it: the volumes (uploaded invoices, generated backups, the session
# key) and your database are left alone by default.
#
# Set before running:
#   $env:ITVAULT_PURGE    = "1"   # also delete the volumes -- permanent data loss
#   $env:ITVAULT_PURGE_DB = "1"   # also delete the itvault-db container + volume
#   $env:ITVAULT_YES      = "1"   # don't ask
#   $env:ITVAULT_DRY      = "1"   # print the plan, change nothing

# Continue, not Stop: this script drives docker (a native command) and reads
# its exit codes explicitly. Under "Stop", redirecting docker's stderr (2>$null)
# while, say, a container doesn't exist would promote that stderr to a
# terminating error and abort the cleanup half-done. Every check here is an
# explicit $LASTEXITCODE test or a try/catch, so Continue is both safe and
# correct.
$ErrorActionPreference = "Continue"

$image    = "ghcr.io/shatheitguy/it-vault"
$name     = if ($env:ITVAULT_NAME) { $env:ITVAULT_NAME } else { "itvault" }
$purge    = [bool]$env:ITVAULT_PURGE
$purgeDb  = [bool]$env:ITVAULT_PURGE_DB
$yes      = [bool]$env:ITVAULT_YES
$dry      = [bool]$env:ITVAULT_DRY

function Step($m) { Write-Host "==> " -NoNewline -ForegroundColor White; Write-Host $m }
function Warn($m) { Write-Host " !  $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host " X  $m" -ForegroundColor Red; exit 1 }
function Kept($m) { Write-Host "   . " -NoNewline -ForegroundColor Green; Write-Host $m }

function Show-Banner {
    $art = @'

  ___ _____   __     __          _ _
 |_ _|_   _|  \ \   / /_ _ _   _| | |_
  | |  | |     \ \ / / _` | | | | | __|
  | |  | |      \ V / (_| | |_| | | |_
 |___| |_|       \_/ \__,_|\__,_|_|\__|
'@
    Write-Host $art -ForegroundColor Green
    Write-Host "        01001001 01010100  ::  uninstaller" -ForegroundColor DarkGray
    Write-Host "               powered by Sha The IT Guy" -ForegroundColor Green
    Write-Host ""
}

function Confirm-Or-Exit($question) {
    if ($yes) { return }
    Write-Host ""
    Write-Host $question -NoNewline
    Write-Host " [y/N] " -NoNewline -ForegroundColor Yellow
    $answer = ""
    try { $answer = Read-Host } catch { $answer = "" }
    if ($answer -notmatch '^(y|yes)$') { Write-Host ""; Die "Nothing was removed." }
}

function Invoke-Quiet {
    param([string[]]$Cmd)
    if ($dry) { Write-Host ("    " + ($Cmd -join " ")); return }
    # Failures are ignored on purpose: an already-absent container or an image
    # still referenced elsewhere shouldn't abort the rest of the cleanup.
    & $Cmd[0] @($Cmd[1..($Cmd.Length - 1)]) 2>$null | Out-Null
}

Show-Banner

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Die "Docker isn't installed, so there's nothing here to remove."
}
docker info 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Die "Docker isn't running. Start Docker Desktop, then run this again."
}

# ---- what is actually here -------------------------------------------

docker container inspect $name 2>$null | Out-Null
$hasContainer = ($LASTEXITCODE -eq 0)

$images = @(docker images --format "{{.Repository}}:{{.Tag}}" 2>$null |
            Where-Object { $_ -like "$image`:*" })
$volumes = @(docker volume ls --format "{{.Name}}" 2>$null |
             Where-Object { $_ -in @("itvault_data", "invoices_data", "backups_data") })

Write-Host "About to remove:"
if ($hasContainer) { Write-Host "   container  $name" }
else { Write-Host "   container  $name (not found)" -ForegroundColor Yellow }
if ($images.Count) { $images | ForEach-Object { Write-Host "   image      $_" } }
else { Write-Host "   image      $image (not found)" -ForegroundColor Yellow }
Write-Host ""

if ($purge) {
    Write-Host "And permanently deleting these volumes:" -ForegroundColor Red
    if ($volumes.Count) {
        $volumes | ForEach-Object { Write-Host "   volume     $_" }
        Write-Host ""
        Write-Host "   That is your uploaded invoices, generated backups and the" -ForegroundColor Red
        Write-Host "   session key. It cannot be undone." -ForegroundColor Red
    } else { Write-Host "   (none found)" -ForegroundColor Yellow }
    Write-Host ""
}

if ($purgeDb) {
    Write-Host "And the database container from this project's suggested setup:" -ForegroundColor Red
    Write-Host "   container  itvault-db"
    Write-Host "   volume     itvault_db  <- your entire IT-Vault database" -ForegroundColor Red
    Write-Host ""
}

Confirm-Or-Exit "Go ahead?"

# ---- remove ----------------------------------------------------------

Step "Removing container '$name'"
Invoke-Quiet @("docker", "rm", "-f", $name)

if ($images.Count -or $dry) {
    Step "Removing image(s)"
    if ($dry -and -not $images.Count) {
        Write-Host "    docker image rm ${image}:latest"
    } else {
        foreach ($t in $images) { Invoke-Quiet @("docker", "image", "rm", $t) }
    }
}

if ($purge) {
    Step "Deleting volumes"
    if ($dry -and -not $volumes.Count) {
        Write-Host "    docker volume rm itvault_data invoices_data backups_data"
    } else {
        foreach ($v in $volumes) { Invoke-Quiet @("docker", "volume", "rm", $v) }
    }
}

if ($purgeDb) {
    Step "Removing the itvault-db container and its volume"
    Invoke-Quiet @("docker", "rm", "-f", "itvault-db")
    Invoke-Quiet @("docker", "volume", "rm", "itvault_db")
}

# The network only exists if it was created following this project's docs, and
# docker refuses to remove one that still has containers attached.
docker network inspect itvault-net 2>$null | Out-Null
if ($LASTEXITCODE -eq 0 -or $dry) {
    Step "Removing the itvault-net network if nothing else uses it"
    Invoke-Quiet @("docker", "network", "rm", "itvault-net")
}

if ($dry) {
    Write-Host ""
    Write-Host "(dry run -- nothing was changed)"
    exit 0
}

# ---- what survived ---------------------------------------------------

Write-Host ""
Write-Host "IT-Vault removed." -ForegroundColor Green
Write-Host ""
Write-Host "Deliberately left alone:"
if (-not $purge) {
    Kept "Volumes itvault_data, invoices_data, backups_data -- your invoices,"
    Write-Host "     backups and session key. Reinstalling picks them straight back up."
    Write-Host "     Delete them with:  docker volume rm itvault_data invoices_data backups_data"
}
if (-not $purgeDb) {
    Kept "Your database. IT-Vault never owned it, so it isn't ours to drop."
    Write-Host "     Drop the schema yourself if you're done with it:  DROP DATABASE itvault;"
}
Kept "Docker itself, and any other containers or images you run."
Write-Host "     Uninstall Docker Desktop from Windows Settings > Apps if you"
Write-Host "     no longer want it."
Write-Host ""
