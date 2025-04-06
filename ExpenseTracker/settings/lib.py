import json
import logging
import pathlib
import re
import shutil
import tempfile
import zipfile

from PySide6 import QtGui, QtCore

from ..ui.actions import signals

"""
Manages settings for ledger.json and client_secret.json files. Provides
schema validation, unified get/set/revert/save methods, and logs important
operations and errors. Supports creating, removing, listing, and loading
"preset" zips containing client_secret.json and ledger.json.

"""

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def is_valid_hex_color(value):
    """
    Checks if a string is a valid #RRGGBB color format.
    """
    return bool(re.fullmatch(r'#[0-9A-Fa-f]{6}', value))


def validate_client_secret_data(data):
    """
    Ensures client_secret data is a dictionary. Raises ValueError if invalid.
    """
    if not isinstance(data, dict):
        msg = f'client_secret data must be a dictionary, got {type(data)}'
        logger.error(msg)
        raise ValueError(msg)


class ConfigPaths:
    """
    Holds file/directory paths and ensures they exist.
    """

    def __init__(self):
        self.template_dir = pathlib.Path(__file__).parent.parent / 'config'
        self.icon_dir = self.template_dir / 'icons'
        self.client_secret_template = self.template_dir / 'client_secret.json.template'
        self.ledger_template = self.template_dir / 'ledger.json.template'
        self.gcp_help_path = self.template_dir / 'gcp.md'

        self.config_dir = pathlib.Path(tempfile.gettempdir()) / 'ExpenseTracker' / 'config'
        self.client_secret_path = self.config_dir / 'client_secret.json'
        self.ledger_path = self.config_dir / 'ledger.json'


        self.presets_dir = self.template_dir / 'presets'

        self._verify_and_prepare()

    def _verify_and_prepare(self):
        logger.info(f'Verifying required directories and templates in {self.template_dir}')
        if not self.template_dir.exists():
            msg = f'Missing template directory: {self.template_dir}'
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

        if not self.config_dir.exists():
            logger.info(f'Creating config directory: {self.config_dir}')
            self.config_dir.mkdir(parents=True, exist_ok=True)

        if not self.client_secret_path.exists():
            logger.info(f'Copying default client_secret from template to {self.client_secret_path}')
            shutil.copy(self.client_secret_template, self.client_secret_path)

        if not self.ledger_path.exists():
            logger.info(f'Copying default ledger from template to {self.ledger_path}')
            shutil.copy(self.ledger_template, self.ledger_path)

        if not self.presets_dir.exists():
            logger.info(f'Creating presets directory: {self.presets_dir}')
            self.presets_dir.mkdir(parents=True, exist_ok=True)

    def revert_ledger_to_template(self):
        """
        Restores ledger.json from the ledger template.
        """
        logger.info(f'Reverting ledger to template: {self.ledger_template}')
        if not self.ledger_template.exists():
            msg = f'Ledger template not found: {self.ledger_template}'
            logger.error(msg)
            raise FileNotFoundError(msg)
        shutil.copy(self.ledger_template, self.ledger_path)

    def revert_client_secret_to_template(self):
        """
        Restores client_secret.json from the client_secret template.
        """
        logger.info(f'Reverting client_secret to template: {self.client_secret_template}')
        if not self.client_secret_template.exists():
            msg = f'Client_secret template not found: {self.client_secret_template}'
            logger.error(msg)
            raise FileNotFoundError(msg)
        shutil.copy(self.client_secret_template, self.client_secret_path)


DATA_MAPPING_KEYS = ['date', 'amount', 'description', 'category', 'account']
HEADER_TYPES = ['string', 'int', 'float', 'date']

