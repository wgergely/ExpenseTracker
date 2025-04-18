"""

"""

import logging
from typing import Any

from PySide6 import QtCore

from .lib import presets


class PresetsModel(QtCore.QAbstractListModel):
    """List‑model view of project presets."""

    NameRole = QtCore.Qt.UserRole + 1
    DescriptionRole = QtCore.Qt.UserRole + 2

    def rowCount(
            self,
            parent: QtCore.QModelIndex = QtCore.QModelIndex(),
    ) -> int:
        if parent.isValid():
            return 0
        return len(presets.presets)

    def data(
            self,
            index: QtCore.QModelIndex,
            role: int = QtCore.Qt.DisplayRole,
    ) -> Any:
        if not index.isValid():
            return None

        item = presets.presets[index.row()]

        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole, self.NameRole):
            return item.name
        if role == self.DescriptionRole:
            return item.description
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.NameRole: b'name',
            self.DescriptionRole: b'description',
        }

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        default = super().flags(index)
        return default | QtCore.Qt.ItemIsEditable if index.isValid() else default

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

        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setFilterRole(PresetsModel.NameRole)
        self.setSortRole(PresetsModel.NameRole)
        self.sort(0, QtCore.Qt.AscendingOrder)

    def filter_string(self):
        """Get the current filter string."""
        return self._filter_string

    def set_filter_string(self, filter_string: str) -> None:
        """Set the filter string for filtering the model data."""
        self._filter_string = filter_string
        self.setFilterWildcard(filter_string)
        self.invalidateFilter()

    def filterAcceptsRow(
            self,
            source_row: int,
            source_parent: QtCore.QModelIndex,
    ) -> bool:
        source = self.sourceModel()

        idx = source.index(source_row, 0, source_parent)
        name = source.data(idx, PresetsModel.NameRole) or ''
        description = source.data(idx, PresetsModel.DescriptionRole) or ''
        regexp = self.filterRegExp()

        if not regexp.pattern():
            return True

        match = bool(regexp.indexIn(name) != -1 or regexp.indexIn(description) != -1)
        return match

    def lessThan(
            self,
            left: QtCore.QModelIndex,
            right: QtCore.QModelIndex,
    ) -> bool:
        left_data = self.sourceModel().data(left, self.sortRole())
        right_data = self.sourceModel().data(right, self.sortRole())

        left_str = str(left_data).lower()
        right_str = str(right_data).lower()

        result = left_str < right_str
        return result
