"""
Google OAuth2 authentication and credential management.

Provides functions and classes to authenticate with Google services,
manage credential storage, and run OAuth flows asynchronously.
"""

import json
import logging
import threading
import time
from typing import Dict, Union, Optional

import google.auth.exceptions
import google.auth.transport.requests
import google.oauth2.credentials
import google_auth_oauthlib.flow
from PySide6 import QtCore, QtWidgets

from ..status import status
from ..ui.ui import BaseProgressDialog

DEFAULT_SCOPES = ['https://www.googleapis.com/auth/spreadsheets', ]


class AuthExpiredError(Exception):
    """Raised when credentials have expired and require interactive refresh."""
    pass


class AuthManager:
    """Manages OAuth2 credentials with thread-safe refresh."""

    def __init__(self):
        self._lock = threading.Lock()
        self._creds: Optional[google.oauth2.credentials.Credentials] = None

    def get_valid_credentials(self) -> google.oauth2.credentials.Credentials:
        """
        Return valid credentials without any UI.

        Raises:
            AuthExpiredError: if no credentials exist or a full interactive flow is required.
            status.AuthenticationExceptionException: if an auto-refresh fails.
            status.CredsInvalidException: if stored credentials are corrupt.
        """
        from ..settings import lib
        with self._lock:
            # Load existing credentials file
            if self._creds is None:
                if not lib.settings.creds_path.exists():
                    # No saved credentials → interactive sign-in required
                    raise AuthExpiredError(
                        'No credentials found; interactive authentication required')
                try:
                    self._creds = google.oauth2.credentials.Credentials.from_authorized_user_file(
                        str(lib.settings.creds_path))
                except Exception as ex:
                    # Credentials file invalid → remove and require re-authentication
                    try:
                        lib.settings.creds_path.unlink()
                    except Exception:
                        pass
                    raise status.CredsInvalidException('Failed to load credentials') from ex

            # Attempt non-interactive refresh if expired
            if self._creds.expired:
                if self._creds.refresh_token:
                    try:
                        self._creds.refresh(
                            google.auth.transport.requests.Request())
                        save_creds(self._creds)
                    except Exception as ex:
                        raise status.AuthenticationExceptionException(
                            'Failed to auto-refresh credentials') from ex
                else:
                    # No refresh token → interactive sign-in required
                    raise AuthExpiredError(
                        'Credentials expired; interactive authentication required')

            return self._creds

    def refresh_credentials_interactive(self) -> google.oauth2.credentials.Credentials:
        """Perform an interactive OAuth flow on the main GUI thread."""
        app = QtWidgets.QApplication.instance() or QtCore.QCoreApplication.instance()
        if not app:
            raise RuntimeError('No Qt application instance; cannot perform interactive auth')
        if QtCore.QThread.currentThread() != app.thread():
            raise RuntimeError('refresh_credentials_interactive must be called from the main GUI thread')

        with self._lock:
            creds = authenticate()
            save_creds(creds)
            self._creds = creds
            return creds

    def force_reauthenticate(self) -> google.oauth2.credentials.Credentials:
        """
        Force interactive reauthentication and clear cached service.
        """
        # Remove any existing credentials to force a fresh login
        from ..settings import lib
        try:
            if lib.settings.creds_path.exists():
                lib.settings.creds_path.unlink()
        except Exception:
            pass

        # Clear any cached Sheets service client
        from . import service
        service.clear_service()

        # Perform interactive authentication via existing flow
        creds = self.refresh_credentials_interactive()
        self._creds = creds
        return creds


auth_manager = AuthManager()


class AuthFlowWorker(QtCore.QThread):
    """
    Runs OAuth web flow in a background thread.

    Signals:
        resultReady (object): Emitted with credentials on success.
        errorOccurred (str): Emitted with an error message on failure.
    """
    resultReady = QtCore.Signal(object)
    # Emits exception instance on failure
    errorOccurred = QtCore.Signal(object)

    def __init__(self, flow: google_auth_oauthlib.flow.InstalledAppFlow, parent=None):
        super().__init__(parent)
        self.flow = flow
        self.creds = None

    def run(self):
        logging.debug(f"[Thread-{threading.get_ident()}] AuthFlowWorker.run: called at {time.time()}")
        try:
            logging.debug(
                f"[Thread-{threading.get_ident()}] AuthFlowWorker.run: flow.run_local_server start at {time.time()}")
            self.creds = self.flow.run_local_server(port=0)
            logging.debug(
                f"[Thread-{threading.get_ident()}] AuthFlowWorker.run: flow.run_local_server returned at {time.time()}")
            if not self.creds or not self.creds.token:
                ex = status.AuthenticationExceptionException(
                    'Authentication did not complete successfully.')
                self.errorOccurred.emit(ex)
            else:
                self.resultReady.emit(self.creds)
        except Exception as ex:
            logging.debug(
                f"[Thread-{threading.get_ident()}] AuthFlowWorker.run: exception at {time.time()}: {ex}")
            self.errorOccurred.emit(ex)