LEDGER_SCHEMA = {
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


def validate_ledger_data(ledger_data):
    """
    Validates that ledger_data conforms to LEDGER_SCHEMA. Raises if invalid.
    """
    logger.debug('Validating ledger data against schema.')
    for field, specs in LEDGER_SCHEMA.items():
        if specs.get('required') and field not in ledger_data:
            msg = f'Missing required field: {field}'
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


def _validate_header(header_dict, allowed_values):
    logger.debug('Validating "header" section.')
    if not isinstance(header_dict, dict):
        msg = 'header must be a dict.'
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


def _validate_data_header_mapping(mapping_dict, specs):
    logger.debug('Validating "data_header_mapping" section.')
    required_keys = set(specs['required_keys'])
    if set(mapping_dict.keys()) != required_keys:
        msg = (
            f'data_header_mapping must have keys {required_keys}, '
            f'got {set(mapping_dict.keys())}.'
        )
        logger.error(msg)
        raise ValueError(msg)
    for val in mapping_dict.values():
        if not isinstance(val, specs['value_type']):
            msg = 'All data_header_mapping values must be strings.'
            logger.error(msg)
            raise TypeError(msg)


def _validate_categories(categories_dict, item_schema):
    logger.debug('Validating "categories" section.')
    if not isinstance(categories_dict, dict):
        msg = '"categories" must be a dict.'
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


class SettingsAPI:
    """
    Provides an interface to get/set/revert/save ledger.json sections and client_secret.json.
    Also supports presets for these files.
    """

    def __init__(self, ledger_path=None, client_secret_path=None):
        self.paths = ConfigPaths()

        self.ledger_path = pathlib.Path(ledger_path) if ledger_path else self.paths.ledger_path

        self.client_secret_path = (
            pathlib.Path(client_secret_path)
            if client_secret_path
            else self.paths.client_secret_path
        )

        self.ledger_data = {}
        for k in LEDGER_SCHEMA.keys():
            self.ledger_data[k] = {}

        self.client_secret_data = {}

        self._connect_signals()
        self.init_data()

    def _connect_signals(self):
        signals.openSpreadsheetRequested.connect(self.open_spreadsheet)

    def init_data(self):
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

    def _load_ledger(self):
        logger.info(f'Loading ledger from "{self.ledger_path}"')
        if not self.ledger_path.exists():
            msg = f'Ledger file not found: {self.ledger_path}'
            logger.error(msg)
            raise FileNotFoundError(msg)
        try:
            with self.ledger_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
            validate_ledger_data(data)
            return data
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.error(f'Failed to load ledger: {e}')
            raise

    def _load_client_secret(self):
        logger.info(f'Loading client_secret from "{self.client_secret_path}"')
        if not self.client_secret_path.exists():
            msg = f'Client secret file not found: {self.client_secret_path}'
            logger.error(msg)
            raise FileNotFoundError(msg)
        try:
            with self.client_secret_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
            validate_client_secret_data(data)
            return data
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f'Failed to load client_secret: {e}')
            raise

    def get_section(self, section_name: str):
        """
        Returns data for a ledger section or 'client_secret'.
        """
        if section_name == 'client_secret':
            return self.client_secret_data
        return self.ledger_data[section_name].copy()

    def set_section(self, section_name, new_data):
        """
        Sets data for a ledger section or 'client_secret' and commits to disk.
        """
        from ..ui.actions import signals

        if section_name == 'client_secret':
            logger.info('Setting entire client_secret data.')
            validate_client_secret_data(new_data)
            self.client_secret_data = new_data
            self.save_section('client_secret')
            return

        if section_name not in self.ledger_data:
            msg = f'Unknown section_name for set: "{section_name}"'
            logger.error(msg)
            raise ValueError(msg)

        current_section_data = self.ledger_data.get(section_name).copy()

        self.ledger_data[section_name] = new_data
        try:
            validate_ledger_data(self.ledger_data)
            self.save_section(section_name)
            signals.configSectionChanged.emit(section_name)

        except (ValueError, TypeError) as e:
            logger.error(f'Validation error on set_section("{section_name}"): {e}')
            self.ledger_data[section_name] = current_section_data
            raise

    def reload_section(self, section_name):
        """
        Reload the current section from disk.
        """
        from ..ui.actions import signals
        if section_name == 'client_secret':
            logger.info('Reloading client_secret from disk.')
            self.client_secret_data = self._load_client_secret()
            return

        if section_name not in self.ledger_data:
            msg = f'Unknown section_name for reload: "{section_name}"'
            logger.error(msg)
            raise ValueError(msg)

        logger.info(f'Reloading section "{section_name}" from disk.')
        try:
            with self.ledger_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
            validate_ledger_data(data)
            self.ledger_data[section_name] = data[section_name]

            signals.configSectionChanged.emit(section_name)

        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.error(f'Failed to reload section "{section_name}": {e}')
            raise

    def revert_section(self, section_name):
        """
        Reverts the given section from its template.
        """
        from ..ui.actions import signals

        if section_name == 'client_secret':
            logger.info('Reverting client_secret to template.')
            self.paths.revert_client_secret_to_template()
            self.client_secret_data = self._load_client_secret()
            return

        if section_name not in self.ledger_data:
            msg = f'Unknown section_name for revert: "{section_name}"'
            logger.error(msg)
            raise ValueError(msg)

        # Load template data
        with self.paths.ledger_template.open('r', encoding='utf-8') as f:
            template_data = json.load(f)

        if section_name not in template_data:
            msg = f'No template-based revert logic for section "{section_name}".'
            logger.error(msg)
            raise ValueError(msg)

        # Revert to template data
        self.ledger_data[section_name] = template_data[section_name]
        self.save_section(section_name)

        signals.configSectionChanged.emit(section_name)

    def save_section(self, section_name):
        """
        Saves the given section to disk.
        """

        # Virtual section
        if section_name == 'client_secret':
            logger.info(f'Saving client_secret to "{self.client_secret_path}"')
            validate_client_secret_data(self.client_secret_data)
            try:
                with self.client_secret_path.open('w', encoding='utf-8') as f:
                    json.dump(self.client_secret_data, f, indent=2, ensure_ascii=False)

            except Exception as e:
                logger.error(f'Error saving client_secret: {e}')
                raise
            return

        if section_name not in self.ledger_data:
            msg = f'Unknown section_name for save: "{section_name}"'
            logger.error(msg)
            raise ValueError(msg)

        with self.ledger_path.open('r', encoding='utf-8') as f:
            original_data = json.load(f)

        if section_name not in original_data:
            msg = f'Unknown section_name for save: "{section_name}"'
            logger.error(msg)
            raise ValueError(msg)

        new_data = original_data.copy()
        new_data[section_name] = self.ledger_data[section_name]

        with self.ledger_path.open('w', encoding='utf-8') as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)

    def save_all(self):
        """
        Saves ledger and client_secret. Rolls back ledger on validation failure.
        """
        logger.info('Saving all settings.')
        original_ledger_data = dict(self.ledger_data)
        try:
            validate_ledger_data(self.ledger_data)
            with self.ledger_path.open('w', encoding='utf-8') as f:
                json.dump(self.ledger_data, f, indent=2, ensure_ascii=False)
        except (ValueError, TypeError) as e:
            logger.error(f'Failed to save ledger: {e}. Rolling back.')
            self.ledger_data = original_ledger_data
            raise

        validate_client_secret_data(self.client_secret_data)
        try:
            with self.client_secret_path.open('w', encoding='utf-8') as f:
                json.dump(self.client_secret_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f'Error saving client_secret: {e}')
            raise

    def list_presets(self):
        """
        Lists all preset zip filenames (without .zip extension).
        """
        return [p.stem for p in self.paths.presets_dir.glob('*.zip')]

    def create_preset(self, preset_name):
        """
        Creates a preset zip with current ledger.json and client_secret.json.
        """
        preset_zip_path = self.paths.presets_dir / f'{preset_name}.zip'
        if preset_zip_path.exists():
            logger.info(f'Overwriting existing preset: {preset_zip_path}')
        try:
            with zipfile.ZipFile(preset_zip_path, 'w') as zf:
                zf.write(self.client_secret_path, arcname='client_secret.json')
                zf.write(self.ledger_path, arcname='ledger.json')
            logger.info(f'Created preset: {preset_zip_path}')
        except Exception as e:
            logger.error(f'Failed to create preset "{preset_name}": {e}')
            raise

    def remove_preset(self, preset_name):
        """
        Removes a preset zip file.
        """
        preset_zip_path = self.paths.presets_dir / f'{preset_name}.zip'
        if not preset_zip_path.exists():
            logger.warning(f'Preset not found for removal: {preset_zip_path}')
            return
        try:
            preset_zip_path.unlink()
            logger.info(f'Removed preset: {preset_zip_path}')
        except Exception as e:
            logger.error(f'Failed to remove preset "{preset_name}": {e}')
            raise

    def load_preset(self, preset_name):
        """
        Loads a preset, overwriting existing ledger.json and client_secret.json.
        """
        preset_zip_path = self.paths.presets_dir / f'{preset_name}.zip'
        if not preset_zip_path.exists():
            msg = f'Preset zip not found: {preset_zip_path}'
            logger.error(msg)
            raise FileNotFoundError(msg)

        try:
            with zipfile.ZipFile(preset_zip_path, 'r') as zf:
                zf.extract('client_secret.json', path=self.paths.config_dir)
                zf.extract('ledger.json', path=self.paths.config_dir)
            logger.info(f'Loaded preset: {preset_name}')
            self.ledger_data = self._load_ledger()
            self.client_secret_data = self._load_client_secret()
        except Exception as e:
            logger.error(f'Failed to load preset "{preset_name}": {e}')
            raise

    @QtCore.Slot()
    def open_spreadsheet(self):
        """
        Opens the spreadsheet in the default browser.
        """
        if not self.ledger_data['spreadsheet']['id']:
            logger.error('No spreadsheet ID found.')
            return

        spreadsheet_id = self.ledger_data['spreadsheet']['id']
        sheet_name = self.ledger_data['spreadsheet']['sheet']

        url = f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid=0'
        if sheet_name:
            url += f'&sheet={sheet_name}'
        logger.info(f'Opening spreadsheet: {url}')
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))


settings = SettingsAPI()
