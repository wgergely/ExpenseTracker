"""Settings library for ledger and authentication configurations.

Provides:
    - Schema validation and enforcement for ledger.json structure.
    - Loading, saving, reverting, and managing application settings.
    - Preset handling for bundling and loading client_secret.json and ledger.json.
    - Constants for column names and data schemas.
"""

import json
import logging
import pathlib
import re
import shutil
import tempfile
from typing import Dict, Any, Optional, List

from PySide6 import QtCore, QtWidgets

from ..status import status

app_name: str = 'ExpenseTracker'


def is_valid_hex_color(value: str) -> bool:
    """Check if a string is a valid hexadecimal color in #RRGGBB format.

    Args:
        value (str): Color string to validate.

    Returns:
        bool: True if value matches '#RRGGBB', False otherwise.
    """
    return bool(re.fullmatch(r'#[0-9A-Fa-f]{6}', value))


EXPENSE_DATA_COLUMNS: List[str] = ['category', 'total', 'transactions', 'description', 'weight']
DATA_MAPPING_KEYS: List[str] = ['date', 'amount', 'description', 'category', 'account']
TRANSACTION_DATA_COLUMNS: List[str] = DATA_MAPPING_KEYS + ['local_id', ]
TREND_DATA_COLUMNS: List[str] = ['category', 'month', 'monthly_total', 'loess']

DATA_MAPPING_SEPARATOR_CHARS: List[str] = ['|', '+']

HEADER_TYPES: List[str] = ['string', 'int', 'float', 'date']

METADATA_KEYS: List[str] = [
    'name',
    'description',
    'locale',
    'summary_mode',
    'hide_empty_categories',
    'exclude_negative',
    'exclude_zero',
    'exclude_positive',
    'yearmonth',
    'span',
    'theme',
    'loess_fraction',
    'negative_span',
]

