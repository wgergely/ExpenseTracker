"""

"""

import enum
from typing import Any, Optional

from PySide6 import QtCore

from .lib import PresetsAPI, PresetType
from ...ui import ui


# Column definitions for PresetModel
class Columns(enum.IntEnum):
    Status = 0
    Name = 1
    Description = 2


class PresetModel(QtCore.QAbstractItemModel):
    """QAbstractItemModel for listing and managing PresetItem instances."""

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        """Initialize the preset model."""
        super().__init__(parent=parent)
        self._api = PresetsAPI()
        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect model updates to PresetsAPI signals for dynamic view updates."""
        self._api.presetAdded.connect(lambda idx: self.beginInsertRows(QtCore.QModelIndex(), idx, idx))
        self._api.presetAdded.connect(self.endInsertRows)

        self._api.presetRemoved.connect(lambda idx: self.beginRemoveRows(QtCore.QModelIndex(), idx, idx))
        self._api.presetRemoved.connect(self.endRemoveRows)

        self._api.presetsReloaded.connect(self.beginResetModel)
        self._api.presetsReloaded.connect(self.endResetModel)

        self._api.presetRenamed.connect(self.beginResetModel)
        self._api.presetRenamed.connect(self.endResetModel)

        self._api.presetUpdated.connect(self.beginResetModel)
        self._api.presetUpdated.connect(self.endResetModel)

        self._api.presetActivated.connect(self.beginResetModel)
        self._api.presetActivated.connect(self.endResetModel)

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._api)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        # Number of columns based on Columns enum
        return len(Columns)

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
        """Provide data for display, editing, decoration, alignment, tooltip, and user roles."""
        if not index.isValid():
            return None

        item = index.internalPointer()
        col = index.column()
        # DisplayRole: status, name, description
        if role == QtCore.Qt.DecorationRole:
            if col == Columns.Status:
                if item.type is PresetType.Active:
                    return ui.get_icon('btn_active', color=ui.Color.Green())
                if item.is_out_of_date:
                    return ui.get_icon('btn_alert', color=ui.Color.Yellow())
                if item.is_active:
                    return ui.get_icon('btn_ok', color=ui.Color.Green())
        if role == QtCore.Qt.DisplayRole:
            if col == Columns.Name:
                if item.type is PresetType.Active:
                    return f'Current Ledger ({item.name})'

                # Show name, suffix '*' if modified
                text = item.name
                if item.is_out_of_date:
                    text += '*'
                return text
            elif col == Columns.Description:
                return item.description
            return None

        if role == QtCore.Qt.EditRole:
            if col == Columns.Name:
                return item.name
            if col == Columns.Description:
                return item.description
            return None

        if role == QtCore.Qt.TextAlignmentRole and col == Columns.Status:
            if col == Columns.Status:
                return QtCore.Qt.AlignCenter
            if col == Columns.Name:
                return QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft
            if col == Columns.Description:
                return QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft

        if role == QtCore.Qt.FontRole:
            if col == Columns.Name:
                if item.type is PresetType.Active:
                    font, _ = ui.Font.BoldFont(ui.Size.MediumText(1.0))
                    return font

                font, _ = ui.Font.MediumFont(ui.Size.MediumText(1.0))

                if item.is_out_of_date:
                    font.setItalic(True)

                return font

            if col == Columns.Description:
                font, _ = ui.Font.MediumFont(ui.Size.MediumText(1.0))
                return font

        if role == QtCore.Qt.ForegroundRole:
            if col == Columns.Name:
                if item.type is PresetType.Active:
                    return ui.Color.Green()
                return ui.Color.Text()

            if col == Columns.Description:
                return ui.Color.SecondaryText()

        if role == QtCore.Qt.ToolTipRole:
            return item.description

        if role == QtCore.Qt.UserRole:
            return item.flags

        if role == QtCore.Qt.UserRole + 1:
            return item.type

        if role == QtCore.Qt.UserRole + 2:
            return item

        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        """Items are selectable, enabled, and columns editable."""
        if not index.isValid():
            return QtCore.Qt.NoItemFlags
        flags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        # only Name and Description columns are editable
        if index.column() in (Columns.Name, Columns.Description):
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
        if index.column() == Columns.Name:
            self._api.rename(item, text)
        elif index.column() == Columns.Description:
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
        if orientation == QtCore.Qt.Horizontal:
            if role == QtCore.Qt.DisplayRole:
                if section == Columns.Status:
                    return ''
                if section == Columns.Name:
                    return 'Name'
                if section == Columns.Description:
                    return 'Description'
            if role == QtCore.Qt.TextAlignmentRole:
                return QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft
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
        # sort by preset name by default
        self.sort(Columns.Name, QtCore.Qt.AscendingOrder)

    def filter_string(self):
        return self._filter_string

    def set_filter_string(self, filter_string: str) -> None:
        self._filter_string = filter_string
        self.setFilterWildcard(filter_string)
        self.invalidateFilter()
