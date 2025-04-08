import enum
import json
import logging
import pathlib
import re
import shutil
import tempfile
from typing import Dict, Any, Optional, List

from PySide6 import QtCore

from ..ui.actions import signals

"""
Manages settings for ledger.json and client_secret.json files. Provides
schema validation, unified get/set/revert/save methods, and logs important
operations and errors. Supports creating, removing, listing, and loading
"preset" zips containing client_secret.json and ledger.json.

"""

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

organization_name: str = 'ExpenseTracker'
app_name: str = 'ExpenseTracker'


class Status(enum.StrEnum):
    UnknownStatus = enum.auto()
    ClientSecretNotFound = enum.auto()
    ClientSecretInvalid = enum.auto()
    SpreadsheetIdNotConfigured = enum.auto()
    SpreadsheetWorksheetNotConfigured = enum.auto()
    NotAuthenticated = enum.auto()
    ServiceUnavailable = enum.auto()
    CacheInvalid = enum.auto()
    StatusOkay = enum.auto()


status_user_strings: Dict[Status, str] = {
    Status.ClientSecretNotFound: 'Google authentication information has not been set up. Please check the settings.',
    Status.ClientSecretInvalid: 'Google Client Secret was not found or is invalid. Please check the settings.',
    Status.SpreadsheetIdNotConfigured: 'Spreadsheet ID is has not yet been set. Make sure you set a valid spreadsheet ID in the settings.',
    Status.SpreadsheetWorksheetNotConfigured: 'Spreadsheet worksheet name is has not yet been set. Make sure you set a valid worksheet name in the settings.',
    Status.NotAuthenticated: 'Not authenticated with Google. Please authenticate.',
    Status.ServiceUnavailable: 'Google Sheets service is unavailable. Please check your connection.',
    Status.CacheInvalid: 'The remote data has not yet been fetched, or is out of date. Please fetch the data again.',
    Status.StatusOkay: 'All settings are valid and the application is ready to use.'
}


def is_valid_hex_color(value: str) -> bool:
    """
    Checks if a string is a valid #RRGGBB color format.
    """
    return bool(re.fullmatch(r'#[0-9A-Fa-f]{6}', value))


EXPENSE_DATA_COLUMNS: List[str] = ['category', 'total', 'transactions']
TRANSACTION_DATA_COLUMNS: List[str] = ['date', 'amount', 'description', 'category', 'account']

DATA_MAPPING_KEYS: List[str] = ['date', 'amount', 'description', 'category', 'account']
DATA_MAPPING_SEPARATOR_CHARS: List[str] = ['|', '+']

HEADER_TYPES: List[str] = ['string', 'int', 'float', 'date']

METADATA_KEYS: List[str] = [
    'locale',
    'summary_mode',
    'hide_empty_categories',
    'exclude_negative',
    'exclude_zero',
    'exclude_positive',
    'show_transactions_window',
    'theme'
]

LEDGER_SCHEMA: Dict[str, Any] = {
    'spreadsheet': {
        'type': dict,
        'required': True,
        'item_schema': {
            'id': {'type': str, 'required': True},
            'description': {'type': str, 'required': True},
            'sheet': {'type': str, 'required': True}
        }
    },
    'header': {
        'type': dict,
        'required': True,
        'allowed_values': HEADER_TYPES
    },
    'metadata': {
        'type': dict,
        'required': True,
        'required_keys': METADATA_KEYS,
        'item_schema': {
            'locale': {'type': str, 'required': True},
            'summary_mode': {'type': str, 'required': True},
            'hide_empty_categories': {'type': bool, 'required': True},
            'exclude_negative': {'type': bool, 'required': True},
            'exclude_zero': {'type': bool, 'required': True},
            'exclude_positive': {'type': bool, 'required': True},
            'show_transactions_window': {'type': bool, 'required': True},
            'theme': {'type': str, 'required': True}
        }
    },
    'data_header_mapping': {
        'type': dict,
        'required': True,
        'required_keys': DATA_MAPPING_KEYS,
        'value_type': str
    },
    'categories': {
        'type': dict,
        'required': True,
        'item_schema': {
            'display_name': {'type': str, 'required': True},
            'color': {'type': str, 'required': True, 'format': 'hexcolor'},
            'description': {'type': str, 'required': True},
            'icon': {'type': str, 'required': True},
            'excluded': {'type': bool, 'required': True}
        }
    }
}


