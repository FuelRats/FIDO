"""
Environment settings (config.py), main()'s refusal to start without them, and the config table
semantics: get_value, get_flag, set_config and scripts/set_config.py.
"""
import asyncio
import contextlib
import io
import logging
import os
import pathlib
import re
import runpy
import secrets
import unittest
from unittest import mock

import config
import fido
from config import IRC
from models import config as config_model, session_scope
from modules import configmanager
from scripts import set_config
from tests import harness

REPO = pathlib.Path(__file__).resolve().parent.parent
CONFIG_PY = REPO / 'config.py'
ENV_EXAMPLE = REPO / 'deploy' / 'fido.env.example'
# The variables boto3 reads for modules/sms.py, besides the FIDO_ ones config.py reads.
BOTO3_ENV = {'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_DEFAULT_REGION'}
TOPIC_ARN = 'arn:aws:sns:eu-central-1:123456789012:fido-sms-test'


def load_config(**env):
    """Execute config.py with only the given FIDO_ variables set; returns its namespace."""
    clean = {name: value for name, value in os.environ.items() if not name.startswith('FIDO_')}
    clean.update(env)
    with mock.patch.dict(os.environ, clean, clear=True):
        return runpy.run_path(str(CONFIG_PY))


class EnvParsingTest(unittest.TestCase):
    def test_booleans(self):
        for raw in ('1', 'true', 'TRUE', 'Yes', 'on', ' On '):
            with mock.patch.dict(os.environ, {'FIDO_X': raw}):
                self.assertIs(config.env_bool('FIDO_X', False), True, raw)
        for raw in ('0', 'false', 'No', 'OFF'):
            with mock.patch.dict(os.environ, {'FIDO_X': raw}):
                self.assertIs(config.env_bool('FIDO_X', True), False, raw)

    def test_empty_or_unset_takes_the_default(self):
        with mock.patch.dict(os.environ, {'FIDO_X': ''}):
            self.assertIs(config.env_bool('FIDO_X', True), True)
            self.assertEqual(config.env_int('FIDO_X', 7), 7)
            self.assertEqual(config.env_str('FIDO_X', 'default'), 'default')
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIs(config.env_bool('FIDO_X', False), False)

    def test_other_boolean_values_raise_and_name_the_variable(self):
        for raw in ('maybe', 'enabled', '2'):
            with mock.patch.dict(os.environ, {'FIDO_X': raw}):
                with self.assertRaisesRegex(ValueError, 'FIDO_X'):
                    config.env_bool('FIDO_X', True)

    def test_integers(self):
        with mock.patch.dict(os.environ, {'FIDO_X': '6697'}):
            self.assertEqual(config.env_int('FIDO_X', 1), 6697)
        with mock.patch.dict(os.environ, {'FIDO_X': 'six'}):
            with self.assertRaisesRegex(ValueError, 'FIDO_X'):
                config.env_int('FIDO_X', 1)

    def test_defaults(self):
        namespace = load_config()
        irc = namespace['IRC']
        self.assertEqual((irc.server, irc.port, irc.useSsl, irc.tlsVerify, irc.tlsServerName),
                         ('127.0.0.1', 6697, True, False, ''))
        self.assertEqual((irc.nickname, irc.commandPrefix, irc.operline, irc.operlinePassword, irc.expectSnomask),
                         ('FIDO[BOT]', '!', '', '', ''))
        self.assertEqual((irc.startupDeadline, irc.silenceLimit), (90, 360))
        self.assertEqual((irc.saslUsername, irc.saslPassword), ('', ''))
        self.assertEqual(namespace['Logging'].level, 'INFO')
        self.assertEqual(namespace['SQLAlchemy'].url, 'sqlite:///FIDO.sqlite')
        self.assertEqual(namespace['SessionHandler'].retention_time, 90)

    def test_values_from_the_environment(self):
        password = f'${secrets.token_urlsafe(12)} with # and spaces '
        sasl_password = f'{secrets.token_urlsafe(12)} :with a colon'
        namespace = load_config(
            FIDO_IRC_SERVER='irc.example.test', FIDO_IRC_PORT='6667', FIDO_IRC_TLS='off', FIDO_TLS_VERIFY='on',
            FIDO_TLS_SERVERNAME='irc.example.test', FIDO_NICK='FIDO-test', FIDO_OPER_NAME='fido-test',
            FIDO_EXPECT_SNOMASK='+cC',
            FIDO_OPER_PASSWORD=password, FIDO_SASL_USERNAME='FIDO-test', FIDO_SASL_PASSWORD=sasl_password,
            FIDO_DB_URL='sqlite:////data/FIDO.sqlite', FIDO_LOG_LEVEL='debug', FIDO_SESSION_RETENTION_DAYS='30',
            FIDO_STARTUP_DEADLINE='5', FIDO_SILENCE_LIMIT='60')
        irc = namespace['IRC']
        self.assertEqual((irc.server, irc.port, irc.useSsl, irc.tlsVerify, irc.tlsServerName),
                         ('irc.example.test', 6667, False, True, 'irc.example.test'))
        self.assertEqual((irc.nickname, irc.operline, irc.operlinePassword, irc.expectSnomask),
                         ('FIDO-test', 'fido-test', password, '+cC'))
        self.assertEqual((irc.saslUsername, irc.saslPassword), ('FIDO-test', sasl_password))
        self.assertEqual((irc.startupDeadline, irc.silenceLimit), (5, 60))
        self.assertEqual(namespace['Logging'].level, 'DEBUG')
        self.assertEqual(namespace['SQLAlchemy'].url, 'sqlite:////data/FIDO.sqlite')
        self.assertEqual(namespace['SessionHandler'].retention_time, 30)

    def test_a_bad_boolean_fails_the_import(self):
        with self.assertRaisesRegex(ValueError, 'FIDO_IRC_TLS'):
            load_config(FIDO_IRC_TLS='sometimes')

    def test_env_example_lists_exactly_the_names_read(self):
        read = set(re.findall(r"env_(?:str|bool|int)\('(FIDO_[A-Z_]+)'", CONFIG_PY.read_text())) | BOTO3_ENV
        lines = [line for line in ENV_EXAMPLE.read_text().splitlines() if line and not line.startswith('#')]
        self.assertEqual({line.split('=', 1)[0] for line in lines}, read)
        self.assertTrue(all(line.endswith('=') for line in lines), 'the example holds names only')


