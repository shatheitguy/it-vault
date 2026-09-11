# IT-Vault installer for Windows.
#
#   irm https://raw.githubusercontent.com/shatheitguy/it-vault/main/install.ps1 | iex
#
# From cmd.exe, wrap it in PowerShell:
#
#   powershell -NoProfile -c "irm https://raw.githubusercontent.com/shatheitguy/it-vault/main/install.ps1 | iex"
#
# Starts IT-Vault as a Docker container and prints where to open it. If Docker
# is missing it offers to install Docker Desktop for you (via winget) -- and if
# you'd rather not have Docker at all, it offers to install IT-Vault straight
# on Windows instead (Python + waitress). Nothing dead-ends on declining.
#
# Set $env:ITVAULT_NO_DOCKER = '1' to skip Docker entirely.
#
# It does NOT install a database: IT-Vault connects to whatever MariaDB/MySQL
# you give it, so your database version, backups and retention stay yours. The
# first-run wizard in the browser asks for the connection details.
#
# Configure with environment variables before running (there are no parameters,
# so the line above works unchanged when piped to iex):
#
#   $env:ITVAULT_PORT = "8080"    # host port,      default 5000
#   $env:ITVAULT_TAG  = "1.6.2"   # image tag,      default latest
#   $env:ITVAULT_NAME = "myvault" # container name, default itvault
#   $env:ITVAULT_YES  = "1"       # don't ask before installing Docker
#   $env:ITVAULT_DRY  = "1"       # print the plan, change nothing

$ErrorActionPreference = "Stop"

$image = "ghcr.io/shatheitguy/it-vault"
$tag  = if ($env:ITVAULT_TAG)  { $env:ITVAULT_TAG }  else { "latest" }
$name = if ($env:ITVAULT_NAME) { $env:ITVAULT_NAME } else { "itvault" }
$port = if ($env:ITVAULT_PORT) { $env:ITVAULT_PORT } else { "5000" }
$dry  = [bool]$env:ITVAULT_DRY
$yes  = [bool]$env:ITVAULT_YES
$noDocker = [bool]$env:ITVAULT_NO_DOCKER
$dir  = if ($env:ITVAULT_DIR) { $env:ITVAULT_DIR } else { Join-Path $env:USERPROFILE "it-vault" }

# Deliberately ASCII-only: Windows PowerShell 5.1 decodes a BOM-less UTF-8
# script as the OEM codepage, so box-drawing characters would arrive as
# mojibake on exactly the consoles this script is most likely to run in.
function Show-Banner {
    $art = @'

  ___ _____   __     __          _ _
 |_ _|_   _|  \ \   / /_ _ _   _| | |_
  | |  | |     \ \ / / _` | | | | | __|
  | |  | |      \ V / (_| | |_| | | |_
 |___| |_|       \_/ \__,_|\__,_|_|\__|
'@
    Write-Host $art -ForegroundColor Green
    Write-Host "        01001001 01010100  ::  asset register + helpdesk" -ForegroundColor DarkGray
    Write-Host "               powered by Sha The IT Guy" -ForegroundColor Green
    Write-Host ""
}

Show-Banner

function Step($m) { Write-Host "==> " -NoNewline -ForegroundColor White; Write-Host $m }
function Warn($m) { Write-Host " !  $m" -ForegroundColor Yellow }
# Piped through `irm | iex` this script runs *inside* the caller's shell, so a
# bare `exit` would close their window. Everything that needs to stop throws
# this sentinel instead, and the wrapper at the bottom turns it back into a
# quiet return to the prompt.
$ITV_STOP = '__ITVAULT_STOP__'
function Stop-Install { throw $ITV_STOP }
function Die($m)  { Write-Host " X  $m" -ForegroundColor Red; throw $ITV_STOP }

function Invoke-Step {
    param([string[]]$Cmd)
    if ($dry) { Write-Host ("    " + ($Cmd -join " ")) ; return }
    & $Cmd[0] @($Cmd[1..($Cmd.Length - 1)]) | Out-Null
    if ($LASTEXITCODE -ne 0) { Die "`"$($Cmd -join ' ')`" failed (exit $LASTEXITCODE)." }
}

function Test-Docker { [bool](Get-Command docker -ErrorAction SilentlyContinue) }

