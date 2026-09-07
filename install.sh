#!/bin/sh
# IT-Vault installer.
#
#   curl -fsSL https://raw.githubusercontent.com/shatheitguy/it-vault/main/install.sh | sh
#
# Starts IT-Vault as a Docker container and prints where to open it. If Docker
# is missing it offers to install it for you -- and if you'd rather not have
# Docker at all, it offers to install IT-Vault straight on the host instead
# (Python + waitress). Nothing dead-ends on declining Docker.
#
# It does NOT install a database: IT-Vault connects to whatever MariaDB/MySQL
# you give it, so your database version, backups and retention stay yours. The
# first-run wizard in the browser asks for the connection details.
#
# Flags: --port (5000), --tag (latest), --name (itvault), --yes, --dry-run,
#        --no-docker (install on the host, no Docker), --dir (install path).
set -eu

IMAGE="ghcr.io/shatheitguy/it-vault"
TAG="${ITVAULT_TAG:-latest}"
NAME="${ITVAULT_NAME:-itvault}"
PORT="${ITVAULT_PORT:-5000}"
YES="${ITVAULT_YES:-}"
NO_DOCKER="${ITVAULT_NO_DOCKER:-}"
DIR="${ITVAULT_DIR:-$HOME/it-vault}"
DRY=""

while [ $# -gt 0 ]; do
    case "$1" in
        --port)    PORT="${2:?--port needs a value}"; shift 2 ;;
        --tag)     TAG="${2:?--tag needs a value}"; shift 2 ;;
        --name)    NAME="${2:?--name needs a value}"; shift 2 ;;
        --yes|-y)  YES=1; shift ;;
        --dry-run) DRY=1; shift ;;
        --no-docker) NO_DOCKER=1; shift ;;
        --dir)     DIR="${2:?--dir needs a value}"; shift 2 ;;
        -h|--help)
            # Prints the comment block at the top, so the help text and the
            # documentation can't drift apart. Only works when the script is
            # on disk -- piped through sh, "$0" isn't this file.
            awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0" \
                2>/dev/null || echo "See https://github.com/shatheitguy/it-vault"
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

# The banner is drawn in box characters, which need a UTF-8 locale to survive
# the trip to the terminal -- otherwise it arrives as mojibake, so a plain
# ASCII version is used instead.
banner() {
    if [ -t 1 ]; then
        GRN="$(printf '\033[32m')"; DIM="$(printf '\033[2m')"
    else
        GRN=''; DIM=''
    fi
    printf '%s' "$GRN"
    case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
        *UTF-8*|*utf8*|*UTF8*|*utf-8*)
            cat <<'ART'

  ██╗████████╗   ██╗   ██╗ █████╗ ██╗   ██╗██╗  ████████╗
  ██║╚══██╔══╝   ██║   ██║██╔══██╗██║   ██║██║  ╚══██╔══╝
  ██║   ██║      ██║   ██║███████║██║   ██║██║     ██║
  ██║   ██║      ╚██╗ ██╔╝██╔══██║██║   ██║██║     ██║
  ██║   ██║       ╚████╔╝ ██║  ██║╚██████╔╝███████╗██║
  ╚═╝   ╚═╝        ╚═══╝  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝
