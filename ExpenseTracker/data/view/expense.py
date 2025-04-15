import logging
from copy import deepcopy

import pandas as pd
from PySide6 import QtWidgets, QtGui, QtCore

from .transaction import TransactionsWidget
from ..model.expense import ExpenseModel, ExpenseSortFilterProxyModel, WeightRole, Columns, CategoryRole, TransactionsRole
from ...settings import lib
from ...ui import ui
from ...ui.actions import signals


class WeightColumnDelegate(QtWidgets.QStyledItemDelegate):
    """A custom delegate to draw a simple bar chart for the chart column.

    """

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem,
              index: QtCore.QModelIndex) -> None:
        super().paint(painter, option, index)

        if index.column() != Columns.Weight or index.row() == index.model().rowCount() - 1:
            return

        selected = option.state & QtWidgets.QStyle.State_Selected
        hover = option.state & QtWidgets.QStyle.State_MouseOver

        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        rect = QtCore.QRectF(option.rect)
        offset = ui.Size.Indicator(0.8)
        rect = rect.adjusted(offset, offset, -offset, -offset)
        center = rect.center()

        rect.setHeight(ui.Size.Margin(0.6) if (selected or hover) else ui.Size.Margin(0.5))
        rect.moveCenter(center)

        gradient = QtGui.QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0.3, ui.Color.Green())
        gradient.setColorAt(0.8, ui.Color.Yellow())
        gradient.setColorAt(1.0, ui.Color.Red())

        width = float(rect.width()) * index.data(WeightRole)
        width = max(width, ui.Size.Separator(1.0)) if index.data(WeightRole) > 0.0 else width
        rect.setWidth(width)

        painter.setBrush(gradient)
        painter.setPen(QtCore.Qt.NoPen)

        o = ui.Size.Separator(5.0) if (hover or selected) else ui.Size.Separator(3.0)
        painter.drawRoundedRect(rect, o, o)


