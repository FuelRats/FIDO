#!/usr/bin/env bash
# Local test bed (plan D14), for the Mac only: two throwaway UnrealIRCd 6.2.6 servers linked as
# hub.irc.example.test and leaf.irc.example.test on a private Docker network with no route out,
# and FIDO run from deploy/compose.yml (with tests/testbed/compose.yml on top) against the hub.
# It prints PASS or FAIL for:
#   (1) FIDO opers with the expected snomask
#   (2) the hub is killed and started again: FIDO restarts and opers again
#   (3) /KILL from a test oper: FIDO restarts and opers again
#   (4) kill -9 of FIDO's process from the Docker host: FIDO restarts and opers again
#   (5) a remote connect on the leaf and a link drop are parsed, with no "unparsed" warning
#   (6) FIDO runs as uid 1000, with the host's time zone and a read-only root filesystem
# Certificates, passwords, env files and FIDO's data are generated per run in a temp dir and a
# Docker volume. Containers, network, volumes, images and the temp dir are removed at the end;
# TESTBED_KEEP_IMAGES=1 keeps the two images. Usage: bash tests/testbed/run.sh
set -euo pipefail

TESTBED_DIR=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$TESTBED_DIR/../.." && pwd)
export TESTBED_DIR

PROJECT=fido-testbed
IRCD_IMAGE=fido-testbed/unrealircd:6.2.6
FIDO_TAG=testbed
export FIDO_TAG
CONTAINER=fr-fido-testbed
OPER_NAME=fido-testbed
SNOMASK=+bcdfkoqsBCOS
OPERED="opered, snomask $SNOMASK"
TEST_NICK=Jameson
WAIT=180   # seconds any one step may take; Docker's restart delay doubles towards 60 s
POLL=1     # seconds between two checks
LOG_TAIL=40

WORK=$(mktemp -d "${TMPDIR:-/tmp}/fido-testbed.XXXXXX")

compose() {
    docker compose -p "$PROJECT" --project-directory "$WORK" \
        -f "$REPO/deploy/compose.yml" -f "$TESTBED_DIR/compose.yml" "$@"
}

cleanup() {
    local status=$?
    compose --profile tools down -v --remove-orphans >/dev/null 2>&1 || true
    if [ "${TESTBED_KEEP_IMAGES:-0}" != 1 ]; then
        docker image rm "$IRCD_IMAGE" "fr-fido:$FIDO_TAG" >/dev/null 2>&1 || true
    fi
    rm -rf "$WORK"
    exit "$status"
}
trap cleanup EXIT

say() { printf '%s\n' "$*"; }

# A random [A-Za-z0-9] string of the given length (openssl output, so no pipe is cut short).
random_alnum() {
    local value
    value=$(openssl rand -base64 $(($1 * 2)) | tr -dc 'A-Za-z0-9' | cut -c "1-$1")
    [ "${#value}" -eq "$1" ] || { say "could not generate a random value" >&2; return 1; }
    printf '%s' "$value"
}

fido_logs() { docker logs "$CONTAINER" 2>&1; }

# Lines of FIDO's log that contain every given string.
log_lines() {
    local lines
    lines=$(fido_logs)
    for text in "$@"; do
        lines=$(printf '%s\n' "$lines" | grep -aF -- "$text" || true)
    done
    printf '%s' "$lines"
}

count() {
    local lines
    lines=$(log_lines "$@")
    if [ -z "$lines" ]; then echo 0; else printf '%s\n' "$lines" | wc -l | tr -d ' '; fi
}

restart_count() { docker inspect -f '{{.RestartCount}}' "$CONTAINER"; }

# wait_until <description> <command...>: run the command every POLL seconds until it succeeds.
wait_until() {
    local what=$1
    shift
    local end=$((SECONDS + WAIT))
    until "$@"; do
        if [ "$SECONDS" -ge "$end" ]; then
            say "timed out after $WAIT s waiting for: $what"
            return 1
        fi
        sleep "$POLL"
    done
}

pass() { say "PASS ($1) $2"; }

fail() {
    say "FAIL ($1) $2"
    say "--- last $LOG_TAIL lines of FIDO's log"
    fido_logs | tail -n "$LOG_TAIL" || true
    say "--- last $LOG_TAIL lines of the hub's log"
    compose logs --no-log-prefix hub 2>&1 | tail -n "$LOG_TAIL" || true
    exit 1
}

# quiet <command...>: run the command, showing its output only if it fails.
quiet() {
    local output
    if ! output=$("$@" 2>&1); then
        printf '%s\n' "$output"
        return 1
    fi
}

restarted_and_opered() {
    [ "$(restart_count)" -gt "$1" ] && [ "$(count "$OPERED")" -gt "$2" ]
}

