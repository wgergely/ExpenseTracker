import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from PySide6 import QtWidgets

from .lib import (
    PresetItem, PresetsAPI, PresetType
)
from ...settings import lib

temp_dir = Path(tempfile.gettempdir()) / 'ExpenseTracker_testdata'


def setUpModule():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    if not QtWidgets.QApplication.instance():
        QtWidgets.QApplication([])


class TestPresetItem(unittest.TestCase):
    def setUp(self):
        # Prepare backup directory
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        # Backup existing config and presets
        shutil.copytree(lib.settings.config_dir, temp_dir / lib.settings.config_dir.name)
        shutil.copytree(lib.settings.presets_dir, temp_dir / lib.settings.presets_dir.name)
        # Clear presets directory for a clean test environment
        if lib.settings.presets_dir.exists():
            shutil.rmtree(lib.settings.presets_dir)
        lib.settings.presets_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(lib.settings.presets_dir)
        shutil.rmtree(lib.settings.config_dir)

        # copy back the backup
        shutil.copytree(temp_dir / lib.settings.config_dir.name, lib.settings.config_dir)
        shutil.copytree(temp_dir / lib.settings.presets_dir.name, lib.settings.presets_dir)

        # remove the temp dir
        shutil.rmtree(temp_dir)

    def test_open_ledger_missing_ledger(self):
        # ZIP without ledger.json should raise RuntimeError
        temp = Path(tempfile.mkdtemp())
        zip_path = temp / 'no_ledger.zip'
        with zipfile.ZipFile(zip_path, 'w'):
            pass
        with self.assertRaises(RuntimeError):
            PresetItem.open_ledger(zip_path)

    def test_open_ledger_malformed_json(self):
        # ZIP with invalid JSON in ledger.json should raise ValueError
        temp = Path(tempfile.mkdtemp())
        zip_path = temp / 'bad_json.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr(lib.settings.ledger_path.name, 'not a json')
        with self.assertRaises(ValueError):
            PresetItem.open_ledger(zip_path)

    def test_init_item_invalid_missing_name(self):
        # Missing metadata.name yields Invalid preset
        temp = Path(tempfile.mkdtemp())
        zip_path = temp / 'missing_name.zip'
        data = {'metadata': {'description': 'desc'}}
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr(lib.settings.ledger_path.name, json.dumps(data))
        item = PresetItem(zip_path)
        self.assertFalse(item.is_valid)
        self.assertEqual(item.type, PresetType.Invalid)

    def test_init_item_valid(self):
        # Valid metadata yields Saved preset
        temp = Path(tempfile.mkdtemp())
        zip_path = temp / 'valid.zip'
        data = {'metadata': {'name': 'test', 'description': 'desc'}}
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr(lib.settings.ledger_path.name, json.dumps(data))
        item = PresetItem(zip_path)
        self.assertTrue(item.is_valid)
        self.assertTrue(item.is_saved)
        self.assertEqual(item.name, 'test')
        self.assertEqual(item.description, 'desc')

    def test_load_current(self):
        # Current live config yields Active, active, unmodified preset
        item = PresetItem(None)
        self.assertEqual(item.type, PresetType.Active)
        self.assertTrue(item.is_active)
        self.assertFalse(item.is_out_of_date)
        self.assertTrue(item.is_valid)