def validate_ledger_data(ledger_data: Dict[str, Any]) -> None:
    """
    Validates that ledger_data conforms to LEDGER_SCHEMA. Raises if invalid.
    """
    logger.debug('Validating ledger data against schema.')
    for field, specs in LEDGER_SCHEMA.items():
        if specs.get('required') and field not in ledger_data:
            msg: str = f'Missing required field: {field}'
            logger.error(msg)
            raise ValueError(msg)

        if field not in ledger_data:
            continue

        if not isinstance(ledger_data[field], specs['type']):
            msg = f'Field "{field}" must be {specs["type"]}, got {type(ledger_data[field])}.'
            logger.error(msg)
            raise TypeError(msg)

        if field == 'header':
            _validate_header(ledger_data[field], specs['allowed_values'])
        elif field == 'data_header_mapping':
            _validate_data_header_mapping(ledger_data[field], specs)
        elif field == 'categories':
            _validate_categories(ledger_data[field], specs['item_schema'])


def _validate_header(header_dict: Dict[str, Any], allowed_values: List[str]) -> None:
    logger.debug('Validating "header" section.')
    if not isinstance(header_dict, dict):
        msg: str = 'header must be a dict.'
        logger.error(msg)
        raise TypeError(msg)
    for k, v in header_dict.items():
        if not isinstance(k, str):
            msg = f'Header key "{k}" is not a string.'
            logger.error(msg)
            raise TypeError(msg)
        if not isinstance(v, str):
            msg = f'Header value "{v}" must be a string.'
            logger.error(msg)
            raise TypeError(msg)
        if v not in allowed_values:
            msg = f'Header value "{v}" must be one of {allowed_values}.'
            logger.error(msg)
            raise ValueError(msg)


def _validate_data_header_mapping(mapping_dict: Dict[str, Any], specs: Dict[str, Any]) -> None:
    logger.debug('Validating "data_header_mapping" section.')
    required_keys = set(specs['required_keys'])
    if set(mapping_dict.keys()) != required_keys:
        msg: str = (
            f'data_header_mapping must have keys {required_keys}, '
            f'got {set(mapping_dict.keys())}.'
        )
        logger.error(msg)
        raise ValueError(msg)
    for val in mapping_dict.values():
        if not isinstance(val, specs['value_type']):
            msg: str = 'All data_header_mapping values must be strings.'
            logger.error(msg)
            raise TypeError(msg)


def _validate_categories(categories_dict: Dict[str, Any], item_schema: Dict[str, Any]) -> None:
    logger.debug('Validating "categories" section.')
    if not isinstance(categories_dict, dict):
        msg: str = '"categories" must be a dict.'
        logger.error(msg)
        raise TypeError(msg)
    for cat_name, cat_info in categories_dict.items():
        if not isinstance(cat_info, dict):
            msg = f'Category "{cat_name}" must be a dict.'
            logger.error(msg)
            raise TypeError(msg)
        for field, field_specs in item_schema.items():
            if field_specs['required'] and field not in cat_info:
                msg = f'Category "{cat_name}" missing "{field}".'
                logger.error(msg)
                raise ValueError(msg)
            if field not in cat_info:
                continue
            if not isinstance(cat_info[field], field_specs['type']):
                msg = (
                    f'Category "{cat_name}" field "{field}" must be {field_specs["type"]}, '
                    f'got {type(cat_info[field])}.'
                )
                logger.error(msg)
                raise TypeError(msg)
            if field_specs.get('format') == 'hexcolor':
                if not is_valid_hex_color(cat_info[field]):
                    msg = (
                        f'Category "{cat_name}" field "{field}" must be a valid '
                        f'hex color (#RRGGBB), got "{cat_info[field]}".'
                    )
                    logger.error(msg)
                    raise ValueError(msg)


