"""
Google OAuth2 Authentication Module.

This module provides a high-level interface for authenticating
Google services and obtaining valid credentials. Credentials are cached
locally in an OS-specific temporary directory to avoid repeated logins.

This implementation uses a QThread to run the OAuth web flow asynchronously,
and a custom QDialog to show authentication progress. The dialog displays
a live countdown of the remaining time and a Cancel button. If the user cancels
or the flow does not complete within 60 seconds, the process is aborted.
"""

import json
import logging
import os
import pathlib
import tempfile
from typing import Optional, List, Dict, Any

import google.auth.exceptions
import google.auth.transport.requests
import google.oauth2.credentials
import google_auth_oauthlib.flow

from PySide6 import QtCore, QtWidgets

logging.basicConfig(level=logging.INFO)

# Adjust the scopes as needed (e.g. for Sheets read/write)
DEFAULT_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Fixed location of client_secret.json (relative to this module)
CLIENT_SECRETS_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    '..',
    'config',
    'client_secret.json'
))


def get_temp_auth_dir() -> str:
    """Get or create the temporary folder used for credential caching."""
    auth_dir = pathlib.Path(tempfile.gettempdir()) / 'ExpensesTracker' / 'auth'
    auth_dir.mkdir(parents=True, exist_ok=True)
    return str(auth_dir)


def load_credentials(token_path: str) -> Optional[google.oauth2.credentials.Credentials]:
    """Load cached credentials from the given token path."""
    if not os.path.exists(token_path):
        logging.info(f'No token file found at {token_path}.')
        return None
    try:
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(token_path)
        return creds
    except (ValueError, json.JSONDecodeError):
        logging.warning(f'Token file at {token_path} is corrupt or invalid JSON.')
        return None


def save_credentials(creds: google.oauth2.credentials.Credentials, token_path: str) -> None:
    """Save the given credentials to the specified token path."""
    with open(token_path, 'w', encoding='utf-8') as token_file:
        token_file.write(creds.to_json())
    logging.info(f'Credentials saved to {token_path}.')


def load_client_config(path: str) -> Dict[str, Any]:
    """Load and parse the client_secret JSON file."""
    if not os.path.exists(path):
        message = (
            f'No client_secret.json found at {path}.\n\n'
            'You must create an OAuth2 client of type "Desktop App" in your Google Cloud Console, '
            'then download the JSON.\n'
            'Steps:\n'
            '1. Go to https://console.cloud.google.com/apis/credentials\n'
            '2. Create or select a project.\n'
            '3. Create credentials -> OAuth Client ID -> Desktop App.\n'
            '4. Download the JSON and place it at the specified path.\n'
        )
        raise RuntimeError(message)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError as ex:
        message = f'The file at {path} is not valid JSON or is corrupted.\nError details: {ex}'
        raise RuntimeError(message)


def validate_client_config(client_config: Dict[str, Any]) -> str:
    """
    Validate that the client configuration is for an OAuth client.
    Accept either an "installed" or "web" configuration.

    Returns:
        The key used ("installed" or "web").

    Raises:
        RuntimeError: If neither configuration is present or required fields are missing.
    """
    key = None
    if "installed" in client_config:
        key = "installed"
    elif "web" in client_config:
        key = "web"
    else:
        raise RuntimeError("Client configuration does not contain an 'installed' or 'web' section.")
    required_keys = ['client_id', 'auth_uri', 'token_uri']
    config_section = client_config[key]
    missing = [k for k in required_keys if k not in config_section]
    if missing:
        raise RuntimeError(f"Missing required fields in the '{key}' section: {missing}.")
    return key


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
    """
    A dialog that shows authentication progress. It includes instructions,
    a live countdown of the remaining time (which will be replaced with a timeout
    message upon expiry), and a Cancel button.
    """
    cancelled = QtCore.Signal()

    def __init__(self, timeout_seconds: int = 60, parent=None):
        from .. import ui
        print("Parent:", ui.parent())

        super().__init__(parent=ui.parent())
        self.setWindowTitle("Authenticating with Google")
        self.setModal(True)
        self.resize(400, 180)
        self.timeout_seconds = timeout_seconds
        self.remaining = timeout_seconds

        layout = QtWidgets.QVBoxLayout(self)

        instructions = QtWidgets.QLabel(
            "A browser window should have opened for Google sign-in.\n"
            "Please complete sign-in in your browser.\n"
            "Waiting for you to sign in..."
        )
        layout.addWidget(instructions)

        self.countdownLabel = QtWidgets.QLabel(f"Time remaining: {self.remaining} seconds")
        layout.addWidget(self.countdownLabel)

        self.statusLabel = QtWidgets.QLabel("")
        layout.addWidget(self.statusLabel)

        cancelButton = QtWidgets.QPushButton("Cancel")
        cancelButton.clicked.connect(self.on_cancel)
        layout.addWidget(cancelButton)

        self.countdownTimer = QtCore.QTimer(self)
        self.countdownTimer.setInterval(1000)
        self.countdownTimer.timeout.connect(self.update_countdown)
        self.countdownTimer.start()

    def update_countdown(self):
        self.remaining -= 1
        self.countdownLabel.setText(f"Time remaining: {self.remaining} seconds")
        if self.remaining <= 0:
            self.countdownTimer.stop()

    def on_cancel(self):
        self.cancelled.emit()
        self.reject()

    def show_timeout_message(self):
        self.countdownLabel.setText("Authentication timed out. Please try again.")
        self.countdownTimer.stop()


