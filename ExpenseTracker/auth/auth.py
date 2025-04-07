"""
Google OAuth2 Authentication Module.

This module provides a high-level interface for authenticating
Google services and getting valid credentials.

This implementation uses a QThread to run the OAuth web flow asynchronously,
and a custom QDialog to show authentication progress.

"""

import json
import logging
from typing import Optional

import google.auth.exceptions
import google.auth.transport.requests
import google.oauth2.credentials
import google_auth_oauthlib.flow
from PySide6 import QtCore, QtWidgets

from ..settings import lib

logging.basicConfig(level=logging.INFO)

DEFAULT_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


def verify_creds():
    """Check if the credential file exists and is valid.

    Raises:
        RuntimeError: If the credentials are invalid or expired.

    """
    try:
        creds = get_creds()
    except (FileNotFoundError, ValueError) as ex:
        logging.error(f'Error verifying credentials: {ex}')
        raise RuntimeError(f'Error verifying credentials: {ex}') from ex

    if not creds or not creds.valid:
        logging.error('Credentials are invalid or expired.')
        raise RuntimeError('Credentials are invalid or expired.')


def get_creds() -> Optional[google.oauth2.credentials.Credentials]:
    """Get OAuth credentials for Google API.

    """
    if not lib.settings.paths.creds_path.exists():
        logging.error(f'Client secret file not found at {lib.settings.paths.creds_path}.')
        raise FileNotFoundError(
            f'Client secret file not found at {lib.settings.paths.creds_path}.')

    try:
        return google.oauth2.credentials.Credentials.from_authorized_user_file(
            str(lib.settings.paths.creds_path)
        )
    except (ValueError, json.JSONDecodeError):
        logging.critical(f'Failed to load credentials from {lib.settings.paths.creds_path}.')
        raise


def save_creds(creds: google.oauth2.credentials.Credentials) -> None:
    """Save the given credentials to the specified token path.

    """
    with open(lib.settings.paths.creds_path, 'w', encoding='utf-8') as token_file:
        data = creds.to_json()
        token_file.write(data)

    logging.info(f'Credentials saved to {lib.settings.paths.creds_path}.')


class AuthFlowWorker(QtCore.QThread):
    """
    QThread subclass that runs the OAuth web flow.

    Emits:
      - resultReady(object): with the credentials on success.
      - errorOccurred(str): with an error message on failure.
    """
    resultReady = QtCore.Signal(object)
    errorOccurred = QtCore.Signal(str)

    def __init__(self, flow: google_auth_oauthlib.flow.InstalledAppFlow, parent=None):
        super().__init__(parent)
        self.flow = flow
        self.creds = None

    def run(self):
        try:
            self.creds = self.flow.run_local_server(port=0)
            if not self.creds or not self.creds.token:
                self.errorOccurred.emit("Authentication did not complete successfully.")
            else:
                self.resultReady.emit(self.creds)
        except Exception as ex:
            self.errorOccurred.emit(str(ex))


class AuthProgressDialog(QtWidgets.QDialog):
    """Authentication progress dialog.

    """
    cancelled = QtCore.Signal()

    def __init__(self, timeout_seconds: int = 60, parent=None):
        from .. import ui
        super().__init__(parent=ui.parent())
        self.setWindowTitle('Authenticating with Google')
        self.setModal(True)
        self.resize(400, 180)
        self.timeout_seconds = timeout_seconds
        self.remaining = timeout_seconds

        layout = QtWidgets.QVBoxLayout(self)

        instructions = QtWidgets.QLabel(
            'A browser window should have opened for Google sign-in.\n'
            'Please complete sign-in in your browser.\n'
            'Waiting for you to sign in...'
        )
        layout.addWidget(instructions)

        self.countdownLabel = QtWidgets.QLabel(f'Time remaining: {self.remaining} seconds')
        layout.addWidget(self.countdownLabel)

        self.statusLabel = QtWidgets.QLabel('')
        layout.addWidget(self.statusLabel)

        cancelButton = QtWidgets.QPushButton('Cancel')
        cancelButton.clicked.connect(self.on_cancel)
        layout.addWidget(cancelButton)

        self.countdownTimer = QtCore.QTimer(self)
        self.countdownTimer.setInterval(1000)
        self.countdownTimer.timeout.connect(self.update_countdown)
        self.countdownTimer.start()

    def update_countdown(self):
        self.remaining -= 1
        self.countdownLabel.setText(f'Time remaining: {self.remaining} seconds')
        if self.remaining <= 0:
            self.countdownTimer.stop()

    def on_cancel(self):
        self.cancelled.emit()
        self.reject()

    def show_timeout_message(self):
        self.countdownLabel.setText('Authentication timed out. Please try again.')
        self.countdownTimer.stop()


def authenticate(force: bool = False) -> google.oauth2.credentials.Credentials:
    """
    Authenticate the user via OAuth2 and return valid credentials.

    This function first attempts to load and refresh cached credentials.
    If not available, it starts a new OAuth flow in a QThread while showing a
    progress dialog with a live countdown and a Cancel button. If the flow does not complete
    within 60 seconds or the user cancels, the process is aborted.

    Args:
        force (bool): If True, forces re-authentication even if valid cached credentials exist.

    Returns:
        google.oauth2.credentials.Credentials: The authenticated credentials.

    Raises:
        RuntimeError: If authentication fails, is cancelled, or times out.
    """
    scopes = DEFAULT_SCOPES

    creds = None if force else get_creds()
    if creds:
        if not set(scopes).issubset(set(creds.scopes or [])):
            logging.info('Cached credentials have mismatched scopes. Re-authentication required.')
            creds = None

    if creds and creds.valid:
        logging.info('Cached credentials are valid.')
        return creds

    if creds and creds.expired and creds.refresh_token:
        logging.info('Cached credentials expired; attempting refresh.')
        try:
            creds.refresh(google.auth.transport.requests.Request())
            logging.info('Successfully refreshed credentials.')
            save_creds(creds)
            return creds
        except google.auth.exceptions.RefreshError as ex:
            logging.warning(f'Refresh failed: {ex}')
            creds = None

    logging.info('Starting new OAuth flow...')

    if not lib.settings.paths.client_secret_path.exists():
        logging.error(f'Client secret file not found at {lib.settings.paths.client_secret_path}.')
        raise FileNotFoundError(
            f'Client secret file not found at {lib.settings.paths.client_secret_path}.')

    # Get client config
    data = lib.settings.get_section('client_secret')
    lib.settings.validate_client_secret(data)

    # Start OAuth flow
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(data, scopes=scopes)

    # OPen progress dialog
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
    timer.timeout.connect(lambda: (dialog.show_timeout_message(), loop.quit()))
    timer.start(60000)

    dialog.show()
    loop.exec()
    timer.stop()

    if auth_worker.isRunning():
        auth_worker.terminate()
        auth_worker.wait()
        raise RuntimeError('OAuth flow timed out (no response from browser).')

    dialog.close()

    if result['error']:
        raise RuntimeError(f'OAuth flow failed: {result["error"]}')
    if not result['creds']:
        raise RuntimeError('Authentication was cancelled or timed out.')

    creds = result['creds']
    save_creds(creds)
    return creds


def unauthenticate() -> None:
    """Delete the cached credentials file."""
    if not lib.settings.paths.creds_path.exists():
        logging.warning('No cached credentials file found to delete.')
        return

    lib.settings.paths.creds_path.unlink()
    logging.info(f'Deleted credentials at {lib.settings.paths.creds_path}')
