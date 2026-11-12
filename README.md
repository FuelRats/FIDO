# FIDO
IRC bot to moderate the fuelrats public channels

# Contribute
Python 3.12, PRs welcome.

## Configuration
FIDO reads its settings from environment variables when `config.py` is imported. An unset or
empty variable takes the default. Booleans accept `1/true/yes/on` and `0/false/no/off` (any
case); any other value stops the import with an error naming the variable.
`deploy/fido.env.example` lists the names; in an env file, single-quote every value.

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
| `FIDO_EXPECT_SNOMASK` | empty | Snomask expected after OPER; a different one logs a warning. Empty: no check |
| `FIDO_DB_URL` | `sqlite:///FIDO.sqlite` | SQLAlchemy URL of the database |
| `FIDO_LOG_LEVEL` | `INFO` | Logging level name; logs go to stdout |
| `FIDO_SESSION_RETENTION_DAYS` | `90` | Days of IRC sessions kept |
| `FIDO_STARTUP_DEADLINE` | `90` | Seconds from the start of the connect to the server confirming OPER |
| `FIDO_SILENCE_LIMIT` | `360` | Seconds without any line from the server before the session counts as lost |

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
`sms/topic/<group>`.

## Process contract
One process runs one IRC session and then exits; it does not reconnect. Run it under a
supervisor that restarts it, for example a container with `restart: unless-stopped`.

| Exit code | When |
|---|---|
| 0 | SIGTERM or SIGINT: sends QUIT with the reason `restarting`, waits at most 3 s for the server to close the link, exits |
| 1 | Session lost: the connection closed or failed, the nick differs from `FIDO_NICK`, OPER was not confirmed within `FIDO_STARTUP_DEADLINE`, nothing arrived for `FIDO_SILENCE_LIMIT`, or OPER was refused (464 or 491, after a 300 s hold) |
| 2 | `FIDO_OPER_NAME` or `FIDO_OPER_PASSWORD` unset, `FIDO_LOG_LEVEL` not a level name, or `FIDO_STARTUP_DEADLINE` or `FIDO_SILENCE_LIMIT` not above 0. A boolean or integer that does not parse stops the import instead (Python exits 1 with the error) |

In a container, point `FIDO_DB_URL` at a mounted volume (for example
`sqlite:////data/FIDO.sqlite`) so the database outlives the container, and use host networking
so FIDO connects from 127.0.0.1 as the IRC server expects.

## Tests
The tests need no IRC server or secrets. Run them in the Python 3.12 image from the repo root:
```
docker run --rm -v "$PWD":/src -w /src python:3.12-slim sh -c 'pip install -q -r requirements.txt && pip check && python -W error::DeprecationWarning -c "import fido" && python -m unittest discover -s tests -v'
```

## Dependencies
`requirements.in` lists the direct dependencies. `requirements.txt` is the `pip freeze` of a clean
`python:3.12-slim` install of it; regenerate it the same way after changing `requirements.in`.

# Todo
* https://jira.fuelrats.com/projects/FIDO/issues