class AuthProgressDialog(BaseProgressDialog):
    """
    Dialog displaying authentication progress with countdown and cancel.

    Signals:
        cancelled (): Emitted when the user cancels authentication.
    """

    def __init__(self, timeout_seconds: int = 60) -> None:
        super().__init__(timeout_seconds)

    def _populate_content(self, layout: QtWidgets.QVBoxLayout) -> None:
        label = QtWidgets.QLabel(
            'Please complete sign-in in your browser.\n'
            'Waiting...'
        )
        layout.addWidget(label, 1)

        self.countdown_label = QtWidgets.QLabel(
            f'Time remaining: {self.remaining} seconds'
        )
        layout.addWidget(self.countdown_label)

        self.status_label = QtWidgets.QLabel('')
        layout.addWidget(self.status_label)

        self.cancel_button = QtWidgets.QPushButton('Cancel')
        layout.addWidget(self.cancel_button, 1)
    
    @QtCore.Slot()
    def _update_countdown_label(self) -> None:
        self.countdown_label.setText(f'Time remaining: {self.remaining} seconds')

    @QtCore.Slot()
    def on_timeout(self) -> None:
        self.countdown_label.setText('Authentication timed out. Please try again.')
        self.countdown_timer.stop()


def get_creds() -> google.oauth2.credentials.Credentials:
    """
    Obtain valid OAuth2 credentials for Google Sheets API.

    Returns:
        google.oauth2.credentials.Credentials: Authorized credentials.

    Raises:
        status.ClientSecretNotFoundException: If client secret file is missing.
        status.CredsNotFoundException: If credentials cannot be obtained.
    """
    from ..settings import lib
    if not lib.settings.client_secret_path.exists():
        raise status.ClientSecretNotFoundException

    if not lib.settings.creds_path.exists():
        logging.debug('Credentials file not found. Attempting to authenticate...')
        creds = authenticate()
        if not creds:
            raise status.CredsNotFoundException
        return creds

    try:
        logging.debug(f'Loading credentials from {lib.settings.creds_path}...')
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(
            str(lib.settings.creds_path)
        )
        logging.debug(f'Credentials loaded successfully. Scopes={creds.scopes}')
        return creds
    except (ValueError, json.JSONDecodeError) as ex:
        logging.error(f'Failed to load credentials, will attempt to re-authenticate: {ex}')

    logging.debug(f'Deleting {lib.settings.creds_path}...')
    lib.settings.creds_path.unlink()

    logging.debug('Attempting to re-authenticate...')
    creds = authenticate()

    return creds


def save_creds(creds: Union[google.oauth2.credentials.Credentials, Dict]) -> None:
    """
    Save OAuth2 credentials to the configured token file.

    Args:
        creds (Union[google.oauth2.credentials.Credentials, Dict]): Credentials or dict to save.
    """
    from ..settings import lib
    with open(lib.settings.creds_path, 'w', encoding='utf-8') as token_file:
        data = creds.to_json()
        token_file.write(data)

    logging.debug(f'Credentials saved to {lib.settings.creds_path}.')




