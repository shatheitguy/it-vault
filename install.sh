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
# It offers to install MariaDB too, asking for the database name, username and
# password, then handing IT-Vault the connection -- so there is no setup
# wizard to fill in and no GRANT to get wrong. On Docker this is a container
# (network + volume, MariaDB image). On --no-docker it is the same offer
# through the host's own package manager (apt/dnf/yum/pacman on Linux, brew
# on macOS) instead. Say no either way and IT-Vault connects to whatever
# MariaDB/MySQL you already run, with the first-run wizard asking for the
# details; either way your database version, backups and retention stay yours.
#
# Flags: --port (5000), --tag (latest), --name (itvault), --yes, --dry-run,
#        --no-docker (install on the host, no Docker), --dir (install path),
#        --with-db (install MariaDB without being asked),
#        --no-db (do not ask, use the browser wizard),
#        --db-name / --db-user / --db-pass (unattended, implies --with-db),
#        --db-image (Docker only: database image, default mariadb:latest).
set -eu

IMAGE="ghcr.io/shatheitguy/it-vault"
TAG="${ITVAULT_TAG:-latest}"
NAME="${ITVAULT_NAME:-itvault}"
PORT="${ITVAULT_PORT:-5000}"
YES="${ITVAULT_YES:-}"
NO_DOCKER="${ITVAULT_NO_DOCKER:-}"
WITH_DB="${ITVAULT_WITH_DB:-}"
NO_DB="${ITVAULT_NO_DB:-}"
NET="${ITVAULT_NET:-itvault-net}"
DB_NAME_V="${ITVAULT_DB_NAME:-itvault}"
DB_USER_V="${ITVAULT_DB_USER:-itvault}"
# Tracks whether this run actually chose the name/user above, as opposed to
# just landing on the default -- load_conf()'s own merge treats "itvault"
# as already decided, which the Docker path gets away with because an
# existing database container's real env always wins on adoption regardless.
# install_native() has no such adoption step, so it uses these to tell "the
# default" from "what a previous run saved" instead of silently creating a
# second, empty database under the default name on every re-run.
DB_NAME_EXPLICIT=""
[ -n "${ITVAULT_DB_NAME:-}" ] && DB_NAME_EXPLICIT=1
DB_USER_EXPLICIT=""
[ -n "${ITVAULT_DB_USER:-}" ] && DB_USER_EXPLICIT=1
DB_CONTAINER="${ITVAULT_DB_NAME_CONTAINER:-itvault-db}"
# Tracks upstream by default. Safe for a fresh install, because the volume is
# created in the same breath as the container -- whatever "latest" is that day
# initialises it, and the two agree. What it cannot do is start a newer major
# against a data directory an older one wrote, so provision_db() checks for
# that before starting anything. Pin it (mariadb:12, mysql:8, ...) to opt out.
DB_IMAGE="${ITVAULT_DB_IMAGE:-mariadb:latest}"
# Declared here, not down beside provision_db: anything below the argument
# parsing would overwrite whatever --db-pass had just set.
DB_PASS_V="${ITVAULT_DB_PASS:-}"
DB_ROOT_PASS_V=""
DIR="${ITVAULT_DIR:-$HOME/it-vault}"
# Where this installer keeps what it decided, so a later run does not have
# to ask again. The database credentials used to live only in the app
# container's environment, so replacing that container lost them and the
# setup wizard asked for a database on an install that already had one.
# Written automatically; nobody has to create or edit it.
CONF_DIR="${ITVAULT_CONF_DIR:-}"
if [ -z "$CONF_DIR" ]; then
    if [ "$(id -u)" = "0" ]; then CONF_DIR="/etc/itvault"; else CONF_DIR="$HOME/.itvault"; fi
fi
CONF_FILE="$CONF_DIR/install.env"
DRY=""

while [ $# -gt 0 ]; do
    case "$1" in
        --port)    PORT="${2:?--port needs a value}"; shift 2 ;;
        --tag)     TAG="${2:?--tag needs a value}"; shift 2 ;;
        --name)    NAME="${2:?--name needs a value}"; shift 2 ;;
        --yes|-y)  YES=1; shift ;;
        --dry-run) DRY=1; shift ;;
        --no-docker) NO_DOCKER=1; shift ;;
        --with-db) WITH_DB=1; shift ;;
        --no-db)   WITH_DB=""; NO_DB=1; shift ;;
        --db-name) WITH_DB=1; DB_NAME_V="${2:?--db-name needs a value}"; DB_NAME_EXPLICIT=1; shift 2 ;;
        --db-user) WITH_DB=1; DB_USER_V="${2:?--db-user needs a value}"; DB_USER_EXPLICIT=1; shift 2 ;;
        --db-pass) WITH_DB=1; DB_PASS_V="${2:?--db-pass needs a value}"; shift 2 ;;
        --db-image) DB_IMAGE="${2:?--db-image needs a value}"; shift 2 ;;
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
banner_art() {
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
}

BANNER_SUB1='             IT Asset register + Helpdesk'
BANNER_SUB2='               powered by Sha The IT Guy'

