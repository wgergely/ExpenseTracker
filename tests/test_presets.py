# tests/test_presets.py
"""
Comprehensive unit‑tests for ExpenseTracker.settings.presets.lib

Run with:
    python -m unittest tests.test_presets
"""
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

from ExpenseTracker.settings import lib
from ExpenseTracker.settings.presets.lib import (
    MAX_BACKUPS,
    PRESET_FORMAT,
    PresetItem,
    PresetsAPI,
)
from tests.base import BaseTestCase

DUMMY_SECRET = {
    "installed": {
        "client_id": "dummy",
        "project_id": "dummy",
        "client_secret": "dummy",
        "auth_uri": "https://example",
        "token_uri": "https://example",
    }
}


def _write_json(p: Path, data: Dict[str, Any]) -> None:
    with p.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=4, ensure_ascii=False)


def _make_preset_zip(
        dest: Path,
        ledger_data: Optional[Dict[str, Any]] = None,
        extra_member: Optional[tuple[str, bytes]] = None,
) -> None:
    """Create a minimal preset ZIP with a (possibly custom) ledger.json."""
    ledger_data = ledger_data or lib.settings.ledger_data
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr(lib.settings.ledger_path.name, json.dumps(ledger_data, indent=2))
        if extra_member:
            zf.writestr(*extra_member)


