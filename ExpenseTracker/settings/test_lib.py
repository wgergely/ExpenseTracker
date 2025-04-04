import shutil
import tempfile
import unittest
from pathlib import Path

from .lib import SettingsAPI


class TestSettingsAPI(unittest.TestCase):
    def setUp(self):
        """
        Backup any existing /tmp/ExpenseTracker, then remove it so each test has a clean slate.
        """
        self.temp_dir = Path(tempfile.gettempdir())
        self.expense_tracker_dir = self.temp_dir / 'ExpenseTracker'
        self.backup_dir = self.temp_dir / 'ExpenseTracker_backup'

        if self.expense_tracker_dir.exists():
            if self.backup_dir.exists():
                shutil.rmtree(self.backup_dir)
            shutil.move(str(self.expense_tracker_dir), str(self.backup_dir))

        self.settings_api = SettingsAPI()

    def tearDown(self):
        """
        Remove test's ExpenseTracker dir and restore any backup.
        """
        if self.expense_tracker_dir.exists():
            shutil.rmtree(self.expense_tracker_dir)

        if self.backup_dir.exists():
            shutil.move(str(self.backup_dir), str(self.expense_tracker_dir))

    def test_initial_load(self):
        self.assertIsInstance(self.settings_api.ledger_data, dict)
        self.assertIsInstance(self.settings_api.client_secret_data, dict)

    def test_set_get_section_ledger(self):
        new_header = {'Date': 'date', 'ID': 'int'}
        self.settings_api.set_section('header', new_header)
        retrieved_header = self.settings_api.get_section('header')
        self.assertEqual(retrieved_header, new_header)

    def test_ledger_validation_fail_revert(self):
        original_ledger = dict(self.settings_api.ledger_data)
        invalid_ledger = {
            'sheet': 'Sheet1'
            # Missing 'id', 'header', 'data_header_mapping', 'categories'
        }
        with self.assertRaises(ValueError):
            self.settings_api.set_section('ledger', invalid_ledger)
        self.assertEqual(self.settings_api.ledger_data, original_ledger)

    def test_set_client_secret_invalid_type_raises(self):
        with self.assertRaises(ValueError):
            self.settings_api.set_section('client_secret', 'I am not a dict')

    def test_save_section_ledger(self):
        self.settings_api.ledger_data['id'] = 'HelloLedger'
        self.settings_api.save_section('ledger')
        reloaded = SettingsAPI().ledger_data
        self.assertEqual(reloaded['id'], 'HelloLedger')

    def test_save_section_client_secret(self):
        self.settings_api.client_secret_data['newKey'] = 'secretValue'
        self.settings_api.save_section('client_secret')
        reloaded = SettingsAPI().client_secret_data
        self.assertEqual(reloaded['newKey'], 'secretValue')

    def test_revert_section_ledger(self):
        self.settings_api.ledger_data['id'] = 'WillBeReverted'
        self.settings_api.save_section('ledger')
        self.settings_api.revert_section('ledger')
        loaded_after_revert = self.settings_api.ledger_data
        self.assertNotEqual(loaded_after_revert.get('id'), 'WillBeReverted')

    def test_unicode_support(self):
        unicode_str = 'こんにちは世界'
        self.settings_api.ledger_data['id'] = unicode_str
        self.settings_api.save_section('ledger')
        reloaded_ledger = SettingsAPI().ledger_data
        self.assertEqual(reloaded_ledger['id'], unicode_str)

        self.settings_api.client_secret_data['unicode_value'] = unicode_str
        self.settings_api.save_section('client_secret')
        reloaded_cs = SettingsAPI().client_secret_data
        self.assertEqual(reloaded_cs['unicode_value'], unicode_str)

    def test_create_list_remove_preset(self):
        # Modify and save data so the preset has unique values
        self.settings_api.ledger_data['id'] = 'PresetLedger'
        self.settings_api.client_secret_data['preset_field'] = 'SecretPreset'
        self.settings_api.save_all()

        preset_name = 'testPreset'
        self.settings_api.create_preset(preset_name)

        # Check preset is listed
        presets = self.settings_api.list_presets()
        self.assertIn(preset_name, presets)

        # Remove the preset
        self.settings_api.remove_preset(preset_name)
        presets_after_removal = self.settings_api.list_presets()
        self.assertNotIn(preset_name, presets_after_removal)

    def test_create_and_load_preset(self):
        """
        Create a preset from modified data, revert to template, then load preset
        and ensure data is restored.
        """
        # 1) Modify current data
        original_ledger_id = 'MyUniqueLedgerId'
        original_secret_key = 'MySecretKey123'
        self.settings_api.ledger_data['id'] = original_ledger_id
        self.settings_api.client_secret_data['some_secret'] = original_secret_key
        self.settings_api.save_all()

        # 2) Create preset
        preset_name = 'testLoadPreset'
        self.settings_api.create_preset(preset_name)

        # 3) Revert to template (so we can see the preset's effect clearly)
        self.settings_api.revert_section('ledger')
        self.settings_api.revert_section('client_secret')
        self.assertNotEqual(self.settings_api.ledger_data.get('id'), original_ledger_id)
        self.assertNotEqual(self.settings_api.client_secret_data.get('some_secret'), original_secret_key)

        # 4) Load the preset
        self.settings_api.load_preset(preset_name)
        # 5) Confirm data is restored
        self.assertEqual(self.settings_api.ledger_data.get('id'), original_ledger_id)
        self.assertEqual(self.settings_api.client_secret_data.get('some_secret'), original_secret_key)


if __name__ == '__main__':
    unittest.main()