# IT-Vault's accent is #ff3b30, so the banner is red rather than the green it
# used to be. The reveal ramps from a dark ember to that accent, which reads
# as the thing powering up instead of just appearing.
#
# Animation is a nicety, never a requirement. It is skipped entirely unless
# stdout is a terminal, the terminal is wide enough that the art cannot wrap
# (wrapping would break the cursor-up redraw), and `sleep` accepts fractions
# -- busybox builds often don't. Any of those failing gives the same banner,
# drawn once.
banner() {
    _cols=0
    if command -v tput >/dev/null 2>&1; then
        _cols="$(tput cols 2>/dev/null || echo 0)"
    fi
    if [ "${_cols:-0}" -lt 62 ] 2>/dev/null; then
        _sz="$(stty size 2>/dev/null || echo '')"
        [ -n "$_sz" ] && _cols="${_sz#* }"
    fi


    _anim=""
    if [ -t 1 ] && [ "${_cols:-0}" -ge 62 ] 2>/dev/null && sleep 0.02 2>/dev/null; then
        case "${TERM:-}" in
            *256color*|*-truecolor|alacritty|kitty|wezterm|foot|xterm*|screen*|tmux*) _anim=1 ;;
        esac
    fi

    if [ -z "$_anim" ]; then
        # Flat: colour if we're on a terminal at all, nothing if we're piped.
        if [ -t 1 ]; then printf '\n%s' "$(printf '\033[1;31m')"; else printf '\n'; fi
        banner_art
        [ -t 1 ] && printf '%s' "$N"
        printf '%s\n%s\n\n' "$BANNER_SUB1" "$BANNER_SUB2"
        return
    fi

    # dark ember -> the accent, one shade per line as it is revealed
    _ramp='88 124 160 196 203 203'
    printf '\n'
    _i=0
    banner_art | while IFS= read -r _line; do
        _i=$((_i + 1))
        _c=0; _n=0
        for _s in $_ramp; do
            _n=$((_n + 1))
            [ "$_n" -eq "$_i" ] && _c="$_s"
        done
        [ "$_c" -eq 0 ] && _c=203
        printf '\033[38;5;%sm%s\033[0m\n' "$_c" "$_line"
        sleep 0.03
    done

    # No second pass over the finished block. Redrawing it needed the cursor
    # moved back up over the art, which renders as one banner on screen but
    # leaves every frame behind in scrollback and in any captured log -- the
    # install output showed the banner three times. The reveal above is
    # animation enough and only ever writes each line once.

    printf '\033[2m%s\033[0m\n' "$BANNER_SUB1"
    sleep 0.04
    printf '\033[38;5;203m%s\033[0m\n\n' "$BANNER_SUB2"
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

# Where a prompt reads from. Piped through `sh` the script itself is on stdin,
# so reading a prompt from stdin would silently swallow the rest of the script.
# /dev/tty is the terminal in both cases; empty means there is no terminal at
# all (CI, a cron job), and every prompt then falls back to its default.
TTY=""
if [ -r /dev/tty ]; then TTY=/dev/tty; fi

# openssl if we have it, /dev/urandom otherwise -- no weak fallback.
gen_pass() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 20
    else
        LC_ALL=C tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 40
    fi
}

# Prompt for a value. The prompt goes to stderr and only the answer to stdout,
# so the caller can capture one without the other.
#
# The retry loop is wrapped in a single redirection rather than redirecting
# each `read`: one open descriptor advances through the input properly, and a
# capped number of tries means a /dev/tty that isn't really a terminal can't
# spin here forever.
ask_line() {
    _prompt="$1"; _default="${2:-}"; _val=""; _try=0
    if [ -z "$TTY" ] || [ -n "$YES" ]; then
        printf '%s' "$_default"
        return 0
    fi
    {
        while [ "$_try" -lt 6 ]; do
            _try=$((_try + 1))
            if [ -n "$_default" ]; then
                printf '  %s %s[%s]%s: ' "$_prompt" "$Y" "$_default" "$N" >&2
            else
                printf '  %s: ' "$_prompt" >&2
            fi
            read -r _val || _val=""
            [ -z "$_val" ] && _val="$_default"
            case "$_val" in
                "")
                    printf '     a value is needed\n' >&2 ;;
                *[!A-Za-z0-9_]*)
                    # MariaDB identifiers, and these end up in a docker -e
                    # value: keeping them boring avoids quoting surprises on
                    # either side.
                    printf '     letters, digits and underscores only\n' >&2 ;;
                *)
                    printf '%s' "$_val"; return 0 ;;
            esac
        done
        printf '     giving up and using %s\n' "${_default:-nothing}" >&2
        printf '%s' "$_default"
    } < "$TTY"
}

# Prompt for a password without echoing it, and ask again to catch typos.
# Entering nothing accepts the generated default, which is the sane choice.
ask_secret() {
    _prompt="$1"; _default="${2:-}"; _v=""; _v2=""; _saved=""; _try=0
    if [ -z "$TTY" ] || [ -n "$YES" ]; then
        printf '%s' "$_default"
        return 0
    fi
    {
        while [ "$_try" -lt 6 ]; do
            _try=$((_try + 1))
            printf '  %s %s[Enter = generate one]%s: ' "$_prompt" "$Y" "$N" >&2
            # stdin is the terminal inside this block, so stty needs no
            # redirection of its own -- and it is saved and restored rather
            # than assumed, so a failure can't leave echo switched off.
            _saved="$(stty -g 2>/dev/null || printf '')"
            [ -n "$_saved" ] && stty -echo 2>/dev/null || true
            read -r _v || _v=""
            [ -n "$_saved" ] && stty "$_saved" 2>/dev/null || true
            printf '\n' >&2
            if [ -z "$_v" ]; then
                printf '%s' "$_default"; return 0
            fi
            case "$_v" in
                *[!A-Za-z0-9_@%+=:,./-]*)
                    printf '     no spaces or quotes please -- letters, digits and _@%%+=:,./- are fine\n' >&2
                    continue ;;
            esac
            if [ "${#_v}" -lt 8 ]; then
                printf '     at least 8 characters\n' >&2
                continue
            fi
            printf '  confirm: ' >&2
            [ -n "$_saved" ] && stty -echo 2>/dev/null || true
            read -r _v2 || _v2=""
            [ -n "$_saved" ] && stty "$_saved" 2>/dev/null || true
            printf '\n' >&2
            if [ "$_v" != "$_v2" ]; then
                printf '     those did not match\n' >&2
                continue
            fi
            printf '%s' "$_v"; return 0
        done
        printf '     too many tries -- using a generated password\n' >&2
        printf '%s' "$_default"
    } < "$TTY"
}