ART
            ;;
        *)
            cat <<'ART'

  ___ _____   __     __          _ _
 |_ _|_   _|  \ \   / /_ _ _   _| | |_
  | |  | |     \ \ / / _` | | | | | __|
  | |  | |      \ V / (_| | |_| | | |_
 |___| |_|       \_/ \__,_|\__,_|_|\__|
ART
            ;;
    esac
    printf '%s' "$N"
    printf '%s        01001001 01010100  ::  asset register + helpdesk%s\n' "$DIM" "$N"
    printf '%s               powered by Sha The IT Guy%s\n\n' "$GRN" "$N"
}

warn() { printf '%s !%s  %s\n' "$Y" "$N" "$*"; }
die()  { printf '%s ✕%s  %s\n' "$R" "$N" "$*" >&2; exit 1; }

# Piped through `sh`, stdin is the script itself, so a prompt has to read the
# terminal directly or it silently eats the rest of the script.
ask() {
    [ -n "$YES" ] && return 0
    printf '\n%s %s[y/N]%s ' "$1" "$Y" "$N"
    ans=""
    if [ -t 0 ]; then
        read -r ans || ans=""
    elif [ -r /dev/tty ]; then
        read -r ans < /dev/tty || ans=""
    else
        say ""
        warn "Nothing to read an answer from. Re-run with --yes to proceed unattended."
        return 1
    fi
    case "$ans" in
        y|Y|yes|YES) return 0 ;;
        *) return 1 ;;
    esac
}

# Docker needs root unless the user is in the docker group. Rather than
# assuming, this is set once from what actually works, and every later docker
# call goes through it.
DK="docker"

set_docker_prefix() {
    if docker info >/dev/null 2>&1; then
        DK="docker"
        return 0
    fi
    if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1 \
       && sudo docker info >/dev/null 2>&1; then
        DK="sudo docker"
        return 0
    fi
    if command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
        DK="sudo docker"
        return 0
    fi
    return 1
}

run() {
    if [ -n "$DRY" ]; then
        printf '    %s %s\n' "$DK" "$*"
    else
        # shellcheck disable=SC2086  # $DK is deliberately two words sometimes
        $DK "$@" >/dev/null
    fi
}

# IT-Vault is a Flask app, so it runs perfectly well straight on the host --
# Docker is just the packaged route. This is the fallback for anyone who says
# no to installing Docker: same app, run under waitress from a virtualenv.
install_native() {
    step "Installing IT-Vault without Docker (Python + waitress)"

    PY=""
    for c in python3 python; do
        if command -v "$c" >/dev/null 2>&1; then
            if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null; then
                PY="$c"; break
            fi
        fi
    done
    [ -n "$PY" ] || die "Python 3.9+ is needed for a no-Docker install and wasn't found.
    Install Python, then run this again with --no-docker:
      https://www.python.org/downloads/"

    if [ -n "$DRY" ]; then
        say "    would install into: $DIR"
        say "    would run: $PY -m venv .venv && .venv/bin/pip install -r requirements.txt"
        say "    would start with: .venv/bin/python serve.py"
        return 0
    fi

    command -v curl >/dev/null 2>&1 || die "curl is needed to download IT-Vault."

    step "Downloading IT-Vault into $DIR"
    mkdir -p "$DIR"
    curl -fsSL https://github.com/shatheitguy/it-vault/archive/refs/heads/main.tar.gz         | tar xz -C "$DIR" --strip-components=1         || die "Couldn't download or unpack IT-Vault into $DIR."

    step "Creating a virtualenv and installing dependencies"
    ( cd "$DIR" && "$PY" -m venv .venv ) || die "Couldn't create a virtualenv in $DIR/.venv."
    ( cd "$DIR" && .venv/bin/pip install --quiet --upgrade pip         && .venv/bin/pip install --quiet -r requirements.txt )         || die "Couldn't install the Python dependencies."

    say ""
    say "${G}IT-Vault is installed at${N} ${B}$DIR${N}"
    say ""
    say "It still needs a database -- any MariaDB 10.6+ / MySQL 8+. Point it at one"
    say "with the DB_* environment variables, then start it:"
    say ""
    say "  ${B}cd $DIR${N}"
    say "  ${B}export DB_HOST=127.0.0.1 DB_USER=itvault DB_PASS=your-password DB_NAME=itvault${N}"
    say "  ${B}ITVAULT_PORT=$PORT .venv/bin/python serve.py${N}"
    say ""
    say "Then open ${B}http://localhost:$PORT${N} for the setup wizard."
    say ""
    say "No database yet? Start one in a line (needs Docker) or install MariaDB from"
    say "your package manager -- see ${B}https://github.com/shatheitguy/it-vault#step-1--get-a-database${N}"
}

# Called wherever Docker is missing and the user declines to install it: offer
# the no-Docker route rather than dead-ending on "install Docker yourself".
offer_native_or_die() {
    if ask "Install IT-Vault without Docker instead (Python on this machine)?"; then
        install_native
        exit 0
    fi
    die "$1"
}

install_docker() {
    os="$(uname -s)"
    case "$os" in
        Linux)
            ask "Docker isn't installed. Install it now with Docker's official script?" || offer_native_or_die \
"Nothing was installed. Install Docker yourself and run this again:
      https://docs.docker.com/engine/install/
    Or re-run with --yes to install it unattended."
            command -v curl >/dev/null 2>&1 || die "curl is needed to fetch the Docker installer."
            step "Installing Docker (https://get.docker.com -- needs root)"
            if [ "$(id -u)" = "0" ]; then
                curl -fsSL https://get.docker.com | sh
            else
                command -v sudo >/dev/null 2>&1 || die \
"Installing Docker needs root and sudo isn't available. Run this as root,
    or install Docker yourself: https://docs.docker.com/engine/install/"
                curl -fsSL https://get.docker.com | sudo sh
            fi
            if command -v systemctl >/dev/null 2>&1; then
                step "Enabling the Docker service"
                if [ "$(id -u)" = "0" ]; then
                    systemctl enable --now docker >/dev/null 2>&1 || true
                else
                    sudo systemctl enable --now docker >/dev/null 2>&1 || true
                fi
            fi
            # Group membership only takes effect on a new login, so this run
            # falls back to sudo rather than telling the user to log out.
            if [ "$(id -u)" != "0" ] && command -v sudo >/dev/null 2>&1; then
                sudo usermod -aG docker "$(id -un)" >/dev/null 2>&1 || true
                warn "Added you to the 'docker' group -- log out and back in to use docker without sudo."
            fi
            ;;
        Darwin)
            if command -v brew >/dev/null 2>&1; then
                ask "Docker isn't installed. Install Docker Desktop with Homebrew?" || offer_native_or_die \
"Nothing was installed. Get Docker Desktop and run this again:
      https://docs.docker.com/desktop/install/mac-install/"
                step "Installing Docker Desktop (brew install --cask docker)"
                brew install --cask docker
                step "Starting Docker Desktop"
                open -a Docker || true
                say "    First launch asks you to accept Docker's licence terms."
            else
                offer_native_or_die \
"Docker isn't installed, and Homebrew isn't here to install it.
    Get Docker Desktop, open it once, then run this again:
      https://docs.docker.com/desktop/install/mac-install/"
            fi
            ;;
        *)
            offer_native_or_die \
"Docker isn't installed, and this script doesn't know how to install it on
    $os. Install Docker, then run this again:
      https://docs.docker.com/get-docker/"
            ;;
    esac

    # Docker Desktop on macOS in particular takes a while, and wants a click
    # on first run, so this waits instead of failing the moment it's absent.
    step "Waiting for the Docker engine (up to 3 minutes)"
    i=0
    while [ "$i" -lt 90 ]; do
        if command -v docker >/dev/null 2>&1 && set_docker_prefix; then
            return 0
        fi
        i=$((i + 1))
        sleep 2
    done
    die \
"Docker was installed but its engine isn't answering yet.
    Start Docker (on macOS: open Docker Desktop and accept the terms), then
    run this installer again."
}

banner

# ---- checks ----------------------------------------------------------

# --no-docker / ITVAULT_NO_DOCKER: skip Docker entirely and run on the host.
if [ -n "$NO_DOCKER" ]; then
    install_native
    exit 0
fi

if [ -n "$DRY" ]; then
    command -v docker >/dev/null 2>&1 \
        || warn "Docker isn't installed here -- showing the plan anyway."
else
    if ! command -v docker >/dev/null 2>&1; then
        install_docker
    elif ! set_docker_prefix; then
        die \
"Docker is installed but not reachable. Either it isn't running:
      sudo systemctl start docker
    or your user can't talk to it (log out and back in after being added to
    the 'docker' group)."
    fi

    # An existing container is left alone rather than replaced: it owns the
    # data volumes, and recreating it behind the user's back is how people
    # lose things.
    # shellcheck disable=SC2086
    if $DK container inspect "$NAME" >/dev/null 2>&1; then
        # shellcheck disable=SC2086
        state="$($DK container inspect -f '{{.State.Status}}' "$NAME")"
        if [ "$state" = "running" ]; then
            say ""
            say "${G}IT-Vault is already running${N} as container '$NAME'."
            say ""
            say "  Open it:       http://localhost:$PORT"
            say "  Update it:     in the app, Settings ▸ General ▸ Check for Updates"
            say "  Or by hand:    $DK pull $IMAGE:$TAG && $DK rm -f $NAME"
            say "                 then run this installer again"
            say "  See its logs:  $DK logs -f $NAME"
            say ""
            exit 0
        fi
        step "Container '$NAME' exists but is $state -- starting it"
        run start "$NAME"
        say ""
        say "${G}Started.${N} Open http://localhost:$PORT"
        say ""
        exit 0
    fi
fi

# ---- install ---------------------------------------------------------

step "Pulling $IMAGE:$TAG"
if [ -n "$DRY" ]; then
    printf '    docker pull %s\n' "$IMAGE:$TAG"
else
    # shellcheck disable=SC2086
    $DK pull "$IMAGE:$TAG" >/dev/null || die \
"Could not pull $IMAGE:$TAG. Check the tag exists and that you can reach
    ghcr.io."
fi

step "Creating volumes (itvault_data, invoices_data, backups_data)"
run volume create itvault_data
run volume create invoices_data
run volume create backups_data

step "Starting container '$NAME' on port $PORT"
# --add-host is what lets DB_HOST=host.docker.internal reach a database
# installed on this machine rather than inside the container. Docker Desktop
# provides it already; on Linux it has to be asked for.
run run -d \
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
    # shellcheck disable=SC2086
    if ! $DK container inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null | grep -q true; then
        say ""
        warn "The container stopped. Its last words:"
        # shellcheck disable=SC2086
        $DK logs --tail 20 "$NAME" 2>&1 | sed 's/^/    /'
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
say "  Logs:       $DK logs -f $NAME"
say "  Stop:       $DK stop $NAME"
say "  Uninstall:  $DK rm -f $NAME     (volumes, and your database, are kept)"
say ""
