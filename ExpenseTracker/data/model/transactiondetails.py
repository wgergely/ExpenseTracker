import logging
from typing import Optional, Any, List, Dict

import pandas as pd
from PySide6 import QtWidgets, QtCore

from ...core import database
from ...settings import lib
from ...settings import locale
from ...ui import ui
from ...ui.actions import signals

MappedToRole = QtCore.Qt.UserRole + 0
IsMergeMappedRole = QtCore.Qt.UserRole + 1
IsExtraRole = QtCore.Qt.UserRole + 2


class TransactionDetailsModel(QtCore.QAbstractTableModel):
    amountChanged = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent=parent)
        self._data: List[Dict[str, Any]] = []
        self._connect_signals()

    def _connect_signals(self) -> None:
        signals.transactionItemSelected.connect(self.init_data)
        signals.dataAboutToBeFetched.connect(self.clear_data)
        signals.presetAboutToBeActivated.connect(self.clear_data)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 2

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self._data)

    def init_data(self, local_id: int) -> None:
        if local_id <= 0:  # Handle non-positive local_id by clearing
            self.clear_data()
            return

        self.beginResetModel()
        self._data.clear()
        try:
            self._populate_model_data(local_id)
        finally:
            self.endResetModel()

    def clear_data(self) -> None:
        self.beginResetModel()
        self._data.clear()
        self.endResetModel()
        self.amountChanged.emit('')

    def _populate_model_data(self, local_id: int) -> None:
        row_data = database.database.get_row(local_id)
        if not row_data:
            logging.warning(f'No data found for local_id: {local_id}')
            self.amountChanged.emit(locale.format_currency_value(0.0, lib.settings['locale']))
            return

        df_raw = pd.DataFrame([row_data])

        config = lib.settings.get_section('mapping')
        header_config = lib.settings.get_section('header')

        current_data_list: List[Dict[str, Any]] = []
        primary_amount_value: Optional[float] = None

        for raw_column in df_raw.columns:
            is_merge_mapped = any(
                raw_column in lib.parse_merge_mapping(str(v)) for k, v in config.items() if lib.is_merge_mapped(str(v))
            )
            is_extra = not bool(next(iter(
                k for k, v in config.items() if raw_column in lib.parse_merge_mapping(str(v))
            ), None))
            mapped_to = next(iter(
                k for k, v in config.items() if raw_column in lib.parse_merge_mapping(str(v))
            ), None)

            value = df_raw.iloc[0][raw_column]
            processed_value = value if not pd.isna(value) else None

            mapped_type = header_config.get(raw_column, 'string')

            if processed_value is not None:
                if mapped_type == 'date':
                    processed_value = pd.to_datetime(processed_value, errors='coerce')
                    if pd.isna(processed_value): processed_value = None
                elif mapped_type == 'float':
                    processed_value = pd.to_numeric(processed_value, errors='coerce')
                    if pd.isna(processed_value): processed_value = None
                elif mapped_type == 'int':
                    processed_value = pd.to_numeric(processed_value, errors='coerce', downcast='integer')
                    if pd.isna(processed_value): processed_value = None
                elif mapped_type == 'string':
                    processed_value = str(processed_value)

            if mapped_to == 'amount':
                if isinstance(processed_value, (int, float)):
                    primary_amount_value = float(processed_value)
                elif isinstance(processed_value, str):
                    try:
                        primary_amount_value = float(processed_value)
                    except ValueError:
                        logging.warning(
                            f"Could not convert string amount value '{processed_value}' to float for {raw_column}")

            current_data_list.append({
                'label': raw_column,
                'value': processed_value,
                'mapped_to': mapped_to,
                'is_merge_mapped': is_merge_mapped,
                'is_extra': is_extra
            })

        self._data = current_data_list

        if primary_amount_value is not None:
            amount_str_for_label = locale.format_currency_value(primary_amount_value, lib.settings['locale'])
        else:
            amount_str_for_label = locale.format_currency_value(0.0, lib.settings['locale'])
        self.amountChanged.emit(amount_str_for_label)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._data)):
            return None

        row_item = self._data[index.row()]
        column = index.column()

        if role == QtCore.Qt.DisplayRole:
            if column == 0:
                return str(row_item['label'])
            if column == 1:
                value = row_item['value']
                if value is None:
                    return ''

                if row_item['mapped_to'] == 'amount':
                    if isinstance(value, (int, float)):
                        return locale.format_currency_value(float(value), lib.settings['locale'])
                    return str(value)

                if isinstance(value, pd.Timestamp):
                    if isinstance(value, pd.Timestamp):
                        return value.strftime('%d/%m/%Y')

                return str(value)
        elif role == QtCore.Qt.FontRole:
            if column == 0:
                font, _ = ui.Font.ThinFont(ui.Size.SmallText(1.0))
                return font
            if column == 1:
                font, _ = ui.Font.BoldFont(ui.Size.SmallText(1.0))
                return font
        elif role == QtCore.Qt.TextAlignmentRole:
            if column == 0:
                return QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
            if column == 1:
                return QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter

        elif role == QtCore.Qt.EditRole:
            if column == 0:
                return str(row_item['label'])
            if column == 1:
                return row_item['value']

        elif role == MappedToRole:
            return row_item['mapped_to']
        elif role == IsMergeMappedRole:
            return row_item['is_merge_mapped']
        elif role == IsExtraRole:
            return row_item['is_extra']

        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = QtCore.Qt.DisplayRole) -> Any:
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            if section == 0:
                return 'Field'
            if section == 1:
                return 'Value'
        return None