# Asked before anything is pulled, because "install a database too" is what
# most people actually want and the manual route -- network, volume, CREATE
# USER, GRANT, and the 1045 that follows a missed step -- is where installs
# die. Declining is fine: the browser wizard then asks for a server you run.
db_prompt() {
    say ""
    say "${B}Database${N}"
    say "  IT-Vault needs MariaDB or MySQL. It can install one here as a container"
    say "  and wire itself up, or you can point it at a server you already run."
    ask "Install MariaDB here and connect IT-Vault to it?" || return 1
    say ""
    DB_NAME_V="$(ask_line 'Database name    ' "$DB_NAME_V")"
    DB_USER_V="$(ask_line 'Database username' "$DB_USER_V")"
    DB_PASS_V="$(ask_secret 'Database password' "$(gen_pass)")"
    say ""
    say "    database  ${B}${DB_NAME_V}${N}"
    say "    username  ${B}${DB_USER_V}${N}"
    say "    password  ${B}set${N}"
    return 0
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
        # Quoted where it matters: printing --health-cmd's value as bare
        # words made the dry run read as a different command from the real one.
        printf '    %s' "$DK"
        for _a in "$@"; do
            case "$_a" in
                *[!A-Za-z0-9_./:=-]*) printf " '%s'" "$_a" ;;
                *) printf ' %s' "$_a" ;;
            esac
        done
        printf '\n'
    else
        # shellcheck disable=SC2086  # $DK is deliberately two words sometimes
        $DK "$@" >/dev/null
    fi
}

# --with-db: stand up MariaDB and hand IT-Vault the connection, so there is no
# network to create, no user to GRANT, no volume to reason about and no setup
# wizard to fill in. Everything the manual route gets wrong is done here once.

# The MariaDB major version that last wrote the data directory. The server
# records it in the datadir itself, so reading it needs no database running --
# just a throwaway container with the volume mounted. Empty means the volume
# is new (or not a MariaDB datadir), which is the normal case.
_db_volume_version() {
    $DK run --rm -v itvault_db:/d --entrypoint sh "$DB_IMAGE" -c \
        'cat /d/mariadb_upgrade_info 2>/dev/null || cat /d/mysql_upgrade_info 2>/dev/null' \
        2>/dev/null | head -n 1 | tr -d '\r\n' | sed 's/-MariaDB$//'
}

# What the image we are about to run actually is, asked of the image rather
# than parsed out of its tag -- "latest" says nothing about the version.
_db_image_version() {
    $DK run --rm --entrypoint mariadbd "$DB_IMAGE" --version 2>/dev/null \
        | sed -n 's/.*Ver \([0-9][0-9.]*\).*/\1/p' | head -n 1
}

# A data directory written by one major and started by another is upgraded in
# place, one way, with no prompt -- or the server refuses and the container
# restart-loops. With DB_IMAGE following "latest" that can happen without
# anyone choosing it, so it is checked here instead of discovered afterwards.
#
# Only reachable when the volume already exists and holds data, which means an
# earlier install whose container was removed but whose volume was kept -- the
# exact thing this script's own "docker rm -f itvault-db" hint leaves behind.
_check_db_volume_major() {
    [ -n "$DRY" ] && return 0
    $DK volume inspect itvault_db >/dev/null 2>&1 || return 0
    have="$(_db_volume_version)"
    [ -n "$have" ] || return 0
    want="$(_db_image_version)"
    [ -n "$want" ] || return 0
    [ "${have%%.*}" = "${want%%.*}" ] && return 0
    say ""
    warn "The itvault_db volume holds MariaDB ${have} data, but $DB_IMAGE is ${want}."
    say  "    Starting a different major version against it rewrites the data"
    say  "    directory in place, and that cannot be undone."
    say  ""
    say  "    Keep the version that wrote it:"
    say  "      ${B}--db-image mariadb:${have%%.*}${N}"
    say  ""
    say  "    Or, if you do mean to upgrade, back the volume up first:"
    say  "      ${B}docker run --rm -v itvault_db:/d -v \$PWD:/b busybox tar czf /b/itvault_db.tgz -C /d .${N}"
    say  ""
    return 1
}

# Read back what a previous run decided. Only fills values that are still
# unset, so a flag or an environment variable on this run always wins.
load_conf() {
    [ -r "$CONF_FILE" ] || return 1
    # shellcheck disable=SC1090
    . "$CONF_FILE" 2>/dev/null || return 1
    [ -n "$DB_NAME_V" ]   || DB_NAME_V="${SAVED_DB_NAME:-$DB_NAME_V}"
    [ -n "$DB_USER_V" ]   || DB_USER_V="${SAVED_DB_USER:-$DB_USER_V}"
    [ -n "$DB_PASS_V" ]   || DB_PASS_V="${SAVED_DB_PASS:-}"
    [ -n "$SAVED_DB_HOST" ] && DB_HOST_SAVED="$SAVED_DB_HOST"
    return 0
}

# Record it. 600 on the file and 700 on the directory: it holds a database
# password, so it is readable only by whoever installed IT-Vault.
save_conf() {
    [ -n "$DRY" ] && return 0
    ( umask 077 && mkdir -p "$CONF_DIR" ) 2>/dev/null || return 1
    {   printf "# Written by the IT-Vault installer -- do not delete.\n"
        printf "# It is what lets an update keep this install's database.\n"
        printf "SAVED_DB_HOST=%s\n" "$1"
        printf "SAVED_DB_NAME=%s\n" "$2"
        printf "SAVED_DB_USER=%s\n" "$3"
        printf "SAVED_DB_PASS=%s\n" "$4"
    } > "$CONF_FILE" 2>/dev/null || return 1
    chmod 600 "$CONF_FILE" 2>/dev/null || true
    say "    configuration saved to ${B}$CONF_FILE${N} -- updates reuse it"
    return 0
}

