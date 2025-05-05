import json
from unittest.mock import patch

import google.oauth2.credentials as cred_mod

from ExpenseTracker.core import auth
from ExpenseTracker.settings import lib
from ExpenseTracker.status.status import CredsInvalidException, AuthenticationExceptionException
from .base import BaseTestCase


class TestAuthManager(BaseTestCase):
    """Unit tests for the AuthManager behavior."""

    def test_missing_credentials_raises_AuthExpiredError(self):
        manager = auth.AuthManager()
        with self.assertRaises(auth.AuthExpiredError):
            manager.get_valid_credentials()

    def test_invalid_credentials_file_raises_CredsInvalidException(self):
        # Write invalid JSON to creds file
        creds_path = lib.settings.creds_path
        creds_path.write_text('not a json', encoding='utf-8')
        manager = auth.AuthManager()
        with self.assertRaises(CredsInvalidException):
            manager.get_valid_credentials()

    def test_auto_refresh_succeeds(self):
        # Dummy credentials that can refresh successfully
        class DummyCreds:
            def __init__(self):
                self.expired = True
                self.refresh_token = 'rt'

            def refresh(self, request):
                self.expired = False

        dummy = DummyCreds()
        # Patch credential loading and saving
        with patch.object(
                cred_mod.Credentials,
                'from_authorized_user_file',
                new=classmethod(lambda cls, f: dummy)
        ), patch.object(auth, 'save_creds', new=lambda creds: None):
            # Ensure creds file exists
            lib.settings.creds_path.write_text(json.dumps({'token': 't'}), encoding='utf-8')
            manager = auth.AuthManager()
            result = manager.get_valid_credentials()
            self.assertIs(result, dummy)

    def test_no_refresh_token_raises_AuthExpiredError(self):
        # Dummy creds without refresh_token
        class DummyCreds:
            def __init__(self):
                self.expired = True
                self.refresh_token = None

        dummy = DummyCreds()
        with patch.object(
                cred_mod.Credentials,
                'from_authorized_user_file',
                new=classmethod(lambda cls, f: dummy)
        ):
            lib.settings.creds_path.write_text(json.dumps({'token': 't'}), encoding='utf-8')
            manager = auth.AuthManager()
            with self.assertRaises(auth.AuthExpiredError):
                manager.get_valid_credentials()

    def test_refresh_failure_raises_AuthenticationExceptionException(self):
        # Dummy creds that fail to refresh
        class DummyCreds:
            def __init__(self):
                self.expired = True
                self.refresh_token = 'rt'

            def refresh(self, request):
                raise Exception('refresh failed')

        dummy = DummyCreds()
        with patch.object(
                cred_mod.Credentials,
                'from_authorized_user_file',
                new=classmethod(lambda cls, f: dummy)
        ):
            lib.settings.creds_path.write_text(json.dumps({'token': 't'}), encoding='utf-8')
            manager = auth.AuthManager()
            with self.assertRaises(AuthenticationExceptionException):
                manager.get_valid_credentials()
