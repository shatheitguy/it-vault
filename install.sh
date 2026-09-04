#!/bin/sh
# IT-Vault installer.
#
#   curl -fsSL https://raw.githubusercontent.com/shatheitguy/it-vault/main/install.sh | sh
#
# Starts IT-Vault as a Docker container and prints where to open it. It does
# NOT install a database: IT-Vault connects to whatever MariaDB/MySQL you give
# it, so your database version, backups and retention stay yours. The first-run
# wizard in the browser asks for the connection details.
#
# Env vars / flags: --port (5000), --tag (latest), --name (itvault), --dry-run.
set -eu

IMAGE="ghcr.io/shatheitguy/it-vault"
TAG="${ITVAULT_TAG:-latest}"
NAME="${ITVAULT_NAME:-itvault}"
PORT="${ITVAULT_PORT:-5000}"
DRY=""

while [ $# -gt 0 ]; do
    case "$1" in
        --port)    PORT="${2:?--port needs a value}"; shift 2 ;;
        --tag)     TAG="${2:?--tag needs a value}"; shift 2 ;;
        --name)    NAME="${2:?--name needs a value}"; shift 2 ;;
        --dry-run) DRY=1; shift ;;
        -h|--help)
            # Prints the comment block at the top, so the help text and the
            # documentation can't drift apart. Only works when the script is
            # on disk -- piped through sh, "$0" isn't this file.
            awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0" \
                2>/dev/null || say "See https://github.com/shatheitguy/it-vault"
            exit 0 ;;
        *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
    esac
done

# Colour only when writing to a terminal, so piping to a file or a log stays
# readable instead of filling up with escape codes.
if [ -t 1 ]; then
    B="$(printf '\033[1m')"; R="$(printf '\033[31m')"
    G="$(printf '\033[32m')"; Y="$(printf '\033[33m')"; N="$(printf '\033[0m')"
else
    B=""; R=""; G=""; Y=""; N=""
fi

say()  { printf '%s\n' "$*"; }
step() { printf '%s==>%s %s\n' "$B" "$N" "$*"; }
warn() { printf '%s !%s  %s\n' "$Y" "$N" "$*"; }
die()  { printf '%s ✕%s  %s\n' "$R" "$N" "$*" >&2; exit 1; }

run() {
    if [ -n "$DRY" ]; then
        printf '    %s\n' "$*"
    else
        "$@" >/dev/null
    fi
}

# ---- checks ----------------------------------------------------------

if ! command -v docker >/dev/null 2>&1; then
    # A dry run is for reading the plan before trusting it, so it must work
    # on a machine that hasn't got Docker yet.
    if [ -n "$DRY" ]; then
        warn "Docker isn't installed here -- showing the plan anyway."
    else
        die "Docker isn't installed. Get it from
    https://docs.docker.com/get-docker/  then run this again."
    fi
fi

if [ -z "$DRY" ] && ! docker info >/dev/null 2>&1; then
    die "Docker is installed but not running (or your user can't reach it).
    Start Docker, or add yourself to the 'docker' group, then run this again."
fi

# An existing container is left alone rather than replaced: it owns the data
# volumes, and recreating it behind the user's back is how people lose things.
if [ -z "$DRY" ] && docker container inspect "$NAME" >/dev/null 2>&1; then
    state="$(docker container inspect -f '{{.State.Status}}' "$NAME")"
    if [ "$state" = "running" ]; then
        url="$(docker container port "$NAME" 5000/tcp 2>/dev/null | head -1)"
        say ""
        say "${G}IT-Vault is already running${N} as container '$NAME'${url:+ on $url}."
        say ""
        say "  Update it:     in the app, Settings ▸ General ▸ Check for Updates"
        say "  Or by hand:    docker pull $IMAGE:$TAG && docker rm -f $NAME"
        say "                 then run this installer again"
        say "  See its logs:  docker logs -f $NAME"
        say ""
        exit 0
    fi
    step "Container '$NAME' exists but is $state -- starting it"
    run docker start "$NAME"
    say ""
    say "${G}Started.${N} Open http://localhost:$PORT"
    say ""
    exit 0
fi

# ---- install ---------------------------------------------------------

step "Pulling $IMAGE:$TAG"
if [ -n "$DRY" ]; then
    printf '    docker pull %s\n' "$IMAGE:$TAG"
elif ! docker pull "$IMAGE:$TAG" >/dev/null; then
    die "Could not pull $IMAGE:$TAG. Check the tag exists and that you can
    reach ghcr.io."
fi

step "Creating volumes (itvault_data, invoices_data, backups_data)"
run docker volume create itvault_data
run docker volume create invoices_data
run docker volume create backups_data

step "Starting container '$NAME' on port $PORT"
# --add-host is what lets DB_HOST=host.docker.internal reach a database
# installed on this machine rather than inside the container. Docker Desktop
# provides it already; on Linux it has to be asked for.
run docker run -d \
    --name "$NAME" \
    --restart unless-stopped \
    -p "$PORT:5000" \
    -v itvault_data:/app/data \
    -v invoices_data:/app/invoices \
    -v backups_data:/app/backups \
    -e ITVAULT_DATA_DIR=/app/data \
    --add-host host.docker.internal:host-gateway \
    "$IMAGE:$TAG"

if [ -n "$DRY" ]; then
    say ""
    say "(dry run -- nothing was changed)"
    exit 0
fi

# Wait for the app to answer rather than claiming success the moment `docker
# run` returns, so a container that dies on startup is reported as a failure.
step "Waiting for IT-Vault to come up"
i=0
while [ "$i" -lt 60 ]; do
    if ! docker container inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null | grep -q true; then
        say ""
        warn "The container stopped. Its last words:"
        docker logs --tail 20 "$NAME" 2>&1 | sed 's/^/    /'
        die "IT-Vault did not start."
    fi
    if command -v curl >/dev/null 2>&1; then
        curl -fsS -o /dev/null "http://localhost:$PORT/login.html" 2>/dev/null && break
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O /dev/null "http://localhost:$PORT/login.html" 2>/dev/null && break
    else
        sleep 3; break
    fi
    i=$((i + 1))
    sleep 1
done

say ""
say "${G}IT-Vault is running.${N}  Open ${B}http://localhost:$PORT${N}"
say ""
say "${B}You still need a database.${N} IT-Vault doesn't ship one -- point it at any"
say "MariaDB 10.6+ or MySQL 8+ and it builds its own schema. Don't have one yet?"
say ""
say "    docker volume create itvault_db"
say "    docker run -d --name itvault-db --restart unless-stopped \\"
say "      -e MARIADB_ROOT_PASSWORD='<a-strong-root-password>' \\"
say "      -e MARIADB_DATABASE=itvault \\"
say "      -e MARIADB_USER=itvault -e MARIADB_PASSWORD='<a-strong-password>' \\"
say "      -v itvault_db:/var/lib/mysql mariadb:11"
say "    docker network create itvault-net"
say "    docker network connect itvault-net itvault-db"
say "    docker network connect itvault-net $NAME"
say ""
say "Then the setup wizard in your browser asks for the connection (host"
say "${B}itvault-db${N} for the above, or ${B}host.docker.internal${N} for a database installed"
say "on this machine) and for the admin account you want to create."
say ""
say "  Logs:       docker logs -f $NAME"
say "  Stop:       docker stop $NAME"
say "  Uninstall:  docker rm -f $NAME     (volumes, and your database, are kept)"
say ""
