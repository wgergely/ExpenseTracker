import datetime
import json
import logging
import re
import shutil
import zipfile
from enum import Enum, IntFlag, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from PySide6 import QtCore

from .. import lib
from ...ui.actions import signals

PRESET_FORMAT = 'zip'
# Maximum number of backup files to retain
MAX_BACKUPS = 5


class PresetType(Enum):
    """
    Represents the type of preset.

    'Active' indicates the live configuration that hasn't been saved yet.
    'Saved' refers to a valid preset stored on disk as a ZIP file.
    'Invalid' marks a preset that couldn't be loaded or parsed correctly.

    Higher-level APIs should skip Invalid presets when listing and visually indicate them
    to prevent unintended activation or edits.
    """
    Active = auto()
    Saved = auto()
    Invalid = auto()


class PresetFlags(IntFlag):
    """
    Indicates additional status for a preset.

    'Active' means the preset's name matches the current live configuration.
    'Out-of-date' means its stored content differs from the live ledger sections.
    """
    Unmodified = 0
    Active = auto()
    OutOfDate = auto()


class PresetItem:
    """
    Manages a single preset, representing either the live app settings
    or a snapshot stored in a ZIP archive.

    During initialization, it attempts to load
    ledger.json metadata, classify the item type, and determine its Active/Out-of-date state.
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
        self.type = PresetType.Active
        self.flags = PresetFlags.Unmodified
        self._name = ''
        self._description = ''

        self._connect_signals()

        self._init_item()

    def _connect_signals(self):
        """
        Connect signals to update the preset item when settings change.
        """
        signals.configSectionChanged.connect(self._init_item)

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
        # Reset flags before (re)initializing status
        self.flags = PresetFlags.Unmodified
        if not self.path or not self.path.exists():
            # Live configuration item
            self._load_current()
            return

        try:
            data = self.open_ledger(self.path)
            md = data.get('metadata', {})
            name = md.get('name', '')
            description = md.get('description', '')

            self._name = name
            self._description = description

            if not name:
                logging.warning(f'Preset {self.path} has no name')
                self.type = PresetType.Invalid
            else:
                self.type = PresetType.Saved

        except Exception as ex:
            logging.warning(f'Failed to load preset at {self.path}: {ex}')
            self.type = PresetType.Invalid
            return

        current_name = lib.settings['name']
        # Mark active if this preset name matches the live configuration
        if current_name == self._name:
            self.flags |= PresetFlags.Active
            # Only active presets track out-of-date state
            if self._differs_from_current():
                self.flags |= PresetFlags.OutOfDate

    def _load_current(self) -> None:
        """
        Initialize from live settings, distinguishing saved versus new unsaved configs.
        """
        name = lib.settings['name'] or ''

        description = lib.settings['description'] or ''
        self._description = description or ''

        if not name:
            # A preset without a name is always invalid
            self.type = PresetType.Invalid
            self.flags = PresetFlags.Unmodified
            return

        self._name = name

        # Virtual live config: always active, not representing a saved preset
        self.type = PresetType.Active
        self.flags = PresetFlags.Active

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
        if self.type is PresetType.Active:
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
        if self.type is PresetType.Active:
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
    def is_out_of_date(self) -> bool:
        """
        True when the preset's content doesn't match the live ledger.
        """
        return bool(self.flags & PresetFlags.OutOfDate)

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


class PresetsAPI(QtCore.QObject):
    """
    Manages presets: the live in-memory configuration plus on-disk ZIP snapshots.
    Provides methods to create, rename, duplicate, remove, activate, backup, and restore presets.
    """

    # Signals to notify views of changes
    presetsReloaded = QtCore.Signal()
    presetAdded = QtCore.Signal(int)
    presetRemoved = QtCore.Signal(int)
    presetRenamed = QtCore.Signal(int)
    presetActivated = QtCore.Signal(int)
    presetUpdated = QtCore.Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._items: List[PresetItem] = []
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
        # notify listeners that list was reloaded
        self.presetsReloaded.emit()

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
        # Append timestamp with microseconds to avoid collisions
        while (lib.settings.presets_dir / f'{candidate}.{PRESET_FORMAT}').exists():
            ts = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
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

        # Prevent duplicate saved presets; ignore the virtual live config
        if any(it.is_saved and it.name == name for it in self._items):
            logging.error(f"Cannot create preset: '{name}' already exists on disk")
            raise RuntimeError(f'Preset already exists: {name}')

        filename = f'{self._sanitize(name)}.{PRESET_FORMAT}'
        path = lib.settings.presets_dir / filename

        # Archive all files recursively from config_dir
        with zipfile.ZipFile(path, 'w') as zf:
            for f in lib.settings.config_dir.rglob('*'):
                if f.is_file():
                    arc = f.relative_to(lib.settings.config_dir).as_posix()
                    zf.write(f, arcname=arc)

        # Instantiate and set metadata via item setters without triggering reloads
        item = PresetItem(path)
        try:
            signals.blockSignals(True)
            item.name = name
            if description is not None:
                item.description = description
        finally:
            signals.blockSignals(False)
        # Determine initial flags: active if name matches live config, otherwise unmodified
        try:
            current_name = lib.settings['name'] or ''
        except Exception:
            current_name = ''
        if name == current_name:
            logging.debug(f"New preset '{name}' matches active configuration name; marking as active")
            item.flags = PresetFlags.Active
        else:
            item.flags = PresetFlags.Unmodified
        self._items.append(item)
        # notify listeners of new preset at end
        idx = len(self._items) - 1
        self.presetAdded.emit(idx)
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
            # capture old name for propagation
            old_name = item.name
            # record index before rename
            idx = self._items.index(item)
            # rename primary item
            item.name = new_name
            # if this is a saved preset, also rename its file on disk
            if item.is_saved and item.path:
                new_filename = f'{self._sanitize(new_name)}.{PRESET_FORMAT}'
                new_path = lib.settings.presets_dir / new_filename
                if new_path != item.path:
                    item.path.rename(new_path)
                    item.path = new_path
            # propagate name change to matching presets
            if item.type is PresetType.Active:
                # active renamed: update saved presets that matched old name
                for other in list(self._items):
                    if other is item:
                        continue
                    if other.is_saved and other.name == old_name:
                        other.name = new_name
            else:
                # a saved preset renamed: update active config if it matched old name
                active = self._items[0]
                if active.name == old_name:
                    active.name = new_name
            # notify listeners of rename
            self.presetRenamed.emit(idx)
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

        # Instantiate duplicate and update metadata without triggering presetChanged
        new_item = PresetItem(new_path)
        try:
            signals.blockSignals(True)
            # Set new name and description in the archive
            new_item.name = new_name
            new_item.description = item.description
        finally:
            signals.blockSignals(False)
        # Recompute flags based on updated metadata (e.g., active/out-of-date)
        try:
            new_item._init_item()
        except Exception:
            pass
        # Add to internal list and notify listeners
        self._items.append(new_item)
        idx = len(self._items) - 1
        self.presetAdded.emit(idx)
        return new_item

    def set_description(self, item: PresetItem, new_description: str) -> bool:
        """
        Update the description for a preset and propagate to any matching items.
        """
        try:
            old_name = item.name
            # update primary item
            if item.type is PresetType.Active:
                # live config
                lib.settings['description'] = new_description
                item._description = new_description
            else:
                # saved preset: update metadata inside ZIP
                data = PresetItem.open_ledger(item.path)
                data.setdefault('metadata', {})['description'] = new_description
                PresetItem.write_ledger(item.path, data)
                item._description = new_description
            # propagate to other items with the same preset name
            for other in self._items:
                if other is item:
                    continue
                if other.name != old_name:
                    continue
                # update matching items
                if other.type is PresetType.Active:
                    lib.settings['description'] = new_description
                    other._description = new_description
                else:
                    data = PresetItem.open_ledger(other.path)
                    data.setdefault('metadata', {})['description'] = new_description
                    PresetItem.write_ledger(other.path, data)
                    other._description = new_description
            # notify views
            signals.presetsChanged.emit()
            return True
        except Exception as ex:
            logging.error(f'Failed to set description for preset: {ex}')
            return False

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
        # remove from internal list
        try:
            idx = self._items.index(item)
            self._items.pop(idx)
        except ValueError:
            idx = None
        # notify listeners of removal
        if idx is not None:
            self.presetRemoved.emit(idx)
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
        # Prevent activation of out-of-date presets (requires snapshot to match live config)
        if item.is_out_of_date:
            logging.error(f'Cannot activate out-of-date preset: {item.name}')
            raise RuntimeError(
                f"Cannot activate out-of-date preset '{item.name}'. Please update it before activating."
            )
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
            # Extract preset into config directory
            with zipfile.ZipFile(item.path, 'r') as zf:
                # prevent path traversal: ensure all members extract inside config_dir
                root = lib.settings.config_dir.resolve()
                for member in zf.namelist():
                    dest = (lib.settings.config_dir / member).resolve()
                    if not dest.is_relative_to(root):
                        raise RuntimeError(f'Unsafe entry in preset: {member}')
                zf.extractall(lib.settings.config_dir)
            # Reload settings (ledger and client_secret) from new files
            try:
                lib.settings.init_data()
            except Exception as ex:
                logging.error(f'Failed to reload settings after activation: {ex}')
            # Notify data fetch and config editors of updated sections
            signals.dataAboutToBeFetched.emit()
            # Client secret section may have changed
            signals.configSectionChanged.emit('client_secret')
            # Ledger sections
            for section in lib.LEDGER_SCHEMA:
                signals.configSectionChanged.emit(section)
            logging.debug(f'Activated preset: {item.name}')
            # Reload presets list to update model items (flags, names, active state)
            self.load_presets()
            # Emit global activation signal for UI components
            signals.presetActivated.emit()
            return True
        except Exception as ex:
            logging.error(f'Failed to activate preset {item.name}: {ex}')
            return False

    def backup(self) -> PresetItem:
        """
        Create a timestamped backup of the current configuration without altering metadata.
        Returns the created backup PresetItem.
        """
        # Prepare backup filename
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'backup_{stamp}.{PRESET_FORMAT}'
        path = lib.settings.presets_dir / filename
        # Remove any existing file with the same name
        if path.exists():
            path.unlink()
        # Archive current config directory directly, preserving in-file metadata
        with zipfile.ZipFile(path, 'w') as zf:
            for f in lib.settings.config_dir.rglob('*'):
                if f.is_file():
                    arc = f.relative_to(lib.settings.config_dir).as_posix()
                    zf.write(f, arcname=arc)
        # Cleanup old backups beyond limit
        try:
            # List backup files sorted by modification time (oldest first)
            backups = sorted(
                lib.settings.presets_dir.glob(f'backup_*.{PRESET_FORMAT}'),
                key=lambda p: p.stat().st_mtime
            )
            # Remove oldest if exceeding MAX_BACKUPS
            if len(backups) > MAX_BACKUPS:
                for old in backups[:-MAX_BACKUPS]:
                    try:
                        old.unlink()
                    except Exception as ex:
                        logging.warning(f'Failed to remove old backup {old}: {ex}')
        except Exception as ex:
            logging.warning(f'Error cleaning up backups: {ex}')
        # Return newly created backup PresetItem (not added to preset list)
        return PresetItem(path)

    def restore(self) -> bool:
        """
        Restore the most recent backup preset without creating another backup.
        Returns True on success, False otherwise.
        """
        # Locate backup files on disk by prefix
        presets_dir = lib.settings.presets_dir
        pattern = f'backup_*.{PRESET_FORMAT}'
        backup_paths = list(presets_dir.glob(pattern))
        if not backup_paths:
            logging.error('No backup available to restore')
            return False
        # Use the most recent backup by modification time
        backup_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        backup_path = backup_paths[0]
        backup_item = PresetItem(backup_path)
        return self.activate(backup_item, backup=False)

    def update(self, item: PresetItem) -> bool:
        """
        Update an existing saved preset archive with the current configuration.

        Args:
            item: The PresetItem to update.

        Returns:
            bool: True if the update was successful, False otherwise.
        """
        if not item.is_saved or not item.path:
            logging.error('Cannot update non-saved preset')
            return False
        if not item.is_active:
            logging.error(f'Cannot update preset \'{item.name}\' because it is not active')
            return False
        try:
            # Create temporary archive
            tmp_path = item.path.with_name(item.path.name + '.tmp')
            with zipfile.ZipFile(tmp_path, 'w') as zf:
                for f in lib.settings.config_dir.rglob('*'):
                    if f.is_file():
                        arc = f.relative_to(lib.settings.config_dir).as_posix()
                        zf.write(f, arcname=arc)
            # Replace original preset with updated archive
            tmp_path.replace(item.path)
            # Reinitialize item flags based on new content
            try:
                item._init_item()
            except Exception:
                pass
            # notify listeners of updated snapshot
            try:
                idx = self._items.index(item)
            except ValueError:
                idx = None
            if idx is not None:
                self.presetUpdated.emit(idx)
            logging.debug(f'Updated preset snapshot: {item.name}')
            return True
        except Exception as ex:
            logging.error(f'Failed to update preset {item.name}: {ex}')
            return False

    def items(self) -> List[PresetItem]:
        """
        Return a snapshot list of all presets, including the live configuration.
        """
        return list(self._items)