class MainValidationTest(unittest.TestCase):
    def run_main(self) -> int:
        with harness.preserved_root_logging(), harness.capture_logs(logging.INFO) as logs, \
                mock.patch.object(fido, 'FIDO', side_effect=AssertionError('must not connect')):
            code = asyncio.run(fido.main())
        self.logs = logs
        return code

    def test_missing_oper_credentials_exit_2(self):
        with mock.patch.multiple(IRC, operline='', operlinePassword=''):
            self.assertEqual(self.run_main(), fido.EXIT_CONFIG)
        messages = self.logs.messages()
        self.assertIn('Configuration error: FIDO_OPER_NAME is not set', messages)
        self.assertIn('Configuration error: FIDO_OPER_PASSWORD is not set', messages)

    def test_other_problems_are_reported(self):
        with mock.patch.multiple(IRC, operline='fido-test', operlinePassword='set', startupDeadline=0,
                                 silenceLimit=-1), mock.patch.object(config.Logging, 'level', 'LOUD'):
            self.assertEqual(fido.config_problems(), [
                "FIDO_LOG_LEVEL 'LOUD' is not a logging level name",
                'FIDO_STARTUP_DEADLINE must be above 0',
                'FIDO_SILENCE_LIMIT must be above 0',
            ])

    def test_session_retention_below_one_day_is_refused(self):
        problem = 'FIDO_SESSION_RETENTION_DAYS must be at least 1'
        for days, problems in ((0, [problem]), (-30, [problem]), (1, []), (90, [])):
            with mock.patch.multiple(IRC, operline='fido-test', operlinePassword='set'), \
                    mock.patch.object(config.SessionHandler, 'retention_time', days):
                self.assertEqual(fido.config_problems(), problems, days)
        with mock.patch.multiple(IRC, operline='fido-test', operlinePassword='set'), \
                mock.patch.object(config.SessionHandler, 'retention_time', 0):
            self.assertEqual(self.run_main(), fido.EXIT_CONFIG)
        self.assertIn(f'Configuration error: {problem}', self.logs.messages())

    def test_complete_settings_have_no_problems(self):
        with mock.patch.multiple(IRC, operline='fido-test', operlinePassword='set'):
            self.assertEqual(fido.config_problems(), [])

    def test_sasl_settings_come_in_pairs(self):
        pair_problem = 'FIDO_SASL_USERNAME and FIDO_SASL_PASSWORD must both be set, or both left empty'
        for username, password, problems in (('FIDO-test', '', [pair_problem]), ('', 'set', [pair_problem]),
                                             ('FIDO-test', 'set', []), ('', '', [])):
            with mock.patch.multiple(IRC, operline='fido-test', operlinePassword='set', saslUsername=username,
                                     saslPassword=password):
                self.assertEqual(fido.config_problems(), problems, (username, password))

    def test_half_a_sasl_pair_exits_2(self):
        with mock.patch.multiple(IRC, operline='fido-test', operlinePassword='set', saslUsername='FIDO-test',
                                 saslPassword=''):
            self.assertEqual(self.run_main(), fido.EXIT_CONFIG)
        self.assertIn('Configuration error: FIDO_SASL_USERNAME and FIDO_SASL_PASSWORD must both be set, '
                      'or both left empty', self.logs.messages())


