from PySide6 import QtWidgets, QtGui, QtCore

from .transaction import TransactionsWidget
from ..model.expense import ExpenseModel, ExpenseSortFilterProxyModel, WeightRole
from ...ui import ui
from ...ui.actions import signals


class GraphDelegate(QtWidgets.QStyledItemDelegate):
    """A custom delegate to draw a simple bar chart for the chart column.

    """

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem,
              index: QtCore.QModelIndex) -> None:
        super().paint(painter, option, index)
        if index.column() != 1 or index.row() == index.model().rowCount() - 1:
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


class ExpenseView(QtWidgets.QTableView):
    """
    ExpenseView is a custom QTableView for displaying monthly expense data.

    Double-clicking or pressing Enter on a row opens a dockable TransactionsWidget on the right.
    Tab and Shift+Tab navigate between rows (unless at the beginning or end of the list).
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
        self._init_actions()
        self._init_model()
        self._connect_signals()

        QtCore.QTimer.singleShot(0, self.model().sourceModel().init_data)

    def _init_model(self) -> None:
        model = ExpenseModel()
        proxy = ExpenseSortFilterProxyModel()
        proxy.setSourceModel(model)
        self.setModel(proxy)

        self._init_section_sizing()

    def _init_delegates(self) -> None:
        self.setItemDelegate(GraphDelegate(self))

    def _init_actions(self) -> None:
        pass

    def _connect_signals(self) -> None:
        self.doubleClicked.connect(self.activate_action)

        self.selectionModel().selectionChanged.connect(signals.categorySelectionChanged)
        self.model().sourceModel().modelAboutToBeReset.connect(signals.categorySelectionChanged)
        self.model().sourceModel().modelReset.connect(signals.categorySelectionChanged)

    def _init_section_sizing(self) -> None:
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
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
