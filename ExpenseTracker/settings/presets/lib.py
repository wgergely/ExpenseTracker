import datetime
import json
import logging
import re
import shutil
import zipfile
from enum import Enum, IntFlag, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .. import lib
from ...ui.actions import signals

PRESET_FORMAT = 'zip'


class PresetType(Enum):
    """
    Represents the type of preset.

    'New' indicates the live configuration that hasn't been saved yet.
    'Saved' refers to a valid preset stored on disk as a ZIP file.
    'Invalid' marks a preset that couldn't be loaded or parsed correctly.

    Higher-level APIs should skip Invalid presets when listing and visually indicate them
    to prevent unintended activation or edits.
    """
    New = auto()
    Saved = auto()
    Invalid = auto()


class PresetFlags(IntFlag):
    """
    Indicates additional status for a preset.

    'Active' means the preset's name matches the current live configuration.
    'Modified' means its stored content differs from the live ledger sections.
    """
    Unmodified = 0
    Active = auto()
    Modified = auto()


class PresetItem:
    """
    Manages a single preset, representing either the live app settings
    or a snapshot stored in a ZIP archive.

    During initialization, it attempts to load
    ledger.json metadata, classify the item type, and determine its Active/Modified state.
    Any errors during loading result in the item being marked as Invalid.
    """

    def __init__(self, path: Optional[Path] = None):
        """
        Create a PresetItem for the given path.

        If the path is omitted or invalid,
        the item wraps the current live configuration.

        Args:
            path: Path to a preset ZIP, or None/invalid for live settings.
        """
        self.path = path
        self.type = PresetType.New
        self.flags = PresetFlags.Unmodified
        self._name = ''
        self._description = ''
        self._init_item()

    def __repr__(self) -> str:
        """
        Return a concise representation for debugging, showing name, type, and flags.
        """
        return (f'<PresetItem name={self._name!r}, '
                f'type={self.type.name}, flags={self.flags!r}>')

    @classmethod
    def open_ledger(cls, zip_path: Path) -> Dict[str, Any]:
        """
        Read and parse ledger.json from a preset ZIP.

        Raises:
            RuntimeError: if the ZIP is corrupt or missing ledger.json.
            ValueError: if ledger.json contains invalid JSON.
        """
        with zipfile.ZipFile(zip_path, 'r') as zf:
            if zf.testzip() or lib.settings.ledger_path.name not in zf.namelist():
                raise RuntimeError(f'Missing or corrupt ledger in {zip_path}')
            raw = zf.read(lib.settings.ledger_path.name)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError(f'Malformed JSON in ledger.json of {zip_path}')

    @classmethod
    def write_ledger(cls, zip_path: Path, ledger_data: Dict[str, Any]) -> None:
        """
        Replace ledger.json inside the ZIP and preserve all other entries' metadata.
        """
        with zipfile.ZipFile(zip_path, 'r') as zf:
            infos = [zf.getinfo(n) for n in zf.namelist()
                     if n != lib.settings.ledger_path.name]
            data_map = {info: zf.read(info.filename) for info in infos}
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for info, content in data_map.items():
                zf.writestr(info, content)
            zf.writestr(lib.settings.ledger_path.name,
                        json.dumps(ledger_data, indent=2))

    def _init_item(self) -> None:
        """
        Determine if the item represents a saved preset or the live config,
        then load metadata and compute status flags.

        Errors mark it Invalid.
        """
        if not self.path or not self.path.exists():
            self._load_current()
            return

        try:
            data = self.open_ledger(self.path)
            md = data.get('metadata', {})
            name = md.get('name')
            description = md.get('description', '')
            if not name:
                raise ValueError('Preset missing name')
            self._name = name
            self._description = description
            self.type = PresetType.Saved
        except Exception as ex:
            logging.error(f'Failed to load preset at {self.path}: {ex}')
            self.type = PresetType.Invalid
            return

        current_name = lib.settings['name']
        if current_name == self._name:
            self.flags |= PresetFlags.Active
        if current_name and self._differs_from_current():
            self.flags |= PresetFlags.Modified

    def _load_current(self) -> None:
        """
        Initialize from live settings, distinguishing saved versus new unsaved configs.
        """
        name = lib.settings['name']
        description = lib.settings['description']
        self._name = name or ''
        self._description = description or ''
        # Reset flags so no accumulation
        self.flags = PresetFlags.Unmodified

        if name:
            matches = []
            for p in lib.settings.presets_dir.glob(f'*.{PRESET_FORMAT}'):
                try:
                    if self.open_ledger(p).get('metadata', {}).get('name') == name:
                        matches.append(p)
                except Exception as ex:
                    logging.warning(f'Failed to read preset {p}: {ex}')
            if matches:
                if len(matches) > 1:
                    logging.warning(f'Multiple presets named \'{name}\' found: '
                                    f'{[p.name for p in matches]}. '
                                    'Using the most recently modified.')
                matches.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                self.path = matches[0]
                self.type = PresetType.Saved
                self.flags = PresetFlags.Active
                if self._differs_from_current():
                    self.flags |= PresetFlags.Modified
                return
            # no saved preset found -> new config
            self.type = PresetType.New
            self.flags = PresetFlags.Active | PresetFlags.Modified
        else:
            # untitled fresh config is always active and modified
            self.type = PresetType.New
            self.flags = PresetFlags.Active | PresetFlags.Modified

    def _differs_from_current(self) -> bool:
        """
        Compare key ledger sections against live data.
        """
        try:
            preset_data = self.open_ledger(self.path)
        except Exception as ex:
            logging.error(f'Failed to read preset {self.path}: {ex}')
            return True
        live = lib.settings.ledger_data
        for sec in lib.LEDGER_SCHEMA:
            if sec == 'metadata':
                continue
            if preset_data.get(sec) != live.get(sec):
                return True
        return False

    @property
    def name(self) -> str:
        """
        Return the preset's configured name.
        """
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """
        Update the preset name in live settings or rewrite the ZIP,
        then emit presetsChanged.
        """
        if not value:
            logging.warning('Ignored empty name')
            return
        if self.type is PresetType.New:
            lib.settings['name'] = value
            self._name = value
            return
        try:
            data = self.open_ledger(self.path)
            data.setdefault('metadata', {})['name'] = value
            self.write_ledger(self.path, data)
            self._name = value
            signals.presetsChanged.emit()
        except Exception as ex:
            logging.error(f'Name update failed: {ex}')

    @property
    def description(self) -> str:
        """
        Return the preset's description text.
        """
        return self._description

    @description.setter
    def description(self, value: str) -> None:
        """
        Update the description in live settings or rewrite the ZIP,
        then emit presetsChanged.
        """
        if self.type is PresetType.New:
            lib.settings['description'] = value
            self._description = value
            return
        try:
            data = self.open_ledger(self.path)
            data.setdefault('metadata', {})['description'] = value
            self.write_ledger(self.path, data)
            self._description = value
            signals.presetsChanged.emit()
        except Exception as ex:
            logging.error(f'Description update failed: {ex}')

    @property
    def is_active(self) -> bool:
        """
        True when the preset's name matches the live configuration.
        """
        return bool(self.flags & PresetFlags.Active)

    @property
    def is_modified(self) -> bool:
        """
        True when the preset's content doesn't match the live ledger.
        """
        return bool(self.flags & PresetFlags.Modified)

    @property
    def is_saved(self) -> bool:
        """
        True if this preset was loaded from a ZIP on disk.
        """
        return self.type is PresetType.Saved

    @property
    def is_valid(self) -> bool:
        """
        True unless loading failed and the type was set to Invalid.
        """
        return self.type is not PresetType.Invalid