class ConfigTableTest(unittest.TestCase):
    def setUp(self):
        self.db = self.enterContext(harness.TempDB())

    def add(self, module, key, value):
        with session_scope() as session:
            session.add(config_model.Config(module=module, key=key, value=value))

    def test_get_config_returns_every_value(self):
        self.add('channels', 'join', '#ratchat')
        self.add('channels', 'join', '#rat-ops')
        self.assertEqual(sorted(configmanager.get_config('channels', 'join')), ['#rat-ops', '#ratchat'])

    def test_get_value_falls_back_to_the_default(self):
        self.assertEqual(configmanager.get_value('channelprotection', 'maxmessages'), '4')
        self.add('channelprotection', 'maxmessages', '9')
        self.assertEqual(configmanager.get_value('channelprotection', 'maxmessages'), '9')
        self.assertIsNone(configmanager.get_value('notices', 'unknown'))

    def test_set_config_replaces_every_row_with_one(self):
        self.add('droneprotection', 'lockdown', 'True')
        self.add('droneprotection', 'lockdown', 'True')
        self.assertEqual(configmanager.set_config('droneprotection', 'lockdown', 'False'), ['True', 'True'])
        self.assertEqual(configmanager.get_config('droneprotection', 'lockdown'), ['False'])
        self.assertEqual(configmanager.set_config('notices', 'sms', 'on'), [])

    def test_del_config_removes_the_rows(self):
        self.add('droneprotection', 'lockdown', 'True')
        configmanager.del_config('droneprotection', 'lockdown')
        self.assertEqual(configmanager.get_config('droneprotection', 'lockdown'), [])

    def test_get_flag(self):
        self.assertIs(configmanager.get_flag('notices', 'sms', True), True)
        self.assertIs(configmanager.get_flag('notices', 'sms', False), False)
        configmanager.set_config('notices', 'sms', 'OFF')
        self.assertIs(configmanager.get_flag('notices', 'sms', True), False)
        configmanager.set_config('notices', 'sms', 'on')
        self.assertIs(configmanager.get_flag('notices', 'sms', False), True)

    def test_get_flag_with_another_value_warns_and_uses_the_default(self):
        configmanager.set_config('notices', 'sms', 'maybe')
        with self.assertLogs('modules.configmanager', logging.WARNING):
            self.assertIs(configmanager.get_flag('notices', 'sms', True), True)

    def test_get_flag_sees_a_change_made_by_another_connection(self):
        configmanager.set_config('notices', 'opers_reports', 'on')
        self.assertIs(configmanager.get_flag('notices', 'opers_reports', True), True)
        with contextlib.closing(self.db.connect()) as other:
            other.execute("update config set value = 'off' where module = 'notices' and key = 'opers_reports'")
            other.commit()
        self.assertIs(configmanager.get_flag('notices', 'opers_reports', True), False)


