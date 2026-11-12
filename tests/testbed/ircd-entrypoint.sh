#!/bin/sh
# Entrypoint of the test bed's hub and leaf: fills the @...@ placeholders of common.conf and
# <role>.conf from the environment, then runs UnrealIRCd in the foreground, logging to stderr.
# Usage: ircd-entrypoint.sh hub|leaf
set -eu
role=$1
conf=/home/ircd/unrealircd/conf

for value in "$TESTBED_FIDO_OPER_PASSWORD" "$TESTBED_TESTOP_PASSWORD" "$TESTBED_LINK_PASSWORD" \
             "$TESTBED_CLOAK_KEY_1" "$TESTBED_CLOAK_KEY_2" "$TESTBED_CLOAK_KEY_3"; do
    case "$value" in
        '' | *[!A-Za-z0-9]*) echo "test bed secrets must be non-empty [A-Za-z0-9]" >&2; exit 1 ;;
    esac
done

render() {
    sed -e "s|@ROLE@|$role|g" \
        -e "s|@FIDO_OPER_PASSWORD@|$TESTBED_FIDO_OPER_PASSWORD|g" \
        -e "s|@TESTOP_PASSWORD@|$TESTBED_TESTOP_PASSWORD|g" \
        -e "s|@LINK_PASSWORD@|$TESTBED_LINK_PASSWORD|g" \
        -e "s|@CLOAK_KEY_1@|$TESTBED_CLOAK_KEY_1|g" \
        -e "s|@CLOAK_KEY_2@|$TESTBED_CLOAK_KEY_2|g" \
        -e "s|@CLOAK_KEY_3@|$TESTBED_CLOAK_KEY_3|g" \
        "/testbed/$1" > "$conf/$2"
    chmod 0600 "$conf/$2"
}

render common.conf common.conf
render "$role.conf" unrealircd.conf
exec /home/ircd/unrealircd/bin/unrealircd -F