def _authenticate() -> google.oauth2.credentials.Credentials:
    """
    Run OAuth flow synchronously in the main GUI thread to authenticate and obtain credentials.

    Returns:
        Credentials: The authenticated credentials.

    Raises:
        status.AuthenticationExceptionException: If authentication fails or is cancelled.
        status.CredsInvalidException: If credentials returned are invalid.
        status.ClientSecretNotFoundException: If the client secret file is not found.
    """
    from ..settings import lib

    scopes = DEFAULT_SCOPES
    creds = None

    # reuse valid cached credentials
    if lib.settings.creds_path.exists():
        creds = get_creds()
        if creds:
            if not set(scopes).issubset(set(creds.scopes or [])):
                logging.debug('Cached credentials have mismatched scopes; clearing.')
                creds = None
            elif not creds.expired:
                logging.debug('Using valid cached credentials.')
                return creds

    # attempt refresh if expired
    if creds and creds.expired and creds.refresh_token:
        logging.debug('Cached credentials expired; attempting refresh.')
        try:
            creds.refresh(google.auth.transport.requests.Request())
            logging.debug('Successfully refreshed credentials.')
            save_creds(creds)
            return creds
        except google.auth.exceptions.RefreshError as ex:
            logging.error(f'Refresh failed: {ex}; will perform new flow.')

    # ensure client secret is present
    if not lib.settings.client_secret_path.exists():
        raise status.ClientSecretNotFoundException
    lib.settings.validate_client_secret()
    client_config = lib.settings.get_section('client_secret')

    logging.debug('Starting synchronous OAuth flow...')
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(client_config, scopes=scopes)
    try:
        creds = flow.run_local_server(port=0)
    except Exception as ex:
        logging.error(f'OAuth flow error: {ex}')
        raise status.AuthenticationExceptionException(f'OAuth flow failed: {ex}')

    if not creds:
        raise status.AuthenticationExceptionException('Authentication was cancelled or no credentials obtained.')

    if not creds.valid:
        raise status.CredsInvalidException('Invalid credentials returned from OAuth flow.')

    logging.debug('Saving credentials...')
    save_creds(creds)
    return creds


def authenticate() -> google.oauth2.credentials.Credentials:
    """
    Run OAuth flow to authenticate and obtain credentials.

    Returns:
        google.oauth2.credentials.Credentials: The authenticated credentials.

    Raises:
        status.AuthenticationExceptionException: If authentication fails or is cancelled.
        status.CredsInvalidException: If credentials returned are invalid.
    """
    logging.debug(f"[Thread-{threading.get_ident()}] authenticate: start at {time.time()}")
    scopes = DEFAULT_SCOPES

    creds = None

    from ..settings import lib
    if lib.settings.creds_path.exists():
        creds = get_creds()
        if creds and not set(scopes).issubset(set(creds.scopes or [])):
            logging.debug('Cached credentials have mismatched scopes. Re-authentication required.')
            creds = None

    if creds:
        logging.debug('Cached credentials are valid.')
        return creds

    if creds and creds.expired and creds.refresh_token:
        logging.debug('Cached credentials expired; attempting refresh.')

        try:
            creds.refresh(google.auth.transport.requests.Request())
            logging.debug('Successfully refreshed credentials.')
            save_creds(creds)
            return creds
        except google.auth.exceptions.RefreshError as ex:
            logging.error(f'Refresh failed: {ex}, attempting re-authentication.')

    from ..settings import lib
    if not lib.settings.client_secret_path.exists():
        raise status.ClientSecretNotFoundException

    # Get client config
    lib.settings.validate_client_secret()
    data = lib.settings.get_section('client_secret')

    logging.debug('Starting new OAuth flow...')
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(data, scopes=scopes)

    dialog = AuthProgressDialog(timeout_seconds=60)

    auth_worker = AuthFlowWorker(flow)
    result = {'creds': None, 'error': None}
    loop = QtCore.QEventLoop()

    auth_worker.resultReady.connect(lambda c: (result.update({'creds': c}), loop.quit()))
    auth_worker.errorOccurred.connect(lambda err: (result.update({'error': err}), loop.quit()))
    dialog.cancelled.connect(lambda: loop.quit())

    auth_worker.start()

    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: (dialog.on_timeout(), loop.quit()))
    timer.start(60000)

    dialog.show()
    loop.exec()
    timer.stop()

    if auth_worker.isRunning():
        auth_worker.terminate()
        auth_worker.wait()
        raise status.AuthenticationExceptionException('OAuth flow timed out (no response from browser).')

    dialog.close()

    logging.debug('OAuth flow completed.')
    if result['error']:
        raise status.AuthenticationExceptionException(f'OAuth flow failed: {result["error"]}')
    if not result['creds']:
        raise status.AuthenticationExceptionException('Authentication was cancelled or timed out.')

    if 'creds' not in result or not result['creds']:
        raise status.CredsInvalidException('Invalid credentials returned from OAuth flow.')

    logging.debug('Saving credentials...')
    creds = result['creds']
    save_creds(creds)
    return creds


def sign_out() -> None:
    """
    Delete stored credentials to sign out the user.
    """
    from ..settings import lib
    if lib.settings.creds_path.exists():
        logging.debug(f'Deleting {lib.settings.creds_path}...')
        lib.settings.creds_path.unlink()
        logging.debug('Successfully signed out.')
    else:
        logging.debug('No credentials file found. No action taken.')