class PresetsAPI:
    """
    Manages presets: the live in-memory configuration plus on-disk ZIP snapshots.
    Provides methods to create, rename, duplicate, remove, activate, backup, and restore presets.
    """

    def __init__(self) -> None:
        self._items: List[PresetItem] = []
        signals.presetsChanged.connect(self.load_presets)
        self.load_presets()

    def load_presets(self) -> None:
        """Reload the list of presets.

        Always includes one virtual item for the current configuration, followed by
        valid saved ZIPs excluding backups.
        """
        self._items.clear()
        # Virtual live config
        self._items.append(PresetItem(None))
        # On-disk presets
        presets_dir = lib.settings.presets_dir
        if not presets_dir.exists():
            return
        for zip_path in presets_dir.glob(f'*.{PRESET_FORMAT}'):
            if zip_path.name.startswith('backup_'):
                continue
            item = PresetItem(zip_path)
            if item.is_valid:
                self._items.append(item)
            else:
                logging.warning(f'Skipped invalid preset: {zip_path}')

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, key: Union[int, str]) -> PresetItem:
        if isinstance(key, int):
            return self._items[key]
        if isinstance(key, str):
            for item in self._items:
                if item.name == key:
                    return item
            raise KeyError(f'No preset named \'{key}\'')
        raise TypeError('Key must be int or str')

    def get(self, name: str) -> Optional[PresetItem]:
        """Return the preset with the given name, or None if not found.

        Args:
            name: The name of the preset to look up.

        Returns:
            The matching PresetItem, or None if no match.
        """
        return next((item for item in self._items if item.name == name), None)

    @staticmethod
    def _sanitize(name: str) -> str:
        """
        Make a safe filename. Append timestamp suffix on collisions.
        """
        base = re.sub(r'[\\/*?":<>|]', '_', name).strip().strip('.') or 'preset'
        candidate = base
        while (lib.settings.presets_dir / f'{candidate}.{PRESET_FORMAT}').exists():
            ts = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
            candidate = f'{base}_{ts}'
        return candidate

    def new(self, name: str, description: Optional[str] = None) -> PresetItem:
        """Create a new preset from the current configuration.

        Requires a valid ledger.json and client_secret.json; raises RuntimeError on
        failure.

        Args:
            name: The name for the new preset.
            description: Optional description for the new preset.

        Returns:
            The newly created PresetItem.
        """
        # Validate live config
        try:
            lib.settings.load_ledger()
        except Exception as ex:
            raise RuntimeError('Cannot create preset: ledger.json missing or invalid') from ex
        try:
            lib.settings.load_client_secret()
        except Exception as ex:
            raise RuntimeError('Cannot create preset: client_secret.json missing or invalid') from ex

        # Ensure directories exist
        lib.settings.presets_dir.mkdir(parents=True, exist_ok=True)
        lib.settings.config_dir.mkdir(parents=True, exist_ok=True)

        if self.get(name):
            raise RuntimeError(f'Preset already exists: {name}')

        filename = f'{self._sanitize(name)}.{PRESET_FORMAT}'
        path = lib.settings.presets_dir / filename

        # Archive all files recursively from config_dir
        with zipfile.ZipFile(path, 'w') as zf:
            for f in lib.settings.config_dir.rglob('*'):
                if f.is_file():
                    arc = f.relative_to(lib.settings.config_dir).as_posix()
                    zf.write(f, arcname=arc)

        # Instantiate and set metadata via item setters
        item = PresetItem(path)
        item.name = name
        if description is not None:
            item.description = description

        self._items.append(item)
        signals.presetsChanged.emit()
        return item

    def rename(self, item: PresetItem, new_name: str) -> bool:
        """
        Rename a preset. Updates metadata and renames the ZIP file.
        Returns True on success, False otherwise.
        """
        if not new_name:
            logging.warning('Ignored empty new_name')
            return False
        try:
            item.name = new_name
            if item.is_saved and item.path:
                new_filename = f'{self._sanitize(new_name)}.{PRESET_FORMAT}'
                new_path = lib.settings.presets_dir / new_filename
                if new_path != item.path:
                    item.path.rename(new_path)
                    item.path = new_path
            signals.presetsChanged.emit()
            return True
        except Exception as ex:
            logging.error(f'Failed to rename preset: {ex}')
            return False

    def duplicate(self, item: PresetItem, new_name: str) -> PresetItem:
        """
        Duplicate a saved preset under a new name. Preserves all files and updates metadata.
        Returns the newly duplicated PresetItem.
        """
        if not item.is_saved or not item.path:
            raise RuntimeError('Only saved presets can be duplicated')
        if self.get(new_name):
            raise RuntimeError(f'Preset already exists: {new_name}')

        new_filename = f'{self._sanitize(new_name)}.{PRESET_FORMAT}'
        new_path = lib.settings.presets_dir / new_filename
        shutil.copy2(item.path, new_path)

        new_item = PresetItem(new_path)
        new_item.name = new_name
        new_item.description = item.description

        self._items.append(new_item)
        signals.presetsChanged.emit()
        return new_item

    def remove(self, item: PresetItem) -> bool:
        """
        Remove a saved preset from the disk and the internal list.
        Returns True on success, False otherwise.
        """
        if not item.is_saved or not item.path:
            return False
        try:
            item.path.unlink()
        except Exception as ex:
            logging.error(f'Failed to delete preset at {item.path}: {ex}')
            return False
        self._items.remove(item)
        signals.presetsChanged.emit()
        return True

    def activate(self, item: PresetItem, backup: bool = True) -> bool:
        """
        Activate a saved preset: optionally back up the current config, wipe config_dir,
        then extract the snapshot.
        Returns True on success.

        Args:
            item: the preset to activate
            backup: if True, create a backup before activation
        """
        if not item.is_saved or not item.path:
            logging.error('Cannot activate non-saved preset')
            return False
        # Backup if requested
        if backup:
            try:
                self.backup()
            except Exception as ex:
                logging.error(f'Backup failed, aborting activation: {ex}')
                return False
        # Clear config_dir completely
        try:
            if lib.settings.config_dir.exists():
                shutil.rmtree(lib.settings.config_dir)
            lib.settings.config_dir.mkdir(parents=True, exist_ok=True)
        except Exception as ex:
            logging.error(f'Failed to clear config directory: {ex}')
            return False
        # Extract preset
        try:
            with zipfile.ZipFile(item.path, 'r') as zf:
                # prevent path traversal: ensure all members extract inside config_dir
                root = lib.settings.config_dir.resolve()
                for member in zf.namelist():
                    dest = (lib.settings.config_dir / member).resolve()
                    if not dest.is_relative_to(root):
                        raise RuntimeError(f'Unsafe entry in preset: {member}')
                zf.extractall(lib.settings.config_dir)
            signals.dataAboutToBeFetched.emit()
            signals.configSectionChanged.emit('client_secret')
            for section in lib.LEDGER_SCHEMA:
                signals.configSectionChanged.emit(section)
            logging.info(f'Activated preset: {item.name}')
            return True
        except Exception as ex:
            logging.error(f'Failed to activate preset {item.name}: {ex}')
            return False

    def backup(self) -> PresetItem:
        """
        Create a timestamped backup of the current configuration.
        Returns the created backup PresetItem.
        """
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        name = f'backup_{stamp}'
        existing = self.get(name)
        if existing:
            self.remove(existing)
        return self.new(name)

    def restore(self) -> bool:
        """
        Restore the most recent backup preset without creating another backup.
        Returns True on success, False otherwise.
        """
        backups = [itm for itm in self._items if itm.name.startswith('backup_') and itm.is_saved]
        if not backups:
            logging.error('No backup available to restore')
            return False
        backups.sort(key=lambda x: x.path.stat().st_mtime, reverse=True)
        backup_item = backups[0]
        return self.activate(backup_item, backup=False)

    def items(self) -> List[PresetItem]:
        """
        Return a snapshot list of all presets, including the live configuration.
        """
        return list(self._items)