# ---------------------------------------------------------------------------
# Volumes left behind by an older layout.
#
# `docker compose` prefixes volume names with its project directory, so running
# compose from /home/it/itvault creates itvault_invoices_data next to the
# invoices_data this installer uses. Both are real volumes holding real data,
# and a container mounted on the wrong one looks exactly like data loss: the
# rows are there, the files are not, and nothing says why.
#
# docker-compose.yml pins `name:` on every volume now, so the two can no longer
# diverge -- but that does nothing for an install where they already have. This
# finds the twin, and adopts it when the answer is unambiguous.
#
# The rule is deliberately narrow: copy ONLY when the volume we are about to
# mount is empty and its twin is not. Two volumes with data in both is a
# question about which is current, and guessing at that is how the wrong copy
# wins. In that case it says so and changes nothing.
# ---------------------------------------------------------------------------

# Number of files in a volume, or 0 if it does not exist / cannot be read.
# Uses the app image, which is already pulled by the time this runs, rather
# than pulling busybox just to count files.
_vol_files() {
    $DK run --rm -v "$1":/v "$IMAGE:$TAG" \
        sh -c 'find /v -type f 2>/dev/null | wc -l' 2>/dev/null \
        | tr -d " \r\n" || echo 0
}

# Any volume whose name ends in _<canonical>, which is what compose prefixing
# produces. itvault_invoices_data is the twin of invoices_data.
_vol_twins() {
    $DK volume ls --format '{{.Name}}' 2>/dev/null \
        | grep -E "_$1\$" | grep -v "^$1\$" || true
}

adopt_orphan_volumes() {
    _adopted=0
    for _v in itvault_data invoices_data backups_data itvault_db; do
        _mine="$(_vol_files "$_v")"
        case "$_mine" in ''|*[!0-9]*) _mine=0 ;; esac
        for _twin in $(_vol_twins "$_v"); do
            _theirs="$(_vol_files "$_twin")"
            case "$_theirs" in ''|*[!0-9]*) _theirs=0 ;; esac
            [ "$_theirs" -gt 0 ] || continue
            if [ "$_mine" -gt 0 ]; then
                say ""
                warn "Two volumes hold data for $_v:"
                say  "    ${B}$_v${N} ($_mine files) is the one IT-Vault will use"
                say  "    ${B}$_twin${N} ($_theirs files) was left by an older compose layout"
                say  "  Nothing was changed -- which one is current is your call. To look inside:"
                say  "    ${B}$DK run --rm -v $_twin:/v $IMAGE:$TAG ls -la /v${N}"
                continue
            fi
            step "Adopting $_twin into $_v ($_theirs files)"
            if [ -n "$DRY" ]; then
                printf '    docker run --rm -v %s:/from -v %s:/to %s sh -c "cp -an /from/. /to/"\n' \
                    "$_twin" "$_v" "$IMAGE:$TAG"
                continue
            fi
            # -n never overwrites, so this can only ever add files. The source
            # volume is left untouched: if this turns out to be the wrong
            # choice, nothing has been destroyed to undo.
            if $DK run --rm -v "$_twin":/from -v "$_v":/to "$IMAGE:$TAG" \
                    sh -c 'cp -an /from/. /to/ 2>/dev/null; exit 0' >/dev/null 2>&1; then
                _adopted=$((_adopted + 1))
                _mine="$(_vol_files "$_v")"
                say "    ${G}recovered${N} -- $_v now holds $_mine files"
            else
                warn "Could not copy $_twin into $_v; left both alone."
            fi
        done
    done
    if [ "$_adopted" -gt 0 ]; then
        say ""
        say "  ${G}$_adopted volume(s) recovered${N} from an older compose layout."
        say "  The originals were not deleted -- remove them yourself once you are happy:"
        say "    ${B}$DK volume ls${N}"
        say ""
    fi
}

# One value out of the database container's environment. That is where the
# credentials that created it still live, which is what makes adopting it
# possible at all.
_db_container_env() {
    $DK inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \
        "$DB_CONTAINER" 2>/dev/null | sed -n "s/^$1=//p" | head -n 1
}

