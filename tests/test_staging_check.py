"""
tools/staging_check.py on a temp DB from prod's schema: it reads every key the code reads, prints
counts and key names only, and writes nothing. Synthetic data only.
"""
import datetime
import hashlib
import io
import pathlib
import re
import unittest

from tests import harness
from models import asn_blacklist, config, ircsessions, monitor, session_scope
from modules import configmanager
from tools import staging_check

REPO = pathlib.Path(__file__).resolve().parent.parent
CODE_DIRS = ('modules',)
CODE_FILES = ('fido.py',)
# get_config/get_value/get_flag calls with a literal module and key.
LITERAL_READ = re.compile(r"get_(?:config|value|flag)\(\s*(?:module=)?['\"](\w+)['\"]\s*,\s*(?:key=)?['\"]([\w/]+)['\"]")

SECRET_VALUES = ('arn:aws:sns:eu-central-1:123456789012:fido-sms-test', '#hidden-oper-room', 'Distinctive kick reason',
                 'Jameson7', '192.0.2.123', 'EXAMPLE-NET-HOLDER', 'Reason: watched (Jameson4)')


def code_paths():
    for name in CODE_FILES:
        yield REPO / name
    for directory in CODE_DIRS:
        yield from (REPO / directory).rglob('*.py')


class StagingCheckTest(unittest.TestCase):
    def setUp(self):
        self.db = self.enterContext(harness.TempDB())
        with session_scope() as session:
            session.add_all([
                config.Config(module='sms', key='topic/ops', value=SECRET_VALUES[0]),
                config.Config(module='channels', key='operchannel', value=SECRET_VALUES[1]),
                config.Config(module='channelprotection', key='reason', value=SECRET_VALUES[2]),
                config.Config(module='channels', key='join', value='#ratchat'),
                config.Config(module='channels', key='join', value='#rat-ops'),
                ircsessions.IRCSessions(timestamp=datetime.datetime.now(), nickname=SECRET_VALUES[3],
                                        hostmask=SECRET_VALUES[4], network='192.0.2.0/24'),
                asn_blacklist.ASNBlacklist(timestamp=datetime.datetime.now(), asn='AS64511', prefix='192.0.2.0',
                                           cidr='24', reason='test', asn_name=SECRET_VALUES[5]),
                monitor.Monitor(timestamp=datetime.datetime.now(), nickname=SECRET_VALUES[3], msg=SECRET_VALUES[6]),
            ])

    def run_check(self) -> str:
        out = io.StringIO()
        self.assertEqual(staging_check.main(self.db.url, write=out.write), 0)
        return out.getvalue()

    def digest(self) -> str:
        return hashlib.sha256(pathlib.Path(self.db.path).read_bytes()).hexdigest()

    def test_prints_counts_and_key_names_only(self):
        output = self.run_check()
        for value in SECRET_VALUES:
            self.assertNotIn(value, output)
        self.assertIn('channels/join: 2 rows', output)
        self.assertIn('sms/topic/*: 1 key: sms/topic/ops', output)
        self.assertIn('session tracker: 1 row, lookup of Jameson or 192.0.2.1: 0 rows', output)
        self.assertIn('monitor list: 1 row', output)
        self.assertIn('ASN bans: 1 row for 1 ASNs, 1 prefixes loaded, 0 unparsable; 192.0.2.1 banned: yes', output)
        self.assertTrue(output.endswith('staging check done, nothing written\n'))

    def test_lists_every_key_the_code_reads(self):
        output = self.run_check()
        for module, key in set(configmanager.DEFAULTS) | set(configmanager.GATES):
            self.assertIn(f'  {module}/{key}: ', output)
        literal_reads = set()
        for path in code_paths():
            literal_reads.update(LITERAL_READ.findall(path.read_text(encoding='utf-8')))
        self.assertTrue(literal_reads)
        self.assertEqual(literal_reads - set(staging_check.CONFIG_KEYS), set())

    def test_writes_nothing(self):
        before = self.digest()
        self.run_check()
        self.assertEqual(self.digest(), before)

    def test_writes_fail_on_its_engine(self):
        engine = staging_check.read_only_engine(self.db.url)
        try:
            with engine.connect() as connection, self.assertRaisesRegex(Exception, 'readonly|read-only|query_only'):
                connection.exec_driver_sql("delete from config")
        finally:
            engine.dispose()
        self.assertEqual(self.db.count('config'), 5)


if __name__ == '__main__':
    unittest.main()