def authenticate(
        scopes: Optional[List[str]] = None,
        token_filename: str = 'auth_token.json',
        force: bool = False,
) -> google.oauth2.credentials.Credentials:
    """
    Authenticate the user via OAuth2 and return valid credentials.

    This function first attempts to load and refresh cached credentials.
    If not available, it starts a new OAuth flow in a QThread while showing a
    progress dialog with a live countdown and a Cancel button. If the flow does not complete
    within 60 seconds or the user cancels, the process is aborted.

    Returns:
        google.oauth2.credentials.Credentials: The authenticated credentials.

    Raises:
        RuntimeError: If authentication fails, is cancelled, or times out.
    """
    if scopes is None:
        scopes = DEFAULT_SCOPES

    # 1. Load and validate client configuration.
    client_config_data = load_client_config(CLIENT_SECRETS_PATH)
    config_key = validate_client_config(client_config_data)

    # 2. Attempt to load cached credentials.
    auth_dir = get_temp_auth_dir()
    token_path = os.path.join(auth_dir, token_filename)
    creds = None if force else load_credentials(token_path)
    if creds:
        if not set(scopes).issubset(set(creds.scopes or [])):
            logging.info("Cached credentials have mismatched scopes. Re-authentication required.")
            creds = None
    if creds and creds.valid:
        logging.info(f"Loaded valid credentials from {token_path}.")
        return creds
    if creds and creds.expired and creds.refresh_token:
        logging.info("Cached credentials expired; attempting refresh.")
        try:
            creds.refresh(google.auth.transport.requests.Request())
            logging.info("Successfully refreshed credentials.")
            save_credentials(creds, token_path)
            return creds
        except google.auth.exceptions.RefreshError as ex:
            logging.warning(f"Refresh failed: {ex}")
            creds = None

    # 3. Start a new OAuth flow.
    logging.info("Starting new OAuth flow...")
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(client_config_data, scopes=scopes)
    # We no longer set a clickable URL; we rely on the default browser behavior.

    dialog = AuthProgressDialog(timeout_seconds=60)
    auth_worker = AuthFlowWorker(flow)
    result = {"creds": None, "error": None}
    loop = QtCore.QEventLoop()

    auth_worker.resultReady.connect(lambda c: (result.update({"creds": c}), loop.quit()))
    auth_worker.errorOccurred.connect(lambda err: (result.update({"error": err}), loop.quit()))
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
        raise RuntimeError("OAuth flow timed out (no response from browser).")

    dialog.close()

    if result["error"]:
        raise RuntimeError("OAuth flow failed: " + result["error"])
    if not result["creds"]:
        raise RuntimeError("Authentication was cancelled or timed out.")

    creds = result["creds"]
    save_credentials(creds, token_path)
    return creds


def unauthenticate(token_filename: str = 'auth_token.json') -> None:
    """Delete the cached credentials file."""
    auth_dir = get_temp_auth_dir()
    token_path = os.path.join(auth_dir, token_filename)
    if os.path.exists(token_path):
        os.remove(token_path)
        logging.info(f"Credentials file {token_path} deleted.")
    else:
        logging.info(f"No credentials file found at {token_path}.")
