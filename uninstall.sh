#!/bin/sh
# IT-Vault uninstaller.
#
#   curl -fsSL https://raw.githubusercontent.com/shatheitguy/it-vault/main/uninstall.sh | sh
#
# Removes the IT-Vault container and image. Your data is NOT touched unless you
# ask for it: the volumes (uploaded invoices, generated backups, the session
# key) and your database are left alone by default.
#
# Flags:
#   --purge      also delete the IT-Vault volumes -- permanent data loss
#   --purge-db   also delete the itvault-db container and its volume, if you
#                created one from this project's suggested command
#   --yes        don't ask
#   --dry-run    print the plan, change nothing
set -eu

IMAGE="ghcr.io/shatheitguy/it-vault"
NAME="${ITVAULT_NAME:-itvault}"
PURGE=""
PURGE_DB=""
YES="${ITVAULT_YES:-}"
DRY=""

while [ $# -gt 0 ]; do
    case "$1" in
        --name)      NAME="${2:?--name needs a value}"; shift 2 ;;
        --purge)     PURGE=1; shift ;;
        --purge-db)  PURGE_DB=1; shift ;;
        --yes|-y)    YES=1; shift ;;
        --dry-run)   DRY=1; shift ;;
        -h|--help)
            awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0" \
                2>/dev/null || echo "See https://github.com/shatheitguy/it-vault"
            exit 0 ;;
        *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
    esac
done

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
kept() { printf '   %s·%s %s\n' "$G" "$N" "$*"; }

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
    case "$ans" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

DK="docker"
command -v docker >/dev/null 2>&1 || die "Docker isn't installed, so there's nothing here to remove."
if ! docker info >/dev/null 2>&1; then
    if command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
        DK="sudo docker"
    else
        die "Docker isn't running (or your user can't reach it), so nothing can be removed yet."
    fi
fi

run() {
    if [ -n "$DRY" ]; then
        printf '    %s %s\n' "$DK" "$*"
    else
        # shellcheck disable=SC2086
        $DK "$@" >/dev/null 2>&1 || true
    fi
}

# ---- what is actually here -------------------------------------------

# shellcheck disable=SC2086
HAS_CONTAINER=$($DK container inspect "$NAME" >/dev/null 2>&1 && echo 1 || echo "")
# shellcheck disable=SC2086
HAS_IMAGE=$($DK image inspect "$IMAGE:latest" >/dev/null 2>&1 && echo 1 || echo "")
# shellcheck disable=SC2086
IMAGES=$($DK images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep "^$IMAGE:" || true)
# shellcheck disable=SC2086
VOLUMES=$($DK volume ls --format '{{.Name}}' 2>/dev/null \
    | grep -E '^(itvault_data|invoices_data|backups_data)$' || true)

say ""
say "${B}About to remove:${N}"
[ -n "$HAS_CONTAINER" ] && say "   container  $NAME" || say "   container  $NAME ${Y}(not found)${N}"
if [ -n "$IMAGES" ]; then
    say "$IMAGES" | sed 's/^/   image      /'
else
    say "   image      $IMAGE ${Y}(not found)${N}"
fi
say ""

if [ -n "$PURGE" ]; then
    say "${R}${B}And permanently deleting these volumes:${N}"
    if [ -n "$VOLUMES" ]; then
        say "$VOLUMES" | sed 's/^/   volume     /'
        say ""
        say "   ${R}That is your uploaded invoices, generated backups and the"
        say "   session key. It cannot be undone.${N}"
    else
        say "   ${Y}(none found)${N}"
    fi
    say ""
fi

if [ -n "$PURGE_DB" ]; then
    say "${R}${B}And the database container from this project's suggested setup:${N}"
    say "   container  itvault-db"
    say "   volume     itvault_db  ${R}<- your entire IT-Vault database${N}"
    say ""
fi

ask "Go ahead?" || die "Nothing was removed."

# ---- remove ----------------------------------------------------------

if [ -n "$HAS_CONTAINER" ] || [ -n "$DRY" ]; then
    step "Removing container '$NAME'"
    run rm -f "$NAME"
fi

if [ -n "$IMAGES" ] || [ -n "$DRY" ]; then
    step "Removing image$([ -n "$IMAGES" ] && echo "s")"
    if [ -n "$DRY" ] && [ -z "$IMAGES" ]; then
        printf '    %s image rm %s:latest\n' "$DK" "$IMAGE"
    else
        for tag in $IMAGES; do
            run image rm "$tag"
        done
    fi
fi

if [ -n "$PURGE" ]; then
    if [ -n "$VOLUMES" ] || [ -n "$DRY" ]; then
        step "Deleting volumes"
        if [ -n "$DRY" ] && [ -z "$VOLUMES" ]; then
            printf '    %s volume rm itvault_data invoices_data backups_data\n' "$DK"
        else
            for v in $VOLUMES; do
                run volume rm "$v"
            done
        fi
    fi
fi

if [ -n "$PURGE_DB" ]; then
    step "Removing the itvault-db container and its volume"
    run rm -f itvault-db
    run volume rm itvault_db
fi

# The network only exists if it was created following this project's docs, and
# removing it is safe once nothing is attached -- docker refuses otherwise.
# shellcheck disable=SC2086
if $DK network inspect itvault-net >/dev/null 2>&1 || [ -n "$DRY" ]; then
    step "Removing the itvault-net network if nothing else uses it"
    run network rm itvault-net
fi

if [ -n "$DRY" ]; then
    say ""
    say "(dry run -- nothing was changed)"
    exit 0
fi

# ---- what survived ---------------------------------------------------

say ""
say "${G}IT-Vault removed.${N}"
say ""
say "${B}Deliberately left alone:${N}"
if [ -z "$PURGE" ]; then
    kept "Volumes itvault_data, invoices_data, backups_data -- your invoices,"
    say  "     backups and session key. Reinstalling picks them straight back up."
    say  "     Delete them with:  $DK volume rm itvault_data invoices_data backups_data"
fi
if [ -z "$PURGE_DB" ]; then
    kept "Your database. IT-Vault never owned it, so it isn't ours to drop."
    say  "     Drop the schema yourself if you're done with it:"
    say  "       DROP DATABASE itvault;"
fi
kept "Docker itself, and any other containers or images you run."
say  "     Remove Docker through your package manager or Docker Desktop's"
say  "     own uninstaller if you no longer want it."
say ""
