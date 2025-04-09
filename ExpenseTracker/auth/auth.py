"""
Google OAuth2 Authentication Module.

This module provides a high-level interface for authenticating
Google services and getting valid credentials.

This implementation uses a QThread to run the OAuth web flow asynchronously,
and a custom QDialog to show authentication progress.

"""

import json
import logging
from typing import Dict, Union

import google.auth.exceptions
import google.auth.transport.requests
import google.oauth2.credentials
import google_auth_oauthlib.flow
from PySide6 import QtCore, QtWidgets

from ..settings import lib
from ..status import status

logging.basicConfig(level=logging.INFO)

DEFAULT_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


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
                self.errorOccurred.emit('Authentication did not complete successfully.')
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


def get_creds() -> google.oauth2.credentials.Credentials:
    """Get OAuth credentials for connecting to Google services.

    """
    if not lib.settings.client_secret_path.exists():
        raise status.ClientSecretNotFoundException

    if not lib.settings.creds_path.exists():
        raise status.CredsNotFoundException

    try:
        logging.info(f'Loading credentials from {lib.settings.creds_path}...')
        return google.oauth2.credentials.Credentials.from_authorized_user_file(
            str(lib.settings.creds_path)
        )
    except (ValueError, json.JSONDecodeError) as ex:
        logging.error(f'Failed to load credentials, will attempt to re-authenticate: {ex}')

    logging.info(f'Deleting {lib.settings.creds_path}...')
    lib.settings.creds_path.unlink()

    logging.info('Attempting to re-authenticate...')
    creds = authenticate()

    return creds


def save_creds(creds: Union[google.oauth2.credentials.Credentials, Dict]) -> None:
    """Save the given credentials to the specified token path.

    """
    with open(lib.settings.creds_path, 'w', encoding='utf-8') as token_file:
        data = creds.to_json()
        token_file.write(data)

    logging.info(f'Credentials saved to {lib.settings.creds_path}.')


def authenticate() -> google.oauth2.credentials.Credentials:
    """
    Authenticate and return credentials.

    Returns:
        google.oauth2.credentials.Credentials: The authenticated credentials.

    Raises:
        RuntimeError: If authentication fails, is cancelled, or times out.
    """
    scopes = DEFAULT_SCOPES

    creds = get_creds()
    if creds and not set(scopes).issubset(set(creds.scopes or [])):
        logging.info('Cached credentials have mismatched scopes. Re-authentication required.')
        creds = None

    if creds:
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
            logging.error(f'Refresh failed: {ex}, attempting re-authentication.')

    if not lib.settings.client_secret_path.exists():
        raise status.ClientSecretNotFoundException

    # Get client config
    lib.settings.validate_client_secret()
    data = lib.settings.get_section('client_secret')

    logging.info('Starting new OAuth flow...')
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(data, scopes=scopes)

    from .. import ui
    dialog = AuthProgressDialog(parent=ui.parent(), timeout_seconds=60)
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
        raise status.ServiceUnavailableException('OAuth flow timed out (no response from browser).')

    dialog.close()

    logging.info('OAuth flow completed.')
    if result['error']:
        raise status.ServiceUnavailableException(f'OAuth flow failed: {result["error"]}')
    if not result['creds']:
        raise status.ServiceUnavailableException('Authentication was cancelled or timed out.')

    if 'creds' not in result or not result['creds']:
        raise status.CredsInvalidException('Invalid credentials returned from OAuth flow.')

    logging.info('Saving credentials...')
    creds = result['creds']
    save_creds(creds)
    return creds
