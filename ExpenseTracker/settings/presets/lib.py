import datetime
import json
import logging
import zipfile
from pathlib import Path

from .. import lib



PRESET_FORMAT = 'zip'


class PresetItem:
    """Represents a preset item.

    Attributes:
        name (str): The preset name.
        path (Path): The path to the preset archive.
        description (str): The description extracted from the preset.
    """

    def __init__(self, name: str, path: Path):
        """Initialize a PresetItem instance.

        Args:
            name (str): Preset name.
            path (Path): Preset file path.
        """
        self._name = name
        self._path = path
        self._description = None

    def __repr__(self):
        return f'PresetItem(name={self.name}, path={self.path})'

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = value

    @property
    def path(self) -> Path:
        return self._path

    @path.setter
    def path(self, value: Path):
        self._path = value

    @property
    def description(self) -> str:
        """Return the preset description from the ledger file within the archive."""
        if self._description is not None:
            return self._description

        with zipfile.ZipFile(self._path, 'r') as zipf:
            if zipf.testzip() is not None or lib.settings.ledger_path.name not in zipf.namelist():
                self._description = ''
            else:
                try:
                    data = json.loads(zipf.read(lib.settings.ledger_path.name))
                    self._description = data.get('description', '')
                except json.JSONDecodeError:
                    logging.error(f'Failed to decode JSON from {self._path}')
                    self._description = ''
                except KeyError:
                    logging.error(f'Key not found in JSON from {self._path}')
                    self._description = ''
                except Exception as e:
                    logging.error(f'Error reading preset description: {e}')
                    self._description = ''
        return self._description


class PresetsAPI(lib.ConfigPaths):
    """API for managing presets including loading, adding, renaming, removing, backup, and activation."""

    def __init__(self):
        """Initialize the API and load presets."""
        super().__init__()
        self.presets = []
        self.load_presets()

    def load_presets(self):
        """Load all presets from the presets directory."""
        if not self.presets_dir.exists():
            logging.error(f'Presets directory does not exist: {self.presets_dir}')
            return

        for file in self.presets_dir.glob(f'*.{PRESET_FORMAT}'):
            if not file.is_file():
                continue
            if file.name.startswith('backup_'):
                continue
            self.presets.append(PresetItem(file.stem, file.absolute()))

    def get_preset(self, name: str) -> PresetItem | None:
        """Retrieve a preset by its name.

        Args:
            name (str): Preset name.

        Returns:
            PresetItem or None: The matching preset if found.
        """
        for preset in self.presets:
            if preset.name == name:
                return preset
        return None

    def remove_preset(self, name: str):
        """Remove a preset by name.

        Args:
            name (str): The name of the preset to remove.
        """
        preset = self.get_preset(name)
        if not preset:
            logging.error(f'Preset not found: {name}')
            return

        try:
            preset.path.unlink()
            self.presets.remove(preset)
            logging.info(f'Removed preset: {name}')
        except Exception as e:
            logging.error(f'Failed to remove preset {name}: {e}')

    def rename_preset(self, old_name: str, new_name: str):
        """Rename an existing preset.

        Args:
            old_name (str): Current name of the preset.
            new_name (str): The new preset name.
        """
        preset = self.get_preset(old_name)
        if not preset:
            logging.error(f'Preset not found: {old_name}')
            return

        try:
            new_path = preset.path.with_stem(new_name)
            preset.path.rename(new_path)
            preset.name = new_name
            preset.path = new_path
            logging.info(f'Renamed preset from {old_name} to {new_name}')
        except Exception as e:
            logging.error(f'Failed to rename preset {old_name} to {new_name}: {e}')

    def add_preset(self, name: str):
        """Add a new preset by archiving the current configuration.

        Args:
            name (str): The name for the new preset.

        Raises:
            RuntimeError: If the config directory does not exist or the preset already exists.
        """
        if not self.config_dir.exists():
            raise RuntimeError(f'Could not create preset: {self.config_dir} does not exist')

        if not self.client_secret_path.exists():
            logging.warning(
                f'Configuration incomplete, missing client secret: {self.client_secret_path}')
        if not self.ledger_path.exists():
            logging.warning(
                f'Configuration incomplete, missing ledger: {self.ledger_path}')
        if not self.creds_path.exists():
            logging.warning(
                f'Configuration incomplete, missing credentials: {self.creds_path}')
        if not self.db_path.exists():
            logging.warning(
                f'Configuration incomplete, missing database: {self.db_path}')

        if self.get_preset(name):
            raise RuntimeError(f'Preset already exists: {name}')

        path = self.presets_dir / f'{name}.{PRESET_FORMAT}'

        with zipfile.ZipFile(path, 'w') as zipf:
            for file in self.config_dir.glob('*'):
                if file.is_file():
                    zipf.write(file, arcname=file.name)

        if name.startswith('backup_'):
            return
        self.presets.append(PresetItem(name, path))

    def backup_config(self):
        """Create a backup preset from the current configuration."""
        name = f'backup_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}'

        if self.get_preset(name):
            logging.warning(f'Backup preset already exists: {name}')
            self.remove_preset(name)

        logging.info(f'Creating backup preset: {name}')
        self.add_preset(name)

    def activate_preset(self, name: str) -> bool:
        """Activate the specified preset by replacing the current configuration.

        Args:
            name (str): The preset to activate.

        Returns:
            bool: True if activation succeeded, False otherwise.
        """
        if not self.presets_dir.exists():
            logging.error(f'Presets directory does not exist: {self.presets_dir}')
            return False

        preset = self.get_preset(name)
        if not preset:
            logging.error(f'Preset not found: {name}')
            return False

        self.backup_config()

        from ...ui.actions import signals
        signals.dataAboutToBeFetched.emit()

        for file in self.config_dir.glob('*'):
            if file.is_file():
                logging.info(f'Removing file: {file}')
                file.unlink()

        logging.info(f'Extracting preset: {preset.path}')
        with zipfile.ZipFile(preset.path, 'r') as zipf:
            zipf.extractall(self.config_dir)

        signals.dataFetched.emit()
        signals.configSectionChanged.emit('client_secret')
        for k in lib.LEDGER_SCHEMA:
            signals.configSectionChanged.emit(k)

        logging.info(f'Activated preset: {name}')
        return True


presets = PresetsAPI()