# Replace the app container with the new image, reusing this install's own
# settings. Volumes are never touched, so assets, tickets, branding and the
# database all stay exactly where they are.
update_in_place() {
    step "Pulling $IMAGE:$TAG"
    if [ -n "$DRY" ]; then
        printf '    docker pull %s\n' "$IMAGE:$TAG"
    else
        # shellcheck disable=SC2086
        $DK pull "$IMAGE:$TAG" >/dev/null || die "Could not pull $IMAGE:$TAG."
    fi

    # Where the database is, in order of trust: what this installer saved,
    # then the database container's own environment, then whatever the old
    # app container was told.
    _u_host=""; _u_name=""; _u_user=""; _u_pass=""
    if load_conf; then
        _u_host="${DB_HOST_SAVED:-}"; _u_name="$DB_NAME_V"
        _u_user="$DB_USER_V"; _u_pass="$DB_PASS_V"
    fi
    if [ -z "$_u_pass" ] && $DK inspect "$DB_CONTAINER" >/dev/null 2>&1; then
        _u_host="$DB_CONTAINER"
        _u_name="$(_db_container_env MARIADB_DATABASE)"
        _u_user="$(_db_container_env MARIADB_USER)"
        _u_pass="$(_db_container_env MARIADB_PASSWORD)"
    fi
    if [ -z "$_u_pass" ]; then
        _u_host="$(_app_container_env DB_HOST)"
        _u_name="$(_app_container_env DB_NAME)"
        _u_user="$(_app_container_env DB_USER)"
        _u_pass="$(_app_container_env DB_PASS)"
    fi

    # Keep the network and published port the running container already has,
    # so an update never quietly moves the app somewhere else.
    _u_net="$($DK inspect -f "{{range \$k, \$v := .NetworkSettings.Networks}}{{\$k}} {{end}}" "$NAME" 2>/dev/null | awk "{print \$1}")"
    # println, not bare output: publishing -p 5000:5000 binds BOTH IPv4 and
    # IPv6, so this printed two host ports with nothing between them and the
    # update tried to publish 50005000 -- which docker rejects, after the old
    # container had already been removed.
    _u_port="$($DK inspect \
        -f "{{range \$p, \$c := .NetworkSettings.Ports}}{{range \$c}}{{println .HostPort}}{{end}}{{end}}" \
        "$NAME" 2>/dev/null | sed -n "1p")"
    case "$_u_port" in
        ''|*[!0-9]*) _u_port="" ;;
    esac
    if [ -n "$_u_port" ] && [ "$_u_port" -ge 1 ] && [ "$_u_port" -le 65535 ]; then
        PORT="$_u_port"
    fi
    # Everything the new container needs is settled BEFORE the old one is
    # removed. Working it out afterwards is how a bad value left this host
    # with no container at all.
    case "$PORT" in
        ''|*[!0-9]*) die "Could not work out which port to publish (got '$PORT'). Nothing was changed." ;;
    esac

    # Before the container is recreated: if an older compose layout left a
    # prefixed twin holding the real data, adopt it now, while the volume this
    # install mounts is still the empty one.
    adopt_orphan_volumes

    step "Replacing the container (volumes are kept)"
    run rm -f "$NAME"

    set -- run -d \
        --name "$NAME" \
        --restart unless-stopped \
        -p "$PORT:5000" \
        -v itvault_data:/app/data \
        -v invoices_data:/app/invoices \
        -v backups_data:/app/backups \
        -e ITVAULT_DATA_DIR=/app/data \
        --add-host host.docker.internal:host-gateway
    if [ -n "$_u_net" ] && [ "$_u_net" != "bridge" ]; then
        set -- "$@" --network "$_u_net"
    fi
    if [ -n "$_u_host" ]; then
        set -- "$@" -e DB_HOST="$_u_host" -e DB_PORT=3306 \
            -e DB_NAME="$_u_name" -e DB_USER="$_u_user" -e DB_PASS="$_u_pass"
    fi
    if ! run "$@" "$IMAGE:$TAG"; then
        say ""
        warn "The new container did not start, and the old one is already gone."
        say "    Your data is untouched -- it is all in the volumes. Bring it back with:"
        say "      ${B}curl -sSL https://raw.githubusercontent.com/shatheitguy/it-vault/main/install.sh | sh${N}"
        say ""
        return 1
    fi

    if [ -n "$_u_host" ]; then
        save_conf "$_u_host" "$_u_name" "$_u_user" "$_u_pass" >/dev/null 2>&1 || true
    fi
    [ -n "$DRY" ] && return 0
    say ""
    say "${G}Updated.${N} Open http://localhost:$PORT"
    say "  Your database, assets, tickets and branding were not touched."
    say ""
}

# One value out of the APP container's environment -- the last resort when
# working out where an existing install's database is.
_app_container_env() {
    $DK inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \
        "$NAME" 2>/dev/null | sed -n "s/^$1=//p" | head -n 1
}