# Runs a docker command for its exit code only, swallowing all output. The
# local ErrorActionPreference is the whole point: with the script-level "Stop"
# in force, redirecting a native command's stderr (2>&1) promotes each line to
# a terminating error, so a plain `docker info` while the engine is still
# starting would abort the entire script instead of just reporting "not up
# yet". Lowering it here keeps the retry loops actually looping.
function Invoke-DockerQuiet {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$DockerArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        $null = & docker @DockerArgs 2>&1
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Test-DockerRunning {
    if (-not (Test-Docker)) { return $false }
    return (Invoke-DockerQuiet 'info')
}

# winget puts docker.exe on the machine PATH, but this process started with the
# old environment. Re-read it so the new install is visible without a restart.
function Update-PathFromRegistry {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user    = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @($machine, $user) | Where-Object { $_ }
    $env:Path = ($parts -join ";")
}

function Confirm-Or-Exit($question) {
    if ($yes) { return }
    Write-Host ""
    Write-Host $question -NoNewline
    Write-Host " [y/N] " -NoNewline -ForegroundColor Yellow
    $answer = ""
    try { $answer = Read-Host } catch { $answer = "" }
    if ($answer -notmatch '^(y|yes)$') {
        Write-Host ""
        Write-Host "Docker won't be installed."
        Write-Host ""
        Write-Host "IT-Vault can still run directly on Windows (Python + waitress),"
        Write-Host "with no Docker at all."
        Write-Host ""
        Write-Host "Install it that way instead?" -NoNewline
        Write-Host " [y/N] " -NoNewline -ForegroundColor Yellow
        $native = ""
        try { $native = Read-Host } catch { $native = "" }
        if ($native -match '^(y|yes)$') {
            Install-Native
            Stop-Install
        }
        Write-Host ""
        Write-Host "Nothing was installed. Ways forward:"
        Write-Host ""
        Write-Host "  Install Docker Desktop yourself, then run this again:"
        Write-Host "    https://docs.docker.com/desktop/install/windows-install/"
        Write-Host ""
        Write-Host "  Or install without Docker:  `$env:ITVAULT_NO_DOCKER = '1'"
        Write-Host ""
        Stop-Install
    }
}

# IT-Vault is a Flask app, so Docker is only the packaged route -- it runs fine
# straight on Windows. This is the fallback for anyone who declines Docker.
function Install-Native {
    Step "Installing IT-Vault without Docker (Python + waitress)"

    $py = $null
    foreach ($c in @("python", "python3", "py")) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if ($cmd) {
            $ok = & $c -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { $py = $c; break }
        }
    }
    if (-not $py) {
        Die @"
Python 3.9+ is needed for a no-Docker install and wasn't found.
    Install Python, then run this again with:  `$env:ITVAULT_NO_DOCKER = '1'
      https://www.python.org/downloads/
"@
    }

    if ($dry) {
        Write-Host "    would install into: $dir"
        Write-Host "    would run: $py -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
        Write-Host "    would start with: .venv\Scripts\python serve.py"
        return
    }

    Step "Downloading IT-Vault into $dir"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $zip = Join-Path $env:TEMP "it-vault-main.zip"
    try {
        Invoke-WebRequest -Uri "https://github.com/shatheitguy/it-vault/archive/refs/heads/main.zip" -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $env:TEMP -Force
        Copy-Item -Path (Join-Path $env:TEMP "it-vault-main\*") -Destination $dir -Recurse -Force
    } catch {
        Die "Couldn't download or unpack IT-Vault into $dir. $($_.Exception.Message)"
    }

    Step "Creating a virtualenv and installing dependencies"
    Push-Location $dir
    try {
        & $py -m venv .venv
        if ($LASTEXITCODE -ne 0) { Die "Couldn't create a virtualenv in $dir\.venv." }
        & ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
        & ".venv\Scripts\pip.exe" install --quiet -r requirements.txt
        if ($LASTEXITCODE -ne 0) { Die "Couldn't install the Python dependencies." }
    } finally { Pop-Location }

    Write-Host ""
    Write-Host "IT-Vault is installed at " -NoNewline; Write-Host $dir -ForegroundColor Green
    Write-Host ""
    Write-Host "It still needs a database -- any MariaDB 10.6+ / MySQL 8+. Point it at one"
    Write-Host "with the DB_* environment variables, then start it:"
    Write-Host ""
    Write-Host "  cd $dir" -ForegroundColor White
    Write-Host "  `$env:DB_HOST='127.0.0.1'; `$env:DB_USER='itvault'; `$env:DB_PASS='your-password'; `$env:DB_NAME='itvault'" -ForegroundColor White
    Write-Host "  `$env:ITVAULT_PORT='$port'; .venv\Scripts\python.exe serve.py" -ForegroundColor White
    Write-Host ""
    Write-Host "Then open http://localhost:$port for the setup wizard."
    Write-Host ""
    Write-Host "No database yet? See https://github.com/shatheitguy/it-vault#step-1--get-a-database"
}

function Install-DockerDesktop {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Warn "Docker isn't installed, and winget isn't available to install it."
        Write-Host ""
        Write-Host "Install IT-Vault without Docker instead (Python on this machine)?" -NoNewline
        Write-Host " [y/N] " -NoNewline -ForegroundColor Yellow
        $native = ""
        try { $native = Read-Host } catch { $native = "" }
        if ($native -match '^(y|yes)$') { Install-Native; Stop-Install }
        Die @"
Install Docker Desktop by hand, then run this again:
      https://docs.docker.com/desktop/install/windows-install/
    Or install without Docker:  `$env:ITVAULT_NO_DOCKER = '1'
"@
    }

    Confirm-Or-Exit "Docker isn't installed. Install Docker Desktop now (about 600 MB)?"

    Step "Installing Docker Desktop via winget -- this takes a few minutes"
    Write-Host "    Windows will ask for permission; Docker Desktop's own licence"
    Write-Host "    terms require a paid subscription for larger companies."
    # Not Invoke-Step: winget's progress output is worth showing, and it uses
    # non-zero exit codes for outcomes that aren't failures (already installed,
    # reboot required), so its result is interpreted rather than trusted.
    winget install --id Docker.DockerDesktop --exact --source winget `
        --accept-package-agreements --accept-source-agreements
    $code = $LASTEXITCODE

    Update-PathFromRegistry

    if (-not (Test-Docker)) {
        Die @"
Docker Desktop did not finish installing (winget exit $code).
    Install it by hand, then run this again:
      https://docs.docker.com/desktop/install/windows-install/
    If it complains about WSL 2, run 'wsl --install' in an admin
    PowerShell, reboot, then try again.
"@
    }

    Step "Starting Docker Desktop"
    $exe = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $exe) { Start-Process -FilePath $exe | Out-Null }

    # The engine takes a while, and the very first launch usually wants the
    # user to accept the licence in the GUI, so this waits rather than failing
    # instantly -- but it does give up and say what to do.
    Write-Host "    Docker Desktop's first launch opens a window and asks you to"
    Write-Host "    accept its terms -- do that if it appears; this keeps waiting."
    Step "Waiting for the Docker engine (up to 3 minutes)"
    foreach ($i in 1..90) {
        if (Test-DockerRunning) {
            Write-Host ""
            Write-Host "Docker engine is up." -ForegroundColor Green
            return
        }
        Start-Sleep -Seconds 2
    }
    Die @"
Docker Desktop is installed, but its engine hasn't started within 3 minutes.
    This is normal on a first install -- it isn't an error you did anything to
    cause. Finish it off by hand:
      1. Open Docker Desktop from the Start menu.
      2. Accept its terms if asked, and wait for the whale icon to say
         'Engine running' (this can take a few minutes the first time).
      3. If it asks for WSL 2: run  wsl --install  in an admin PowerShell,
         reboot, then open Docker Desktop again.
    Once it says running, re-run the same one-line install command -- it will
    skip straight past this step.
"@
}

