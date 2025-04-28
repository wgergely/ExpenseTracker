import logging

from PySide6 import QtCore, QtWidgets, QtGui

from . import log
from .model import LogFilterProxyModel, Columns
from .model import LogTableModel, get_handler
from ..ui import ui


class LogTableView(QtWidgets.QTableView):
    """A QTableView displaying log messages from LogTableModel."""

    def __init__(self, parent=None):
        """Initializes the log table view."""
        super().__init__(parent=parent)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        self.setWordWrap(True)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

        self._init_model()
        self._init_headers()
        self._init_actions()
        self._connect_signals()

    def _init_model(self):
        proxy = LogFilterProxyModel(self)
        model = LogTableModel(parent=self)
        proxy.setSourceModel(model)
        proxy.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setModel(proxy)

    def _init_headers(self):
        header = self.horizontalHeader()
        header.setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        header.setDefaultSectionSize(ui.Size.DefaultWidth(0.3))
        header.setSectionResizeMode(Columns.Date.value, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(Columns.Module.value, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(Columns.Level, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(Columns.Message.value, QtWidgets.QHeaderView.Stretch)
        header.setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self.setSortingEnabled(True)
        self.sortByColumn(Columns.Date, QtCore.Qt.DescendingOrder)

        header = self.verticalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setDefaultSectionSize(ui.Size.RowHeight(1.0))
        header.setHidden(True)

    def _init_actions(self):
        pass

    def _connect_signals(self):
        self.model().rowsInserted.connect(self.on_rows_inserted)

    @QtCore.Slot()
    def on_rows_inserted(self):
        """Resize rows after insert to accommodate new entries."""
        header = self.horizontalHeader()
        sort_col = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        model = self.model()

        # Scroll and select based on sort order
        if sort_col == Columns.Date.value and sort_order == QtCore.Qt.DescendingOrder:
            # newest at top
            self.scrollToTop()
            idx = model.index(0, 0)
        else:
            # newest at bottom
            self.scrollToBottom()
            idx = model.index(model.rowCount() - 1, 0)

        # Select and ensure visibility
        if idx.isValid():
            sel = self.selectionModel()
            sel.clearSelection()
            sel.select(idx, QtCore.QItemSelectionModel.ClearAndSelect)
            sel.setCurrentIndex(idx, QtCore.QItemSelectionModel.NoUpdate)
            self.scrollTo(idx)

    def sizeHint(self):
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(0.5)
        )


class LogDockWidget(QtWidgets.QDockWidget):
    """Dockable widget for viewing application logs."""

    def __init__(self, parent=None) -> None:
        super().__init__('Logs', parent)
        self.setObjectName('ExpenseTrackerLogDockWidget')
        self.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable |
            QtWidgets.QDockWidget.DockWidgetFloatable
        )

        widget = QtWidgets.QWidget(self)
        QtWidgets.QVBoxLayout(widget)
        widget.layout().setContentsMargins(0, 0, 0, 0)
        widget.layout().setSpacing(0)

        self.view = LogTableView(widget)
        self.view.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        widget.layout().addWidget(self.view, 1)

        self.setWidget(widget)

        self._init_actions()
        self._connect_signals()

    def _connect_signals(self) -> None:
        self.visibilityChanged.connect(self.on_visibility_changed)

    def _init_actions(self) -> None:
        proxy = self.view.model()

        action = QtGui.QAction('App Level', self)
        menu = QtWidgets.QMenu(self)
        action_group = QtGui.QActionGroup(self)
        action_group.setExclusive(True)

        for name, lvl in [
            ('Debug', logging.DEBUG),
            ('Info', logging.INFO),
            ('Warning', logging.WARNING),
            ('Error', logging.ERROR),
            ('Critical', logging.CRITICAL),
        ]:
            act = menu.addAction(name)
            act.setData(lvl)
            act.setCheckable(True)
            if logging.getLogger().level == lvl:
                act.setChecked(True)
            action_group.addAction(act)
        action_group.triggered.connect(lambda a: log.set_logging_level(a.data()))

        action.setMenu(menu)
        action.setToolTip('Set application logging level')
        self.view.addAction(action)

        action = QtGui.QAction('View Filter', self)
        menu = QtWidgets.QMenu(self)
        action_group = QtGui.QActionGroup(self)
        action_group.setExclusive(True)

        for name, lvl in [
            ('Debug', logging.DEBUG),
            ('Info', logging.INFO),
            ('Warning', logging.WARNING),
            ('Error', logging.ERROR),
            ('Critical', logging.CRITICAL),
        ]:
            act = menu.addAction(name)
            act.setData(lvl)
            act.setCheckable(True)
            if proxy.filter_level() == lvl:
                act.setChecked(True)
            action_group.addAction(act)
        action_group.triggered.connect(lambda a: proxy.set_filter_level(a.data()))

        action.setMenu(menu)
        action.setToolTip('Filter view by minimum logging level')
        self.view.addAction(action)

        # Clear logs action
        action = QtGui.QAction('Clear Logs', self)
        action.setIcon(ui.get_icon('btn_delete'))
        action.setToolTip('Clear all log entries')
        action.triggered.connect(self._clear_logs)
        self.view.addAction(action)

    @QtCore.Slot()
    def _clear_logs(self) -> None:
        """Clear log entries from the model and the log tank."""
        # Clear underlying log tank
        try:
            handler = get_handler()
            handler.clear_logs()
        except RuntimeError:
            logging.warning('TankHandler not found; cannot clear underlying logs.')
        # Clear model entries
        proxy = self.view.model()
        src = proxy.sourceModel()
        src.clear_logs()

    @QtCore.Slot(bool)
    def on_visibility_changed(self, visible: bool) -> None:
        """Pause or resume log model updates when dock visibility changes."""
        model = self.view.model().sourceModel()
        if visible:
            model.resume()
        else:
            model.pause()
