"""
Transaction preview view for displaying full details of a single transaction.
"""
import logging
from typing import Optional, Any, List, Dict

import pandas as pd
from PySide6 import QtWidgets, QtCore, QtGui

# Assuming these are correctly imported from your project structure
from ...core import database
from ...settings import lib
from ...settings import locale
from ...ui import ui
from ...ui.actions import signals  # signals.transactionItemSelected is used by the model
from ...ui.dockable_widget import DockableWidget

# Define User Roles for clarity
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
        # Model listens to transactionItemSelected directly
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


class TransactionDetailsDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent=parent)

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> None:
        column = index.column()

        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)

        hover = option.state & QtWidgets.QStyle.State_MouseOver
        selected = option.state & QtWidgets.QStyle.State_Selected

        o = ui.Size.Indicator(2.0)
        rect = option.rect.adjusted(o, o, -o, -o)

        font, metrics = ui.Font.ThinFont(ui.Size.SmallText(1.0))

        x = rect.x()
        y = rect.center().y() - metrics.height() // 2.0
        baseline_y = y + metrics.ascent() + ui.Size.Indicator(1.0)

        if column == 0:

            color = ui.Color.SecondaryText()

            painter.setPen(color)
            painter.setBrush(color)
            painter.setFont(font)

            painter.drawText(
                x,
                y - metrics.lineSpacing() // 2.0,
                rect.width(),
                metrics.height(),
                QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                metrics.elidedText(
                    index.data(QtCore.Qt.DisplayRole),
                    QtCore.Qt.ElideRight,
                    rect.width()
                )
            )

            # draw line
            if hover or selected:
                pen = QtGui.QPen(ui.Color.SecondaryText())
            else:
                pen = QtGui.QPen(ui.Color.DisabledText())

            pen.setWidthF(ui.Size.Separator(1.0))
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawLine(
                option.rect.left(),
                baseline_y - metrics.lineSpacing() // 2.0,
                option.rect.right(),
                baseline_y - metrics.lineSpacing() // 2.0
            )

            color = ui.Color.Green()

            painter.setPen(color)
            painter.setBrush(color)

            if index.data(MappedToRole):
                v = index.data(MappedToRole)
                if index.data(IsMergeMappedRole):
                    v = f'{v} +'

                painter.drawText(
                    x,
                    y + metrics.lineSpacing() // 2.0 + ui.Size.Indicator(1.0),
                    rect.width(),
                    metrics.height(),
                    QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                    metrics.elidedText(
                        v,
                        QtCore.Qt.ElideRight,
                        rect.width()
                    )
                )
            elif index.data(IsExtraRole):
                color = ui.Color.Yellow()
                painter.setPen(color)
                painter.setBrush(color)

                painter.drawText(
                    x,
                    y + metrics.lineSpacing() // 2.0 + ui.Size.Indicator(1.0),
                    rect.width(),
                    metrics.height(),
                    QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                    metrics.elidedText(
                        'Unmapped',
                        QtCore.Qt.ElideRight,
                        rect.width()
                    )
                )



        elif column == 1:
            font, metrics = ui.Font.BoldFont(ui.Size.SmallText(1.0))

            o = ui.Size.Indicator(2.0)
            bounding_rect = metrics.boundingRect(
                rect,
                QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter | QtCore.Qt.TextWordWrap,
                index.data(QtCore.Qt.DisplayRole)
            )
            _rect = bounding_rect.adjusted(-o, -o, o, o)
            painter.setPen(QtCore.Qt.NoPen)
            if selected:
                _color = ui.Color.Background()
            else:
                _color = ui.Color.Opaque()

            painter.setBrush(_color)
            painter.drawRoundedRect(_rect, o, o)

            if hover or selected:
                color = ui.Color.SelectedText()
            else:
                color = ui.Color.SecondaryText()

            painter.setPen(color)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setFont(font)

            painter.drawText(
                rect,
                QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter | QtCore.Qt.TextWordWrap,
                index.data(QtCore.Qt.DisplayRole)
            )

            # draw line
            if hover or selected:
                pen = QtGui.QPen(ui.Color.SecondaryText())
            else:
                pen = QtGui.QPen(ui.Color.DisabledText())

            pen.setWidthF(ui.Size.Separator(1.0))
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            padding = ui.Size.Indicator(2.0)
            painter.drawLine(
                option.rect.left(),
                baseline_y - metrics.lineSpacing() // 2.0,
                _rect.left() - padding,
                baseline_y - metrics.lineSpacing() // 2.0
            )


