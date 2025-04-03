"""Google OAuth2 Authentication Module.

This module provides a high-level interface for authenticating
Google services and getting valid credentials. Credentials
are cached locally in the OS-specific temporary directory to
avoid repeated logins.

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

logging.basicConfig(level=logging.INFO)

# Adjust the SCOPES you need, for example, for Sheets read/write.
DEFAULT_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Fixed location of client_secret.json (relative to this Python module).
CLIENT_SECRETS_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    '..',
    'config',
    'client_secret.json'
))


def get_temp_auth_dir() -> str:
    """Get or create the path to the temporary folder used for credential caching.

    Returns:
        str: A string representing the path to the authentication directory.
    """
    auth_dir = pathlib.Path(tempfile.gettempdir()) / 'ExpensesTracker' / 'auth'
    auth_dir.mkdir(parents=True, exist_ok=True)
    return str(auth_dir)


def load_credentials(token_path: str) -> Optional[google.oauth2.credentials.Credentials]:
    """Attempt to load previously saved credentials from the specified token path.

    Args:
        token_path (str): Path to the credentials JSON file.

    Returns:
        google.oauth2.credentials.Credentials | None:
            Credentials if they exist and parse successfully, or `None` if loading fails.
    """
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
    """Save the provided credentials to the specified token path.

    Args:
        creds (google.oauth2.credentials.Credentials): The credentials to save.
        token_path (str): Path where the credentials should be stored.
    """
    with open(token_path, 'w', encoding='utf-8') as token_file:
        token_file.write(creds.to_json())
    logging.info(f'Credentials saved to {token_path}.')


def load_client_config(path: str) -> Dict[str, Any]:
    """Load the client_secret JSON file from disk and return its contents.

    Args:
        path (str): Path to the client_secret.json file.

    Raises:
        RuntimeError: If the file doesn't exist or isn't valid JSON.

    Returns:
        Dict[str, Any]: Parsed JSON contents of the client_secret file.
    """
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
        message = (
            f'The file at {path} is not valid JSON or is corrupted.\n'
            f'Error details: {ex}'
        )
        raise RuntimeError(message)


def validate_installed_app_config(client_config: Dict[str, Any]) -> None:
    """Ensure the JSON config has the correct structure for an "Installed App" OAuth client.

    Specifically, check the presence of an 'installed' key and required subkeys.

    Args:
        client_config (Dict[str, Any]): The loaded JSON data.

    Raises:
        RuntimeError: If the data is missing essential fields or structure.
    """
    if 'installed' not in client_config:
        message = (
            "The JSON doesn't include an 'installed' section, which indicates this "
            'is not an Installed App OAuth client JSON.\n'
            'Make sure you created an OAuth Client of type "Desktop App" in Google Cloud.\n'
        )
        raise RuntimeError(message)

    required_keys = ['client_id', 'auth_uri', 'token_uri']
    installed_part = client_config['installed']

    missing = [k for k in required_keys if k not in installed_part]
    if missing:
        message = (
            f"Missing required fields in the 'installed' section: {missing}\n"
            'Please recreate or re-download your Desktop App OAuth JSON.'
        )
        raise RuntimeError(message)


def authenticate(
        scopes: Optional[List[str]] = None,
        token_filename: str = 'auth_token.json',
        force: bool = False,
) -> google.oauth2.credentials.Credentials:
    """Authenticate the user via OAuth2 and return valid credentials.

    Args:
        scopes (List[str], optional): List of OAuth2 scopes. Defaults to DEFAULT_SCOPES.
        token_filename (str, optional): Name of the token file. Defaults to 'auth_token.json'.
        force (bool, optional): If True, skip any existing credentials and re-auth. Defaults to False.

    Returns:
        google.oauth2.credentials.Credentials: An object containing the user credentials.

    Raises:
        RuntimeError: If the client_secret.json is missing or invalid.
    """
    if scopes is None:
        scopes = DEFAULT_SCOPES

    # 1. Load and validate the client_secret JSON
    client_config_data = load_client_config(CLIENT_SECRETS_PATH)
    validate_installed_app_config(client_config_data)

    # 2. Attempt to load cached credentials
    auth_dir = get_temp_auth_dir()
    token_path = os.path.join(auth_dir, token_filename)

    # If force=True, skip loading any existing credentials.
    creds = None if force else load_credentials(token_path)

    # 3. If credentials exist, check the scope and validity
    if creds:
        if not set(scopes).issubset(set(creds.scopes or [])):
            logging.info('Credentials found, but scopes mismatch. Re-auth is required.')
            creds = None  # Force re-auth

    if creds and creds.valid:
        logging.info(f'Loaded valid credentials from {token_path}.')
        return creds

    if creds and creds.expired and creds.refresh_token:
        logging.info(f'Credentials found at {token_path}, attempting refresh.')
        try:
            creds.refresh(google.auth.transport.requests.Request())
            logging.info('Successfully refreshed credentials.')
            save_credentials(creds, token_path)
            return creds
        except google.auth.exceptions.RefreshError as ex:
            logging.warning(f'Failed to refresh credentials: {ex}')
            # Fall through to re-auth if refresh fails

    # 4. No valid/refreshable creds => start a new browser-based OAuth flow
    logging.info('No valid credentials found (or force=True), starting new OAuth flow.')
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(client_config_data, scopes=scopes)
    creds = flow.run_local_server(port=0)
    save_credentials(creds, token_path)

    return creds


def unathenticate(token_filename: str = 'auth_token.json') -> None:
    """Delete the cached credentials file.

    Args:
        token_filename (str, optional): Name of the token file. Defaults to 'auth_token.json'.
    """
    auth_dir = get_temp_auth_dir()
    token_path = os.path.join(auth_dir, token_filename)

    if os.path.exists(token_path):
        os.remove(token_path)
        logging.info(f'Credentials file {token_path} deleted.')
    else:
        logging.info(f'No credentials file found at {token_path}. Nothing to delete.')
