"""Transactions table model and proxy.

Includes classes to display, edit, sort, and filter transaction data.
"""
import enum
import logging
from typing import Any, Optional, Dict, Tuple

import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

from ...settings import lib
from ...settings import locale
from ...ui import ui
from ...ui.actions import signals


class Columns(enum.IntEnum):
    """Column indices for the TransactionsModel table."""
    Date = 0
    Amount = 1
    Description = 2
    Category = 3
    Account = 4


class TransactionsModel(QtCore.QAbstractTableModel):
    """Table model for displaying transaction data.

    Header labels are derived from mapping configuration and formatted from ledger settings.
    """

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent=parent)

        self._pending_data = []
        self._data = []
        # track failed edit operations per (row, column): error message
        self._failed_cells: Dict[Tuple[int, int], str] = {}

        self._init_data_timer = QtCore.QTimer(self)
        self._init_data_timer.setSingleShot(True)
        self._init_data_timer.setInterval(QtWidgets.QApplication.keyboardInputInterval())

        self._connect_signals()

    def _connect_signals(self) -> None:
        signals.presetAboutToBeActivated.connect(self.clear_data)
        signals.dataAboutToBeFetched.connect(self.clear_data)

        signals.transactionsChanged.connect(self.queue_data_init)
        self._init_data_timer.timeout.connect(lambda: self.init_data(self._pending_data))

        from ...core.sync import sync
        sync.dataUpdated.connect(self.on_sync_success)
        sync.commitFinished.connect(self.on_sync_complete)

        self.modelAboutToBeReset.connect(lambda: signals.transactionItemSelected.emit(-1))

    @QtCore.Slot(list)
    def queue_data_init(self, data: list) -> None:
        self._pending_data = data
        self._init_data_timer.start(self._init_data_timer.interval())

    @QtCore.Slot(list)
    def init_data(self, data: list) -> None:
        self.beginResetModel()
        self._data = []
        self._pending_data = []
        try:
            if not data:
                return
            self._data = data
        except Exception as ex:
            logging.error(f'Failed to load transactions data: {ex}')
            self._data = []
        finally:
            self.endResetModel()

    @QtCore.Slot()
    def clear_data(self) -> None:
        self.beginResetModel()
        self._data = []
        self._pending_data = []
        # clear any failure markers
        self._failed_cells.clear()
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(lib.TRANSACTION_DATA_COLUMNS)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole):
        """Returns data for the specified index and role.

        Args:
            index (QtCore.QModelIndex): The model index.
            role (int): The data role.

        Returns:
            Any: Data appropriate for the role, or None.
        """
        if not self._data or not index.isValid():
            return None
        row = index.row()
        col_idx = index.column()
        if row < 0 or row >= self.rowCount():
            return None

        # if this cell has a recorded failure, show its error message in statusTip/tooltip
        if role in (QtCore.Qt.StatusTipRole, QtCore.Qt.ToolTipRole):
            if (row, col_idx) in self._failed_cells:
                return self._failed_cells[(row, col_idx)]

        col_key = lib.TRANSACTION_DATA_COLUMNS[col_idx]
        value = self._data[row][col_key]

        if role == QtCore.Qt.EditRole:
            if col_idx == Columns.Date.value:
                if isinstance(value, pd.Timestamp):
                    return value.strftime('%Y-%m-%d')
                return f'{value}'
            return value

        if col_idx == Columns.Date.value:
            if role == QtCore.Qt.DisplayRole:
                if isinstance(value, pd.Timestamp):
                    return value.strftime('%d/%m/%Y')
                return f'{value}'
            elif role == QtCore.Qt.FontRole:
                font, _ = ui.Font.ThinFont(ui.Size.SmallText(1.0))
                font.setWeight(QtGui.QFont.Normal)
                return font
            elif role in (QtCore.Qt.StatusTipRole, QtCore.Qt.ToolTipRole):
                if isinstance(value, pd.Timestamp):
                    return value.strftime('%d/%m/%Y')
                return f'{value}'

        elif col_idx == Columns.Amount.value:
            if role == QtCore.Qt.DisplayRole:
                if isinstance(value, (int, float)):
                    return locale.format_currency_value(value, lib.settings['locale'])
                return f'{value}'
            elif role == QtCore.Qt.FontRole:
                font, _ = ui.Font.BlackFont(ui.Size.MediumText(1.0))
                font.setWeight(QtGui.QFont.Black)
                return font
            elif role == QtCore.Qt.ForegroundRole:
                if not isinstance(value, (int, float)):
                    return None
                if value < 0:
                    return ui.Color.Red()
                elif value == 0:
                    return ui.Color.DisabledText()
                else:
                    return ui.Color.Green()
            elif role in (QtCore.Qt.StatusTipRole, QtCore.Qt.ToolTipRole):
                if isinstance(value, (int, float)):
                    return locale.format_currency_value(value, lib.settings['locale'])
                return f'{value}'

        elif col_idx == Columns.Description.value:
            if role == QtCore.Qt.DisplayRole:
                if isinstance(value, str):
                    lines = value.split('\n')
                    first_line = lines[0]
                    other_lines = lines[1:] if len(lines) > 1 else []
                    other_lines = [line.strip() for line in other_lines if line.strip()]
                    return f'{first_line}\n{", ".join(other_lines)}' if other_lines else first_line
                return f'{value}'
            elif role == QtCore.Qt.FontRole:
                font, _ = ui.Font.MediumFont(ui.Size.SmallText(1.0))
                return font
            elif role in (QtCore.Qt.StatusTipRole, QtCore.Qt.ToolTipRole):
                if isinstance(value, str):
                    return value

        elif col_idx == Columns.Category.value:
            config = lib.settings.get_section('categories') or {}
            if role == QtCore.Qt.DisplayRole:
                if value in config:
                    display_name = config[value].get('display_name', value)
                    if display_name:
                        return display_name
                return f'{value}'
            elif role == QtCore.Qt.DecorationRole:
                if value not in config:
                    return None

                icon_name = config[value].get('icon', 'cat_unclassified')
                hex_color = config[value].get('color', ui.Color.Text().name(QtGui.QColor.HexRgb))
                color = QtGui.QColor(hex_color)

                icon = ui.get_icon(icon_name, color=color, engine=ui.CategoryIconEngine)
                return icon
            elif role in (QtCore.Qt.StatusTipRole, QtCore.Qt.ToolTipRole):
                categories = lib.settings.get_section('categories') or {}
                if value in categories:
                    display_name = categories[value]['display_name']
                else:
                    display_name = f'{value}'
                return f'{display_name} ({value})'

        else:
            if role == QtCore.Qt.DisplayRole:
                return f'{value}'
            elif role in (QtCore.Qt.StatusTipRole, QtCore.Qt.ToolTipRole):
                return f'{value}'

        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation,
                   role: int = QtCore.Qt.DisplayRole) -> Any:
        if not self._data:
            return None
        if role != QtCore.Qt.DisplayRole:
            return None
        if orientation == QtCore.Qt.Horizontal:
            if 0 <= section < self.columnCount():
                return lib.TRANSACTION_DATA_COLUMNS[section].title()
        elif orientation == QtCore.Qt.Vertical:
            return f'{section + 1}'
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        if not index.isValid():
            return QtCore.Qt.NoItemFlags
        flags = super().flags(index)

        if index.column() == Columns.Category.value:
            # allow editing if this row has a local_id
            row = index.row()
            try:
                rec = self._data[row]
            except Exception:
                return flags
            if rec.get('local_id', None) is not None:
                flags |= QtCore.Qt.ItemIsEditable
        return flags

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = QtCore.Qt.EditRole) -> bool:
        if role == QtCore.Qt.EditRole and index.column() == Columns.Category.value:
            row = index.row()
            try:
                rec = self._data[row]
                local_id = rec.get('local_id')
            except Exception:
                return False
            if local_id is None:
                return False
            # Queue the edit
            from ...core.sync import sync
            # logical field name is 'category'
            sync.queue_edit(local_id, 'category', value)
            # Update the in-memory model
            rec['category'] = value
            self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])
            return True
        return False

    @QtCore.Slot(list)
    def on_sync_success(self, ops: list) -> None:
        for op in ops:
            # find matching record in _data
            for row_idx, rec in enumerate(self._data):
                if rec.get('local_id') == op.local_id:
                    # update in-memory value
                    rec[op.column] = op.new_value
                    # emit dataChanged for the cell
                    try:
                        col_idx = lib.TRANSACTION_DATA_COLUMNS.index(op.column)
                        idx = self.index(row_idx, col_idx)
                        self.dataChanged.emit(idx, idx, [QtCore.Qt.DisplayRole])
                    except Exception as ex:
                        logging.error(f'Update failed: {ex}')
                        pass
                    break
        # on successful sync, clear any failure markers for these ops
        for op in ops:
            for row_idx, rec in enumerate(self._data):
                if rec.get('local_id') == op.local_id:
                    try:
                        col_idx = lib.TRANSACTION_DATA_COLUMNS.index(op.column)
                        self._failed_cells.pop((row_idx, col_idx), None)
                    except Exception:
                        pass

    @QtCore.Slot(object)
    def on_sync_complete(self, results: object) -> None:
        """Handle failures from commitFinished: mark cells dirty with error messages."""
        for key, (ok, msg) in results.items():
            if ok:
                continue
            # expect key as (local_id, column)
            if isinstance(key, (tuple, list)) and len(key) == 2:
                lid, col = key
            else:
                continue
            # find row and column index
            for row_idx, rec in enumerate(self._data):
                if rec.get('local_id') == lid:
                    try:
                        col_idx = lib.TRANSACTION_DATA_COLUMNS.index(col)
                        # record failure message
                        self._failed_cells[(row_idx, col_idx)] = msg
                        idx = self.index(row_idx, col_idx)
                        # notify view for statusTip and redraw
                        self.dataChanged.emit(idx, idx, [QtCore.Qt.StatusTipRole, QtCore.Qt.ToolTipRole])
                    except Exception as ex:
                        logging.error(f'Failed to mark failed cell: {ex}')
                    break


class TransactionsSortFilterProxyModel(QtCore.QSortFilterProxyModel):
    """Sort and filter proxy model for transaction data.

    Sorts by absolute amount in the Amount column and filters by Description wildcard.
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setDynamicSortFilter(True)
        self.setFilterKeyColumn(Columns.Description.value)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setSortRole(QtCore.Qt.EditRole)

        self._filter_string = ''

        self._connect_signals()

    def _connect_signals(self) -> None:
        @QtCore.Slot()
        def reset():
            self.set_filter_string('')
            self.invalidateFilter()

        signals.transactionsChanged.connect(reset)

    def filter_string(self):
        """Get the current filter string."""
        return self._filter_string

    def set_filter_string(self, filter_string: str) -> None:
        """Set the filter string for filtering the model data."""
        self._filter_string = filter_string
        self.setFilterWildcard(filter_string)
        self.invalidateFilter()