class TransactionDetailsDockWidget(DockableWidget):
    """Dock widget for displaying transaction details."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            'Transaction Details',
            parent=parent,
            min_height=ui.Size.DefaultHeight(0.5),
            min_width=ui.Size.DefaultWidth(0.5)
        )
        self.setObjectName('ExpenseTrackerTransactionDetailsDockWidget')
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Preferred)
        self.setProperty('rounded', True)

        self.view: Optional[QtWidgets.QTableView] = None
        self.amount_label: Optional[QtWidgets.QLabel] = None

        self._create_ui()
        self._init_model()
        self._connect_signals()

    def _create_ui(self) -> None:
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        widget = QtWidgets.QWidget(parent=self)
        QtWidgets.QVBoxLayout(widget)
        widget.layout().setAlignment(QtCore.Qt.AlignCenter)

        o = ui.Size.Margin(1.0)
        widget.layout().setContentsMargins(o, o, o, o)
        widget.layout().setSpacing(0)

        widget.setProperty('transparent', True)

        widget.layout().addSpacing(ui.Size.Margin(0.5))

        self.amount_label = QtWidgets.QLabel(parent=widget)
        self.amount_label.setProperty('rounded', True)
        self.amount_label.setProperty('h2', True)
        self.amount_label.setProperty('button', True)
        self.amount_label.setAlignment(QtCore.Qt.AlignCenter)
        self.amount_label.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Fixed)
        widget.layout().addWidget(self.amount_label, 0, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self.view = QtWidgets.QTableView(parent=widget)
        self.view.setProperty('rounded', True)
        self.view.setProperty('transparent', True)

        self.view.setItemDelegate(TransactionDetailsDelegate(parent=self.view))
        self.view.setProperty('noitembackground', True)

        self.view.setFocusPolicy(QtCore.Qt.NoFocus)
        self.view.setAlternatingRowColors(False)
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.view.setShowGrid(False)

        self.view.setWordWrap(True)
        self.view.setTextElideMode(QtCore.Qt.ElideNone)

        widget.layout().addWidget(self.view, 1)

        self.setWidget(widget)

    def _init_model(self) -> None:
        model = TransactionDetailsModel(parent=self)  # Model is parented to the DockWidget
        self.view.setModel(model)

        self.update_amount_label('')
        self._init_headers()

    def _init_headers(self) -> None:
        if self.view is None:
            logging.error('View not initialized before _init_headers call.')
            return

        v_header = self.view.verticalHeader()
        h_header = self.view.horizontalHeader()

        v_header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        v_header.setMinimumSectionSize(ui.Size.RowHeight(0.8))
        v_header.setVisible(False)

        h_header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        h_header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        h_header.setStretchLastSection(True)
        h_header.setVisible(False)

        self.view.setTextElideMode(QtCore.Qt.ElideNone)

    def _connect_signals(self) -> None:
        self.view.model().amountChanged.connect(self.update_amount_label)
        self.view.model().modelReset.connect(self.view.resizeRowsToContents)

    @QtCore.Slot(str)
    def update_amount_label(self, amount: str) -> None:
        self.amount_label.setText(amount)
        self.amount_label.setHidden(not amount)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(
            ui.Size.DefaultWidth(0.5),
            ui.Size.DefaultHeight(0.8)
        )
