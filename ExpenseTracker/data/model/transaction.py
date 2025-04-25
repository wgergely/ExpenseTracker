import enum
import logging
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
        signals.expenseCategoryChanged.connect(self.init_data)

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
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable


class TransactionsSortFilterProxyModel(QtCore.QSortFilterProxyModel):
    """
    Sort/Filter proxy for TransactionsModel.
    Sorts by absolute amount for column 1. Allows text filtering on description (column 2).
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setDynamicSortFilter(True)
        self.setFilterKeyColumn(Columns.Description.value)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setSortRole(QtCore.Qt.EditRole)

        self._filter_string = ''

    def filter_string(self):
        """Get the current filter string."""
        return self._filter_string

    def set_filter_string(self, filter_string: str) -> None:
        """Set the filter string for filtering the model data."""
        self._filter_string = filter_string
        self.setFilterWildcard(filter_string)
        self.invalidateFilter()
