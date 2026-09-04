# IT-Vault installer for Windows.
#
#   irm https://raw.githubusercontent.com/shatheitguy/it-vault/main/install.ps1 | iex
#
# Starts IT-Vault as a Docker container and prints where to open it. It does
# NOT install a database: IT-Vault connects to whatever MariaDB/MySQL you give
# it, so your database version, backups and retention stay yours. The first-run
# wizard in the browser asks for the connection details.
#
# Configure with environment variables before running (there are no parameters,
# so the line above works unchanged when piped to iex):
#
#   $env:ITVAULT_PORT = "8080"    # host port,      default 5000
#   $env:ITVAULT_TAG  = "1.6.1"   # image tag,      default latest
#   $env:ITVAULT_NAME = "myvault" # container name, default itvault
#   $env:ITVAULT_DRY  = "1"       # print the plan, change nothing

$ErrorActionPreference = "Stop"

$image = "ghcr.io/shatheitguy/it-vault"
$tag  = if ($env:ITVAULT_TAG)  { $env:ITVAULT_TAG }  else { "latest" }
$name = if ($env:ITVAULT_NAME) { $env:ITVAULT_NAME } else { "itvault" }
$port = if ($env:ITVAULT_PORT) { $env:ITVAULT_PORT } else { "5000" }
$dry  = [bool]$env:ITVAULT_DRY

function Step($m) { Write-Host "==> " -NoNewline -ForegroundColor White; Write-Host $m }
function Warn($m) { Write-Host " !  $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host " X  $m" -ForegroundColor Red; exit 1 }

function Invoke-Step {
    param([string[]]$Cmd)
    if ($dry) { Write-Host ("    " + ($Cmd -join " ")) ; return }
    & $Cmd[0] @($Cmd[1..($Cmd.Length - 1)]) | Out-Null
    if ($LASTEXITCODE -ne 0) { Die "`"$($Cmd -join ' ')`" failed (exit $LASTEXITCODE)." }
}

# ---- checks ----------------------------------------------------------

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    # A dry run is for reading the plan before trusting it, so it has to work
    # on a machine that hasn't got Docker yet.
    if ($dry) { Warn "Docker isn't installed here -- showing the plan anyway." }
    else { Die "Docker isn't installed. Get Docker Desktop from`n    https://docs.docker.com/desktop/install/windows-install/  then run this again." }
}

if (-not $dry) {
    docker info 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { Die "Docker is installed but not running. Start Docker Desktop, then run this again." }

    # An existing container is left alone rather than replaced: it owns the
    # data volumes, and recreating it behind the user's back is how people
    # lose things.
    docker container inspect $name 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $state = (docker container inspect -f "{{.State.Status}}" $name)
        if ($state -eq "running") {
            Write-Host ""
            Write-Host "IT-Vault is already running as container '$name'." -ForegroundColor Green
            Write-Host ""
            Write-Host "  Update it:     in the app, Settings > General > Check for Updates"
            Write-Host "  Or by hand:    docker pull ${image}:${tag} ; docker rm -f $name"
            Write-Host "                 then run this installer again"
            Write-Host "  See its logs:  docker logs -f $name"
            Write-Host ""
            exit 0
        }
        Step "Container '$name' exists but is $state -- starting it"
        Invoke-Step @("docker", "start", $name)
        Write-Host ""
        Write-Host "Started. Open http://localhost:$port" -ForegroundColor Green
        Write-Host ""
        exit 0
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
    exit 0
}

# Wait for the app to answer rather than claiming success the moment
# `docker run` returns, so a container that dies on startup is reported.
Step "Waiting for IT-Vault to come up"
$up = $false
foreach ($i in 1..60) {
    if ((docker container inspect -f "{{.State.Running}}" $name 2>$null) -ne "true") {
        Write-Host ""
        Warn "The container stopped. Its last words:"
        docker logs --tail 20 $name 2>&1 | ForEach-Object { Write-Host "    $_" }
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
