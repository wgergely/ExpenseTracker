import json
from unittest.mock import patch

import google.oauth2.credentials as cred_mod

from ExpenseTracker.core import auth
from ExpenseTracker.settings import lib
from ExpenseTracker.status.status import CredsInvalidException, AuthenticationExceptionException
from tests.base import BaseTestCase


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

    def test_force_reauthenticate_clears_creds_and_service(self):
        """force_reauthenticate should delete stored creds, clear service cache, and return new creds"""
        from ExpenseTracker.core import service
        manager = auth.auth_manager
        # Seed existing credentials and service cache
        dummy_old = object()
        manager._creds = dummy_old
        # Ensure creds file exists
        creds_path = lib.settings.creds_path
        creds_path.write_text('old', encoding='utf-8')
        # Seed cached service
        service._cached_service = object()

        # Patch interactive refresh to return new creds
        dummy_new = object()
        with patch.object(manager, 'refresh_credentials_interactive', return_value=dummy_new) as mock_refresh:
            result = manager.force_reauthenticate()
            mock_refresh.assert_called_once()
            self.assertIs(result, dummy_new)

        # Stored creds file must be removed
        self.assertFalse(creds_path.exists(), 'Credentials file was not deleted')
        # Service cache must be cleared
        self.assertIsNone(service._cached_service, 'Service cache was not cleared')
        # AuthManager._creds updated
        self.assertIs(manager._creds, dummy_new)