class PresetsAPITests(BaseTestCase):
    """
    Adds directory‑hygiene for presets & templates **without** mocks/patches.
    """

    _presets_backup: Optional[Path]
    _template_backup: Optional[Path]

    def setUp(self) -> None:
        super().setUp()

        self._presets_backup = None
        if lib.settings.presets_dir.exists():
            self._presets_backup = Path(tempfile.mkdtemp(prefix="expensetracker_presets_"))
            shutil.copytree(lib.settings.presets_dir, self._presets_backup, dirs_exist_ok=True)
            shutil.rmtree(lib.settings.presets_dir)
        lib.settings.presets_dir.mkdir(parents=True, exist_ok=True)

        self._template_backup = None
        if lib.settings.template_dir.exists():
            self._template_backup = Path(tempfile.mkdtemp(prefix="expensetracker_tpl_"))
            shutil.copytree(lib.settings.template_dir, self._template_backup, dirs_exist_ok=True)
            shutil.rmtree(lib.settings.template_dir)
        lib.settings.template_dir.mkdir(parents=True, exist_ok=True)
        (lib.settings.template_dir / "icons").mkdir()
        # minimal, *valid* templates expected by ConfigPaths
        _write_json(
            lib.settings.template_dir / "client_secret.json.template",
            DUMMY_SECRET,
        )
        _write_json(
            lib.settings.template_dir / "ledger.json.template",
            {
                "spreadsheet": {"id": "dummy", "sheet": "Sheet1"},
                "header": {"Date": "date"},
                "metadata": {
                    k: ("" if "description" in k else False if "exclude" in k else 0 if k == "span" else "en_GB")
                    for k in lib.METADATA_KEYS},
                "mapping": {k: k for k in lib.DATA_MAPPING_KEYS},
                "categories": {
                    "dummy": {
                        "display_name": "Dummy",
                        "color": "#FFFFFF",
                        "description": "",
                        "icon": "question",
                        "excluded": False,
                    }
                },
            },
        )

        # re‑verify config paths after template reset
        lib.settings._verify_and_prepare()

        # ensure client_secret exists for preset operations
        _write_json(self.config_paths.client_secret_path, DUMMY_SECRET)

        # finally, create PresetsAPI for the tests
        self.api: PresetsAPI = PresetsAPI()  # type: ignore[arg-type]
        lib.presets = self.api  # convenience shortcut used by the app

    def tearDown(self) -> None:
        # restore template_dir
        if self._template_backup:
            if lib.settings.template_dir.exists():
                shutil.rmtree(lib.settings.template_dir)
            shutil.copytree(self._template_backup, lib.settings.template_dir, dirs_exist_ok=True)
            shutil.rmtree(self._template_backup, ignore_errors=True)

        # restore presets_dir
        if self._presets_backup:
            if lib.settings.presets_dir.exists():
                shutil.rmtree(lib.settings.presets_dir)
            shutil.copytree(self._presets_backup, lib.settings.presets_dir, dirs_exist_ok=True)
            shutil.rmtree(self._presets_backup, ignore_errors=True)

        super().tearDown()

    def test_initial_list_contains_active(self):
        self.assertGreaterEqual(len(self.api), 1)
        active = self.api[0]
        self.assertTrue(active.is_active)
        self.assertFalse(active.is_saved)

    def test_create_duplicate_and_rename(self):
        item = self.api.new("MyPreset", "desc")
        self.assertTrue(item.is_saved)
        self.assertEqual(item.name, "MyPreset")

        dup = self.api.duplicate(item, "Copy")
        self.assertEqual(dup.name, "Copy")
        self.assertTrue(dup.is_saved)

        ok = self.api.rename(dup, "CopyRenamed")
        self.assertTrue(ok)
        self.assertEqual(dup.name, "CopyRenamed")

    def test_set_description_propagates(self):
        item = self.api.new("WithDesc", "old")
        self.api.set_description(item, "new")
        self.assertEqual(item.description, "new")

    def test_backup_and_restore(self):
        self.api.new("B&R", "d")  # guarantee a name for live ledger
        backup_item = self.api.backup()
        self.assertTrue(backup_item.is_saved)

        ok = self.api.restore()
        self.assertTrue(ok)

    def test_activate_and_update_roundtrip(self):
        item = self.api.new("Round", "d")
        self.assertTrue(self.api.activate(item))  # activate saved preset

        hdr = lib.settings.get_section("header")
        hdr["X"] = "string"
        lib.settings.set_section("header", hdr)

        item._init_item()
        self.assertTrue(item.is_out_of_date)
        self.assertTrue(self.api.update(item))
        self.assertFalse(item.is_out_of_date)

    def test_new_fails_without_required_files(self):
        tmp = self.config_paths.ledger_path.with_suffix(".bak")
        self.config_paths.ledger_path.rename(tmp)
        with self.assertRaises(RuntimeError):
            self.api.new("ShouldFail")
        tmp.rename(self.config_paths.ledger_path)

    def test_rename_empty_name_noop(self):
        item = self.api.new("Temp")
        self.assertFalse(self.api.rename(item, ""))

    def test_set_description_on_live_only(self):
        active = self.api[0]
        self.assertTrue(self.api.set_description(active, "live‑only"))
        self.assertEqual(active.description, "live‑only")

    def test_update_fails_if_not_active(self):
        saved = self.api.new("NotActive")
        self.assertFalse(self.api.update(saved))

    def test_update_fails_on_live_item(self):
        self.assertFalse(self.api.update(self.api[0]))

    def test_remove_live_returns_false(self):
        self.assertFalse(self.api.remove(self.api[0]))

    def test_restore_no_backup_returns_false(self):
        for p in self.config_paths.presets_dir.glob(f"backup_*.{PRESET_FORMAT}"):
            p.unlink()
        self.assertFalse(self.api.restore())

    def test_load_presets_skips_corrupt_zip(self):
        bad = self.config_paths.presets_dir / f"corrupt.{PRESET_FORMAT}"
        bad.write_bytes(b"not a zip")
        api = PresetsAPI()
        self.assertIsNone(api.get("corrupt"))

    def test_open_ledger_malformed_json(self):
        z = self.config_paths.presets_dir / f"badjson.{PRESET_FORMAT}"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr(lib.settings.ledger_path.name, "oops")
        with self.assertRaises(ValueError):
            PresetItem.open_ledger(z)

    def test_activate_rejects_zip_with_traversal(self):
        evil = self.config_paths.presets_dir / f"evil.{PRESET_FORMAT}"
        _make_preset_zip(evil, extra_member=("../evil.txt", b"x"))
        item = PresetItem(evil)
        self.assertFalse(
            self.api.activate(item, backup=False),
            "activate() should return False when ZIP contains unsafe paths",
        )

    def test_duplicate_of_non_saved_raises(self):
        with self.assertRaises(RuntimeError):
            self.api.duplicate(self.api[0], "dup")

    def test_sanitize_produces_safe_unique_name(self):
        raw = r'inv*alid:name?'
        safe1 = self.api._sanitize(raw)

        # force a collision
        taken = self.config_paths.presets_dir / f"{safe1}.{PRESET_FORMAT}"
        taken.parent.mkdir(parents=True, exist_ok=True)
        taken.touch()

        safe2 = self.api._sanitize(raw)
        self.assertNotEqual(safe1, safe2)
        for s in (safe1, safe2):
            self.assertNotRegex(s, r'[\\/*?":<>|]')

    def test_backup_retention(self):
        for _ in range(MAX_BACKUPS + 3):
            self.api.backup()
        backups = list(self.config_paths.presets_dir.glob(f"backup_*.{PRESET_FORMAT}"))
        self.assertLessEqual(len(backups), MAX_BACKUPS)
