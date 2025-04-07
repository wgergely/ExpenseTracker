import shutil
import tempfile
import unittest
from pathlib import Path

from .lib import settings, SettingsAPI


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

    def tearDown(self):
        """
        Remove test's ExpenseTracker dir and restore any backup.
        """
        if self.expense_tracker_dir.exists():
            shutil.rmtree(self.expense_tracker_dir)

        if self.backup_dir.exists():
            shutil.move(str(self.backup_dir), str(self.expense_tracker_dir))

    def test_initial_load(self):
        self.assertIsInstance(settings.ledger_data, dict)
        self.assertIsInstance(settings.client_secret_data, dict)

    def test_set_get_section_ledger(self):
        new_header = {'Date': 'date', 'ID': 'int'}
        settings.set_section('header', new_header)
        retrieved_header = settings.get_section('header')
        self.assertEqual(retrieved_header, new_header)

    def test_ledger_validation_fail_revert(self):
        original_ledger = dict(settings.ledger_data)
        invalid_ledger = {
            'worksheet': 'Sheet1'
        }
        with self.assertRaises(ValueError):
            settings.set_section('ledger', invalid_ledger)
        self.assertEqual(settings.ledger_data, original_ledger)

    def test_set_client_secret_invalid_type_raises(self):
        with self.assertRaises(ValueError):
            settings.set_section('client_secret', 'I am not a dict')

    def test_save_section_ledger(self):
        settings.ledger_data['id'] = 'HelloLedger'
        settings.save_section('ledger')
        reloaded = SettingsAPI().ledger_data
        self.assertEqual(reloaded['id'], 'HelloLedger')

    def test_save_section_client_secret(self):
        settings.client_secret_data['newKey'] = 'secretValue'
        settings.save_section('client_secret')
        reloaded = SettingsAPI().client_secret_data
        self.assertEqual(reloaded['newKey'], 'secretValue')

    def test_revert_section_ledger(self):
        settings.ledger_data['id'] = 'WillBeReverted'
        settings.save_section('ledger')
        settings.revert_section('ledger')
        loaded_after_revert = settings.ledger_data
        self.assertNotEqual(loaded_after_revert.get('id'), 'WillBeReverted')

    def test_unicode_support(self):
        unicode_str = 'こんにちは世界'
        settings.ledger_data['id'] = unicode_str
        settings.save_section('ledger')
        reloaded_ledger = SettingsAPI().ledger_data
        self.assertEqual(reloaded_ledger['id'], unicode_str)

        settings.client_secret_data['unicode_value'] = unicode_str
        settings.save_section('client_secret')
        reloaded_cs = SettingsAPI().client_secret_data
        self.assertEqual(reloaded_cs['unicode_value'], unicode_str)

    def test_create_list_remove_preset(self):
        # Modify and save data so the preset has unique values
        settings.ledger_data['id'] = 'PresetLedger'
        settings.client_secret_data['preset_field'] = 'SecretPreset'
        settings.save_all()

        preset_name = 'testPreset'
        settings.create_preset(preset_name)

        # Check preset is listed
        presets = settings.list_presets()
        self.assertIn(preset_name, presets)

        # Remove the preset
        settings.remove_preset(preset_name)
        presets_after_removal = settings.list_presets()
        self.assertNotIn(preset_name, presets_after_removal)

    def test_create_and_load_preset(self):
        """
        Create a preset from modified data, revert to template, then load preset
        and ensure data is restored.
        """
        # 1) Modify current data
        original_ledger_id = 'MyUniqueLedgerId'
        original_secret_key = 'MySecretKey123'
        settings.ledger_data['id'] = original_ledger_id
        settings.client_secret_data['some_secret'] = original_secret_key
        settings.save_all()

        # 2) Create preset
        preset_name = 'testLoadPreset'
        settings.create_preset(preset_name)

        # 3) Revert to template (so we can see the preset's effect clearly)
        settings.revert_section('ledger')
        settings.revert_section('client_secret')
        self.assertNotEqual(settings.ledger_data.get('id'), original_ledger_id)
        self.assertNotEqual(settings.client_secret_data.get('some_secret'), original_secret_key)

        # 4) Load the preset
        settings.load_preset(preset_name)
        # 5) Confirm data is restored
        self.assertEqual(settings.ledger_data.get('id'), original_ledger_id)
        self.assertEqual(settings.client_secret_data.get('some_secret'), original_secret_key)


if __name__ == '__main__':
    unittest.main()
