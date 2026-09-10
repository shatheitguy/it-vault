#!/bin/sh
# Exercise install.sh's config-file and update paths against a fake docker.
#
# There is no Docker on the machine this was written on, and shipping an
# untested installer is what caused the damage this change is meant to
# prevent. So docker is stubbed: it answers like a host that already runs
# IT-Vault against itvault-db, and every call is logged so the commands the
# installer would really run can be asserted on.
set -e
WORK="${TMPDIR:-/tmp}/itv-installer-test"
rm -rf "$WORK"; mkdir -p "$WORK/bin"
LOG="$WORK/docker.log"
: > "$LOG"

cat > "$WORK/bin/docker" <<'FAKE'
#!/bin/sh
echo "$@" >> "$LOG"
case "$1" in
  info|version) exit 0 ;;
  pull) exit 0 ;;
  rm|run|start|network) exit 0 ;;
  inspect)
    # inspect <name>            -> exists?
    # inspect --format <f> <n>  -> a value
    if [ "$2" = "--format" ] || [ "$2" = "-f" ]; then
      fmt="$3"; target="$4"
      case "$fmt" in
        *Config.Env*)
          case "$target" in
            itvault-db) printf 'MARIADB_USER=itvault\nMARIADB_PASSWORD=from-db-container\nMARIADB_DATABASE=itvault\n' ;;
            itvault)    printf 'DB_HOST=itvault-db\nDB_USER=itvault\nDB_PASS=from-app-container\nDB_NAME=itvault\n' ;;
          esac ;;
        *State.Status*)   echo running ;;
        *State.Running*)  echo true ;;
        *NetworkSettings.Networks*) echo "itvault-net " ;;
        *NetworkSettings.Ports*)
          # real docker: one entry for 0.0.0.0 and one for :: -- two host
          # ports. Concatenated, -p 5000:5000 became "50005000" (which docker
          # rejects) and -p 80:5000 becomes "8080" (which it accepts, silently
          # moving the app to the wrong port).
          sp="${STUB_PORT:-5000}"
          case "$fmt" in
            *println*) printf '%s
%s
' "$sp" "$sp" ;;
            *)         printf '%s%s' "$sp" "$sp" ;;
          esac ;;
        *) echo "" ;;
      esac
      exit 0
    fi
    case "$2" in
      itvault|itvault-db|itvault-net) exit 0 ;;
      *) exit 1 ;;
    esac ;;
  container)
    case "$2" in
      inspect)
        if [ "$3" = "-f" ]; then echo running; exit 0; fi
        case "$3" in itvault) exit 0 ;; *) exit 1 ;; esac ;;
    esac ;;
  volume) exit 0 ;;
esac
exit 0
FAKE
sed -i "s|\$LOG|$LOG|" "$WORK/bin/docker"
chmod +x "$WORK/bin/docker"

CONF="$WORK/conf"
fails=0
check() {
  if [ "$2" = "1" ]; then printf '  PASS  %s\n' "$1"
  else printf '  FAIL  %s   %s\n' "$1" "$3"; fails=$((fails+1)); fi
}

echo "1. An existing install offers to update itself, and does it in place"
: > "$LOG"
PATH="$WORK/bin:$PATH" ITVAULT_CONF_DIR="$CONF" ITVAULT_YES=1 \
  sh "$(dirname "$0")/../install.sh" > "$WORK/out1.txt" 2>&1 || true

grep -q 'Pulling' "$WORK/out1.txt" && check "it pulls the new image" 1 || check "it pulls the new image" 0 "$(tail -3 "$WORK/out1.txt")"
grep -q 'rm -f itvault' "$LOG" && check "it replaces the app container" 1 || check "it replaces the app container" 0
grep -q 'Updated' "$WORK/out1.txt" && check "it reports an update, not an install" 1 || check "it reports an update, not an install" 0

# the recreate must carry the database, or the wizard comes back
if grep 'run -d' "$LOG" | grep -q 'DB_PASS=from-db-container'; then
  check "credentials are carried over to the new container" 1
else
  check "credentials are carried over to the new container" 0 "$(grep 'run -d' "$LOG" | head -1)"