provision_db() {
    # A shared user-defined network is what makes container-name DNS work, so
    # the app can reach the database as "itvault-db" without publishing 3306
    # to the LAN at all.
    if ! $DK network inspect "$NET" >/dev/null 2>&1; then
        step "Creating network '$NET'"
        run network create "$NET"
    else
        say "    network '$NET' already exists -- reusing it"
    fi

    # An existing database container is ADOPTED, not refused. Its
    # credentials are readable from its own environment for as long as it
    # exists -- MARIADB_USER/PASSWORD/DATABASE are what created it. This
    # used to give up here and send people to the setup wizard, which is how
    # `docker rm -f itvault` + re-running this script lost a working
    # database pointer on an install that already had one.
    if $DK inspect "$DB_CONTAINER" >/dev/null 2>&1; then
        _adopt_user="$(_db_container_env MARIADB_USER)"
        _adopt_pass="$(_db_container_env MARIADB_PASSWORD)"
        _adopt_name="$(_db_container_env MARIADB_DATABASE)"
        if [ -n "$_adopt_user" ] && [ -n "$_adopt_pass" ] && [ -n "$_adopt_name" ]; then
            step "Adopting the existing database container '$DB_CONTAINER'"
            DB_USER_V="$_adopt_user"
            DB_PASS_V="$_adopt_pass"
            DB_NAME_V="$_adopt_name"
            # it must be running, and on the network the app will join
            if [ "$($DK inspect -f "{{.State.Running}}" "$DB_CONTAINER" 2>/dev/null)" != "true" ]; then
                run start "$DB_CONTAINER"
            fi
            if ! $DK inspect -f "{{range \$k, \$v := .NetworkSettings.Networks}}{{\$k}} {{end}}" \
                    "$DB_CONTAINER" 2>/dev/null | grep -q "$NET"; then
                run network connect "$NET" "$DB_CONTAINER"
            fi
            say "    reusing database '$DB_NAME_V' as user '$DB_USER_V'"
            return 0
        fi
        # No MARIADB_* in its environment: not one of ours, so do not guess.
        say ""
        warn "A container named '$DB_CONTAINER' already exists, and its password is not in its environment."
        say "    Point IT-Vault at it through the setup wizard, or remove it first:"
        say "      ${B}docker rm -f $DB_CONTAINER${N}   ${Y}# keeps the itvault_db volume${N}"
        say ""
        return 1
    fi

    # Whatever was entered at the prompt (or passed with --db-pass) is kept;
    # only an unattended run generates one.
    [ -n "$DB_PASS_V" ] || DB_PASS_V="$(gen_pass)"
    [ -n "$DB_PASS_V" ] || die "Could not generate a database password."
    # root gets its own password, never the application user's -- the app only
    # ever needs its own database, so handing it root's credentials would be
    # giving away far more than it uses.
    DB_ROOT_PASS_V="$(gen_pass)"
    [ -n "$DB_ROOT_PASS_V" ] || die "Could not generate a database root password."

    _check_db_volume_major || return 1

    step "Creating volume itvault_db"
    run volume create itvault_db

    step "Starting MariaDB as '$DB_CONTAINER' (not published to the network)"
    run run -d \
        --name "$DB_CONTAINER" \
        --network "$NET" \
        --restart unless-stopped \
        -e MARIADB_ROOT_PASSWORD="$DB_ROOT_PASS_V" \
        -e MARIADB_DATABASE="$DB_NAME_V" \
        -e MARIADB_USER="$DB_USER_V" \
        -e MARIADB_PASSWORD="$DB_PASS_V" \
        -v itvault_db:/var/lib/mysql \
        --health-cmd "healthcheck.sh --connect --innodb_initialized" \
        --health-interval 5s --health-timeout 5s --health-retries 20 \
        "$DB_IMAGE"

    [ -n "$DRY" ] && return 0

    # MariaDB runs a temporary server on no port at all while it initialises,
    # so connecting during that window is refused. Waiting here is what turns
    # the usual "Errno 111" race into a non-event.
    step "Waiting for MariaDB to finish initialising"
    i=0
    while [ "$i" -lt 60 ]; do
        h="$($DK inspect -f '{{.State.Health.Status}}' "$DB_CONTAINER" 2>/dev/null || echo starting)"
        [ "$h" = "healthy" ] && break
        i=$((i + 1)); sleep 2
        [ $((i % 5)) -eq 0 ] && say "    still initialising (${i}0s)..."
    done
    if [ "$h" != "healthy" ]; then
        warn "MariaDB hasn't reported healthy yet. IT-Vault waits for it on start, so this"
        say  "    usually still works -- check: ${B}docker logs $DB_CONTAINER${N}"
    else
        say "    database ready"
    fi
    return 0
}

# Same concept as provision_db(), for a host that has no Docker at all: install
# MariaDB with whatever package manager is on hand, start it, and create the
# database and user IT-Vault will use -- so a --no-docker install lands
# connected too, with nothing for the setup wizard to ask.
_native_sql_root() {
    # $1 = the SQL. Runs it against the freshly-installed server as root,
    # via the unix socket (no password set yet on a fresh install), with
    # sudo only when this process is not already root.
    if [ "$(id -u)" = "0" ]; then
        "$MYSQL_BIN" -uroot -e "$1" 2>/dev/null
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$MYSQL_BIN" -uroot -e "$1" 2>/dev/null
    else
        "$MYSQL_BIN" -uroot -e "$1" 2>/dev/null
    fi
}

provision_db_native() {
    MYSQL_BIN=""
    os="$(uname -s)"
    case "$os" in
        Linux)
            _sudo=""
            [ "$(id -u)" = "0" ] || _sudo="sudo"
            if [ -n "$_sudo" ] && ! command -v sudo >/dev/null 2>&1; then
                warn "Not root, and sudo isn't available -- can't install MariaDB automatically."
                return 1
            fi
            if command -v mariadb >/dev/null 2>&1 || command -v mysql >/dev/null 2>&1; then
                say "    MariaDB/MySQL client already on this host -- reusing it"
            elif command -v apt-get >/dev/null 2>&1; then
                step "Installing MariaDB (apt-get)"
                $_sudo apt-get update -qq && $_sudo apt-get install -y -qq mariadb-server \
                    || { warn "apt-get install mariadb-server failed."; return 1; }
            elif command -v dnf >/dev/null 2>&1; then
                step "Installing MariaDB (dnf)"
                $_sudo dnf install -y -q mariadb-server \
                    || { warn "dnf install mariadb-server failed."; return 1; }
            elif command -v yum >/dev/null 2>&1; then
                step "Installing MariaDB (yum)"
                $_sudo yum install -y -q mariadb-server \
                    || { warn "yum install mariadb-server failed."; return 1; }
            elif command -v pacman >/dev/null 2>&1; then
                step "Installing MariaDB (pacman)"
                $_sudo pacman -S --noconfirm --needed mariadb \
                    || { warn "pacman -S mariadb failed."; return 1; }
                # Arch ships an empty data directory -- first-run init is on us.
                if [ ! -d /var/lib/mysql/mysql ]; then
                    $_sudo mariadb-install-db --user=mysql --basedir=/usr --datadir=/var/lib/mysql >/dev/null 2>&1
                fi
            else
                warn "No supported package manager found (apt-get/dnf/yum/pacman) --"
                warn "can't install MariaDB automatically."
                return 1
            fi
            step "Starting MariaDB"
            if command -v systemctl >/dev/null 2>&1; then
                $_sudo systemctl enable --now mariadb >/dev/null 2>&1 \
                    || $_sudo systemctl enable --now mysql >/dev/null 2>&1 \
                    || $_sudo systemctl enable --now mysqld >/dev/null 2>&1
            elif command -v service >/dev/null 2>&1; then
                $_sudo service mariadb start >/dev/null 2>&1 || $_sudo service mysql start >/dev/null 2>&1
            fi
            MYSQL_BIN="$(command -v mariadb || command -v mysql)"
            ;;
        Darwin)
            if command -v mariadb >/dev/null 2>&1 || command -v mysql >/dev/null 2>&1; then
                say "    MariaDB/MySQL client already on this host -- reusing it"
            elif command -v brew >/dev/null 2>&1; then
                step "Installing MariaDB (brew)"
                brew install mariadb >/dev/null 2>&1 || { warn "brew install mariadb failed."; return 1; }
            else
                warn "Homebrew isn't installed -- can't install MariaDB automatically on macOS."
                warn "Install it from https://brew.sh, or install MariaDB yourself."
                return 1
            fi
            step "Starting MariaDB"
            brew services start mariadb >/dev/null 2>&1
            MYSQL_BIN="$(command -v mariadb || command -v mysql)"
            ;;
        *)
            warn "Don't know how to install MariaDB natively on $os."
            return 1
            ;;
    esac
    [ -n "$MYSQL_BIN" ] || { warn "MariaDB client not found after install."; return 1; }

    # The server takes a moment to start accepting connections after the
    # service manager reports it launched.
    i=0
    while [ "$i" -lt 30 ]; do
        _native_sql_root "SELECT 1" >/dev/null 2>&1 && break
        i=$((i + 1)); sleep 1
    done
    if [ "$i" -ge 30 ]; then
        warn "MariaDB didn't come up in time -- see the manual steps below."
        return 1
    fi

    [ -n "$DB_PASS_V" ] || DB_PASS_V="$(gen_pass)"
    step "Creating database '$DB_NAME_V' and user '$DB_USER_V'"
    _native_sql_root "
