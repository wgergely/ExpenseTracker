"""
Transaction preview view for displaying full details of a single transaction.
"""
import logging
from typing import Optional

from PySide6 import QtWidgets, QtCore, QtGui

from ..model.transactiondetails import TransactionDetailsModel, MappedToRole, IsMergeMappedRole, IsExtraRole
from ...ui import ui
from ...ui.dockable_widget import DockableWidget


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
                pen = QtGui.QPen(ui.Color.Opaque())
            else:
                pen = QtGui.QPen(ui.Color.Transparent())

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
                pen = QtGui.QPen(ui.Color.Opaque())
            else:
                pen = QtGui.QPen(ui.Color.Opaque())

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
