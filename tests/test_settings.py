# tests/test_settings.py
"""
Comprehensive unit‑tests for ExpenseTracker.settings.lib
(covers helpers, validators, ConfigPaths, and SettingsAPI).

Run with:
    python -m unittest tests.test_settings
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, Dict

from ExpenseTracker.settings import lib
from ExpenseTracker.settings.lib import (
    HEADER_TYPES,
    LEDGER_SCHEMA,
    SettingsAPI,
    _validate_categories,
    _validate_header,
    _validate_mapping,
    is_valid_hex_color,
    parse_merge_mapping,
)
from ExpenseTracker.status import status
from tests.base import BaseTestCase  # (your helper from the previous messages)

HEADER_FIXTURE = {
    "Date": "date",
    "Amount": "float",
    "Description": "string",
    "Category": "string",
    "Account": "string",
}
META_FIXTURE: Dict[str, Any] = {
    "name": "",
    "description": "",
    "locale": "en_US",
    "summary_mode": "normal",
    "hide_empty_categories": False,
    "exclude_negative": False,
    "exclude_zero": False,
    "exclude_positive": False,
    "yearmonth": "",
    "span": 0,
    "theme": "light",
    "loess_fraction": 0.25,
    "negative_span": 0,
}
DUMMY_SECRET = {
    "installed": {
        "client_id": "dummy",
        "project_id": "dummy",
        "client_secret": "dummy",
        "auth_uri": "https://example",
        "token_uri": "https://example",
    }
}


def minimal_ledger() -> Dict[str, Any]:
    return {
        "spreadsheet": {"id": "dummy", "sheet": "dummy"},
        "header": HEADER_FIXTURE,
        "metadata": META_FIXTURE.copy(),
        "mapping": {
            "date": "Date",
            "amount": "Amount",
            "description": "Description",
            "category": "Category",
            "account": "Account",
        },
        "categories": {
            "cash": {
                "display_name": "Cash",
                "color": "#00FF00",
                "description": "Green money",
                "icon": "mdi:cash",
                "excluded": False,
            }
        },
    }


def write_json(p: Path, data: Dict[str, Any]) -> None:
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


class HelperFunctionTests(unittest.TestCase):
    def test_hex_colour_validation(self):
        self.assertTrue(is_valid_hex_color("#abcdef"))
        self.assertFalse(is_valid_hex_color("#abcdex"))
        self.assertFalse(is_valid_hex_color("abcdef"))

    def test_parse_merge_mapping(self):
        self.assertEqual(parse_merge_mapping("A|B+C"), ["A", "B", "C"])
        self.assertEqual(parse_merge_mapping("   "), [])


class ValidatorTests(unittest.TestCase):
    def test_validate_header_good(self):
        _validate_header({"A": "string", "B": "float"}, HEADER_TYPES)  # no raise

    def test_validate_header_bad_type(self):
        with self.assertRaises(TypeError):
            _validate_header({"A": 123}, HEADER_TYPES)

    def test_validate_header_bad_value(self):
        with self.assertRaises(ValueError):
            _validate_header({"A": "money"}, HEADER_TYPES)

    def _good_mapping(self) -> Dict[str, str]:
        return {
            "date": "Date",
            "amount": "Amount",
            "description": "Desc|Note",  # allowed multi
            "category": "Cat",
            "account": "Acc",
        }

    def test_validate_mapping_good(self):
        _validate_mapping(self._good_mapping(), LEDGER_SCHEMA["mapping"])

    def test_validate_mapping_missing_key(self):
        bad = self._good_mapping()
        bad.pop("account")
        with self.assertRaises(ValueError):
            _validate_mapping(bad, LEDGER_SCHEMA["mapping"])

    def test_validate_mapping_unallowed_multi(self):
        bad = self._good_mapping()
        bad["date"] = "Col1|Col2"
        with self.assertRaises(ValueError):
            _validate_mapping(bad, LEDGER_SCHEMA["mapping"])

    def test_validate_categories_good(self):
        good = {
            "food": {
                "display_name": "Food",
                "color": "#123ABC",
                "description": "Meals",
                "icon": "utensils",
                "excluded": False,
            }
        }
        _validate_categories(good, LEDGER_SCHEMA["categories"]["item_schema"])

    def test_validate_categories_bad_colour(self):
        bad = {
            "food": {
                "display_name": "Food",
                "color": "red",
                "description": "Meals",
                "icon": "utensils",
                "excluded": False,
            }
        }
        with self.assertRaises(ValueError):
            _validate_categories(bad, LEDGER_SCHEMA["categories"]["item_schema"])


class RealTemplateSmokeTest(BaseTestCase):
    def test_templates_exist(self):
        cp = lib.ConfigPaths()
        self.assertTrue(cp.client_secret_template.exists())
        self.assertTrue(cp.ledger_template.exists())
        self.assertTrue(cp.icon_dir.is_dir())


class SettingsAPIBehaviour(BaseTestCase):
    """Full functional coverage for SettingsAPI."""

    # utility for tests that need to manipulate header quickly
    def _apply_header_cfg(self, hdr: Dict[str, str] | None = None):
        hdr = hdr or HEADER_FIXTURE
        self.api.ledger_data["header"] = hdr
        self.api.save_section("header")

    def setUp(self) -> None:
        super().setUp()

        # replace ledger + client_secret with pristine minimal versions
        write_json(self.config_paths.ledger_path, minimal_ledger())
        write_json(self.config_paths.client_secret_path, DUMMY_SECRET)

        # reload SettingsAPI with the fresh files
        self.api: SettingsAPI = lib.settings
        self.api.load_ledger()
        self.api.load_client_secret()

    def test_metadata_get_set_and_coercion(self):
        self.api["span"] = "6"  # string → int coercion
        self.assertEqual(self.api["span"], 6)
        with self.assertRaises(KeyError):
            _ = self.api["bogus"]

    def test_metadata_wrong_type_conversion_failure(self):
        with self.assertRaises(ValueError):
            self.api["loess_fraction"] = "not‑a‑float"

    def test_set_section_header_invalid_value_rollback(self):
        header = self.api.get_section("header")
        header["Bad"] = "money"  # not allowed

        with self.assertRaises(Exception):
            self.api.set_section("header", header)

        # ensure rollback happened (Bad key not present)
        self.assertNotIn("Bad", self.api.get_section("header"))

    def test_set_section_mapping_invalid_multi(self):
        mapping = self.api.get_section("mapping")
        mapping["date"] = "Col1|Col2"
        with self.assertRaises(Exception):
            self.api.set_section("mapping", mapping)

    def test_set_section_categories_bad_hex(self):
        cats = self.api.get_section("categories")
        key = next(iter(cats))
        cats[key]["color"] = "red"
        with self.assertRaises(Exception):
            self.api.set_section("categories", cats)

    def test_reload_section(self):
        hdr = self.api.get_section("header")
        hdr["Extra"] = "string"
        self.api.set_section("header", hdr)

        # manually delete the key from file to simulate external change
        with self.api.ledger_path.open("r+", encoding="utf-8") as fp:
            data = json.load(fp)
            data["header"].pop("Extra")
            fp.seek(0)
            json.dump(data, fp, indent=4)
            fp.truncate()

        self.api.reload_section("header")
        self.assertNotIn("Extra", self.api.get_section("header"))

    def test_revert_section_metadata(self):
        # change metadata.theme to unique sentinel then revert
        meta = self.api.get_section("metadata")
        meta["theme"] = "__sentinel__"
        self.api.set_section("metadata", meta)
        self.assertEqual(self.api["theme"], "__sentinel__")

        self.api.revert_section("metadata")
        self.assertNotEqual(self.api["theme"], "__sentinel__")

    def test_validate_client_secret_missing_section(self):
        with self.assertRaises(status.ClientSecretInvalidException):
            self.api.validate_client_secret({"bogus": {}})

    def test_validate_client_secret_missing_fields(self):
        bad = {"installed": {"client_id": "only"}}
        with self.assertRaises(status.ClientSecretInvalidException):
            self.api.validate_client_secret(bad)

    def test_save_all_rollback_on_invalid_ledger(self):
        """`save_all()` must roll back the *file* when validation fails."""
        # break the schema: non‑string mapping value
        bad_mapping = self.api.get_section("mapping")
        bad_mapping["amount"] = 123
        self.api.ledger_data["mapping"] = bad_mapping  # direct mutation

        with self.assertRaises((TypeError, ValueError)):
            self.api.save_all()

        # -------- verify rollback on disk --------
        self.api.load_ledger()  # <‑ reload file
        self.assertIsInstance(
            self.api.get_section("mapping")["amount"], str,
            "ledger file was not rolled back to a valid state",
        )

    def test_save_section_unknown(self):
        with self.assertRaises(ValueError):
            self.api.save_section("does_not_exist")

    def test_block_signals(self):
        self.api.block_signals(True)
        self.api["exclude_zero"] = False  # should not emit, no exception
        self.api.block_signals(False)

    def test_client_secret_revert(self):
        # wipe file and ensure revert restores it
        self.api.client_secret_path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.api.load_client_secret()

        self.api.revert_client_secret_to_template()
        self.assertTrue(self.api.client_secret_path.exists())


class CategoryManagerTests(BaseTestCase):
    """Tests for the CategoryManager unified API."""

    def setUp(self) -> None:
        super().setUp()
        from ExpenseTracker.settings import lib
        base = minimal_ledger()
        base['categories'] = {
            'a': {'display_name': 'A', 'description': '', 'icon': 'i', 'color': '#111111', 'excluded': False},
            'b': {'display_name': 'B', 'description': '', 'icon': 'j', 'color': '#222222', 'excluded': False},
            'c': {'display_name': 'C', 'description': '', 'icon': 'k', 'color': '#333333', 'excluded': False},
        }
        write_json(self.config_paths.ledger_path, base)
        lib.settings.load_ledger()
        self.manager = lib.category_manager
        from ExpenseTracker.ui.actions import signals
        self.signals = signals

    def test_add_and_signal(self):
        calls = []
        self.signals.categoryAdded.connect(lambda name, idx: calls.append((name, idx)))
        data = {'display_name': 'D', 'description': '', 'icon': 'x', 'color': '#444444', 'excluded': False}
        self.manager.add_category('d', data, index=1)
        cats = lib.settings.get_section('categories')
        self.assertIn('d', cats)
        keys = list(cats.keys())
        self.assertEqual(keys[1], 'd')
        self.assertEqual(calls, [('d', 1)])

    def test_remove_and_signal(self):
        calls = []
        self.signals.categoryRemoved.connect(lambda name, idx: calls.append((name, idx)))
        # remove middle 'b'
        self.manager.remove_category('b')
        cats = lib.settings.get_section('categories')
        self.assertNotIn('b', cats)
        self.assertEqual(calls, [('b', 1)])

    def test_move_and_signal(self):
        calls = []
        self.signals.categoryOrderChanged.connect(lambda name, o, n: calls.append((name, o, n)))
        # move 'a' from 0 to 2
        self.manager.move_category(0, 2)
        cats = lib.settings.get_section('categories')
        keys = list(cats.keys())
        self.assertEqual(keys, ['b', 'c', 'a'])
        self.assertEqual(calls, [('a', 0, 2)])

    def test_update_palette_and_signal(self):
        calls = []
        self.signals.categoryPaletteChanged.connect(lambda name: calls.append(name))
        self.manager.update_palette('a', icon='newicon', color='#abcdef')
        cats = lib.settings.get_section('categories')
        self.assertEqual(cats['a']['icon'], 'newicon')
        self.assertEqual(cats['a']['color'], '#abcdef')
        self.assertEqual(calls, ['a'])