class ConfigPaths:

    def __init__(self) -> None:
        self.template_dir: pathlib.Path = pathlib.Path(__file__).parent.parent / 'config'
        self.icon_dir: pathlib.Path = self.template_dir / 'icons'
        self.client_secret_template: pathlib.Path = self.template_dir / 'client_secret.json.template'
        self.ledger_template: pathlib.Path = self.template_dir / 'ledger.json.template'
        self.gcp_help_path: pathlib.Path = self.template_dir / 'gcp.md'

        # Config directories
        self.config_dir: pathlib.Path = pathlib.Path(tempfile.gettempdir()) / 'ExpenseTracker' / 'config'
        self.presets_dir: pathlib.Path = self.config_dir / 'presets'
        self.auth_dir: pathlib.Path = self.config_dir / 'auth'
        self.db_dir: pathlib.Path = self.config_dir / 'db'

        # Config files
        self.client_secret_path: pathlib.Path = self.config_dir / 'client_secret.json'
        self.ledger_path: pathlib.Path = self.config_dir / 'ledger.json'
        self.creds_path: pathlib.Path = self.auth_dir / 'creds.json'
        self.db_path: pathlib.Path = self.db_dir / 'cache.db'
        self.usersettings_path: pathlib.Path = self.config_dir / 'settings.ini'

        self._verify_and_prepare()

    def _verify_and_prepare(self) -> None:
        logger.info(f'Verifying required directories and templates in {self.template_dir}')
        if not self.template_dir.exists():
            msg: str = f'Missing template directory: {self.template_dir}'
            logger.error(msg)
            raise FileNotFoundError(msg)
        if not self.icon_dir.exists():
            msg = f'Missing icon directory: {self.icon_dir}'
            logger.error(msg)
            raise FileNotFoundError(msg)
        if not self.client_secret_template.exists():
            msg = f'Missing client_secret template: {self.client_secret_template}'
            logger.error(msg)
            raise FileNotFoundError(msg)
        if not self.ledger_template.exists():
            msg = f'Missing ledger template: {self.ledger_template}'
            logger.error(msg)
            raise FileNotFoundError(msg)

        # Create directories
        if not self.config_dir.exists():
            logger.info(f'Creating config directory: {self.config_dir}')
            self.config_dir.mkdir(parents=True, exist_ok=True)

        if not self.auth_dir.exists():
            logger.info(f'Creating auth directory: {self.auth_dir}')
            self.auth_dir.mkdir(parents=True, exist_ok=True)

        if not self.db_dir.exists():
            logger.info(f'Creating db directory: {self.db_dir}')
            self.db_dir.mkdir(parents=True, exist_ok=True)

        if not self.presets_dir.exists():
            logger.info(f'Creating presets directory: {self.presets_dir}')
            self.presets_dir.mkdir(parents=True, exist_ok=True)

        # Ensure valid configs exists even if we haven't yet set them up
        if not self.client_secret_path.exists():
            logger.info(f'Copying default client_secret from template to {self.client_secret_path}')
            shutil.copy(self.client_secret_template, self.client_secret_path)
        if not self.ledger_path.exists():
            logger.info(f'Copying default ledger from template to {self.ledger_path}')
            shutil.copy(self.ledger_template, self.ledger_path)

        if not self.presets_dir.exists():
            logger.info(f'Creating presets directory: {self.presets_dir}')
            self.presets_dir.mkdir(parents=True, exist_ok=True)

    def revert_ledger_to_template(self) -> None:
        """
        Restores ledger.json from the ledger template.
        """
        logger.info(f'Reverting ledger to template: {self.ledger_template}')
        if not self.ledger_template.exists():
            msg: str = f'Ledger template not found: {self.ledger_template}'
            logger.error(msg)
            raise FileNotFoundError(msg)
        shutil.copy(self.ledger_template, self.ledger_path)

    def revert_client_secret_to_template(self) -> None:
        """
        Restores client_secret.json from the client_secret template.
        """
        logger.info(f'Reverting client_secret to template: {self.client_secret_template}')
        if not self.client_secret_template.exists():
            msg: str = f'Client_secret template not found: {self.client_secret_template}'
            logger.error(msg)
            raise FileNotFoundError(msg)
        shutil.copy(self.client_secret_template, self.client_secret_path)


