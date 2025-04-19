"""

"""

import logging
from typing import Any

from PySide6 import QtCore

from .lib import presets
from ...ui import ui


class PresetsModel(QtCore.QAbstractItemModel):
    """List‑model view of project presets."""

    def index(self, row: int, column: int = 0, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> QtCore.QModelIndex:
        if parent.isValid() or row < 0 or column != 0:
            return QtCore.QModelIndex()
        preset = presets.get_preset_by_index(row)
        if not preset:
            return QtCore.QModelIndex()
        return self.createIndex(row, 0, preset)

    def parent(self, index: QtCore.QModelIndex = QtCore.QModelIndex()) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 1

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return presets.count()

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        preset = index.internalPointer()
        if not preset:
            return None

        if role == QtCore.Qt.DisplayRole:
            return preset.name
        if role == QtCore.Qt.DecorationRole:
            return ui.get_icon('btn_preset')
        if role == QtCore.Qt.ToolTipRole:
            return preset.description
        if role == QtCore.Qt.EditRole:
            return preset.name
        if role == QtCore.Qt.UserRole:
            return preset.path

        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable

    def setData(
            self,
            index: QtCore.QModelIndex,
            value: Any,
            role: int = QtCore.Qt.EditRole,
    ) -> bool:
        """Rename a preset through inline editing."""
        if role != QtCore.Qt.EditRole or not index.isValid():
            return False

        old_name = presets.presets[index.row()].name
        new_name = str(value).strip()

        if not new_name or new_name == old_name:
            return False

        presets.rename_preset(old_name, new_name)
        self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole, role])
        return True

    @QtCore.Slot()
    def add_preset(self, name: str) -> bool:
        """Archive current configuration as *name* and insert a new row."""
        row = self.rowCount()
        try:
            presets.add_preset(name)
        except RuntimeError as err:
            logging.error(err)
            return False

        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self.endInsertRows()
        return True

    @QtCore.Slot()
    def remove_preset(self, row: int) -> bool:
        """Remove preset at *row*."""
        if row < 0 or row >= self.rowCount():
            return False

        name = presets.presets[row].name
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        presets.remove_preset(name)
        self.endRemoveRows()
        return True

    @QtCore.Slot()
    def activate_preset(self, row: int) -> bool:
        """Activate preset at *row*."""
        if row < 0 or row >= self.rowCount():
            return False
        name = presets.presets[row].name
        return presets.activate_preset(name)

    def preset_path(self, row: int) -> str | None:
        if row < 0 or row >= self.rowCount():
            return None
        return str(presets.presets[row].path)


class PresetsSortFilterProxyModel(QtCore.QSortFilterProxyModel):
    """Proxy model to enable sorting and filtering of presets by name or description."""

    def __init__(
            self,
            parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._filter_string = ''

        self.setDynamicSortFilter(True)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setSortRole(QtCore.Qt.DisplayRole)
        self.setFilterRole(QtCore.Qt.DisplayRole)
        self.sort(0, QtCore.Qt.AscendingOrder)

    def filter_string(self):
        return self._filter_string

    def set_filter_string(self, filter_string: str) -> None:
        self._filter_string = filter_string
        self.setFilterWildcard(filter_string)
        self.invalidateFilter()
