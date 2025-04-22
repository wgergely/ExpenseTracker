"""

"""

from typing import Any, Optional

from PySide6 import QtCore

from .lib import PresetsAPI
from ...ui import ui
from ...ui.actions import signals


class PresetModel(QtCore.QAbstractItemModel):
    """QAbstractItemModel for listing and managing PresetItem instances."""

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        """Initialize the preset model."""
        super().__init__(parent=parent)
        self._api = PresetsAPI()

        self._connect_signals()

    def _connect_signals(self) -> None:
        @QtCore.Slot()
        def reload() -> None:
            self.beginResetModel()
            self._api.load_presets()
            self.endResetModel()

        signals.presetsChanged.connect(reload)

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._api)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 2

    def index(
            self,
            row: int,
            column: int = 0,
            parent: QtCore.QModelIndex = QtCore.QModelIndex()
    ) -> QtCore.QModelIndex:
        """Create index for item at row/column."""
        if (
                parent.isValid() or
                row < 0 or
                row >= len(self._api) or
                column < 0 or
                column >= self.columnCount()
        ):
            return QtCore.QModelIndex()
        item = self._api[row]
        return self.createIndex(row, column, item)

    def parent(self, index: QtCore.QModelIndex) -> QtCore.QModelIndex:
        """Flat list has no parent."""
        return QtCore.QModelIndex()

    def data(
            self,
            index: QtCore.QModelIndex,
            role: int = QtCore.Qt.DisplayRole
    ) -> Any:
        """Provide data for display, edit, decoration, tooltip, and user roles."""
        if not index.isValid():
            return None
        item = index.internalPointer()
        col = index.column()
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            if col == 0:
                return item.name
            if col == 1:
                return item.description
        if role == QtCore.Qt.DecorationRole and col == 0:
            return ui.get_icon('btn_preset')
        if role == QtCore.Qt.ToolTipRole:
            return item.description
        if role == QtCore.Qt.UserRole:
            return item
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        """Items are selectable, enabled, and columns editable."""
        if not index.isValid():
            return QtCore.Qt.NoItemFlags
        flags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        if index.column() in (0, 1):
            flags |= QtCore.Qt.ItemIsEditable
        return flags

    def setData(
            self,
            index: QtCore.QModelIndex,
            value: Any,
            role: int = QtCore.Qt.EditRole
    ) -> bool:
        """Handle renaming and description changes via API."""
        if role != QtCore.Qt.EditRole or not index.isValid():
            return False
        item = index.internalPointer()
        text = str(value)
        if index.column() == 0:
            self._api.rename(item, text)
        elif index.column() == 1:
            item.description = text
        else:
            return False
        self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])
        return True

    def headerData(
            self,
            section: int,
            orientation: QtCore.Qt.Orientation,
            role: int = QtCore.Qt.DisplayRole
    ) -> Any:
        """Return headers: 'Name' for column 0, 'Description' for column 1."""
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            if section == 0:
                return 'Name'
            if section == 1:
                return 'Description'
        return None

    def insertRows(
            self,
            row: int,
            count: int,
            parent: QtCore.QModelIndex = QtCore.QModelIndex()
    ) -> bool:
        """Insert a new preset with a default name."""
        if parent.isValid() or count != 1:
            return False
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        item = self._api.new('New Preset')
        self.endInsertRows()
        return True

    def removeRows(
            self,
            row: int,
            count: int,
            parent: QtCore.QModelIndex = QtCore.QModelIndex()
    ) -> bool:
        """Remove the preset at the given row and rollback if deletion fails."""
        if parent.isValid() or count != 1:
            return False
        item = self._api[row]
        # Attempt deletion first
        success = self._api.remove(item)
        if not success:
            return False
        # Notify model of row removal
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        self.endRemoveRows()
        return True


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