class SetConfigScriptTest(unittest.TestCase):
    def setUp(self):
        self.db = self.enterContext(harness.TempDB())

    def run_script(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = set_config.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_prints_old_and_new_values(self):
        self.assertEqual(self.run_script('notices', 'opers_reports', 'off'),
                         (set_config.EXIT_OK, "notices/opers_reports: (unset) -> 'off'\n", ''))
        self.assertEqual(self.run_script('notices', 'opers_reports', 'on'),
                         (set_config.EXIT_OK, "notices/opers_reports: 'off' -> 'on'\n", ''))
        self.assertEqual(configmanager.get_config('notices', 'opers_reports'), ['on'])

    def test_sms_topic_keys_are_accepted(self):
        code, out, _ = self.run_script('sms', 'topic/ops', TOPIC_ARN)
        self.assertEqual(code, set_config.EXIT_OK)
        self.assertEqual(configmanager.get_config('sms', 'topic/ops'), [TOPIC_ARN])

    def test_secret_keys_are_refused_without_printing_them(self):
        configmanager.set_config('nexmo', 'secret', 'stored-value')
        for module, key in (('sms', 'secret'), ('sms', 'topic/'), ('SMS', 'appid'), ('nexmo', 'secret')):
            code, out, err = self.run_script(module, key, 'new-value')
            self.assertEqual(code, set_config.EXIT_REFUSED, (module, key))
            self.assertEqual(out, '')
            self.assertIn(f'Refusing {module}/{key}', err)
            self.assertNotIn('stored-value', err)
        self.assertEqual(configmanager.get_config('nexmo', 'secret'), ['stored-value'])
        self.assertEqual(configmanager.get_config('sms', 'secret'), [])

    def test_gates_take_only_on_or_off(self):
        for value in ('false', '0', 'no', 'disabled', ''):
            code, out, err = self.run_script('notices', 'sms', value)
            self.assertEqual(code, set_config.EXIT_REFUSED, value)
            self.assertEqual(out, '')
            self.assertIn('Refusing notices/sms', err)
            self.assertIn("'on' or 'off'", err)
        self.assertEqual(configmanager.get_config('notices', 'sms'), [])
        for module, key in configmanager.GATES:
            self.assertEqual(self.run_script(module, key, 'OFF')[0], set_config.EXIT_OK, (module, key))
            self.assertIs(configmanager.gate_open((module, key)), False)

    def test_keys_with_an_integer_default_take_only_integers(self):
        for key in ('droneinterval', 'maxdrones', 'maxhighlightcount', 'maxmessages', 'messageinterval',
                    'mutetime'):
            for value in ('four', '4.5', ''):
                code, out, err = self.run_script('channelprotection', key, value)
                self.assertEqual(code, set_config.EXIT_REFUSED, (key, value))
                self.assertEqual(out, '')
                self.assertIn('an integer', err)
            self.assertEqual(configmanager.get_config('channelprotection', key), [])
        self.assertEqual(self.run_script('channelprotection', 'maxmessages', '7')[0], set_config.EXIT_OK)
        self.assertEqual(configmanager.get_value('channelprotection', 'maxmessages'), '7')
        self.assertEqual(self.run_script('channelprotection', 'reason', 'Flooding')[0], set_config.EXIT_OK)

    def test_keys_with_an_integer_default_take_no_integer_below_one(self):
        for key in ('droneinterval', 'maxdrones', 'maxhighlightcount', 'maxmessages', 'messageinterval',
                    'mutetime'):
            for value in ('0', '-1', '-25'):
                with self.subTest(key=key, value=value):
                    code, out, err = self.run_script('channelprotection', key, value)
                    self.assertEqual(code, set_config.EXIT_REFUSED)
                    self.assertEqual(out, '')
                    self.assertIn(f'Refusing channelprotection/{key}: the value must be an integer of at least 1',
                                  err)
                    self.assertEqual(configmanager.get_config('channelprotection', key), [])
            self.assertEqual(self.run_script('channelprotection', key, '1')[0], set_config.EXIT_OK, key)
            self.assertEqual(configmanager.get_value('channelprotection', key), '1')

    def test_a_known_key_spelled_in_another_case_is_refused(self):
        cases = {('Notices', 'sms', 'off'): 'notices/sms', ('notices', 'SMS', 'off'): 'notices/sms',
                 ('channelprotection', 'MaxMessages', '7'): 'channelprotection/maxmessages'}
        for (module, key, value), spelling in cases.items():
            with self.subTest(module=module, key=key):
                code, out, err = self.run_script(module, key, value)
                self.assertEqual(code, set_config.EXIT_REFUSED)
                self.assertEqual(out, '')
                self.assertIn(f'Refusing {module}/{key}: FIDO reads {spelling}', err)
                self.assertEqual(configmanager.get_config(module, key), [])
        self.assertIs(configmanager.gate_open(configmanager.GATE_SMS), True)
        # A key that is neither a gate nor has a default is still written as given.
        self.assertEqual(self.run_script('channelprotection', 'reason_flood', 'Flooding')[0], set_config.EXIT_OK)
        self.assertEqual(configmanager.get_config('channelprotection', 'reason_flood'), ['Flooding'])

    def test_a_multi_row_key_is_collapsed_and_reported(self):
        with session_scope() as session:
            session.add_all([config_model.Config(module='channels', key='join', value='#ratchat'),
                             config_model.Config(module='channels', key='join', value='#rat-ops')])
        code, out, _ = self.run_script('channels', 'join', '#ratchat')
        self.assertEqual(code, set_config.EXIT_OK)
        self.assertIn('Replaced 2 rows with one.', out)
        self.assertEqual(configmanager.get_config('channels', 'join'), ['#ratchat'])


if __name__ == '__main__':
    unittest.main()
