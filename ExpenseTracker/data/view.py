from PySide6 import QtCore, QtWidgets, QtGui
from .model import ExpenseModel, RateRole, TransactionsModel
from .model import ExpenseSortFilterProxyModel, TransactionsSortFilterProxyModel
from ..ui import ui
from ..ui.actions import signals

class TransactionsDialog(QtWidgets.QDockWidget):
    """
    TransactionsDialog is a custom dockable widget for displaying transaction data.

    It initializes the view and sets up the layout for displaying transactions.
    """
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__('Transactions', parent=parent)
        self.setObjectName('ExpenseTrackerTransactionsDialog')
        self.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable |
            QtWidgets.QDockWidget.DockWidgetFloatable
        )
        self.setMinimumSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.0)
        )
        self.view = None
        self.proxy_model = None
        self._create_ui()
        self._init_model()

    def _create_ui(self) -> None:
        content = QtWidgets.QWidget(self)
        QtWidgets.QVBoxLayout(content)

        o = ui.Size.Margin(1.0)
        content.layout().setContentsMargins(o, o, o, o)
        content.layout().setSpacing(o)

        self.view = TransactionsView(content)
        self.view.setObjectName('ExpenseTrackerTransactionsView')
        content.layout().addWidget(self.view, 1)

        self.setWidget(content)

    def _init_model(self) -> None:
        model = TransactionsModel()
        self.proxy_model = TransactionsSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(model)
        # Default sort is by the 'Amount' column (1) in descending order so largest abs at the top.
        self.view.setModel(self.proxy_model)
        self.view.setSortingEnabled(True)
        self.view.horizontalHeader().setSortIndicator(1, QtCore.Qt.DescendingOrder)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.0)
        )

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
        gradient.setColorAt(0.0, ui.Color.Green())
        gradient.setColorAt(1.0, ui.Color.LightRed())

        width = float(rect.width()) * index.data(RateRole)
        width = max(width, ui.Size.Separator(1.0)) if index.data(RateRole) > 0.0 else width
        rect.setWidth(width)

        painter.setBrush(gradient)
        painter.setPen(QtCore.Qt.NoPen)

        o = ui.Size.Separator(5.0) if (hover or selected) else ui.Size.Separator(3.0)
        painter.drawRoundedRect(rect, o, o)

class ExpenseView(QtWidgets.QTableView):
    """
    ExpenseView is a custom QTableView for displaying monthly expense data.

    Double-clicking or pressing Enter on a row opens a dockable TransactionsDialog on the right.
    Tab and Shift+Tab navigate between rows (unless at the beginning or end of the list).
    """
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
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

        self.setContextMenuPolicy(QtCore.Qt.NoContextMenu)

        ui.set_stylesheet(self)

        self._init_delegates()
        self._connect_signals()

    def _init_delegates(self) -> None:
        self.setItemDelegate(GraphDelegate(self))

    def _connect_signals(self) -> None:
        self.doubleClicked.connect(self.activate_action)

    def setModel(self, model):
        if not isinstance(model, ExpenseModel) and not isinstance(model, QtCore.QSortFilterProxyModel):
            raise TypeError('Expected an ExpenseModel or its QSortFilterProxyModel wrapper.')
        super().setModel(model)
        self._init_section_sizing()
        if isinstance(model, ExpenseModel):
            self.selectionModel().selectionChanged.connect(signals.categorySelectionChanged)
            self.model().modelAboutToBeReset.connect(signals.categorySelectionChanged)
            self.model().modelReset.connect(signals.categorySelectionChanged)
        else:
            # If using proxy, connect to the source model for signals
            source = model.sourceModel()
            source.modelAboutToBeReset.connect(signals.categorySelectionChanged)
            source.modelReset.connect(signals.categorySelectionChanged)

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
        Opens a dockable TransactionsDialog on the right side.
        """
        if not index.isValid():
            return

        main = self.window()
        if main is None or not hasattr(main, 'addDockWidget'):
            return

        if not hasattr(main, 'transactions_view') or main.transactions_view is None:
            main.transactions_view = TransactionsDialog(parent=main)
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

class TransactionsView(QtWidgets.QTableView):
    """
    TransactionsView is a custom QTableView for displaying transaction data.

    It configures selection, sizing, and header behavior for an optimal display of the transactions table.
    """
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        self.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.setShowGrid(True)
        self.setAlternatingRowColors(False)
        self.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.0)
        )

    def _init_header(self) -> None:
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(0, QtCore.Qt.AscendingOrder)
        header.setSectionsClickable(True)
        header.setSectionsMovable(False)
        header = self.verticalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        header.setDefaultSectionSize(ui.Size.RowHeight(1.8))
        header.setHidden(True)

    def setModel(self, model: QtCore.QAbstractItemModel) -> None:
        """Sets the model for the view and initializes the header."""
        super().setModel(model)
        self._init_header()