class TestPresetAPI(unittest.TestCase):
    def setUp(self):
        # Prepare backup directory
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        # Backup existing config and presets
        shutil.copytree(lib.settings.config_dir, temp_dir / lib.settings.config_dir.name)
        shutil.copytree(lib.settings.presets_dir, temp_dir / lib.settings.presets_dir.name)
        # Clear presets directory for a clean test environment
        if lib.settings.presets_dir.exists():
            shutil.rmtree(lib.settings.presets_dir)
        lib.settings.presets_dir.mkdir(parents=True, exist_ok=True)

        self.api = PresetsAPI()

    def tearDown(self):
        shutil.rmtree(lib.settings.presets_dir)
        shutil.rmtree(lib.settings.config_dir)

        # copy back the backup
        shutil.copytree(temp_dir / lib.settings.config_dir.name, lib.settings.config_dir)
        shutil.copytree(temp_dir / lib.settings.presets_dir.name, lib.settings.presets_dir)

        # remove the temp dir
        shutil.rmtree(temp_dir)

    def test_initial_state(self):
        # Only live config present initially
        self.assertEqual(len(self.api), 1)
        live = self.api[0]
        self.assertIsInstance(live, PresetItem)
        self.assertTrue(live.is_active)
        self.assertFalse(live.is_out_of_date)
        self.assertTrue(live.is_valid)
        # __getitem__ errors
        with self.assertRaises(IndexError):
            _ = self.api[1]
        with self.assertRaises(TypeError):
            _ = self.api[1.5]
        with self.assertRaises(KeyError):
            _ = self.api['nonexistent']

    def test_new_get_remove(self):
        # Create new preset
        item = self.api.new('preset1', 'desc1')
        self.assertTrue(item.is_saved)
        self.assertEqual(item.name, 'preset1')
        self.assertEqual(item.description, 'desc1')
        # Retrieve
        self.assertIs(self.api.get('preset1'), item)
        # Remove
        self.assertTrue(self.api.remove(item))
        self.assertIsNone(self.api.get('preset1'))
        self.assertFalse(item.path.exists())

    def test_rename(self):
        item = self.api.new('oldname', 'd')
        old_path = item.path
        result = self.api.rename(item, 'newname')
        self.assertTrue(result)
        self.assertEqual(item.name, 'newname')
        self.assertNotEqual(item.path, old_path)
        self.assertFalse(old_path.exists())
        self.assertTrue(item.path.exists())

    def test_duplicate_and_remove(self):
        item = self.api.new('orig', 'desc')
        dup = self.api.duplicate(item, 'copy')
        self.assertTrue(dup.is_saved)
        self.assertEqual(dup.name, 'copy')
        self.assertEqual(dup.description, item.description)
        # Remove duplicate
        self.assertTrue(self.api.remove(dup))
        self.assertIsNone(self.api.get('copy'))
        # Duplicate errors
        with self.assertRaises(RuntimeError):
            self.api.duplicate(PresetItem(None), 'fail')
        with self.assertRaises(RuntimeError):
            self.api.duplicate(item, 'orig')

    def test_activate_and_restore_cycle(self):
        # Record initial metadata name
        initial = lib.settings['name']
        item = self.api.new('activate_test', 'desc')
        # Activate preset
        self.assertTrue(self.api.activate(item))
        # Check ledger.json in config_dir
        # Read live config ledger.json after activation
        data = json.loads(lib.settings.ledger_path.read_text(encoding='utf-8'))
        self.assertEqual(data['metadata']['name'], 'activate_test')
        # Restore backup
        self.assertTrue(self.api.restore())
        # Read live config ledger.json after restore
        data2 = json.loads(lib.settings.ledger_path.read_text(encoding='utf-8'))
        self.assertEqual(data2['metadata']['name'], initial)

    def test_flags_after_creation(self):
        # Newly created preset should be saved but neither active nor modified
        item = self.api.new('flag1', 'desc')
        self.assertTrue(item.is_saved)
        self.assertFalse(item.is_active)
        self.assertFalse(item.is_out_of_date)

    def test_flags_active(self):
        # Creating then activating makes a preset active and unmodified
        item = self.api.new('flag_active', None)
        # Activate the preset
        self.assertTrue(self.api.activate(item))
        # Reload live settings
        lib.settings.ledger_data = lib.settings.load_ledger()
        # Load the same preset item fresh
        fresh = PresetItem(item.path)
        self.assertTrue(fresh.is_active)
        self.assertFalse(fresh.is_out_of_date)

    def test_flags_modified(self):
        # Create a snapshot of current config
        item = self.api.new('flag_mod', None)
        path = item.path
        # Modify live mapping section
        live_map = lib.settings.get_section('mapping')
        # Change a mapping key to simulate divergence
        live_map['date'] = live_map['amount']
        lib.settings.set_section('mapping', live_map)
        # Reload live settings
        lib.settings.ledger_data = lib.settings.load_ledger()
        # New PresetItem should detect modification
        modified = PresetItem(path)
        self.assertFalse(modified.is_active)
        self.assertTrue(modified.is_out_of_date)


if __name__ == '__main__':
    unittest.main()
