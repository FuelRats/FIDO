# FIDO
IRC bot to moderate the fuelrats public channels

# Contribute
Python 3.12, PRs welcome.

## Configuration
FIDO reads its settings from environment variables when `config.py` is imported. An unset or
empty variable takes the default. Booleans accept `1/true/yes/on` and `0/false/no/off` (any
case); any other value, or an integer variable that is not a number, raises a `ValueError` naming
the variable. Started as `python fido.py`, FIDO then logs one `Configuration error` line and
exits with code 2. `deploy/fido.env.example` lists the names; in an env file, single-quote every
value.

| Variable | Default | Meaning |
|---|---|---|
| `FIDO_IRC_SERVER` | `127.0.0.1` | IRC server to connect to |
| `FIDO_IRC_PORT` | `6697` | Port |
| `FIDO_IRC_TLS` | `true` | Connect with TLS |
| `FIDO_TLS_VERIFY` | `false` | Verify the server certificate against the system CA store |
| `FIDO_TLS_SERVERNAME` | empty | Certificate name to verify and send as SNI; empty uses `FIDO_IRC_SERVER` |
| `FIDO_NICK` | `FIDO[BOT]` | Nick; registering under any other nick ends the session |
| `FIDO_OPER_NAME` | none, required | Oper block name |
| `FIDO_OPER_PASSWORD` | none, required | Oper password; it is never logged |
| `FIDO_SASL_USERNAME` | empty | Services account FIDO logs in to with SASL PLAIN (a nick of the account). Set it with `FIDO_SASL_PASSWORD`, or leave both empty for no login |
| `FIDO_SASL_PASSWORD` | empty | Password of that account; it is never logged |
| `FIDO_EXPECT_SNOMASK` | empty | Snomask expected after OPER; a different one logs a warning. Empty: no check |
| `FIDO_DB_URL` | `sqlite:///FIDO.sqlite` | SQLAlchemy URL of the database |
| `FIDO_LOG_LEVEL` | `INFO` | Logging level name; logs go to stdout |
| `FIDO_SESSION_RETENTION_DAYS` | `90` | Days of IRC sessions kept; at least 1 |
| `FIDO_STARTUP_DEADLINE` | `90` | Seconds from the start of the connect to the server confirming OPER |
| `FIDO_SILENCE_LIMIT` | `360` | Seconds without any line from the server before the session counts as lost |
| `AWS_ACCESS_KEY_ID` | none | AWS key of the IAM user allowed to publish to the SMS topics; read by boto3. Without it every SMS fails, and the failure is logged |
| `AWS_SECRET_ACCESS_KEY` | none | Secret of that key; read by boto3 |
| `AWS_DEFAULT_REGION` | none | Read by boto3; FIDO's SNS client always uses `eu-central-1`, so this does not move the SMS topics |

## Running
```
pip install -r requirements.txt
python -m scripts.initializedb          # create missing tables and seed missing config keys
python fido.py
```

`scripts.initializedb` never drops anything. It creates the tables that are missing and seeds the
config keys the protections read when they are absent. It refuses a database that already holds
rows in `ircsessions` or `asn_blacklist` unless `--seed-missing` is given.

Runtime switches live in the `config` table and are read on every use, so a change applies
without a restart:
```
python -m scripts.set_config <module> <key> <value>
```
It replaces every row for the key with one and prints the old and new values. It refuses keys
that hold secrets: everything under module `nexmo`, and everything under module `sms` except
`sms/topic/<group>`. It also refuses values FIDO could not read: anything but `on` or `off` for a
gate, and a non-integer for a key whose default is an integer (`channelprotection` keys
`droneinterval`, `maxdrones`, `maxhighlightcount`, `maxmessages`, `messageinterval` and
`mutetime`). Refusals exit with code 2.

Five gates switch behaviour on and off this way. Each is `on` or `off`; a missing row means on.

| Gate (module key) | Controls |
|---|---|
| `notices opers_reports` | G-line, KILL, Q-line, failed-OPER, spamfilter and link reports to the oper channel |
| `notices sms` | The SMS to group `ops` when a spamfilter hit is the ops alert filter |
| `notices ratchat_link_warnings` | The unstable-link warning in #ratchat |
| `newrats greeting` | The #NewRats greeting |
| `channelprotection auto_lockdown` | The automatic lockdown and G-lines after DNSBL reports in #opers from IRC operators (not bots or services bots) |

For example, `python -m scripts.set_config notices sms off`. ASN ban and clone reports have no
gate.

## SMS
FIDO sends SMS through AWS SNS, one topic per group; the topic's subscriptions are the phone
numbers, so FIDO's database holds none. The topic ARN of group `<group>` is the config key
`sms/topic/<group>`:
```
python -m scripts.set_config sms topic/ops arn:aws:sns:eu-central-1:<account>:<topic>
```
IRC operators send to a group with `!smssend <group> <text>`. A group without a topic logs a
warning and sends nothing.

