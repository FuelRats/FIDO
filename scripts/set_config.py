"""
Set one value in the config table of the DB named by FIDO_DB_URL.

Run as: python -m scripts.set_config <module> <key> <value>

Every existing row for module/key is replaced by one row, and the old and new values are
written to stdout. Keys that hold secrets are refused: everything under module nexmo, and
everything under module sms except sms/topic/<group>. So are values FIDO cannot read: a gate
(configmanager.GATES) takes only on or off, and a key whose default is an integer only an integer.
"""
import argparse
import sys

from modules import configmanager

REFUSED_MODULES = {'nexmo'}
SMS_MODULE = 'sms'
SMS_TOPIC_PREFIX = 'topic/'

EXIT_OK = 0
EXIT_REFUSED = 2


def refusal(module: str, key: str):
    """Why module/key may not be set here, or None if it may."""
    if module.lower() in REFUSED_MODULES:
        return f"module {module} holds secrets"
    if module.lower() == SMS_MODULE and not (key.startswith(SMS_TOPIC_PREFIX) and len(key) > len(SMS_TOPIC_PREFIX)):
        return f"only {SMS_MODULE}/{SMS_TOPIC_PREFIX}<group> keys can be set under module {SMS_MODULE}"
    return None


def is_integer(text: str) -> bool:
    """Whether int() reads text, as the protections do."""
    try:
        int(text)
    except ValueError:
        return False
    return True


def value_problem(module: str, key: str, value: str):
    """Why FIDO could not use value for module/key, naming the accepted values, or None if it can."""
    flags = (configmanager.FLAG_ON, configmanager.FLAG_OFF)
    if (module, key) in configmanager.GATES and value.strip().lower() not in flags:
        return f"a gate takes '{flags[0]}' or '{flags[1]}', not {value!r}"
    default = configmanager.DEFAULTS.get((module, key))
    if default is not None and is_integer(default) and not is_integer(value):
        return f"the value must be an integer (default {default}), not {value!r}"
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='python -m scripts.set_config',
                                     description='Replace the value of one config key.')
    parser.add_argument('module')
    parser.add_argument('key')
    parser.add_argument('value')
    args = parser.parse_args(argv)

    reason = refusal(args.module, args.key) or value_problem(args.module, args.key, args.value)
    if reason:
        sys.stderr.write(f"Refusing {args.module}/{args.key}: {reason}\n")
        return EXIT_REFUSED

    old = configmanager.set_config(args.module, args.key, args.value)
    old_text = ', '.join(repr(value) for value in old) if old else '(unset)'
    sys.stdout.write(f"{args.module}/{args.key}: {old_text} -> {args.value!r}\n")
    if len(old) > 1:
        sys.stdout.write(f"Replaced {len(old)} rows with one.\n")
    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
