"""
Unittest-based tests for ExpenseTracker.settings.lib module.
"""
import os
import unittest

from PySide6 import QtWidgets

from . import lib
from ..status.status import (
    ClientSecretInvalidException,
    LedgerConfigInvalidException,
)


def setUpModule():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    if not QtWidgets.QApplication.instance():
        QtWidgets.QApplication([])


class TestUtils(unittest.TestCase):
    def test_is_valid_hex_color(self):
        # valid colors
        for v in ('#FFFFFF', '#000000', '#AaBbCc'):
            self.assertTrue(lib.is_valid_hex_color(v), f"Expected valid: {v}")
        # invalid formats
        for v in ('FFF', '#FFFFF', '#GGGGGG', '123456', '#12345G', ''):
            self.assertFalse(lib.is_valid_hex_color(v), f"Expected invalid: {v}")

    def test_validate_header_success(self):
        header = {'a': 'string', 'b': 'date'}
        # Should not raise
        lib._validate_header(header, lib.HEADER_TYPES)

    def test_validate_header_type_and_value_errors(self):
        # Not a dict
        with self.assertRaises(TypeError):
            lib._validate_header('not a dict', lib.HEADER_TYPES)
        # Key not string
        with self.assertRaises(TypeError):
            lib._validate_header({1: 'string'}, lib.HEADER_TYPES)
        # Value not string
        with self.assertRaises(TypeError):
            lib._validate_header({'col': 123}, lib.HEADER_TYPES)
        # Value not allowed
        with self.assertRaises(ValueError):
            lib._validate_header({'col': 'notatype'}, lib.HEADER_TYPES)

    def test_validate_mapping_success(self):
        mapping = {k: 'x' for k in lib.DATA_MAPPING_KEYS}
        lib._validate_mapping(mapping, lib.LEDGER_SCHEMA['mapping'])

    def test_validate_mapping_key_and_type_errors(self):
        base = {k: 'x' for k in lib.DATA_MAPPING_KEYS}
        # missing key
        m1 = dict(base)
        m1.pop(lib.DATA_MAPPING_KEYS[0])
        with self.assertRaises(ValueError):
            lib._validate_mapping(m1, lib.LEDGER_SCHEMA['mapping'])
        # extra key
        m2 = dict(base)
        m2['extra'] = 'x'
        with self.assertRaises(ValueError):
            lib._validate_mapping(m2, lib.LEDGER_SCHEMA['mapping'])
        # wrong value type
        m3 = {k: 1 for k in lib.DATA_MAPPING_KEYS}
        with self.assertRaises(TypeError):
            lib._validate_mapping(m3, lib.LEDGER_SCHEMA['mapping'])

    def test_validate_categories_success(self):
        schema = lib.LEDGER_SCHEMA['categories']['item_schema']
        cat = {
            'display_name': 'Name',
            'color': '#123456',
            'description': 'desc',
            'icon': 'ico',
            'excluded': False,
        }
        lib._validate_categories({'cat1': cat}, schema)

    def test_validate_categories_errors(self):
        schema = lib.LEDGER_SCHEMA['categories']['item_schema']
        # Not a dict
        with self.assertRaises(TypeError):
            lib._validate_categories('not a dict', schema)
        # Category not dict
        with self.assertRaises(TypeError):
            lib._validate_categories({'cat1': 'bad'}, schema)
        # Missing required field
        cat1 = {
            'display_name': 'Name',
            'color': '#123456',
            'icon': 'ico',
            'excluded': False,
        }
        with self.assertRaises(ValueError):
            lib._validate_categories({'cat1': cat1}, schema)
        # Wrong type for field
        cat2 = {
            'display_name': 'Name',
            'color': '#123456',
            'description': 'desc',
            'icon': 'ico',
            'excluded': 'no',
        }
        with self.assertRaises(TypeError):
            lib._validate_categories({'cat1': cat2}, schema)
        # Bad hex color
        cat3 = {
            'display_name': 'Name',
            'color': '123456',
            'description': 'desc',
            'icon': 'ico',
            'excluded': False,
        }
        with self.assertRaises(ValueError):
            lib._validate_categories({'cat1': cat3}, schema)