class MetadataAPI:
    """A dictionary like object for metadata getting and setting.

    """

    def __getitem__(self, key: str) -> Any:
        if key not in METADATA_KEYS:
            raise KeyError(f'Invalid metadata key: {key}, must be one of {METADATA_KEYS}')

        if 'metadata' not in self.ledger_data:
            raise RuntimeError('Malformed ledger data, missing "metadata" section.')

        # Verify type
        _type = LEDGER_SCHEMA['metadata']['item_schema'].get(key, {}).get('type')
        v = self.ledger_data['metadata'].get(key)

        if _type and not isinstance(v, _type):
            logging.error(f'Metadata key "{key}" is not of type {_type}, got {type(v)}.')
            return None

        return v

    def __setitem__(self, key: str, value: Any) -> None:
        if key not in METADATA_KEYS:
            raise KeyError(f'Invalid metadata key: {key}, must be one of {METADATA_KEYS}')

        if 'metadata' not in self.ledger_data:
            raise RuntimeError('Malformed ledger data, missing "metadata" section.')

        # Verify type
        _type = LEDGER_SCHEMA['metadata']['item_schema'].get(key, {}).get('type')
        if _type and not isinstance(value, _type):
            logging.warning(f'Metadata key "{key}" is not of type {_type}, got {type(value)}.')

            # Try to convert to the expected type
            if _type == str:
                value = str(value)
            elif _type == int:
                try:
                    value = int(value)
                except ValueError:
                    logging.error(f'Cannot convert "{value}" to int.')
                    raise
            elif _type == float:
                try:
                    value = float(value)
                except ValueError:
                    logging.error(f'Cannot convert "{value}" to float.')
                    raise
            elif _type == bool:
                value = bool(value)

        self.ledger_data['metadata'][key] = value
        self.save_section('metadata')