LINKED="Server linked: hub.irc.example.test -> leaf.irc.example.test"
links() { compose logs --no-log-prefix hub 2>&1 | grep -acF -- "$LINKED" || true; }
linked_more_than() { [ "$(links)" -gt "$1" ]; }

client() { compose run --rm --no-deps client "$@"; }

# Setup -----------------------------------------------------------------------------------------

say "work dir $WORK"
umask 077
export TESTBED_FIDO_OPER_PASSWORD TESTBED_TESTOP_PASSWORD TESTBED_LINK_PASSWORD
export TESTBED_CLOAK_KEY_1 TESTBED_CLOAK_KEY_2 TESTBED_CLOAK_KEY_3
TESTBED_FIDO_OPER_PASSWORD=$(random_alnum 32)
TESTBED_TESTOP_PASSWORD=$(random_alnum 32)
TESTBED_LINK_PASSWORD=$(random_alnum 32)
TESTBED_CLOAK_KEY_1=$(random_alnum 100)
TESTBED_CLOAK_KEY_2=$(random_alnum 100)
TESTBED_CLOAK_KEY_3=$(random_alnum 100)

# The files prod keeps in /home/fuelrats/fido-bot, with test bed values.
printf 'FIDO_TAG=%s\n' "$FIDO_TAG" > "$WORK/.env"
cat > "$WORK/fido.env" <<EOF
FIDO_IRC_SERVER='hub.irc.example.test'
FIDO_IRC_PORT='6697'
FIDO_IRC_TLS='on'
FIDO_TLS_VERIFY='on'
FIDO_OPER_NAME='$OPER_NAME'
FIDO_OPER_PASSWORD='$TESTBED_FIDO_OPER_PASSWORD'
FIDO_EXPECT_SNOMASK='$SNOMASK'
FIDO_LOG_LEVEL='DEBUG'
FIDO_STARTUP_DEADLINE='30'
EOF
mkdir "$WORK/data"
chmod 0755 "$WORK/data"
umask 022

compose --profile tools down -v --remove-orphans >/dev/null 2>&1 || true

say "building fr-fido:$FIDO_TAG and $IRCD_IMAGE"
quiet docker build -t "fr-fido:$FIDO_TAG" "$REPO"
quiet docker build -f "$TESTBED_DIR/unrealircd.Dockerfile" -t "$IRCD_IMAGE" "$TESTBED_DIR"
compose --profile tools config --quiet

say "starting hub and leaf"
quiet compose up -d hub leaf
wait_until "hub and leaf linked" linked_more_than 0

say "creating FIDO's database"
quiet compose run --rm --no-deps fr-fido python -m scripts.initializedb
compose run --rm --no-deps fr-fido python -m scripts.set_config channels join '#opers'

say "starting FIDO"
quiet compose up -d fr-fido

# (1) opered -------------------------------------------------------------------------------------

opered_once() { [ "$(count "$OPERED")" -ge 1 ]; }
wait_until "$OPERED" opered_once || fail 1 "FIDO did not log '$OPERED'"
[ "$(count 'differs from the expected')" -eq 0 ] || fail 1 "FIDO warned about its snomask"
pass 1 "opered: $(log_lines "$OPERED" | head -n 1 | sed 's/^.*opered/opered/')"

# (2) hub killed and started again ---------------------------------------------------------------

restarts=$(restart_count)
opered=$(count "$OPERED")
links_before=$(links)
quiet compose kill -s KILL hub
quiet compose start hub
wait_until "a restart and a new '$OPERED'" restarted_and_opered "$restarts" "$opered" \
    || fail 2 "no restart and oper after the hub was killed"
pass 2 "hub killed: RestartCount $restarts -> $(restart_count), opered lines $opered -> $(count "$OPERED")"
wait_until "the leaf relinked" linked_more_than "$links_before" || fail 2 "the leaf did not relink"

# (3) /KILL from a test oper ---------------------------------------------------------------------

restarts=$(restart_count)
opered=$(count "$OPERED")
client --server hub.irc.example.test --nick TestOper --oper testop --send 'KILL FIDO[BOT] :test bed kill' \
    || fail 3 "the test oper could not send KILL"
wait_until "a restart and a new '$OPERED'" restarted_and_opered "$restarts" "$opered" \
    || fail 3 "no restart and oper after /KILL"
[ "$(count '<< ' 'test bed kill')" -ge 1 ] || fail 3 "FIDO's log does not show the KILL"
pass 3 "/KILL: RestartCount $restarts -> $(restart_count), opered lines $opered -> $(count "$OPERED")"

# (4) kill -9 from the host ----------------------------------------------------------------------