## Services login
FIDO's channel status comes from groupsync, which grants it only to clients logged in to a
services account. With `FIDO_SASL_USERNAME` and `FIDO_SASL_PASSWORD` set, FIDO requests the `sasl`
capability (and no other IRCv3 capability) during registration and logs in with SASL PLAIN; the
log shows `SASL logged in as <account>`. When services are down at connect the server does not
offer `sasl`: FIDO registers, opers and joins without a login, and logs in once when the server
announces `sasl` with `CAP NEW`. A failed login (904, 905, or no answer within 15 s) ends the
session after the 300 s hold. Once the nick is registered, NickServ renames an unidentified
FIDO after its protection delay, and that rename also ends the session.

## Process contract
One process runs one IRC session and then exits; it does not reconnect. Run it under a
supervisor that restarts it, for example a container with `restart: unless-stopped`.

| Exit code | When |
|---|---|
| 0 | SIGTERM or SIGINT: sends QUIT with the reason `restarting`, waits at most 3 s for the server to close the link, exits |
| 1 | Session lost: the connection closed or failed, the nick differs from `FIDO_NICK` at registration or the server renamed FIDO away from it later, OPER was not confirmed within `FIDO_STARTUP_DEADLINE`, nothing arrived for `FIDO_SILENCE_LIMIT`, OPER was refused (464 or 491), or the SASL login failed (904, 905, or no answer within 15 s). OPER and SASL failures hold every exit for 300 s, so a wrong password does not restart FIDO in a tight loop |
| 2 | Configuration error, logged as one `Configuration error` line per problem: `FIDO_OPER_NAME` or `FIDO_OPER_PASSWORD` unset, only one of `FIDO_SASL_USERNAME` and `FIDO_SASL_PASSWORD` set, `FIDO_LOG_LEVEL` not a level name, `FIDO_STARTUP_DEADLINE` or `FIDO_SILENCE_LIMIT` not above 0, `FIDO_SESSION_RETENTION_DAYS` below 1, a boolean or integer variable that does not parse, a `FIDO_DB_URL` that is not a database URL, or a database FIDO cannot use: before connecting, FIDO checks that every table exists and that it can read the config table and write (a write it rolls back) |

## Container
The `Dockerfile` builds the image from the `python:3.12-slim` digest it pins. The build fails if
the installed packages differ from `requirements.txt`, and pip is removed from the image. FIDO
runs as uid 1000 from `/app`.

`deploy/compose.yml` runs it in production as compose project `fido`, container `fr-fido`. It uses
host networking, so FIDO connects from 127.0.0.1 as the IRC server expects. The root filesystem is
read-only, all capabilities are dropped, and the restart policy is `unless-stopped`. Next to
`compose.yml`, the project directory holds:
- `.env` with only `FIDO_TAG`, the image tag (`deploy/dot-env.example`);
- `fido.env`, mode 0600, with the settings and secrets (`deploy/fido.env.example`);
- `data/`, owned by uid 1000, mounted at `/data`; compose sets `FIDO_DB_URL` to
  `sqlite:////data/FIDO.sqlite` there.

```
docker build -t fr-fido:<short sha> .
docker compose run --rm fr-fido python -m scripts.initializedb   # once, on an empty data/
docker compose up -d
```

## Tests
The tests need no IRC server or secrets. Run them in the Python 3.12 image from the repo root:
```
docker run --rm -v "$PWD":/src -w /src python:3.12-slim sh -c 'pip install -q -r requirements.txt && pip check && python -W error::DeprecationWarning -c "import fido" && python -m unittest discover -s tests -v'
```
`tests/test_process.py` runs `python fido.py` as a subprocess against a scripted server and checks
the exit codes above. CI (`.github/workflows/ci.yml`) runs the suite in the Dockerfile's base
image on every pull request and every push to `python`, then builds the image.

`bash tests/testbed/run.sh` (on a Mac with Docker; not run in CI) builds two throwaway UnrealIRCd
6.2.6 servers from the checksum-verified release tarball, links them on a private Docker network,
and runs FIDO from `deploy/compose.yml` against them. It checks that FIDO opers, comes back after
the server is killed, after a `/KILL` and after a `kill -9`, parses a remote connect and a link
drop, and runs as uid 1000 with the host's time zone and a read-only root filesystem. It removes
everything it created.

## Dependencies
`requirements.in` lists the direct dependencies. `requirements.txt` is the `pip freeze` of a clean
`python:3.12-slim` install of it; regenerate it the same way after changing `requirements.in`.
Dependabot proposes weekly grouped updates for pip, the base image digest and the GitHub Actions.

# Todo
* https://jira.fuelrats.com/projects/FIDO/issues