class SettingsAPI(ConfigPaths, MetadataAPI):
    """
    Provides an interface to get/set/revert/save ledger.json sections and client_secret.json.
    Also supports presets for these files.
    """
    required_client_secret_keys: List[str] = ['client_id', 'project_id', 'client_secret', 'auth_uri', 'token_uri']

    def __init__(self, ledger_path: Optional[str] = None, client_secret_path: Optional[str] = None) -> None:
        super().__init__()

        self.ledger_path: pathlib.Path = pathlib.Path(ledger_path) if ledger_path else self.ledger_path

        self.client_secret_path: pathlib.Path = (
            pathlib.Path(client_secret_path)
            if client_secret_path
            else self.client_secret_path
        )

        self.ledger_data: Dict[str, Any] = {}
        for k in LEDGER_SCHEMA.keys():
            self.ledger_data[k] = {}

        self.client_secret_data: Dict[str, Any] = {}
        self._watcher: QtCore.QFileSystemWatcher = QtCore.QFileSystemWatcher()

        self._init_watcher()
        self._connect_signals()

        self.init_data()

    def _init_watcher(self):
        self._watcher.addPath(str(self.config_dir))
        self._watcher.addPath(str(self.presets_dir))
        self._watcher.addPath(str(self.auth_dir))
        self._watcher.addPath(str(self.db_dir))

        self._watcher.addPath(str(self.client_secret_path))
        self._watcher.addPath(str(self.ledger_path))
        self._watcher.addPath(str(self.creds_path))
        self._watcher.addPath(str(self.db_path))

    def _connect_signals(self) -> None:
        self._watcher.directoryChanged.connect(signals.configFileChanged)
        self._watcher.fileChanged.connect(signals.configFileChanged)

    def init_data(self) -> None:
        logger.info('Initializing SettingsAPI.')

        try:
            self.ledger_data = self._load_ledger()
        except Exception as e:
            logger.error(f'Failed to load ledger data: {e}')
            raise

        try:
            self.client_secret_data = self._load_client_secret()
        except Exception as e:
            logger.error(f'Failed to load client_secret data: {e}')
            raise

    def _load_ledger(self) -> Dict[str, Any]:
        logger.info(f'Loading ledger from "{self.ledger_path}"')
        if not self.ledger_path.exists():
            msg: str = f'Ledger file not found: {self.ledger_path}'
            logger.error(msg)
            raise FileNotFoundError(msg)
        try:
            with self.ledger_path.open('r', encoding='utf-8') as f:
                data: Dict[str, Any] = json.load(f)
            validate_ledger_data(data)
            return data
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.error(f'Failed to load ledger: {e}')
            raise

    def _load_client_secret(self) -> Dict[str, Any]:
        logger.info(f'Loading client_secret from "{self.client_secret_path}"')
        if not self.client_secret_path.exists():
            msg: str = f'Client secret file not found: {self.client_secret_path}'
            logger.error(msg)
            raise FileNotFoundError(msg)
        try:
            with self.client_secret_path.open('r', encoding='utf-8') as f:
                data: Dict[str, Any] = json.load(f)
            self.validate_client_secret(data)
            return data
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f'Failed to load client_secret: {e}')
            raise

    @classmethod
    def validate_client_secret(cls, client_config: Dict[str, Any]) -> str:
        """
        Validate that the client configuration is for an OAuth client.
        Accept either an "installed" or "web" configuration.

        Returns:
            The key used ("installed" or "web").

        Raises:
            RuntimeError: If neither configuration is present or required fields are missing.

        """
        if 'installed' in client_config:
            key: str = 'installed'
        elif 'web' in client_config:
            key = 'web'
        else:
            raise RuntimeError('Client configuration does not contain an \'installed\' or \'web\' section.')

        config_section: Dict[str, Any] = client_config[key]
        missing: List[str] = [k for k in cls.required_client_secret_keys if k not in config_section]
        if missing:
            raise RuntimeError(f"Missing required fields in the '{key}' section: {missing}.")
        return key

    def get_section(self, section_name: str) -> Dict[str, Any]:
        """
        Returns data for a ledger section or 'client_secret'.
        """
        if section_name == 'client_secret':
            return self.client_secret_data.copy()
        return self.ledger_data[section_name].copy()

    def set_section(self, section_name: str, new_data: Dict[str, Any]) -> None:
        """Sets data for a ledger section or 'client_secret' and commits to disk.

        """
        from ..ui.actions import signals

        if section_name == 'client_secret':
            logger.info('Setting entire client_secret data.')
            self.validate_client_secret(new_data)
            self.client_secret_data = new_data
            self.save_section('client_secret')

            signals.configSectionChanged.emit(section_name)
            return

        if section_name not in self.ledger_data:
            msg: str = f'Unknown section_name for set: "{section_name}"'
            logger.error(msg)
            raise ValueError(msg)

        current_section_data: Dict[str, Any] = self.ledger_data.get(section_name).copy()

        self.ledger_data[section_name] = new_data
        try:
            validate_ledger_data(self.ledger_data)
            self.save_section(section_name)
            signals.configSectionChanged.emit(section_name)

        except (ValueError, TypeError) as e:
            logger.error(f'Validation error on set_section("{section_name}"): {e}')
            self.ledger_data[section_name] = current_section_data
            raise

    def reload_section(self, section_name: str) -> None:
        """Reload the current section from disk.

        """
        from ..ui.actions import signals

        if section_name == 'client_secret':
            logger.info('Reloading client_secret from disk.')
            self.client_secret_data = self._load_client_secret()
            return

        if section_name not in self.ledger_data:
            msg: str = f'Unknown section_name for reload: "{section_name}"'
            logger.error(msg)
            raise ValueError(msg)

        logger.info(f'Reloading section "{section_name}" from disk.')
        try:
            with self.ledger_path.open('r', encoding='utf-8') as f:
                data: Dict[str, Any] = json.load(f)
            validate_ledger_data(data)
            self.ledger_data[section_name] = data[section_name]

            signals.configSectionChanged.emit(section_name)

        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.error(f'Failed to reload section "{section_name}": {e}')
            raise

    def revert_section(self, section_name: str) -> None:
        """
        Reverts the given section from its template.
        """
        from ..ui.actions import signals

        if section_name == 'client_secret':
            logger.info('Reverting client_secret to template.')
            self.revert_client_secret_to_template()
            self.client_secret_data = self._load_client_secret()
            return

        if section_name not in self.ledger_data:
            msg: str = f'Unknown section_name for revert: "{section_name}"'
            logger.error(msg)
            raise ValueError(msg)

        # Load template data
        with self.ledger_template.open('r', encoding='utf-8') as f:
            template_data: Dict[str, Any] = json.load(f)

        if section_name not in template_data:
            msg = f'No template-based revert logic for section "{section_name}".'
            logger.error(msg)
            raise ValueError(msg)

        # Revert to template data
        self.ledger_data[section_name] = template_data[section_name]
        self.save_section(section_name)

        signals.configSectionChanged.emit(section_name)

    def save_section(self, section_name: str) -> None:
        """
        Saves the given section to disk.
        """

        if section_name == 'client_secret':
            logger.info(f'Saving client_secret to "{self.client_secret_path}"')
            self.validate_client_secret(self.client_secret_data)
            try:
                with self.client_secret_path.open('w', encoding='utf-8') as f:
                    json.dump(self.client_secret_data, f, indent=4, ensure_ascii=False)

            except Exception as e:
                logger.error(f'Error saving client_secret: {e}')
                raise
            return

        if section_name not in self.ledger_data:
            msg: str = f'Unknown section_name for save: "{section_name}"'
            logger.error(msg)
            raise ValueError(msg)

        with self.ledger_path.open('r', encoding='utf-8') as f:
            original_data: Dict[str, Any] = json.load(f)

        if section_name not in original_data:
            msg = f'Unknown section_name for save: "{section_name}"'
            logger.error(msg)
            raise ValueError(msg)

        new_data: Dict[str, Any] = original_data.copy()
        new_data[section_name] = self.ledger_data[section_name]

        with self.ledger_path.open('w', encoding='utf-8') as f:
            json.dump(new_data, f, indent=4, ensure_ascii=False)

    def save_all(self) -> None:
        """
        Saves ledger and client_secret. Rolls back ledger on validation failure.
        """
        logger.info('Saving all settings.')
        original_ledger_data: Dict[str, Any] = dict(self.ledger_data)
        try:
            validate_ledger_data(self.ledger_data)
            with self.ledger_path.open('w', encoding='utf-8') as f:
                json.dump(self.ledger_data, f, indent=4, ensure_ascii=False)
        except (ValueError, TypeError) as e:
            logger.error(f'Failed to save ledger: {e}. Rolling back.')
            self.ledger_data = original_ledger_data
            raise

        self.validate_client_secret(self.client_secret_data)
        try:
            with self.client_secret_path.open('w', encoding='utf-8') as f:
                json.dump(self.client_secret_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f'Error saving client_secret: {e}')
            raise

    def get_status(self) -> Status:
        """
        Get the configuration state of the application.

        Returns:
            A Status value indicating the configuration state.
        """
        from ..auth import auth
        from ..auth import service
        from ..database import database

        if not self.client_secret_path.exists():
            return Status.ClientSecretNotFound

        try:
            client_secret: Dict[str, Any] = self.get_section('client_secret')
            self.validate_client_secret(client_secret)
        except:
            return Status.ClientSecretInvalid

        try:
            auth.verify_creds()
        except RuntimeError:
            return Status.NotAuthenticated

        config: Dict[str, Any] = self.get_section('spreadsheet')
        if not config.get('id'):
            return Status.SpreadsheetIdNotConfigured
        if not config.get('worksheet'):
            return Status.SpreadsheetWorksheetNotConfigured

        try:
            service.get_service()
        except:
            return Status.ServiceUnavailable

        try:
            database.verify_db()
        except RuntimeError:
            return Status.CacheInvalid

        return Status.StatusOkay


settings: SettingsAPI = SettingsAPI()


class UserSettings(QtCore.QSettings):

    def __init__(self) -> None:
        super().__init__(organization_name, app_name)

        self.setPath(
            QtCore.QSettings.IniFormat,
            QtCore.QSettings.UserScope,
            str(settings.usersettings_path)
        )

        self.setFallbacksEnabled(True)
        self._connect_signals()

    def _connect_signals(self) -> None:
        signals.dataRangeChanged.connect(self.save_data_range)

    @QtCore.Slot(str, int)
    def save_data_range(self, start_date: str, span: int) -> None:
        """Saves the data range to settings.

        """
        self.setValue('data_range/start_date', start_date)
        self.setValue('data_range/span', span)


state: UserSettings = UserSettings()
