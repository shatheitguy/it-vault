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
# It offers to install MariaDB too, asking for the database name, username and
# password, then handing IT-Vault the connection -- so there is no setup
# wizard to fill in and no GRANT to get wrong. On Docker this is a container
# (network + volume, MariaDB image), same as the Linux/macOS installer. With
# ITVAULT_NO_DOCKER it is the same offer via winget (MariaDB.Server) instead.
# Say no either way and IT-Vault connects to whatever MariaDB/MySQL you
# already run, with the first-run wizard asking for the details; either way
# your database version, backups and retention stay yours.
#
# Configure with environment variables before running (there are no parameters,
# so the line above works unchanged when piped to iex):
#
#   $env:ITVAULT_PORT = "8080"    # host port,      default 5000
#   $env:ITVAULT_TAG  = "1.6.2"   # image tag,      default latest
#   $env:ITVAULT_NAME = "myvault" # container name, default itvault
#   $env:ITVAULT_YES  = "1"       # don't ask before installing Docker or MariaDB
#   $env:ITVAULT_DRY  = "1"       # print the plan, change nothing
#   $env:ITVAULT_WITH_DB = "1"    # install MariaDB without being asked
#   $env:ITVAULT_NO_DB   = "1"    # do not ask, use the browser wizard
#   $env:ITVAULT_DB_NAME / ITVAULT_DB_USER / ITVAULT_DB_PASS   # unattended, implies WITH_DB
#   $env:ITVAULT_DB_IMAGE = "mariadb:11"  # Docker only, default mariadb:latest

$ErrorActionPreference = "Stop"

$image = "ghcr.io/shatheitguy/it-vault"
$tag  = if ($env:ITVAULT_TAG)  { $env:ITVAULT_TAG }  else { "latest" }
$name = if ($env:ITVAULT_NAME) { $env:ITVAULT_NAME } else { "itvault" }
$port = if ($env:ITVAULT_PORT) { $env:ITVAULT_PORT } else { "5000" }
$dry  = [bool]$env:ITVAULT_DRY
$yes  = [bool]$env:ITVAULT_YES
$noDocker = [bool]$env:ITVAULT_NO_DOCKER
$dir  = if ($env:ITVAULT_DIR) { $env:ITVAULT_DIR } else { Join-Path $env:USERPROFILE "it-vault" }

# ---- database provisioning (same concept as install.sh) --------------

$dbName = if ($env:ITVAULT_DB_NAME) { $env:ITVAULT_DB_NAME } else { "itvault" }
$dbUser = if ($env:ITVAULT_DB_USER) { $env:ITVAULT_DB_USER } else { "itvault" }
$dbPass = $env:ITVAULT_DB_PASS
$withDb = [bool]$env:ITVAULT_WITH_DB
$noDb   = [bool]$env:ITVAULT_NO_DB
if ($dbPass) { $withDb = $true }
$dbContainer = if ($env:ITVAULT_DB_NAME_CONTAINER) { $env:ITVAULT_DB_NAME_CONTAINER } else { "itvault-db" }
$net = if ($env:ITVAULT_NET) { $env:ITVAULT_NET } else { "itvault-net" }
$dbImage = if ($env:ITVAULT_DB_IMAGE) { $env:ITVAULT_DB_IMAGE } else { "mariadb:latest" }
# Where this installer keeps what it decided, so a later run does not have to
# ask again -- same reasoning as install.sh's CONF_FILE.
$confDir = if ($env:ITVAULT_CONF_DIR) { $env:ITVAULT_CONF_DIR } else { Join-Path $env:USERPROFILE ".itvault" }
$confFile = Join-Path $confDir "install.env.ps1"

function New-DbPassword {
    -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
}

# Reuses a saved connection from a previous run -- an update should keep the
# database it already had rather than asking again.
function Import-SavedConf {
    if (-not (Test-Path $confFile)) { return $false }
    try {
        . $confFile
        if ($script:SAVED_DB_NAME) { $script:dbName = $script:SAVED_DB_NAME }
        if ($script:SAVED_DB_USER) { $script:dbUser = $script:SAVED_DB_USER }
        if ($script:SAVED_DB_PASS) { $script:dbPass = $script:SAVED_DB_PASS }
        return $true
    } catch { return $false }
}