restarts=$(restart_count)
opered=$(count "$OPERED")
# The Docker host is the VM, so the PID from docker top is killed from a container in its PID
# namespace; Docker sees a crash, not a stop.
pid=$(docker top "$CONTAINER" -o pid,args | awk '$2 == "python" && $3 == "fido.py" { print $1 }')
[ -n "$pid" ] || fail 4 "no python fido.py process in docker top"
docker run --rm --pid=host --network none --user 0:0 --entrypoint sh "$IRCD_IMAGE" -c 'kill -9 "$1"' sh "$pid"
wait_until "a restart and a new '$OPERED'" restarted_and_opered "$restarts" "$opered" \
    || fail 4 "no restart and oper after kill -9"
pass 4 "kill -9 of PID $pid: RestartCount $restarts -> $(restart_count), opered lines $opered -> $(count "$OPERED")"

# (5) remote connect and link drop parsed --------------------------------------------------------

client --server leaf.irc.example.test --nick "$TEST_NICK" --stay 2 >/dev/null || fail 5 "the leaf client failed"
connect_seen() { [ "$(count '<< ' 'connect.REMOTE_CLIENT_CONNECT' "Client connecting: $TEST_NICK ")" -ge 1 ]; }
wait_until "FIDO receiving the remote connect" connect_seen || fail 5 "no REMOTE_CLIENT_CONNECT for $TEST_NICK"
session_rows() {
    compose exec -T fr-fido python -c "import sqlite3; print(sqlite3.connect('file:/data/FIDO.sqlite?mode=ro', uri=True).execute(\"select count(*) from ircsessions where nickname = '$TEST_NICK'\").fetchone()[0])"
}
session_stored() { [ "$(session_rows)" -ge 1 ]; }
wait_until "a session row for $TEST_NICK" session_stored || fail 5 "the connect handler stored no session"

# The earlier steps may already have logged link events, so each check waits for its count to rise.
lost_count() { count '<< ' 'link.LINK_DISCONNECTED' 'Lost server link to leaf.irc.example.test'; }
down_count() { count '>> PRIVMSG #opers ' 'LINK DOWN' 'leaf.irc.example.test'; }
restored_count() { count '>> PRIVMSG #opers ' 'LINK RESTORED' 'leaf.irc.example.test'; }
rose() { [ "$("$1")" -gt "$2" ]; }
lost_before=$(lost_count)
down_before=$(down_count)
quiet compose kill -s KILL leaf
wait_until "FIDO receiving the link loss" rose lost_count "$lost_before" || fail 5 "no LINK_DISCONNECTED notice"
wait_until "FIDO reporting LINK DOWN" rose down_count "$down_before" || fail 5 "FIDO did not report the link loss"
restored_before=$(restored_count)
quiet compose start leaf
wait_until "FIDO reporting LINK RESTORED" rose restored_count "$restored_before" \
    || fail 5 "FIDO did not report the relink"
unparsed=$(count 'unparsed')
[ "$unparsed" -eq 0 ] || fail 5 "$unparsed unparsed warnings"
pass 5 "remote connect stored ($(session_rows) session row), LINK DOWN and LINK RESTORED reported, 0 unparsed"

# (6) uid, time zone, read-only root filesystem ----------------------------------------------------

uid=$(compose exec -T fr-fido id -u)
gid=$(compose exec -T fr-fido id -g)
[ "$uid:$gid" = "1000:1000" ] || fail 6 "FIDO runs as $uid:$gid"
host_zone=$(date +%Z)
fido_zone=$(compose exec -T fr-fido date +%Z)
[ "$fido_zone" = "$host_zone" ] || fail 6 "time zone $fido_zone, host $host_zone"
[ "$(docker inspect -f '{{.HostConfig.ReadonlyRootfs}}' "$CONTAINER")" = true ] || fail 6 "root filesystem not read-only"
if compose exec -T fr-fido sh -c 'touch /app/.write-probe' >/dev/null 2>&1; then
    fail 6 "/app is writable"
fi
compose exec -T fr-fido sh -c 'touch /tmp/.write-probe' || fail 6 "/tmp (tmpfs) is not writable"
pass 6 "uid:gid $uid:$gid, time zone $fido_zone (host $host_zone), root filesystem read-only, /tmp writable"

# Extra: the generated oper password is not in FIDO's log at DEBUG (positive control first).
[ "$(printf '%s\n' "$TESTBED_FIDO_OPER_PASSWORD" | grep -cF -- "$TESTBED_FIDO_OPER_PASSWORD")" -eq 1 ]
leaks=$(fido_logs | grep -cF -- "$TESTBED_FIDO_OPER_PASSWORD" || true)
[ "$leaks" -eq 0 ] || { say "FAIL oper password found in FIDO's log ($leaks lines)"; exit 1; }
tracebacks=$(count 'Traceback')
[ "$tracebacks" -eq 0 ] || { say "FAIL $tracebacks tracebacks in FIDO's log"; exit 1; }
say "PASS (extra) oper password in FIDO's DEBUG log: 0 lines; tracebacks: 0"

say "ALL PASS"