function Invoke-ItVaultInstall {

# ---- checks ----------------------------------------------------------

# ITVAULT_NO_DOCKER: skip Docker entirely and run straight on the host.
if ($noDocker) {
    Install-Native
    Stop-Install
}

if (-not (Test-Docker)) {
    # A dry run is for reading the plan before trusting it, so it has to work
    # on a machine that hasn't got Docker yet.
    if ($dry) { Warn "Docker isn't installed here -- showing the plan anyway." }
    else { Install-DockerDesktop }
}

if (-not $dry) {
    if (-not (Test-DockerRunning)) {
        Die "Docker is installed but not running. Start Docker Desktop, wait for it to say 'Engine running', then run this again."
    }

    # An existing container is left alone rather than replaced: it owns the
    # data volumes, and recreating it behind the user's back is how people
    # lose things.
    if (Invoke-DockerQuiet 'container' 'inspect' $name) {
        $state = (docker container inspect -f "{{.State.Status}}" $name)
        if ($state -eq "running") {
            Write-Host ""
            Write-Host "IT-Vault is already running as container '$name'." -ForegroundColor Green
            Write-Host ""
            Write-Host "  Open it:       http://localhost:$port"
            Write-Host "  Update it:     in the app, Settings > General > Check for Updates"
            Write-Host "  Or by hand:    docker pull ${image}:${tag} ; docker rm -f $name"
            Write-Host "                 then run this installer again"
            Write-Host "  See its logs:  docker logs -f $name"
            Write-Host ""
            Stop-Install
        }
        Step "Container '$name' exists but is $state -- starting it"
        Invoke-Step @("docker", "start", $name)
        Write-Host ""
        Write-Host "Started. Open http://localhost:$port" -ForegroundColor Green
        Write-Host ""
        Stop-Install
    }
}

# ---- install ---------------------------------------------------------

Step "Pulling ${image}:${tag}"
Invoke-Step @("docker", "pull", "${image}:${tag}")

Step "Creating volumes (itvault_data, invoices_data, backups_data)"
Invoke-Step @("docker", "volume", "create", "itvault_data")
Invoke-Step @("docker", "volume", "create", "invoices_data")
Invoke-Step @("docker", "volume", "create", "backups_data")

Step "Starting container '$name' on port $port"
Invoke-Step @(
    "docker", "run", "-d",
    "--name", $name,
    "--restart", "unless-stopped",
    "-p", "${port}:5000",
    "-v", "itvault_data:/app/data",
    "-v", "invoices_data:/app/invoices",
    "-v", "backups_data:/app/backups",
    "-e", "ITVAULT_DATA_DIR=/app/data",
    "${image}:${tag}"
)

if ($dry) {
    Write-Host ""
    Write-Host "(dry run -- nothing was changed)"
    Stop-Install
}

# Wait for the app to answer rather than claiming success the moment
# `docker run` returns, so a container that dies on startup is reported.
Step "Waiting for IT-Vault to come up"
$up = $false
foreach ($i in 1..60) {
    $running = ""
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'SilentlyContinue'
    try { $running = (& docker container inspect -f "{{.State.Running}}" $name 2>&1) }
    catch {} finally { $ErrorActionPreference = $prev }
    if ("$running".Trim() -ne "true") {
        Write-Host ""
        Warn "The container stopped. Its last words:"
        $prev = $ErrorActionPreference; $ErrorActionPreference = 'SilentlyContinue'
        try { (& docker logs --tail 20 $name 2>&1) | ForEach-Object { Write-Host "    $_" } }
        catch {} finally { $ErrorActionPreference = $prev }
        Die "IT-Vault did not start."
    }
    try {
        Invoke-WebRequest -Uri "http://localhost:$port/login.html" -UseBasicParsing -TimeoutSec 3 | Out-Null
        $up = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $up) { Warn "It hasn't answered yet -- give it a moment, then open the URL below." }

Write-Host ""
Write-Host "IT-Vault is running." -ForegroundColor Green -NoNewline
Write-Host "  Open http://localhost:$port"
Write-Host ""
Write-Host "You still need a database." -ForegroundColor White
Write-Host "IT-Vault doesn't ship one -- point it at any MariaDB 10.6+ or MySQL 8+ and"
Write-Host "it builds its own schema. Don't have one yet?"
Write-Host ""
Write-Host "    docker volume create itvault_db"
Write-Host "    docker run -d --name itvault-db --restart unless-stopped ``"
Write-Host "      -e MARIADB_ROOT_PASSWORD='<a-strong-root-password>' ``"
Write-Host "      -e MARIADB_DATABASE=itvault ``"
Write-Host "      -e MARIADB_USER=itvault -e MARIADB_PASSWORD='<a-strong-password>' ``"
Write-Host "      -v itvault_db:/var/lib/mysql mariadb:11"
Write-Host "    docker network create itvault-net"
Write-Host "    docker network connect itvault-net itvault-db"
Write-Host "    docker network connect itvault-net $name"
Write-Host ""
Write-Host "Then the setup wizard in your browser asks for the connection (host"
Write-Host "itvault-db for the above, or host.docker.internal for a database installed"
Write-Host "on this machine) and for the admin account you want to create."
Write-Host ""
Write-Host "  Logs:       docker logs -f $name"
Write-Host "  Stop:       docker stop $name"
Write-Host "  Uninstall:  docker rm -f $name     (volumes, and your database, are kept)"
Write-Host ""

}

# Run it. A sentinel throw means "stop, cleanly" -- anything else is a real
# error worth showing. Either way the caller's shell stays open.
try { Invoke-ItVaultInstall }
catch {
    if ($_.Exception.Message -ne $ITV_STOP) {
        Write-Host " X  $($_.Exception.Message)" -ForegroundColor Red
    }
}
