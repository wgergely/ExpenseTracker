"""Unittest base class for creating a clean test environment."""
import enum
import functools
import json
import logging
import os
import shutil
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Sequence, Callable, Any
from unittest.mock import patch

from PySide6 import QtWidgets, QtCore
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from ExpenseTracker.core import auth
from ExpenseTracker.core import database
from ExpenseTracker.core import sync
from ExpenseTracker.settings import lib


class TestAuthEnvKeys(enum.Enum):
    """Environment variable keys for test configuration."""
    TEST_CLIENT_SECRET_ENV_KEY = enum.auto()
    TEST_SERVICE_ACCOUNT_CREDS_ENV_KEY = enum.auto()
    TEST_SPREADHSEET_ID_ENV_KEY = enum.auto()
    TEST_SPREADHSEET_NAME_ENV_KEY = enum.auto()


def patch_get_creds() -> Credentials:
    """Load service‐account creds, log their state, and attempt a refresh for debugging."""
    service_account_info = json.loads(
        os.environ[TestAuthEnvKeys.TEST_SERVICE_ACCOUNT_CREDS_ENV_KEY.name]
    )
    scopes: Sequence[str] = ['https://www.googleapis.com/auth/spreadsheets']

    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=scopes
    )

    # Log initial state
    logging.debug(
        'Initial creds state: valid=%s, expired=%s, token=%r, expiry=%s, scopes=%s, service_account_email=%s',
        creds.valid, creds.expired, creds.token, creds.expiry,
        creds.scopes, creds.service_account_email
    )

    # Try to refresh (this will fetch a fresh access token)
    try:
        creds.refresh(Request())
        logging.debug('Refreshed credentials successfully; new expiry=%s', creds.expiry)
    except RefreshError as exc:
        logging.error(
            'Failed to refresh credentials: %s',
            exc,
            exc_info=True
        )

    # Log post‐refresh state
    logging.debug(
        'Post‐refresh creds state: valid=%s, expired=%s, token=%r, expiry=%s',
        creds.valid, creds.expired, creds.token, creds.expiry
    )

    return creds


@contextmanager
def mute_ui_signals():
    from ExpenseTracker.ui.actions import signals
    blocker = QtCore.QSignalBlocker(signals)  # blocks every signal in `signals`
    try:
        yield
    finally:
        # QSignalBlocker.__exit__ re‑enables automatically, but make it explicit:
        del blocker


class BaseTestCase(unittest.TestCase):
    """Base test case that sets up and tears down a temporary config directory."""

    config_paths: lib.ConfigPaths
    backup_dir: Optional[str]

    def setUp(self) -> None:
        """Set up a clean config directory and reinitialize all APIs."""
        # Ensure headless Qt
        if 'QT_QPA_PLATFORM' not in os.environ:
            os.environ['QT_QPA_PLATFORM'] = 'offscreen'
            logging.debug(f'QT_QPA_PLATFORM set to offscreen for headless testing.')

        # Ensure a QApplication is available
        if not QtWidgets.QApplication.instance():
            QtWidgets.QApplication([])  # type: ignore
            logging.debug(f'QtWidgets.QApplication initialized for tests.')

        # Prepare config paths
        self.config_paths = lib.ConfigPaths()
        self.backup_dir = None
        config_dir: Path = self.config_paths.config_dir

        # Backup and clear the existing config directory
        if config_dir.exists():
            self.backup_dir = tempfile.mkdtemp(prefix='expensetracker_test_')
            logging.debug(f'Created backup directory at {self.backup_dir}')

            shutil.copytree(config_dir, self.backup_dir, dirs_exist_ok=True)
            logging.debug(f'Backed up config directory from {config_dir} to {self.backup_dir}')

            shutil.rmtree(config_dir)
            logging.debug(f'Removed original config directory {config_dir}')

        # Reinitialize settings API
        lib.settings = lib.SettingsAPI()
        logging.debug(f'SettingsAPI reinitialized.')

        # Reinitialize database API
        database.database = None
        database.database = database.DatabaseAPI()
        logging.debug(f'DatabaseAPI reinitialized.')

        # Reinitialize sync API
        sync.sync = None
        sync.sync = sync.SyncAPI()
        logging.debug(f'SyncAPI reinitialized.')

    def tearDown(self) -> None:
        """Tear down the test config and restore any original config directory."""
        if QtWidgets.QApplication.instance():
            QtWidgets.QApplication.instance().quit()

        if self.backup_dir and os.path.isdir(self.backup_dir):
            config_dir: Path = self.config_paths.config_dir

            if config_dir.exists():
                shutil.rmtree(config_dir)
                logging.debug(f'Removed test config directory {config_dir}')

            shutil.copytree(self.backup_dir, config_dir, dirs_exist_ok=True)
            logging.debug(f'Restored config directory from {self.backup_dir} to {config_dir}')

            shutil.rmtree(self.backup_dir)
            logging.debug(f'Removed backup directory {self.backup_dir}')