CREATE DATABASE IF NOT EXISTS \`$DB_NAME_V\`;
CREATE USER IF NOT EXISTS '$DB_USER_V'@'localhost' IDENTIFIED BY '$DB_PASS_V';
GRANT ALL PRIVILEGES ON \`$DB_NAME_V\`.* TO '$DB_USER_V'@'localhost';
FLUSH PRIVILEGES;" || { warn "Could not create the database automatically."; return 1; }

    DB_HOST_V="127.0.0.1"
    say "    database ready: $DB_NAME_V (user $DB_USER_V)"
    return 0
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

    # Same concept as the Docker path: offer to install and wire up the
    # database here too, so a --no-docker install doesn't dead-end at the
    # browser's setup wizard either. This is called from install_native's own
    # entry points (offer_native_or_die, --no-docker) which return before the
    # main flow's own WITH_DB decision ever runs, so it is made again here.
    load_conf && [ -n "$DB_PASS_V" ] && WITH_DB=1
    # load_conf() only backfills DB_NAME_V/DB_USER_V when they are empty, and
    # both already carry the "itvault" default by this point -- so restore
    # the saved name/user explicitly here, unless this run chose its own.
    [ -n "$DB_NAME_EXPLICIT" ] || [ -z "${SAVED_DB_NAME:-}" ] || DB_NAME_V="$SAVED_DB_NAME"
    [ -n "$DB_USER_EXPLICIT" ] || [ -z "${SAVED_DB_USER:-}" ] || DB_USER_V="$SAVED_DB_USER"
    if [ -z "$WITH_DB" ] && [ -z "$NO_DB" ]; then
        if db_prompt; then WITH_DB=1; fi
    fi

    DB_READY=""
    if [ -n "$WITH_DB" ]; then
        if provision_db_native; then
            DB_READY=1
            save_conf "$DB_HOST_V" "$DB_NAME_V" "$DB_USER_V" "$DB_PASS_V"
        else
            warn "Couldn't provision a database automatically -- falling back to the manual steps below."
        fi
    fi

    if [ -n "$DB_READY" ]; then
        # A start script beats telling people to re-type four exports every
        # time: this is what "no setup wizard to fill in" means on the host
        # install too.
        cat > "$DIR/start.sh" <<STARTSH
#!/bin/sh
# Written by the IT-Vault installer. Starts IT-Vault with the database
# provisioned during install -- edit the DB_* lines if that ever changes.
export DB_HOST="$DB_HOST_V"
export DB_NAME="$DB_NAME_V"
export DB_USER="$DB_USER_V"
export DB_PASS="$DB_PASS_V"
export ITVAULT_PORT="$PORT"
cd "$DIR"
exec .venv/bin/python serve.py
STARTSH
        chmod +x "$DIR/start.sh"

        say ""
        say "${G}IT-Vault is installed at${N} ${B}$DIR${N} ${G}and connected to its own MariaDB${N} --"
        say "${G}no setup wizard to fill in.${N}"
        say ""
        say "Start it:"
        say "  ${B}$DIR/start.sh${N}"
        say ""
        say "Then open ${B}http://localhost:$PORT${N} and sign in with the admin account you set up."
        say ""
    else
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
    fi
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
            say "  See its logs:  $DK logs -f $NAME"
            say ""
            # Offer to do the update here rather than printing steps for
            # someone to carry out. The credentials come from the saved
            # configuration (or the database container itself), so
            # recreating the app container cannot lose the connection.
            if ask "Update IT-Vault to the latest image now?"; then
                update_in_place
                exit 0
            fi
            say ""
            say "  Nothing changed. To update later, run this installer again"
            say "  and answer yes, or use:  Settings ▸ General ▸ Check for Updates"
            say ""
            # Someone who installed without a database and now wants one is
            # otherwise stuck: this installer won't recreate a container that
            # owns their volumes, so point at the two steps that do the job.
            if ! $DK network inspect "$NET" >/dev/null 2>&1; then
                say "  To add a database to this install:"
                say "    ${B}$DK rm -f $NAME${N}   ${Y}# volumes are kept${N}"
                say "    then run this installer again and say yes to MariaDB"
                say ""
            else
                say "  MariaDB is already on the '$NET' network. If IT-Vault can't see it:"
                say "    ${B}$DK network connect $NET $NAME${N}"
                say "    then point Settings ▸ Database at host ${B}$DB_CONTAINER${N}"
                say ""
            fi
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

# Asked here rather than after the pull, so the install is not waiting on a
# download before it knows what it is building.
# Anything a previous run saved comes back first, so an install that is
# being repaired or re-run never has to be told its own database again.
if load_conf; then
    say "    reusing the saved configuration from $CONF_FILE"
    [ -n "$DB_PASS_V" ] && WITH_DB=1
fi

# An install that already has our database container is reconnected to it
# rather than asked about it: this is the update path, and the whole point
# is that it keeps the database it already had.
if [ -z "$WITH_DB" ] && [ -z "$NO_DB" ] \
        && $DK inspect "$DB_CONTAINER" >/dev/null 2>&1 \
        && [ -n "$(_db_container_env MARIADB_USER)" ]; then
    say "    found the existing database container -- reconnecting to it"
    WITH_DB=1
fi
if [ -z "$WITH_DB" ] && [ -z "$NO_DB" ]; then
    if db_prompt; then WITH_DB=1; fi
fi

step "Pulling $IMAGE:$TAG"
if [ -n "$DRY" ]; then
    printf '    docker pull %s\n' "$IMAGE:$TAG"
else
    # shellcheck disable=SC2086
    $DK pull "$IMAGE:$TAG" >/dev/null || die \
"Could not pull $IMAGE:$TAG. Check the tag exists and that you can reach
    ghcr.io."
fi

DB_ENV=""
NET_ARG=""
if [ -n "$WITH_DB" ]; then
    if provision_db; then
        DB_ENV=1
        NET_ARG="$NET"
    fi
fi

step "Creating volumes (itvault_data, invoices_data, backups_data)"
run volume create itvault_data
run volume create invoices_data
run volume create backups_data

# Installing over a host that has run compose from a directory called
# something else: the data is in prefixed volumes and this would otherwise
# come up empty and look like a fresh install.
adopt_orphan_volumes

step "Starting container '$NAME' on port $PORT"
# --add-host is what lets DB_HOST=host.docker.internal reach a database
# installed on this machine rather than inside the container. Docker Desktop
# provides it already; on Linux it has to be asked for.
# Assembled rather than inlined, so --with-db can add the network and the
# connection without a second near-identical docker run to keep in step.
set -- run -d \
    --name "$NAME" \
    --restart unless-stopped \
    -p "$PORT:5000" \
    -v itvault_data:/app/data \
    -v invoices_data:/app/invoices \
    -v backups_data:/app/backups \
    -e ITVAULT_DATA_DIR=/app/data \
    --add-host host.docker.internal:host-gateway
if [ -n "$NET_ARG" ]; then
    set -- "$@" --network "$NET_ARG"
fi
if [ -n "$DB_ENV" ]; then
    set -- "$@" \
        -e DB_HOST="$DB_CONTAINER" -e DB_PORT=3306 \
        -e DB_NAME="$DB_NAME_V" -e DB_USER="$DB_USER_V" -e DB_PASS="$DB_PASS_V"
fi
run "$@" "$IMAGE:$TAG"

# Record where the database is before anything else can go wrong. This is
# what makes the next update a no-op for the person running it.
if [ -n "$DB_ENV" ]; then
    save_conf "$DB_CONTAINER" "$DB_NAME_V" "$DB_USER_V" "$DB_PASS_V" || \
        warn "Could not write $CONF_FILE -- an update will fall back to reading the containers."
fi

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
# Only for an install that has NO database. Printing "you still need a
# database" right after provisioning one -- with instructions to go and
# create it -- is worse than saying nothing, and that is what it did.
if [ -n "$DB_ENV" ]; then
    say "${G}MariaDB is set up and connected.${N} No setup wizard to fill in --"
    say "open it and create your admin account."
    say ""
    say "    database   ${B}$DB_NAME_V${N} on container ${B}$DB_CONTAINER${N} (network $NET)"
    say "    username   ${B}$DB_USER_V${N}"
    say ""
    say "  Change it later in Settings ▸ Database. The credentials are in the"
    say "  container's environment:  ${B}$DK inspect $NAME${N}"
else
    say "${B}You still need a database.${N} IT-Vault doesn't ship one -- point it at any"
    say "MariaDB 10.6+ or MySQL 8+ and it builds its own schema. Don't have one yet?"
    say ""
    say "  Re-run this installer and say yes when it offers to install MariaDB,"
    say "  and it does all of the below for you. By hand:"
    say ""
    say "    docker network create itvault-net"
    say "    docker volume create itvault_db"
    say "    docker run -d --name itvault-db --restart unless-stopped \\"
    say "      --network itvault-net \\"
    say "      -e MARIADB_ROOT_PASSWORD='<a-strong-root-password>' \\"
    say "      -e MARIADB_DATABASE=itvault \\"
    say "      -e MARIADB_USER=itvault -e MARIADB_PASSWORD='<a-strong-password>' \\"
    say "      -v itvault_db:/var/lib/mysql $DB_IMAGE"
    say "    docker network connect itvault-net $NAME"
    say ""
    say "Then the setup wizard in your browser asks for the connection (host"
    say "${B}itvault-db${N} for the above, or ${B}host.docker.internal${N} for a database installed"
    say "on this machine) and for the admin account you want to create."
fi
say ""
say "  Logs:       $DK logs -f $NAME"
say "  Stop:       $DK stop $NAME"
say "  Uninstall:  $DK rm -f $NAME     (volumes, and your database, are kept)"
say ""