# 600-equivalent: NTFS ACL restricted to the current user, since this file
# holds a database password.
function Save-Conf($dbHostVal) {
    if ($dry) { return }
    New-Item -ItemType Directory -Force -Path $confDir | Out-Null
    @"
# Written by the IT-Vault installer -- do not delete.
# It is what lets an update keep this install's database.
`$SAVED_DB_HOST = '$dbHostVal'
`$SAVED_DB_NAME = '$dbName'
`$SAVED_DB_USER = '$dbUser'
`$SAVED_DB_PASS = '$dbPass'
"@ | Set-Content -Path $confFile -Encoding ASCII
    try {
        icacls $confFile /inheritance:r /grant:r "$env:USERNAME:F" | Out-Null
    } catch {}
    Write-Host "    configuration saved to $confFile -- updates reuse it"
}

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

function Ask-YesNo($question) {
    if ($yes) { return $true }
    Write-Host ""
    Write-Host $question -NoNewline
    Write-Host " [y/N] " -NoNewline -ForegroundColor Yellow
    $answer = ""
    try { $answer = Read-Host } catch { $answer = "" }
    return ($answer -match '^(y|yes)$')
}

function Ask-Line($prompt, $default) {
    if ($default) { Write-Host "  $prompt [$default]: " -NoNewline -ForegroundColor White }
    else { Write-Host "  ${prompt}: " -NoNewline -ForegroundColor White }
    $v = ""
    try { $v = Read-Host } catch { $v = "" }
    if (-not $v) { $v = $default }
    return $v
}

# Same offer as install.sh's db_prompt(): install MariaDB here and connect
# IT-Vault to it, or decline and use the browser's setup wizard instead.
function Confirm-Db {
    Write-Host ""
    Write-Host "Database" -ForegroundColor White
    Write-Host "  IT-Vault needs MariaDB or MySQL. It can install one here and wire itself"
    Write-Host "  up, or you can point it at a server you already run."
    if (-not (Ask-YesNo "Install MariaDB here and connect IT-Vault to it?")) { return $false }
    $script:dbName = Ask-Line "Database name    " $dbName
    $script:dbUser = Ask-Line "Database username" $dbUser
    if (-not $dbPass) { $script:dbPass = New-DbPassword }
    Write-Host "    database  $dbName"
    Write-Host "    username  $dbUser"
    Write-Host "    password  set"
    return $true
}

# One value out of a container's environment -- same trick install.sh uses to
# adopt an existing database container instead of refusing it.
function Get-ContainerEnvValue($container, $key) {
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'SilentlyContinue'
    try {
        $envLines = & docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' $container 2>$null
        foreach ($l in $envLines) { if ($l -like "$key=*") { return $l.Substring($key.Length + 1) } }
    } catch {} finally { $ErrorActionPreference = $prev }
    return $null
}

# Same concept as install.sh's provision_db(): a shared network so the app
# reaches the database by container name, an existing database container
# adopted rather than refused, and a fresh one created with its own generated
# passwords when neither applies.
function Invoke-ProvisionDb {
    if (-not (Invoke-DockerQuiet 'network' 'inspect' $net)) {
        Step "Creating network '$net'"
        Invoke-Step @("docker", "network", "create", $net)
    } else {
        Write-Host "    network '$net' already exists -- reusing it"
    }

    if (Invoke-DockerQuiet 'inspect' $dbContainer) {
        $adoptUser = Get-ContainerEnvValue $dbContainer "MARIADB_USER"
        $adoptPass = Get-ContainerEnvValue $dbContainer "MARIADB_PASSWORD"
        $adoptName = Get-ContainerEnvValue $dbContainer "MARIADB_DATABASE"
        if ($adoptUser -and $adoptPass -and $adoptName) {
            Step "Adopting the existing database container '$dbContainer'"
            $script:dbUser = $adoptUser; $script:dbPass = $adoptPass; $script:dbName = $adoptName
            $state = (docker inspect -f "{{.State.Running}}" $dbContainer)
            if ("$state".Trim() -ne "true") { Invoke-Step @("docker", "start", $dbContainer) }
            $nets = (docker inspect -f "{{range `$k, `$v := .NetworkSettings.Networks}}{{`$k}} {{end}}" $dbContainer)
            if ("$nets" -notmatch [regex]::Escape($net)) { Invoke-Step @("docker", "network", "connect", $net, $dbContainer) }
            Write-Host "    reusing database '$dbName' as user '$dbUser'"
            return $true
        }
        Warn "A container named '$dbContainer' already exists, and its password is not in its environment."
        Write-Host "    Point IT-Vault at it through the setup wizard, or remove it first:"
        Write-Host "      docker rm -f $dbContainer   # keeps the itvault_db volume"
        return $false
    }

    if (-not $dbPass) { $script:dbPass = New-DbPassword }
    $dbRootPass = New-DbPassword

    Step "Creating volume itvault_db"
    Invoke-Step @("docker", "volume", "create", "itvault_db")

    Step "Starting MariaDB as '$dbContainer' (not published to the network)"
    Invoke-Step @(
        "docker", "run", "-d",
        "--name", $dbContainer,
        "--network", $net,
        "--restart", "unless-stopped",
        "-e", "MARIADB_ROOT_PASSWORD=$dbRootPass",
        "-e", "MARIADB_DATABASE=$dbName",
        "-e", "MARIADB_USER=$dbUser",
        "-e", "MARIADB_PASSWORD=$dbPass",
        "-v", "itvault_db:/var/lib/mysql",
        "--health-cmd", "healthcheck.sh --connect --innodb_initialized",
        "--health-interval", "5s", "--health-timeout", "5s", "--health-retries", "20",
        $dbImage
    )

    Step "Waiting for MariaDB to finish initialising"
    $healthy = $false
    foreach ($i in 1..60) {
        $prev = $ErrorActionPreference; $ErrorActionPreference = 'SilentlyContinue'
        $h = ""
        try { $h = (& docker inspect -f "{{.State.Health.Status}}" $dbContainer 2>$null) } catch {} finally { $ErrorActionPreference = $prev }
        if ("$h".Trim() -eq "healthy") { $healthy = $true; break }
        Start-Sleep -Seconds 2
        if ($i % 5 -eq 0) { Write-Host "    still initialising (${i}0s)..." }
    }
    if (-not $healthy) {
        Warn "MariaDB hasn't reported healthy yet. IT-Vault waits for it on start, so this"
        Write-Host "    usually still works -- check: docker logs $dbContainer"
    } else {
        Write-Host "    database ready"
    }
    return $true
}

