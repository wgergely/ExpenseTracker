from PySide6 import QtWidgets, QtCore, QtGui

from ..model.transaction import TransactionsModel, TransactionsSortFilterProxyModel, Columns
from ...ui import ui
from ...settings import lib


class TransactionsWidget(QtWidgets.QDockWidget):
    """
    TransactionsWidget is a custom dockable widget for displaying transaction data.

    It initializes the view and sets up the layout for displaying transactions.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__('Transactions', parent=parent)
        self.setObjectName('ExpenseTrackerTransactionsWidget')
        self.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable |
            QtWidgets.QDockWidget.DockWidgetFloatable
        )
        self.setMinimumSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.0)
        )
        self.view = None

        self._create_ui()

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

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.0)
        )


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
        self.setShowGrid(True)
        self.setAlternatingRowColors(False)
        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.MinimumExpanding
        )

        ui.set_stylesheet(self)

        self._init_model()
        self._init_actions()
        self._connect_signals()

    def _init_model(self) -> None:
        model = TransactionsModel()
        proxy = TransactionsSortFilterProxyModel(self)
        proxy.setSourceModel(model)
        self.setModel(proxy)

        self._init_section_sizing()

        self.setSortingEnabled(True)
        self.sortByColumn(Columns.Amount.value, QtCore.Qt.DescendingOrder)


    def _init_actions(self) -> None:
        action_group = QtGui.QActionGroup(self)
        action_group.setExclusive(True)

        action = QtGui.QAction('Sort by Date', self)
        action.setCheckable(True)
        action.setChecked(True)
        action.setShortcut('alt+1')
        action.triggered.connect(lambda: self.sortByColumn(Columns.Date.value, self.model().sortOrder()))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort by Amount', self)
        action.setCheckable(True)
        action.setShortcut('alt+2')
        action.triggered.connect(lambda: self.sortByColumn(Columns.Amount.value, self.model().sortOrder()))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort by Description', self)
        action.setCheckable(True)
        action.setShortcut('alt+3')
        action.triggered.connect(lambda: self.sortByColumn(Columns.Description.value, self.model().sortOrder()))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort by Category', self)
        action.setCheckable(True)
        action.setShortcut('alt+4')
        action.triggered.connect(lambda: self.sortByColumn(Columns.Category.value, self.model().sortOrder()))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort by Account', self)
        action.setCheckable(True)
        action.setShortcut('alt+5')
        action.triggered.connect(lambda: self.sortByColumn(Columns.Account.value, self.model().sortOrder()))
        action_group.addAction(action)
        self.addAction(action)

        # separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        action_group = QtGui.QActionGroup(self)
        action_group.setExclusive(True)


        action = QtGui.QAction('Sort Ascending', self)
        action.setCheckable(True)
        action.setShortcut('alt+up')
        action.triggered.connect(lambda: self.sortByColumn(self.model().sortColumn(), QtCore.Qt.AscendingOrder))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort Descending', self)
        action.setCheckable(True)
        action.setChecked(True)
        action.setShortcut('alt+down')
        action.triggered.connect(lambda: self.sortByColumn(self.model().sortColumn(), QtCore.Qt.DescendingOrder))
        action_group.addAction(action)
        self.addAction(action)



    @QtCore.Slot()
    def _init_section_sizing(self) -> None:
        header = self.horizontalHeader()
        header.setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        header.setStretchLastSection(False)

        header.setSectionResizeMode(Columns.Account.value, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Columns.Date.value, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Columns.Amount.value, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Columns.Description.value, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(Columns.Category.value, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Columns.Amount.value, QtWidgets.QHeaderView.ResizeToContents)

        header.setSortIndicatorShown(True)
        header.setSortIndicator(0, QtCore.Qt.AscendingOrder)
        header.setSectionsClickable(True)
        header.setSectionsMovable(False)

        header = self.verticalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        header.setDefaultSectionSize(ui.Size.RowHeight(1.8))
        header.setHidden(True)

    def _connect_signals(self):
        self.model().sourceModel().modelReset.connect(lambda: self.model().sort(self.model().sortColumn(), self.model().sortOrder()))