fi
grep 'run -d' "$LOG" | grep -q 'ITVAULT_DATA_DIR=/app/data' \
  && check "the data volume is still pointed at" 1 || check "the data volume is still pointed at" 0
grep 'run -d' "$LOG" | grep -q 'itvault_data:/app/data' \
  && check "volumes are reused, not recreated" 1 || check "volumes are reused, not recreated" 0
grep 'run -d' "$LOG" | grep -q -- '--network itvault-net' \
  && check "it stays on the same network" 1 || check "it stays on the same network" 0
# A container published with -p 5000:5000 binds IPv4 AND IPv6, so inspecting
# its ports yields TWO host ports. Concatenated they became "50005000", which
# docker rejects -- after the old container had already been removed, leaving
# the host with nothing running.
published="$(grep 'run -d' "$LOG" | grep -oE -- '-p [0-9]+:[0-9]+' | head -1)"
case "$published" in
  '-p 5000:5000') check "it republishes the one port it had" 1 ;;
  *)              check "it republishes the one port it had" 0 "got '$published'" ;;
esac

# The case validation alone cannot catch: two 2-digit ports concatenate into a
# perfectly valid 4-digit one, so the app moves ports without a word.
: > "$LOG"
STUB_PORT=80 PATH="$WORK/bin:$PATH" ITVAULT_CONF_DIR="$CONF" ITVAULT_YES=1   sh "$(dirname "$0")/../install.sh" > "$WORK/out80.txt" 2>&1 || true
p80="$(grep 'run -d' "$LOG" | grep -oE -- '-p [0-9]+:[0-9]+' | head -1)"
case "$p80" in
  '-p 80:5000') check "a 2-digit port is not doubled into 8080" 1 ;;
  *)            check "a 2-digit port is not doubled into 8080" 0 "got '$p80'" ;;
esac
! grep -q 'volume rm\|volume prune' "$LOG" \
  && check "no volume is ever removed" 1 || check "no volume is ever removed" 0

echo
echo "2. It writes the configuration file, so the NEXT run needs nothing"
if [ -f "$CONF/install.env" ]; then
  check "install.env written" 1
  # This filesystem cannot represent POSIX modes (chmod 600 on /tmp reads
  # back 644 here), so assert the installer asks for 600 rather than the
  # mode it ended up with.
  grep -q 'chmod 600 "$CONF_FILE"' "$(dirname "$0")/../install.sh"     && check "the installer locks it to its owner (chmod 600)" 1     || check "the installer locks it to its owner (chmod 600)" 0
  grep -q 'SAVED_DB_PASS=from-db-container' "$CONF/install.env" \
    && check "it holds the database password" 1 || check "it holds the database password" 0 "$(cat "$CONF/install.env")"
  grep -q 'SAVED_DB_HOST=itvault-db' "$CONF/install.env" \
    && check "and where the database is" 1 || check "and where the database is" 0
else
  check "install.env written" 0 "not created"
fi

echo
echo "3. A second run reuses it instead of asking anything"
: > "$LOG"
PATH="$WORK/bin:$PATH" ITVAULT_CONF_DIR="$CONF" ITVAULT_YES=1 \
  sh "$(dirname "$0")/../install.sh" > "$WORK/out2.txt" 2>&1 || true
# The second run takes the update path, which reads the config file itself,
# so assert on what actually reached docker rather than on a message printed
# only by the install path.
if grep 'run -d' "$LOG" | grep -q 'DB_PASS=from-db-container'; then
  check "the saved configuration is used on the second run" 1
else
  check "the saved configuration is used on the second run" 0 "$(grep 'run -d' "$LOG" | head -1)"
fi
! grep -qi 'Install MariaDB here' "$WORK/out2.txt" \
  && check "it does not ask about a database again" 1 || check "it does not ask about a database again" 0

echo
echo "4. Nothing destructive anywhere in either run"
if grep -qE 'volume rm|volume prune|rm -f itvault-db|system prune' "$LOG"; then
  check "no database container or volume touched" 0 "$(grep -E 'volume rm|rm -f itvault-db' "$LOG")"
else
  check "no database container or volume touched" 1
fi

echo
if [ "$fails" = "0" ]; then echo "ALL PASSED"; else echo "$fails FAILED"; fi
exit "$fails"