def with_service(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to inject Sheets service, spreadsheet ID, and worksheet name.

    Args:
        func: The test method to wrap.

    Returns:
        A method with signature
        (self, service, spreadsheet_id, spreadsheet_name, *args, **kwargs).

    """

    @functools.wraps(func)
    def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        creds = auth.get_creds()
        service = build('sheets', 'v4', credentials=creds, cache_discovery=False)
        sheet_cfg = lib.settings.get_section('spreadsheet')
        spreadsheet_id = sheet_cfg['id']
        spreadsheet_name = sheet_cfg['worksheet']
        with service:
            return func(self, service, spreadsheet_id, spreadsheet_name, *args, **kwargs)

    return wrapper


class BaseServiceTestCase(BaseTestCase):
    """Base test case for service-related tests."""

    def setUp(self) -> None:
        super().setUp()

        # verify environment variables
        for key in TestAuthEnvKeys:
            env_key = key.name
            if env_key not in os.environ:
                raise EnvironmentError(f'Missing environment variable: {env_key}')

            if not os.environ[env_key]:
                raise ValueError(f'Environment variable {env_key} is empty.')

        client_secret = os.environ[TestAuthEnvKeys.TEST_CLIENT_SECRET_ENV_KEY.name]

        data = json.loads(client_secret)
        with open(lib.settings.client_secret_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

        spreadsheet_id = os.environ[TestAuthEnvKeys.TEST_SPREADHSEET_ID_ENV_KEY.name]
        spreadsheet_name = os.environ[TestAuthEnvKeys.TEST_SPREADHSEET_NAME_ENV_KEY.name]

        # manually open the ledger.json file
        with open(lib.settings.ledger_path, 'r', encoding='utf-8') as f:
            ledger_data = json.load(f)

        # update the spreadsheet_id and spreadsheet_name
        spreadsheet_section = ledger_data.get('spreadsheet', {})
        spreadsheet_section['id'] = spreadsheet_id
        spreadsheet_section['worksheet'] = spreadsheet_name

        # write the updated data back to the ledger.json file
        with open(lib.settings.ledger_path, 'w', encoding='utf-8') as f:
            json.dump(ledger_data, f, indent=4)

        # reinitialize apis
        lib.settings = None
        lib.settings = lib.SettingsAPI()

        database.database = None
        database.database = database.DatabaseAPI()

        sync.sync = None
        sync.sync = sync.SyncAPI()

        # Patch the auth.get_creds() method to return the service account credentials
        patch('ExpenseTracker.core.auth.get_creds', new=patch_get_creds).start()

    def tearDown(self) -> None:
        super().tearDown()
        patch.stopall()

    def test_test_env_client_secret(self):
        # verify that the client_secret is loaded correctly
        env_data = json.loads(os.environ[TestAuthEnvKeys.TEST_CLIENT_SECRET_ENV_KEY.name])
        config_data: dict = lib.settings.get_section('client_secret')
        self.assertEqual(config_data, env_data, 'Client secret data does not match.')

    def test_test_env_spreadsheet_id(self):
        # verify that the spreadsheet_id is loaded correctly
        env_data = os.environ[TestAuthEnvKeys.TEST_SPREADHSEET_ID_ENV_KEY.name]
        config_data: dict = lib.settings.get_section('spreadsheet')
        self.assertEqual(config_data['id'], env_data, 'Spreadsheet ID does not match.')

    def test_test_env_spreadsheet_name(self):
        # verify that the spreadsheet_name is loaded correctly
        env_data = os.environ[TestAuthEnvKeys.TEST_SPREADHSEET_NAME_ENV_KEY.name]
        config_data: dict = lib.settings.get_section('spreadsheet')
        self.assertEqual(config_data['worksheet'], env_data, 'Spreadsheet name does not match.')

    def test_authenticate(self):
        # verify that the authentication works
        creds = auth.get_creds()
        self.assertIsNotNone(creds, 'Failed to authenticate with service account credentials.')
        self.assertTrue(creds.valid, 'Service account credentials are not valid.')

    @with_service
    def test_sheet_id(self, service, spreadsheet_id, spreadsheet_name):
        # Get the spreadsheet metadata
        spreadsheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet_metadata.get('sheets', [])
        sheet_id = None

        # Find the sheet with the specified name
        for sheet in sheets:
            if sheet.get('properties', {}).get('title') == spreadsheet_name:
                sheet_id = sheet.get('properties', {}).get('sheetId')
                break

        self.assertIsNotNone(sheet_id, f'Sheet with name {spreadsheet_name} not found in spreadsheet {spreadsheet_id}.')

    @with_service
    def test_sheet_name(self, service, spreadsheet_id, spreadsheet_name):
        # Get the spreadsheet metadata
        spreadsheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet_metadata.get('sheets', [])
        sheet_name = None

        # Find the sheet with the specified name
        for sheet in sheets:
            if sheet.get('properties', {}).get('title') == spreadsheet_name:
                sheet_name = sheet.get('properties', {}).get('title')
                break

        self.assertEqual(sheet_name, spreadsheet_name,
                         f'Sheet name {sheet_name} does not match expected name {spreadsheet_name}.')


class ConfigPathsSmokeTest(BaseTestCase):
    def test_real_paths_exist(self):
        cp = lib.ConfigPaths()  # uses the real template + real AppData
        self.assertTrue(cp.client_secret_template.exists())
        self.assertTrue(cp.ledger_template.exists())
        self.assertTrue(cp.icon_dir.is_dir())
