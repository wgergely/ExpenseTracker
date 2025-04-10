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


from ..status import status


DEFAULT_SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly',]


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
        super().__init__(parent=parent)
        self.setWindowTitle('Authenticating')
        self.setModal(True)

        self.countdown_label = None
        self.status_label = None

        self.timeout_seconds = timeout_seconds
        self.remaining = timeout_seconds

        self.countdown_timer = QtCore.QTimer(self)
        self.countdown_timer.setInterval(1000)

        self._create_ui()
        self._connect_signals()

    def showEvent(self, event):
        self.countdown_timer.start()

    def _create_ui(self):
        QtWidgets.QVBoxLayout(self)

        label = QtWidgets.QLabel(
            'Please complete sign-in in your browser.\n'
            'Waiting...'
        )
        self.layout().addWidget(label, 1)

        self.countdown_label = QtWidgets.QLabel(f'Time remaining: {self.remaining} seconds')
        self.layout().addWidget(self.countdown_label)

        self.status_label = QtWidgets.QLabel('')
        self.layout().addWidget(self.status_label)

        self.cancel_button = QtWidgets.QPushButton('Cancel')
        self.layout().addWidget(self.cancel_button, 1)

    def _connect_signals(self):
        self.cancel_button.clicked.connect(self.on_cancel)
        self.countdown_timer.timeout.connect(self.update_countdown)

    def sizeHint(self):
        from ..ui import ui
        return QtCore.QSize(
            ui.Size.DefaultWidth(0.5),
            ui.Size.DefaultHeight(0.5)
        )

    @QtCore.Slot()
    def update_countdown(self):
        self.remaining -= 1
        self.countdown_label.setText(f'Time remaining: {self.remaining} seconds')
        if self.remaining <= 0:
            self.countdown_timer.stop()

    @QtCore.Slot()
    def on_cancel(self):
        self.cancelled.emit()
        self.reject()

    def show_timeout_message(self):
        self.countdown_label.setText('Authentication timed out. Please try again.')
        self.countdown_timer.stop()


def get_creds() -> google.oauth2.credentials.Credentials:
    """Get OAuth credentials for connecting to Google services.

    """
    from ..settings import lib
    if not lib.settings.client_secret_path.exists():
        raise status.ClientSecretNotFoundException

    if not lib.settings.creds_path.exists():
        logging.info('Credentials file not found. Attempting to authenticate...')
        creds = authenticate()
        if not creds:
            raise status.CredsNotFoundException
        return creds

    try:
        logging.info(f'Loading credentials from {lib.settings.creds_path}...')
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(
            str(lib.settings.creds_path)
        )
        logging.info(f'Credentials loaded successfully. Scopes={creds.scopes}')
        return creds
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
    from ..settings import lib
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

    creds = None

    from ..settings import lib
    if lib.settings.creds_path.exists():
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

    from ..settings import lib
    if not lib.settings.client_secret_path.exists():
        raise status.ClientSecretNotFoundException

    # Get client config
    lib.settings.validate_client_secret()
    data = lib.settings.get_section('client_secret')

    logging.info('Starting new OAuth flow...')
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(data, scopes=scopes)

    from ..ui import ui
    dialog = AuthProgressDialog(timeout_seconds=60)
    ui.set_stylesheet(dialog)

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
        raise status.AuthenticationExceptionException('OAuth flow timed out (no response from browser).')

    dialog.close()

    logging.info('OAuth flow completed.')
    if result['error']:
        raise status.AuthenticationExceptionException(f'OAuth flow failed: {result["error"]}')
    if not result['creds']:
        raise status.AuthenticationExceptionException('Authentication was cancelled or timed out.')

    if 'creds' not in result or not result['creds']:
        raise status.CredsInvalidException('Invalid credentials returned from OAuth flow.')

    logging.info('Saving credentials...')
    creds = result['creds']
    save_creds(creds)
    return creds


def sign_out() -> None:
    """Sign out the user by deleting the credentials file.

    """
    from ..settings import lib
    if lib.settings.creds_path.exists():
        logging.info(f'Deleting {lib.settings.creds_path}...')
        lib.settings.creds_path.unlink()
        logging.info('Successfully signed out.')
    else:
        logging.info('No credentials file found. No action taken.')