# Finds mysql.exe after a fresh MariaDB install -- winget's package doesn't
# always land on PATH within the same process that just installed it.
function Find-MysqlExe {
    $roots = @("$env:ProgramFiles\MariaDB*\bin", "${env:ProgramFiles(x86)}\MariaDB*\bin")
    foreach ($root in $roots) {
        $found = Get-ChildItem -Path $root -Filter "mysql.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    $cmd = Get-Command mysql -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

# Same concept as install.sh's provision_db_native(), for anyone who declined
# Docker entirely: install MariaDB via winget, start its service, and create
# the database and user IT-Vault will use.
function Install-MariaDbNative {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Warn "winget isn't available -- can't install MariaDB automatically."
        return $false
    }

    $svc = Get-Service -Name "MariaDB" -ErrorAction SilentlyContinue
    $mysql = $null
    $rootPass = $null
    if ($svc -and $svc.Status -eq "Running") {
        Write-Host "    MariaDB service already installed and running -- reusing it"
        $mysql = Find-MysqlExe
    } else {
        $rootPass = New-DbPassword
        Step "Installing MariaDB (winget) -- this takes a few minutes"
        $prev = $ErrorActionPreference; $ErrorActionPreference = 'SilentlyContinue'
        winget install --id MariaDB.Server --exact --source winget `
            --accept-package-agreements --accept-source-agreements --silent `
            --override "SERVICENAME=MariaDB PASSWORD=$rootPass PORT=3306 /quiet" 2>&1 | Out-Null
        $code = $LASTEXITCODE
        $ErrorActionPreference = $prev

        Step "Waiting for the MariaDB service"
        foreach ($i in 1..30) {
            $svc = Get-Service -Name "MariaDB" -ErrorAction SilentlyContinue
            if ($svc -and $svc.Status -eq "Running") { break }
            if ($svc -and $svc.Status -ne "Running") { try { Start-Service $svc -ErrorAction SilentlyContinue } catch {} }
            Start-Sleep -Seconds 2
        }
        if (-not $svc -or $svc.Status -ne "Running") {
            Warn "MariaDB was installed but its service isn't running (winget exit $code)."
            return $false
        }
        $mysql = Find-MysqlExe
    }

    if (-not $mysql) {
        Warn "MariaDB's service is running, but mysql.exe couldn't be found to create the database."
        return $false
    }

    if (-not $dbPass) { $script:dbPass = New-DbPassword }
    Step "Creating database '$dbName' and user '$dbUser'"
    $sql = "CREATE DATABASE IF NOT EXISTS ``$dbName``; " +
           "CREATE USER IF NOT EXISTS '$dbUser'@'localhost' IDENTIFIED BY '$dbPass'; " +
           "GRANT ALL PRIVILEGES ON ``$dbName``.* TO '$dbUser'@'localhost'; FLUSH PRIVILEGES;"
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'SilentlyContinue'
    if ($rootPass) {
        & $mysql "-uroot" "-p$rootPass" -e $sql 2>$null
    } else {
        # Reused an existing, already-running install: root's original
        # password is unknown to this run, so try the unix-socket-equivalent
        # (no password) first -- a fresh default install often has none.
        & $mysql "-uroot" -e $sql 2>$null
    }
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prev
    if (-not $ok) {
        Warn "Could not create the database automatically -- see the manual steps below."
        return $false
    }
    Write-Host "    database ready: $dbName (user $dbUser)"
    return $true
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

    # Same concept as install.sh's --no-docker path: offer to install and wire
    # up the database here too, so this doesn't dead-end at the browser's
    # setup wizard either.
    Import-SavedConf | Out-Null
    if ($dbPass) { $withDb = $true }
    $dbReady = $false
    if (-not $noDb) {
        if ($withDb -or (Confirm-Db)) {
            $dbReady = Install-MariaDbNative
        }
    }

    if ($dbReady) {
        Save-Conf "127.0.0.1"

        # A start script beats telling people to re-type four env vars every
        # time -- this is what "no setup wizard to fill in" means here too.
        $startScript = Join-Path $dir "start.ps1"
        @"
# Written by the IT-Vault installer. Starts IT-Vault with the database
# provisioned during install -- edit the DB_* lines if that ever changes.
`$env:DB_HOST = '127.0.0.1'
`$env:DB_NAME = '$dbName'
`$env:DB_USER = '$dbUser'
`$env:DB_PASS = '$dbPass'
`$env:ITVAULT_PORT = '$port'
& "$dir\.venv\Scripts\python.exe" "$dir\serve.py"
"@ | Set-Content -Path $startScript -Encoding ASCII

        Write-Host ""
        Write-Host "IT-Vault is installed at " -NoNewline; Write-Host $dir -ForegroundColor Green -NoNewline
        Write-Host " and connected to its own MariaDB --" -ForegroundColor Green
        Write-Host "no setup wizard to fill in." -ForegroundColor Green
        Write-Host ""
        Write-Host "Start it:"
        Write-Host "  powershell -File `"$startScript`"" -ForegroundColor White
        Write-Host ""
        Write-Host "Then open http://localhost:$port and sign in with the admin account you set up."
        Write-Host ""
    } else {
        if (-not $noDb) { Warn "Falling back to the manual steps below." }
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

# ---- database ----------------------------------------------------------

# Asked here rather than after the pull, so the install is not waiting on a
# download before it knows what it is building. Same decision order as
# install.sh: a saved config wins, then an already-adopted database
# container, then (failing both) the prompt.
$dbReady = $false
if (-not $dry) {
    if (Import-SavedConf) {
        Write-Host "    reusing the saved configuration from $confFile"
        if ($dbPass) { $withDb = $true }
    }
    if (-not $withDb -and -not $noDb -and (Invoke-DockerQuiet 'inspect' $dbContainer) `
            -and (Get-ContainerEnvValue $dbContainer "MARIADB_USER")) {
        Write-Host "    found the existing database container -- reconnecting to it"
        $withDb = $true
    }
    if (-not $withDb -and -not $noDb) {
        if (Confirm-Db) { $withDb = $true }
    }
}

# ---- install ---------------------------------------------------------

Step "Pulling ${image}:${tag}"
Invoke-Step @("docker", "pull", "${image}:${tag}")

if ($withDb -and -not $dry) {
    $dbReady = Invoke-ProvisionDb
    if ($dbReady) { Save-Conf "$dbContainer" }
}

Step "Creating volumes (itvault_data, invoices_data, backups_data)"
Invoke-Step @("docker", "volume", "create", "itvault_data")
Invoke-Step @("docker", "volume", "create", "invoices_data")
Invoke-Step @("docker", "volume", "create", "backups_data")

Step "Starting container '$name' on port $port"
$runArgs = @(
    "docker", "run", "-d",
    "--name", $name,
    "--restart", "unless-stopped",
    "-p", "${port}:5000",
    "-v", "itvault_data:/app/data",
    "-v", "invoices_data:/app/invoices",
    "-v", "backups_data:/app/backups",
    "-e", "ITVAULT_DATA_DIR=/app/data"
)
if ($dbReady) {
    $runArgs += @(
        "--network", $net,
        "-e", "DB_HOST=$dbContainer",
        "-e", "DB_NAME=$dbName",
        "-e", "DB_USER=$dbUser",
        "-e", "DB_PASS=$dbPass"
    )
}
$runArgs += "${image}:${tag}"
Invoke-Step $runArgs

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
if ($dbReady) {
    Write-Host "Connected to its own MariaDB -- no setup wizard to fill in. Open the URL" -ForegroundColor Green
    Write-Host "above and sign in with the admin account you set up." -ForegroundColor Green
    Write-Host ""
} else {
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
}
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
