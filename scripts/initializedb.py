"""
Create missing FIDO tables and seed missing config keys in the DB named by FIDO_DB_URL.

Run as: python -m scripts.initializedb [--seed-missing]

Nothing is ever dropped or overwritten. A DB whose ircsessions or asn_blacklist table
holds rows is refused unless --seed-missing is given.
"""
import argparse
import logging
import sys

from sqlalchemy import inspect

import models
from models.meta import Base
from models import asn_blacklist, config, drones, groups, ircsessions, messagecounter, monitor
from modules import configmanager

log = logging.getLogger(__name__)

# Importing these registers all 7 tables on Base.metadata.
MODEL_MODULES = (asn_blacklist, config, drones, groups, ircsessions, messagecounter, monitor)

# Tables whose rows mark a DB that is in use.
GUARDED_TABLES = (ircsessions.IRCSessions, asn_blacklist.ASNBlacklist)

EXIT_OK = 0
EXIT_REFUSED = 1


def populated_tables(engine) -> list:
    """Names of the guarded tables that exist and hold at least one row."""
    existing = set(inspect(engine).get_table_names())
    with models.session_scope() as session:
        return [model.__tablename__ for model in GUARDED_TABLES
                if model.__tablename__ in existing and session.query(model).first() is not None]


def initialize(seed_missing: bool = False) -> int:
    engine = models.engine
    populated = populated_tables(engine)
    if populated and not seed_missing:
        log.error(f"Refusing: {', '.join(populated)} already holds rows. "
                  f"Use --seed-missing to add only missing tables and keys.")
        return EXIT_REFUSED

    existing = set(inspect(engine).get_table_names())
    Base.metadata.create_all(engine)
    created = sorted(set(Base.metadata.tables) - existing)
    log.info(f"Created tables: {', '.join(created) or 'none'}")

    seeded = []
    with models.session_scope() as session:
        for (module, key), value in configmanager.DEFAULTS.items():
            if session.query(config.Config).filter_by(module=module, key=key).first() is None:
                session.add(config.Config(module=module, key=key, value=value))
                seeded.append(f"{module}/{key}")
    log.info(f"Seeded keys: {', '.join(seeded) or 'none'}")
    return EXIT_OK


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='python -m scripts.initializedb',
                                     description='Create missing FIDO tables and seed missing config keys.')
    parser.add_argument('--seed-missing', action='store_true',
                        help='also run on a DB that already holds sessions or ASN bans')
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(message)s')
    return initialize(seed_missing=args.seed_missing)


if __name__ == '__main__':
    sys.exit(main())
