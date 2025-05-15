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
    LEDGER_SCHEMA,
    SettingsAPI,
    _validate_categories,
    _validate_header,
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
    # Return minimal valid ledger data using new 'headers' schema
    return {
        "spreadsheet": {"id": "dummy", "sheet": "dummy"},
        "headers": [
            {"name": "Id", "role": "id", "type": "int"},
            {"name": "Date", "role": "date", "type": "date"},
            {"name": "Amount", "role": "amount", "type": "float"},
            {"name": "Account", "role": "account", "type": "string"},
            {"name": "Description", "role": "description", "type": "string"},
        ],
        "metadata": META_FIXTURE.copy(),
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
    def test_validate_header_list_good(self):
        # Contains all singleton roles exactly once
        headers = [
            {"name": "IdCol", "role": "id", "type": "int"},
            {"name": "DateCol", "role": "date", "type": "date"},
            {"name": "AmountCol", "role": "amount", "type": "float"},
            {"name": "AccountCol", "role": "account", "type": "string"},
            {"name": "DescCol", "role": "description", "type": "string"},
            {"name": "NotesCol", "role": "notes", "type": "string"},
            {"name": "CatCol", "role": "category", "type": "string"},
        ]
        _validate_header(headers)  # should not raise

    def test_validate_header_missing_singleton(self):
        # Missing date role
        headers = [
            {"name": "IdCol", "role": "id", "type": "int"},
            {"name": "AmountCol", "role": "amount", "type": "float"},
            {"name": "AccountCol", "role": "account", "type": "string"},
        ]
        with self.assertRaises(Exception) as cm:
            _validate_header(headers)
        self.assertIn("Role \"date\" must be mapped to exactly one header", str(cm.exception))

    def test_validate_header_duplicate_singleton(self):
        # Duplicate amount role
        headers = [
            {"name": "IdCol", "role": "id", "type": "int"},
            {"name": "DateCol", "role": "date", "type": "date"},
            {"name": "Amount1", "role": "amount", "type": "float"},
            {"name": "Amount2", "role": "amount", "type": "float"},
            {"name": "AccountCol", "role": "account", "type": "string"},
        ]
        with self.assertRaises(Exception) as cm:
            _validate_header(headers)
        self.assertIn("Role \"amount\" must be mapped to exactly one header", str(cm.exception))

    def test_validate_header_invalid_structure(self):
        # None input is not a list
        with self.assertRaises(status.LedgerConfigInvalidException):
            _validate_header(None)  # type: ignore
        # Missing required 'type' key
        with self.assertRaises(status.LedgerConfigInvalidException):
            _validate_header([{"name": "X", "role": "date"}])
        # 'name' must be a string
        with self.assertRaises(status.LedgerConfigInvalidException):
            _validate_header([{"name": 123, "role": "date", "type": "date"}])  # type: ignore
        # Invalid role value
        headers_invalid_role = [
            {"name": "Id", "role": "id", "type": "int"},
            {"name": "Date", "role": "date", "type": "date"},
            {"name": "Amount", "role": "amount", "type": "float"},
            {"name": "Account", "role": "account", "type": "string"},
            {"name": "X", "role": "invalid", "type": "string"},
        ]
        with self.assertRaises(status.LedgerConfigInvalidException):
            _validate_header(headers_invalid_role)
        # Invalid type value
        headers_invalid_type = [
            {"name": "Id", "role": "id", "type": "int"},
            {"name": "Date", "role": "date", "type": "date"},
            {"name": "Amount", "role": "amount", "type": "float"},
            {"name": "Account", "role": "account", "type": "string"},
            {"name": "X", "role": "description", "type": "invalid_type"},
        ]
        with self.assertRaises(status.LedgerConfigInvalidException):
            _validate_header(headers_invalid_type)

    def test_validate_categories_good(self):
        good = {
            "food": {
                "display_name": "Food",
                "color": "#FF0000",
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

    # utility for tests that need to manipulate headers list
    def _apply_headers_cfg(self, hdrs: list[dict] | None = None):
        hdrs = hdrs or self.api.get_section("headers")
        self.api.ledger_data["headers"] = hdrs
        self.api.save_section("headers")

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

    def test_set_section_headers_invalid_value_rollback(self):
        headers = self.api.get_section("headers")
        # introduce invalid type in first header
        headers[0]["type"] = "invalid_type"

        with self.assertRaises(status.LedgerConfigInvalidException):
            self.api.set_section("headers", headers)

        # ensure rollback: first header type remains valid
        current = self.api.get_section("headers")
        self.assertIn(current[0]["type"], [t.value for t in lib.HeaderType])

    # mapping section deprecated: removed mapping tests

    def test_reload_section_headers(self):
        headers = self.api.get_section("headers")
        # append an extra header
        extra = {"name": "Extra", "role": "notes", "type": "string"}
        headers.append(extra)
        self.api.set_section("headers", headers)

        # manually remove extra in file to simulate external change
        with self.api.ledger_path.open("r+", encoding="utf-8") as fp:
            data = json.load(fp)
            data["headers"] = [h for h in data["headers"] if h.get("name") != "Extra"]
            fp.seek(0)
            json.dump(data, fp, indent=4)
            fp.truncate()

        self.api.reload_section("headers")
        names = [h["name"] for h in self.api.get_section("headers")]
        self.assertNotIn("Extra", names)

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
        """`save_all()` must roll back the file when validation fails due to headers."""
        # break the schema: invalid header role
        headers = self.api.get_section("headers")
        headers[0]["role"] = "invalid_role"
        self.api.ledger_data["headers"] = headers  # direct mutation

        with self.assertRaises(status.LedgerConfigInvalidException):
            self.api.save_all()

        # verify rollback on disk: reload and ensure valid header roles
        self.api.load_ledger()
        roles = [h["role"] for h in self.api.get_section("headers")]
        self.assertTrue(all(role in [r.value for r in lib.HeaderRole] for role in roles),
            "ledger file was not rolled back to a valid state")

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