class TestMetadataSection(unittest.TestCase):
    """Tests for metadata section operations via SettingsAPI."""

    def setUp(self):
        # Minimal ledger_data with all required sections
        lib.settings.ledger_data = {
            'spreadsheet': {},
            'header': {},
            'metadata': {
                'name': 'Test',
                'description': 'Desc',
                'locale': 'en',
                'summary_mode': 'A',
                'hide_empty_categories': False,
                'exclude_negative': False,
                'exclude_zero': False,
                'exclude_positive': False,
                'yearmonth': '2020-01',
                'span': 12,
                'theme': 'light'
            },
            'mapping': {k: 'x' for k in lib.DATA_MAPPING_KEYS},
            'categories': {
                'c': {
                    'display_name': 'N',
                    'color': '#000000',
                    'description': 'd',
                    'icon': 'i',
                    'excluded': False,
                }
            }
        }
        # Track saves
        self.saved = []
        lib.settings.save_section = lambda name: self.saved.append(name)

    def test_get_section_metadata_copy(self):
        data = lib.settings.get_section('metadata')
        self.assertEqual(data['name'], 'Test')
        # Mutate copy
        data['name'] = 'Changed'
        # Original stays the same
        self.assertEqual(lib.settings.ledger_data['metadata']['name'], 'Test')

    def test_set_section_metadata_success(self):
        new_meta = {
            'name': 'New',
            'description': 'D',
            'locale': 'fr',
            'summary_mode': 'B',
            'hide_empty_categories': True,
            'exclude_negative': True,
            'exclude_zero': True,
            'exclude_positive': True,
            'yearmonth': '2021-05',
            'span': 6,
            'theme': 'dark'
        }
        # Should succeed and save
        lib.settings.set_section('metadata', new_meta)
        self.assertEqual(lib.settings.ledger_data['metadata'], new_meta)
        self.assertIn('metadata', self.saved)

    def test_set_section_metadata_invalid(self):
        # Missing required metadata keys should raise
        bad_meta = {'name': 'X'}
        with self.assertRaises(Exception):
            lib.settings.set_section('metadata', bad_meta)
        # Nothing saved
        self.assertEqual(self.saved, [])


class TestSettingsAPI(unittest.TestCase):
    def setUp(self):
        # use instance without init to avoid file ops
        self.s = lib.SettingsAPI.__new__(lib.SettingsAPI)

    def test_validate_client_secret_errors_and_success(self):
        # missing sections
        with self.assertRaises(ClientSecretInvalidException):
            lib.settings.validate_client_secret({})
        # installed present but missing keys
        with self.assertRaises(ClientSecretInvalidException):
            lib.settings.validate_client_secret({'installed': {}})
        # valid installed
        good = {'installed': {k: 'v' for k in lib.settings.required_client_secret_keys}}
        self.assertEqual(lib.settings.validate_client_secret(good), 'installed')
        # valid web only
        good2 = {'web': {k: 'v' for k in lib.settings.required_client_secret_keys}}
        self.assertEqual(lib.settings.validate_client_secret(good2), 'web')
        # both installed and web: should pick installed
        both = {
            'installed': {k: 'i' for k in lib.settings.required_client_secret_keys},
            'web': {k: 'w' for k in lib.settings.required_client_secret_keys},
        }
        self.assertEqual(lib.settings.validate_client_secret(both), 'installed')

    def test_validate_ledger_data_errors_and_success(self):
        # empty data
        with self.assertRaises(RuntimeError):
            lib.settings.validate_ledger_data(data={})
        # missing mapping
        data = make_minimal_ledger = {
            'spreadsheet': {},
            'header': {},
            'metadata': {},
            'categories': {'c': {
                'display_name': 'N', 'color': '#000000',
                'description': 'd', 'icon': 'i', 'excluded': False
            }},
        }
        with self.assertRaises(LedgerConfigInvalidException):
            lib.settings.validate_ledger_data(data=data)
        # minimal valid data
        valid = make_minimal_ledger = {
            'spreadsheet': {},
            'header': {},
            'metadata': {},
            'mapping': {k: 'x' for k in lib.DATA_MAPPING_KEYS},
            'categories': {'c': {
                'display_name': 'N', 'color': '#000000',
                'description': 'd', 'icon': 'i', 'excluded': False
            }},
        }
        # should not raise
        lib.settings.validate_ledger_data(data=valid)

    def test_get_section_and_set_section_errors_and_copy(self):
        # unknown get
        with self.assertRaises(KeyError):
            _ = lib.settings.get_section('bad')  # type: ignore
        # unknown set
        with self.assertRaises(ValueError):
            lib.settings.set_section('bad', {})
        # get_section returns a copy
        lib.settings.ledger_data = {'sec': {'a': 1}}
        out = lib.settings.get_section('sec')
        self.assertEqual(out, {'a': 1})
        self.assertIsNot(out, lib.settings.ledger_data['sec'])
        # client_secret copy
        lib.settings.client_secret_data = {'k': 2}
        out2 = lib.settings.get_section('client_secret')
        self.assertEqual(out2, {'k': 2})
        self.assertIsNot(out2, lib.settings.client_secret_data)

    def test_set_section_client_secret_success(self):
        # override save_section to avoid file write
        saved = []
        lib.settings.save_section = lambda name: saved.append(name)
        # valid data
        new = {'installed': {k: 'v' for k in lib.settings.required_client_secret_keys}}
        # should not raise
        lib.settings.set_section('client_secret', new)
        self.assertIs(lib.settings.client_secret_data, new)
        self.assertEqual(saved, ['client_secret'])


if __name__ == '__main__':
    unittest.main()