class IconColumnDelegate(QtWidgets.QStyledItemDelegate):
    """A custom delegate to draw the icon for the icon column.

    """

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem,
              index: QtCore.QModelIndex) -> None:
        super().paint(painter, option, index)

        if index.column() != Columns.Icon or index.row() == index.model().rowCount() - 1:
            return

        # Background
        category = index.data(CategoryRole)
        config = lib.settings.get_section('categories')
        color = config.get(category, {}).get('color', None)
        if color:
            color = QtGui.QColor.fromString(color)
            rect = QtCore.QRectF(option.rect)
            m = ui.Size.Margin(0.5)
            rect = rect.adjusted(
                m, m, -m, -m
            )
            o = ui.Size.Indicator(2.0)
            painter.setBrush(color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(rect, o, o)

        # Icon
        center = option.rect.center()

        rect = QtCore.QRect(
            0, 0,
            ui.Size.Margin(1.0),
            ui.Size.Margin(1.0),
        )
        rect.moveCenter(center)

        icon = index.data(QtCore.Qt.DecorationRole)
        if icon is not None:
            icon.paint(painter, rect, QtCore.Qt.AlignCenter)


class ExpenseView(QtWidgets.QTableView):
    """
    The view to display the expense data in a table format.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent=parent)
        self.horizontalHeader().hide()
        self.verticalHeader().hide()

        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.MinimumExpanding
        )

        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setWordWrap(True)
        self.setTextElideMode(QtCore.Qt.ElideRight)

        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        ui.set_stylesheet(self)

        self._init_delegates()
        self._init_model()
        self._init_actions()
        self._connect_signals()

        QtCore.QTimer.singleShot(0, self.model().sourceModel().init_data)

    def _init_model(self) -> None:
        model = ExpenseModel()
        proxy = ExpenseSortFilterProxyModel()
        proxy.setSourceModel(model)
        self.setModel(proxy)

        self._init_section_sizing()

    def _init_delegates(self) -> None:
        self.setItemDelegateForColumn(Columns.Weight.value, WeightColumnDelegate(self))
        self.setItemDelegateForColumn(Columns.Icon.value, IconColumnDelegate(self))

    def _init_actions(self) -> None:
        action_group = QtGui.QActionGroup(self)
        action_group.setExclusive(False)

        action = QtGui.QAction('Show Icons', self)
        action.setCheckable(True)
        action.setChecked(True)
        action.setShortcut('alt+I')
        action.toggled.connect(lambda v: self.setColumnHidden(Columns.Icon.value, not v))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Show Category', self)
        action.setCheckable(True)
        action.setChecked(True)
        action.setShortcut('alt+C')
        action.toggled.connect(lambda v: self.setColumnHidden(Columns.Category.value, not v))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Show Graph', self)  # weights
        action.setCheckable(True)
        action.setChecked(True)
        action.setShortcut('alt+G')
        action.toggled.connect(lambda v: self.setColumnHidden(Columns.Weight.value, not v))
        action.toggled.connect(
            lambda v:
            self.horizontalHeader().setSectionResizeMode(Columns.Amount.value,
                                                         QtWidgets.QHeaderView.ResizeToContents) if v else
            self.horizontalHeader().setSectionResizeMode(Columns.Amount.value, QtWidgets.QHeaderView.Stretch)
        )
        action_group.addAction(action)
        self.addAction(action)

        # separator
        action = QtGui.QAction('', self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        # sort column
        # action group
        action_group = QtGui.QActionGroup(self)
        action_group.setExclusive(True)

        action = QtGui.QAction('Sort by Category', self)
        action.setCheckable(True)
        action.setChecked(True)
        action.triggered.connect(lambda: self.model().sort(Columns.Category.value))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort by Amount', self)
        action.setCheckable(True)
        action.setChecked(False)
        action.triggered.connect(lambda: self.model().sort(Columns.Amount.value))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('', self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        action = QtGui.QAction('Refresh Data...', self)
        action.setShortcut('Ctrl+R')
        action.setIcon(ui.get_icon('btn_fetch', color=ui.Color.Green()))
        action.triggered.connect(signals.dataFetchRequested)
        self.addAction(action)

        action = QtGui.QAction('Reload', self)
        action.setShortcut('Ctrl+Shift+R')
        action.setIcon(ui.get_icon('btn_reload'))
        action.triggered.connect(self.model().sourceModel().init_data)
        self.addAction(action)

        action = QtGui.QAction('', self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        action = QtGui.QAction('Open Settings...', self)
        action.setShortcuts(['Ctrl+,', 'Ctrl+.', 'Ctrl+P'])
        action.setIcon(ui.get_icon('btn_settings'))
        action.triggered.connect(signals.openSettings)
        self.addAction(action)

    def _connect_signals(self) -> None:
        self.doubleClicked.connect(self.activate_action)

        @QtCore.Slot()
        def emit_category_selection_changed() -> None:
            """
            Emit the category selection changed signal.
            """
            if not self.selectionModel().hasSelection():
                logging.debug('No selection')
                signals.expenseCategoryChanged.emit([])
                return

            index = next(iter(self.selectionModel().selectedIndexes()), QtCore.QModelIndex())
            if not index.isValid():
                logging.debug('No valid index')
                signals.expenseCategoryChanged.emit([])
                return

            v = index.data(TransactionsRole)
            if not v:
                v = []
            else:
                v = deepcopy(v)
            logging.debug('Category selection changed')
            signals.expenseCategoryChanged.emit(v)

        self.selectionModel().selectionChanged.connect(emit_category_selection_changed)
        self.model().sourceModel().modelReset.connect(emit_category_selection_changed)

    def _init_section_sizing(self) -> None:
        header = self.horizontalHeader()
        header.setSectionResizeMode(Columns.Icon.value, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Columns.Category.value, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Columns.Weight.value, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(Columns.Amount.value, QtWidgets.QHeaderView.ResizeToContents)
        header = self.verticalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        header.setDefaultSectionSize(ui.Size.RowHeight(1.4))

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(480, 120)

    @QtCore.Slot(QtCore.QModelIndex)
    def activate_action(self, index: QtCore.QModelIndex) -> None:
        """
        Slot called on double-clicking or pressing Enter on a row.
        Opens a dockable TransactionsWidget on the right side.
        """
        if not index.isValid():
            return

        main = self.window()
        if main is None or not hasattr(main, 'addDockWidget'):
            return

        if not hasattr(main, 'transactions_view') or main.transactions_view is None:
            main.transactions_view = TransactionsWidget(parent=main)
            main.addDockWidget(QtCore.Qt.RightDockWidgetArea, main.transactions_view)
        elif main.transactions_view.isVisible():
            main.transactions_view.raise_()
            return

        main.transactions_view.show()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            index = self.currentIndex()
            if index.isValid():
                self.activate_action(index)
            return
        if key == QtCore.Qt.Key_Tab:
            current = self.currentIndex()
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                if current.isValid() and current.row() > 0:
                    new_index = self.model().index(current.row() - 1, current.column())
                    self.setCurrentIndex(new_index)
                    return
            else:
                if current.isValid() and current.row() < self.model().rowCount() - 1:
                    new_index = self.model().index(current.row() + 1, current.column())
                    self.setCurrentIndex(new_index)
                    return
        super().keyPressEvent(event)
