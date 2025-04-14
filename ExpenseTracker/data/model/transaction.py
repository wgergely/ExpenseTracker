import enum
import logging
from copy import deepcopy
from typing import Any

import pandas as pd
from PySide6 import QtCore, QtGui

from ...settings import lib
from ...settings import locale
from ...ui import ui
from ...ui.actions import signals


class Columns(enum.IntEnum):
    Date = 0
    Amount = 1
    Description = 2
    Category = 3
    Account = 4


class TransactionsModel(QtCore.QAbstractTableModel):
    """
    TransactionsModel displays transaction data as table rows and columns.
    The header names are derived from the transaction DataFrame columns, which are
    renamed based on the ledger.json "mapping" configuration.
    """

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent=parent)

        self._data = []

        self._connect_signals()

    def _connect_signals(self) -> None:
        signals.dataAboutToBeFetched.connect(self.clear_data)
        signals.categorySelectionChanged.connect(self.init_data)

    @QtCore.Slot(list)
    def init_data(self, data) -> None:
        self.beginResetModel()
        self._data = []
        try:
            if not data:
                logging.warning('TransactionsModel: No data available.')
                return
            self._data = data
        except Exception as ex:
            logging.error(f'Failed to load transactions data: {ex}')
            self._data = []
        finally:
            self.endResetModel()

    @QtCore.Slot()
    def clear_data(self) -> None:
        """
        Clear the model data and reset the DataFrame.
        """
        self.beginResetModel()
        self._data = []
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(lib.TRANSACTION_DATA_COLUMNS)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if not self._data:
            return None
        if not index.isValid():
            return None
        row = index.row()
        col_idx = index.column()
        col_key = lib.TRANSACTION_DATA_COLUMNS[col_idx]

        if row < 0 or row >= self.rowCount():
            return None

        value = self._data[row][col_key]

        if role == QtCore.Qt.DisplayRole:
            if col_idx == Columns.Date.value:
                if isinstance(value, pd.Timestamp):
                    return value.strftime('%d/%m/%Y')
                return f'{value}'
            elif col_idx == Columns.Amount.value:
                if isinstance(value, (int, float)):
                    return locale.format_currency_value(value, lib.settings['locale'])
                else:
                    return f'{value}'
            elif col_idx == Columns.Description.value:
                if isinstance(value, str):
                    lines = value.split('\n')
                    first_line = lines[0]
                    other_lines = lines[1:] if len(lines) > 1 else []
                    other_lines = [line.strip() for line in other_lines if line.strip()]
                    if other_lines:
                        other_lines = f', '.join(other_lines)
                    else:
                        other_lines = ''
                    return f'{first_line}\n{other_lines}'
                else:
                    return f'{value}'
            elif col_idx == Columns.Category.value:
                categories = lib.settings.get_section('categories')
                if not categories:
                    return f'{value}'
                if value in categories:
                    display_name = categories[value]['display_name']
                else:
                    display_name = f'{value}'
                return display_name
            else:
                return f'{value}'
        elif role == QtCore.Qt.DecorationRole:
            if col_idx == Columns.Category.value:
                return ui.get_icon(value)
        elif role == QtCore.Qt.FontRole:
            if col_idx == Columns.Date.value:
                font, _ = ui.Font.ThinFont(ui.Size.SmallText(1.0))
                font.setWeight(QtGui.QFont.Normal)
                return font
            if col_idx == Columns.Amount.value:
                font, _ = ui.Font.BlackFont(ui.Size.MediumText(1.0))
                font.setWeight(QtGui.QFont.Black)
                return font
            if col_idx == Columns.Description.value:
                font, _ = ui.Font.MediumFont(ui.Size.SmallText(1.0))
                return font

        elif role == QtCore.Qt.ForegroundRole:
            if col_idx == Columns.Amount.value:
                if not isinstance(value, (int, float)):
                    return None
                if value < 0:
                    return ui.Color.Red()
                if value == 0:
                    return ui.Color.DisabledText()
                if value > 0:
                    return ui.Color.Green()

        elif role == QtCore.Qt.EditRole:
            return value

        elif role in (QtCore.Qt.StatusTipRole, QtCore.Qt.ToolTipRole):
            if col_idx == 0:
                if isinstance(value, pd.Timestamp):
                    return value.strftime('%d/%m/%Y')
                else:
                    return f'{value}'
            elif col_idx == Columns.Amount.value:
                if isinstance(value, float):
                    return locale.format_currency_value(value, lib.settings['locale'])
                elif isinstance(value, int):
                    return locale.format_currency_value(value, lib.settings['locale'])
                else:
                    return f'{value}'
            elif col_idx == Columns.Description.value:
                if isinstance(value, str):
                    return f'{value}'
            elif col_idx == Columns.Category.value:
                categories = lib.settings.get_section('categories')
                if not categories:
                    return f'{value}'

                if value in categories:
                    display_name = categories[value]['display_name']
                else:
                    display_name = f'{value}'
                return f'{display_name} ({value})'

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
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable


class TransactionsSortFilterProxyModel(QtCore.QSortFilterProxyModel):
    """
    Sort/Filter proxy for TransactionsModel.
    Sorts by absolute amount for column 1. Allows text filtering on description (column 2).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDynamicSortFilter(True)
        # By default, filter on the description column (2).
        self.setFilterKeyColumn(2)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)

    def lessThan(self, left: QtCore.QModelIndex, right: QtCore.QModelIndex) -> bool:
        if left.column() == Columns.Amount.value and right.column() == Columns.Amount.value:
            left_val = left.model().data(left, QtCore.Qt.EditRole)
            right_val = right.model().data(right, QtCore.Qt.EditRole)
            left_abs = abs(left_val) if isinstance(left_val, (int, float)) else 0
            right_abs = abs(right_val) if isinstance(right_val, (int, float)) else 0
            return left_abs < right_abs
        return super().lessThan(left, right)