LEDGER_SCHEMA: Dict[str, Any] = {
    'spreadsheet': {
        'type': dict,
        'required': True,
        'item_schema': {
            'id': {'type': str, 'required': True},
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
            'name': {'type': str, 'required': True},
            'description': {'type': str, 'required': True},
            'locale': {'type': str, 'required': True},
            'summary_mode': {'type': str, 'required': True},
            'hide_empty_categories': {'type': bool, 'required': True},
            'exclude_negative': {'type': bool, 'required': True},
            'exclude_zero': {'type': bool, 'required': True},
            'exclude_positive': {'type': bool, 'required': True},
            'yearmonth': {'type': str, 'required': True},
            'span': {'type': int, 'required': True},
            'theme': {'type': str, 'required': True},
            'loess_fraction': {'type': float, 'required': True},
            'negative_span': {'type': int, 'required': True},
        }
    },
    'mapping': {
        'type': dict,
        'required': True,
        'required_keys': DATA_MAPPING_KEYS,
        'value_type': str,
        # Only these logical mapping keys may contain multiple headers separated
        'multi_allowed_keys': ['description']
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


def parse_mapping_spec(spec: str) -> list[str]:
    """Split a mapping specification string into individual header names.

    Splits on configured separator characters, strips whitespace, and drops empty segments.

    Args:
        spec (str): Mapping specification (e.g., 'ColA|ColB').

    Returns:
        list[str]: List of header names extracted from spec.
    """
    import re
    pattern = '|'.join(map(re.escape, DATA_MAPPING_SEPARATOR_CHARS))
    parts = re.split(pattern, spec or '')
    return [hdr.strip() for hdr in parts if hdr and hdr.strip()]


def _validate_header(header_dict: Dict[str, Any], allowed_values: List[str]) -> None:
    """Validate the 'header' section of the ledger configuration.

    Ensures header_dict is a mapping of column names to allowed type strings.

    Args:
        header_dict: Mapping of header names to type identifiers.
        allowed_values: List of allowed type identifiers (e.g., 'string', 'int').

    Raises:
        TypeError: If header_dict is not a dict or contains non-string keys/values.
        ValueError: If a header value is not one of the allowed_values.
    """
    logging.debug('Validating "header" section.')
    if not isinstance(header_dict, dict):
        msg: str = 'header must be a dict.'
        logging.error(msg)
        raise TypeError(msg)
    for k, v in header_dict.items():
        if not isinstance(k, str):
            msg = f'Header key "{k}" is not a string.'
            logging.error(msg)
            raise TypeError(msg)
        if not isinstance(v, str):
            msg = f'Header value "{v}" must be a string.'
            logging.error(msg)
            raise TypeError(msg)
        if v not in allowed_values:
            msg = f'Header value "{v}" must be one of {allowed_values}.'
            logging.error(msg)
            raise ValueError(msg)


def _validate_mapping(mapping_dict: Dict[str, Any], specs: Dict[str, Any]) -> None:
    """Validate the 'mapping' section of the ledger configuration.

    Ensures mapping_dict has exactly the required keys and that values conform to type and
    multi-value rules defined in specs.

    Args:
        mapping_dict: Mapping from internal data keys to spreadsheet column specifications.
        specs: Schema dict containing 'required_keys', 'value_type', and 'multi_allowed_keys'.

    Raises:
        ValueError: If mapping_dict keys do not match required_keys or if unauthorized multi-mapping.
        TypeError: If a mapping value is not of the expected type.
    """
    logging.debug('Validating "mapping" section.')
    required_keys = set(specs['required_keys'])
    if set(mapping_dict.keys()) != required_keys:
        msg: str = (
            f'mapping must have keys {required_keys}, '
            f'got {set(mapping_dict.keys())}.'
        )
        logging.error(msg)
        raise ValueError(msg)
    # validate each mapping value and enforce single vs. multi mapping rules
    allowed_multi = specs.get('multi_allowed_keys', [])
    for key, val in mapping_dict.items():
        if not isinstance(val, specs['value_type']):
            msg: str = 'All mapping values must be strings.'
            logging.error(msg)
            raise TypeError(msg)
        # unless explicitly allowed, mapping must reference exactly one column
        if key not in allowed_multi:
            for sep in DATA_MAPPING_SEPARATOR_CHARS:
                if sep in val:
                    msg = (
                        f'Mapping for "{key}" must not contain multiple source columns; '
                        f'found separator "{sep}" in "{val}".'
                    )
                    logging.error(msg)
                    raise ValueError(msg)


def _validate_categories(categories_dict: Dict[str, Any], item_schema: Dict[str, Any]) -> None:
    """Validate the 'categories' section of the ledger configuration.

    Ensures categories_dict maps category names to dicts of required fields matching item_schema.

    Args:
        categories_dict: Mapping of category identifiers to their configuration dicts.
        item_schema: Dict describing required fields, types, and format constraints.

    Raises:
        TypeError: If categories_dict is not a dict or category entries are not dicts or wrong types.
        ValueError: If a required field is missing or fails format validation (e.g., hexcolor).
    """
    logging.debug('Validating "categories" section.')
    if not isinstance(categories_dict, dict):
        msg: str = '"categories" must be a dict.'
        logging.error(msg)
        raise TypeError(msg)
    for cat_name, cat_info in categories_dict.items():
        if not isinstance(cat_info, dict):
            msg = f'Category "{cat_name}" must be a dict.'
            logging.error(msg)
            raise TypeError(msg)
        for field, field_specs in item_schema.items():
            if field_specs['required'] and field not in cat_info:
                msg = f'Category "{cat_name}" missing "{field}".'
                logging.error(msg)
                raise ValueError(msg)
            if field not in cat_info:
                continue
            if not isinstance(cat_info[field], field_specs['type']):
                msg = (
                    f'Category "{cat_name}" field "{field}" must be {field_specs["type"]}, '
                    f'got {type(cat_info[field])}.'
                )
                logging.error(msg)
                raise TypeError(msg)
            if field_specs.get('format') == 'hexcolor':
                if not is_valid_hex_color(cat_info[field]):
                    msg = (
                        f'Category "{cat_name}" field "{field}" must be a valid '
                        f'hex color (#RRGGBB), got "{cat_info[field]}".'
                    )
                    logging.error(msg)
                    raise ValueError(msg)


class ConfigPaths:
    """Manage application file paths and ensure default templates and directories exist.

    This class initializes paths for configuration templates, icons, presets, database,
    and user settings. It verifies the presence of template assets and prepares
    default configuration files by copying them into the user data directory.
    """

    def __init__(self) -> None:
        """Set up application paths and ensure required directories and templates exist.

        Defines template, config, auth, db, presets, and user settings paths.
        Creates missing directories and copies default templates where needed.
        """
        # Set the application name and organization
        QtWidgets.QApplication.setApplicationName(app_name)
        QtWidgets.QApplication.setOrganizationName('')
        logging.debug(f'Setting application name: {app_name}')

        # Get the app data directory
        p = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.AppDataLocation)
        app_data_dir = pathlib.Path(p)
        logging.debug(f'Using app data directory: {app_data_dir}')

        self.template_dir: pathlib.Path = pathlib.Path(__file__).parent.parent / 'config'
        self.icon_dir: pathlib.Path = self.template_dir / 'icons'
        self.client_secret_template: pathlib.Path = self.template_dir / 'client_secret.json.template'
        self.ledger_template: pathlib.Path = self.template_dir / 'ledger.json.template'

        self.gcp_help_path: pathlib.Path = self.template_dir / 'gcp.md'
        self.stylesheet_path = self.template_dir / 'stylesheet.qss'
        self.font_path = self.template_dir / 'font' / 'Inter.ttc'

        self.presets_dir: pathlib.Path = app_data_dir / 'presets'
        self.config_dir: pathlib.Path = app_data_dir / 'config'
        self.auth_dir: pathlib.Path = self.config_dir / 'auth'
        self.db_dir: pathlib.Path = self.config_dir / 'db'

        # Config files
        self.client_secret_path: pathlib.Path = self.config_dir / 'client_secret.json'
        self.ledger_path: pathlib.Path = self.config_dir / 'ledger.json'
        self.creds_path: pathlib.Path = self.auth_dir / 'creds.json'
        self.db_path: pathlib.Path = self.db_dir / 'cache.db'

        # Usersettings
        self.usersettings_path: pathlib.Path = pathlib.Path(
            tempfile.gettempdir()) / 'ExpenseTracker' / 'usersettings.ini'

        self._verify_and_prepare()

    def _verify_and_prepare(self) -> None:
        """Verify templates exist and prepare configuration directories and files.

        Ensures template and icon directories and template files are present.
        Creates missing config, auth, db, and presets directories.
        Copies default ledger and client_secret templates into the config directory if absent.

        Raises:
            FileNotFoundError: If required template directory or file is missing.
        """
        logging.debug(f'Verifying required directories and templates in {self.template_dir}')
        if not self.template_dir.exists():
            msg: str = f'Missing template directory: {self.template_dir}'
            logging.error(msg)
            raise FileNotFoundError(msg)
        if not self.icon_dir.exists():
            msg = f'Missing icon directory: {self.icon_dir}'
            logging.error(msg)
            raise FileNotFoundError(msg)
        if not self.client_secret_template.exists():
            msg = f'Missing client_secret template: {self.client_secret_template}'
            logging.error(msg)
            raise FileNotFoundError(msg)
        if not self.ledger_template.exists():
            msg = f'Missing ledger template: {self.ledger_template}'
            logging.error(msg)
            raise FileNotFoundError(msg)

        # Create directories
        if not self.config_dir.exists():
            logging.debug(f'Creating config directory: {self.config_dir}')
            self.config_dir.mkdir(parents=True, exist_ok=True)

        if not self.auth_dir.exists():
            logging.debug(f'Creating auth directory: {self.auth_dir}')
            self.auth_dir.mkdir(parents=True, exist_ok=True)

        if not self.db_dir.exists():
            logging.debug(f'Creating db directory: {self.db_dir}')
            self.db_dir.mkdir(parents=True, exist_ok=True)

        if not self.presets_dir.exists():
            logging.debug(f'Creating presets directory: {self.presets_dir}')
            self.presets_dir.mkdir(parents=True, exist_ok=True)

        # Ensure valid configs exists even if we haven't yet set them up
        if not self.client_secret_path.exists():
            logging.debug(f'Copying default client_secret from template to {self.client_secret_path}')
            shutil.copy(self.client_secret_template, self.client_secret_path)
        if not self.ledger_path.exists():
            logging.debug(f'Copying default ledger from template to {self.ledger_path}')
            shutil.copy(self.ledger_template, self.ledger_path)

        if not self.presets_dir.exists():
            logging.debug(f'Creating presets directory: {self.presets_dir}')
            self.presets_dir.mkdir(parents=True, exist_ok=True)

    def revert_ledger_to_template(self) -> None:
        """Restore ledger.json from the default template file.

        Raises:
            FileNotFoundError: If the ledger template file is missing.
        """
        logging.debug(f'Reverting ledger to template: {self.ledger_template}')
        if not self.ledger_template.exists():
            msg: str = f'Ledger template not found: {self.ledger_template}'
            logging.error(msg)
            raise FileNotFoundError(msg)
        shutil.copy(self.ledger_template, self.ledger_path)

    def revert_client_secret_to_template(self) -> None:
        """Restore client_secret.json from the default template file.

        Raises:
            FileNotFoundError: If the client_secret template file is missing.
        """
        logging.debug(f'Reverting client_secret to template: {self.client_secret_template}')
        if not self.client_secret_template.exists():
            msg: str = f'Client_secret template not found: {self.client_secret_template}'
            logging.error(msg)
            raise FileNotFoundError(msg)
        shutil.copy(self.client_secret_template, self.client_secret_path)


class SettingsAPI(ConfigPaths):
    """
    Provides an interface to get/set/revert/save ledger.json sections and client_secret.json.
    Also supports presets for these files.
    """
    required_client_secret_keys: List[str] = ['client_id', 'project_id', 'client_secret', 'auth_uri', 'token_uri']

    def __init__(self, ledger_path: Optional[str] = None, client_secret_path: Optional[str] = None) -> None:
        """Initialize SettingsAPI and load ledger and client_secret data.

        Args:
            ledger_path: Optional path to a custom ledger.json file.
            client_secret_path: Optional path to a custom client_secret.json file.
        """
        super().__init__()

        self.ledger_path: pathlib.Path = pathlib.Path(ledger_path) if ledger_path else self.ledger_path

        self.client_secret_path: pathlib.Path = (
            pathlib.Path(client_secret_path)
            if client_secret_path
            else self.client_secret_path
        )

        self._signals_blocked: bool = False

        self.ledger_data: Dict[str, Any] = {}
        for k in LEDGER_SCHEMA.keys():
            self.ledger_data[k] = {}

        self.client_secret_data: Dict[str, Any] = {}

        self._connect_signals()

        self.init_data()

    def __getitem__(self, key: str) -> Any:
        """Retrieve a metadata value using dictionary-style access.

        Args:
            key: Metadata key to retrieve.

        Returns:
            Value stored for the metadata key.

        Raises:
            KeyError: If key is not in METADATA_KEYS.
            RuntimeError: If metadata section is missing from ledger_data.
        """
        if key not in METADATA_KEYS:
            raise KeyError(f'Invalid metadata key: {key}, must be one of {METADATA_KEYS}')

        if 'metadata' not in self.ledger_data:
            raise RuntimeError('Malformed ledger data, missing "metadata" section.')

        # Verify type
        _type = LEDGER_SCHEMA['metadata']['item_schema'].get(key, {}).get('type', None)
        if _type is None:
            logging.error(f'Metadata key "{key}" is not defined in schema.')
            return None

        v = self.ledger_data['metadata'].get(key)

        if _type and not isinstance(v, _type):
            logging.error(f'Metadata key "{key}" is not of type {_type}, got {type(v)}.')
            return None

        return v

    def __setitem__(self, key: str, value: Any) -> None:
        """Assign a metadata value using dictionary-style access and persist it.

        Args:
            key: Metadata key to set.
            value: Value to assign to the metadata key.

        Raises:
            KeyError: If key is not in METADATA_KEYS or undefined in schema.
            RuntimeError: If metadata section is missing.
        """
        if key not in METADATA_KEYS:
            raise KeyError(f'Invalid metadata key: {key}, must be one of {METADATA_KEYS}')

        if 'metadata' not in self.ledger_data:
            raise RuntimeError('Malformed ledger data, missing "metadata" section.')

        # Verify
        _type = LEDGER_SCHEMA['metadata']['item_schema'].get(key, {}).get('type', None)
        if _type is None:
            logging.error(f'Metadata key "{key}" is not defined in schema.')
            raise KeyError(f'Metadata key "{key}" is not defined in schema.')

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

        if self._signals_blocked:
            return

        from ..ui.actions import signals
        signals.metadataChanged.emit(key, value)

    def _connect_signals(self) -> None:
        """Connect preset-related signals to reload configuration data."""
        from ..ui.actions import signals

        signals.presetsChanged.connect(self.init_data)
        signals.presetActivated.connect(self.init_data)

    def block_signals(self, v: bool) -> None:
        """Enable or disable emission of configuration change signals.

        Args:
            v: True to block signals, False to allow signals to emit.
        """
        self._signals_blocked = v

    @QtCore.Slot()
    def init_data(self) -> None:
        """Reload ledger and client_secret data, emitting UI update signals."""
        self.load_ledger()
        self.load_client_secret()

        from ..ui.actions import signals
        signals.configSectionChanged.emit('client_secret')
        for section in LEDGER_SCHEMA.keys():
            if section == 'metadata':
                continue
            signals.configSectionChanged.emit(section)

        for k, v in self.ledger_data.get('metadata', {}).items():
            signals.metadataChanged.emit(k, v)

    def load_ledger(self) -> Dict[str, Any]:
        """Load ledger.json from disk and validate against schema.

        Returns:
            The loaded ledger data dictionary.

        Raises:
            status.LedgerConfigNotFoundException: If ledger.json file is missing.
            status.LedgerConfigInvalidException: If JSON parsing or validation fails.
        """
        logging.debug(f'Loading ledger from "{self.ledger_path}"')
        if not self.ledger_path.exists():
            raise status.LedgerConfigNotFoundException

        try:
            with self.ledger_path.open('r', encoding='utf-8') as f:
                data: Dict[str, Any] = json.load(f)
            self.ledger_data = data
            self.validate_ledger_data()
            return self.ledger_data

        except Exception as ex:
            raise status.LedgerConfigInvalidException from ex

    def load_client_secret(self) -> Dict[str, Any]:
        """Load client_secret.json from disk and validate required OAuth fields.

        Returns:
            The loaded client secret data dictionary.

        Raises:
            FileNotFoundError: If client_secret.json file is missing.
            status.ClientSecretInvalidException: If JSON parsing or required fields are missing.
        """
        logging.debug(f'Loading client_secret from "{self.client_secret_path}"')
        if not self.client_secret_path.exists():
            msg: str = f'Client secret file not found: {self.client_secret_path}'
            logging.error(msg)
            raise FileNotFoundError(msg)
        try:
            with self.client_secret_path.open('r', encoding='utf-8') as f:
                data: Dict[str, Any] = json.load(f)
            self.client_secret_data = data
            self.validate_client_secret()
            return self.client_secret_data
        except (ValueError, json.JSONDecodeError) as ex:
            raise status.ClientSecretInvalidException from ex

    def validate_client_secret(self, data=None) -> str:
        """Validate that the client configuration contains required OAuth credentials.

        Args:
            data (dict, optional): Client secret data to validate. Defaults to loaded client_secret_data.

        Returns:
            str: Section key used ('installed' or 'web').

        Raises:
            status.ClientSecretInvalidException: If no valid client_secret section exists or required fields are missing.
        """
        # Use provided data if any, else use loaded client_secret_data
        if data is None:
            data = self.client_secret_data

        # Determine which section to use: prefer 'installed', then 'web'

        key = next((k for k in ('installed', 'web') if k in data), None)
        if not key:
            raise status.ClientSecretInvalidException('Missing "installed" or "web" section in client_secret.')

        logging.debug(f'Found "{key}" section in client_secret.')

        config_section: Dict[str, Any] = data[key]
        missing: List[str] = [k for k in self.required_client_secret_keys if k not in config_section]
        if missing:
            raise status.ClientSecretInvalidException(
                f'Missing required fields in the \'{key}\' section: {missing}.'
            )
        return key

    def validate_ledger_data(self, data: Dict[str, Any] = None) -> None:
        """Validate ledger data against the defined LEDGER_SCHEMA.

        Checks each section for required presence, correct types, and nested schema constraints.

        Args:
            data (dict, optional): Ledger data to validate. Defaults to self.ledger_data.

        Raises:
            RuntimeError: If data is empty.
            status.LedgerConfigInvalidException: If a required section is missing or validation fails.
        """
        # Use provided data if any, else use loaded ledger_data
        if data is None:
            data = self.ledger_data
        if not data:
            raise RuntimeError('Ledger data is empty.')

        logging.debug('Validating ledger data against schema.')
        for field, specs in LEDGER_SCHEMA.items():
            if specs.get('required') and field not in data:
                msg: str = f'Missing required field: {field}'
                raise status.LedgerConfigInvalidException(msg)

            if field not in data:
                continue

            if not isinstance(data[field], specs['type']):
                msg = f'Field "{field}" must be {specs["type"]}, got {type(data[field])}.'
                raise status.LedgerConfigInvalidException(msg)

            if field == 'header':
                _validate_header(data[field], specs['allowed_values'])
            elif field == 'mapping':
                _validate_mapping(data[field], specs)
            elif field == 'categories':
                _validate_categories(data[field], specs['item_schema'])

        logging.debug('Ledger data is valid.')

    def get_section(self, section_name: str) -> Dict[str, Any]:
        """Retrieve a copy of configuration data for a ledger or client_secret section.

        Args:
            section_name: Section name ('client_secret' or key from ledger schema).

        Returns:
            A copied dict of the requested section data.

        Raises:
            KeyError: If section_name is not in ledger_data.
        """
        if section_name == 'client_secret':
            return self.client_secret_data.copy()

        return self.ledger_data[section_name].copy()

    def set_section(self, section_name: str, new_data: Dict[str, Any]) -> None:
        """Replace and persist a configuration section.

        Args:
            section_name: Section to update ('client_secret' or ledger key).
            new_data: New data dict for the section.

        Raises:
            TypeError: If new_data type is invalid for the metadata section.
            ValueError: If required metadata keys are missing or section_name is unrecognized.
        """
        from ..ui.actions import signals

        if section_name == 'client_secret':
            logging.debug('Setting entire client_secret data.')
            self.validate_client_secret(new_data)
            self.client_secret_data = new_data
            self.save_section('client_secret')

            signals.configSectionChanged.emit(section_name)
            return

        # Special handling for the metadata section
        if section_name == 'metadata':
            # Validate that metadata is a dict
            if not isinstance(new_data, dict):
                msg = f'{section_name} must be a dict.'
                logging.error(msg)
                raise TypeError(msg)

            # Check for missing metadata keys
            missing_meta = [k for k in METADATA_KEYS if k not in new_data]
            if missing_meta:
                msg = f'Missing metadata keys: {missing_meta}'
                logging.error(msg)
                raise ValueError(msg)

            # All required keys present; update and save
            self.ledger_data[section_name] = new_data
            self.save_section(section_name)
            signals.configSectionChanged.emit(section_name)

            return

        if section_name not in self.ledger_data:
            msg: str = f'Unknown section_name for set: "{section_name}"'
            logging.error(msg)
            raise ValueError(msg)

        current_section_data: Dict[str, Any] = self.ledger_data.get(section_name).copy()

        self.ledger_data[section_name] = new_data
        try:
            self.validate_ledger_data()
            self.save_section(section_name)
            signals.configSectionChanged.emit(section_name)

        except (ValueError, TypeError) as e:
            logging.error(f'Validation error on set_section("{section_name}"): {e}')
            self.ledger_data[section_name] = current_section_data
            raise

    def reload_section(self, section_name: str) -> None:
        """Reload a configuration section from its source file and emit change signal.

        Args:
            section_name: Section to reload ('client_secret' or ledger key).

        Raises:
            ValueError: If section_name is unrecognized.
            JSONDecodeError: If parsing ledger.json fails.
            status.LedgerConfigInvalidException: If reloaded data fails validation.
        """
        from ..ui.actions import signals

        if section_name == 'client_secret':
            logging.debug('Reloading client_secret from disk.')
            self.load_client_secret()
            return

        if section_name not in self.ledger_data:
            msg: str = f'Unknown section_name for reload: "{section_name}"'
            logging.error(msg)
            raise ValueError(msg)

        logging.debug(f'Reloading section "{section_name}" from disk.')
        try:
            with self.ledger_path.open('r', encoding='utf-8') as f:
                data: Dict[str, Any] = json.load(f)
            self.validate_ledger_data(data=data)
            self.ledger_data[section_name] = data[section_name]

            signals.configSectionChanged.emit(section_name)

        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logging.error(f'Failed to reload section "{section_name}": {e}')
            raise

    def revert_section(self, section_name: str) -> None:
        """Revert a configuration section to its template default and save.

        Args:
            section_name: Section to revert ('client_secret' or ledger key).

        Raises:
            ValueError: If section_name is invalid or not present in the template.
        """
        from ..ui.actions import signals

        if section_name == 'client_secret':
            logging.debug('Reverting client_secret to template.')
            self.revert_client_secret_to_template()
            self.load_client_secret()
            return

        if section_name not in self.ledger_data:
            msg: str = f'Unknown section_name for revert: "{section_name}"'
            logging.error(msg)
            raise ValueError(msg)

        # Load template data
        with self.ledger_template.open('r', encoding='utf-8') as f:
            template_data: Dict[str, Any] = json.load(f)

        if section_name not in template_data:
            msg = f'No template-based revert logic for section "{section_name}".'
            logging.error(msg)
            raise ValueError(msg)

        # Revert to template data
        self.ledger_data[section_name] = template_data[section_name]
        self.save_section(section_name)

        signals.configSectionChanged.emit(section_name)

    def save_section(self, section_name: str) -> None:
        """Persist a single configuration section to its corresponding file.

        Args:
            section_name: The section to save ('client_secret' or ledger key).

        Raises:
            ValueError: If section_name is not recognized.
            Exception: For I/O or validation errors when writing to file.
        """

        if section_name == 'client_secret':
            logging.debug(f'Saving client_secret to "{self.client_secret_path}"')
            self.validate_client_secret(self.client_secret_data)
            try:
                with self.client_secret_path.open('w', encoding='utf-8') as f:
                    json.dump(self.client_secret_data, f, indent=4, ensure_ascii=False)

            except Exception as e:
                logging.error(f'Error saving client_secret: {e}')
                raise
            return

        if section_name not in self.ledger_data:
            msg: str = f'Unknown section_name for save: "{section_name}"'
            logging.error(msg)
            raise ValueError(msg)

        with self.ledger_path.open('r', encoding='utf-8') as f:
            original_data: Dict[str, Any] = json.load(f)

        if section_name not in original_data:
            msg = f'Unknown section_name for save: "{section_name}"'
            logging.error(msg)
            raise ValueError(msg)

        new_data: Dict[str, Any] = original_data.copy()
        new_data[section_name] = self.ledger_data[section_name]

        with self.ledger_path.open('w', encoding='utf-8') as f:
            json.dump(new_data, f, indent=4, ensure_ascii=False)

    def save_all(self) -> None:
        """Save both ledger.json and client_secret.json atomically, with rollback on failure.

        Validates data before writing. If ledger save fails, restores previous state.

        Raises:
            status.LedgerConfigInvalidException: On ledger validation failure.
            Exception: For I/O errors writing files.
        """
        logging.debug('Saving all settings.')
        original_ledger_data: Dict[str, Any] = dict(self.ledger_data)
        try:
            self.validate_ledger_data()
            with self.ledger_path.open('w', encoding='utf-8') as f:
                json.dump(self.ledger_data, f, indent=4, ensure_ascii=False)
        except (ValueError, TypeError) as e:
            logging.error(f'Failed to save ledger: {e}. Rolling back.')
            self.ledger_data = original_ledger_data
            raise

        self.validate_client_secret(self.client_secret_data)
        try:
            with self.client_secret_path.open('w', encoding='utf-8') as f:
                json.dump(self.client_secret_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f'Error saving client_secret: {e}')
            raise


settings: SettingsAPI = SettingsAPI()
