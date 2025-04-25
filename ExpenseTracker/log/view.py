import logging

from PySide6 import QtCore, QtWidgets, QtGui

from .model import LogFilterProxyModel, Columns
from .model import LogTableModel, get_handler
from ..ui import ui


class LogTableView(QtWidgets.QTableView):
    """A QTableView displaying log messages from LogTableModel."""

    def __init__(self, parent=None):
        """Initializes the log table view."""
        super().__init__(parent=parent)
        self.setWordWrap(True)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        self._init_model()
        self._init_headers()
        self._init_actions()
        self._connect_signals()

    def _init_model(self):
        """Creates and sets the LogTableModel through a filter proxy."""
        proxy = LogFilterProxyModel(self)
        model = LogTableModel(parent=self)
        proxy.setSourceModel(model)
        proxy.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setModel(proxy)

    def _init_headers(self):
        """Configures column headers and resizing."""
        header = self.horizontalHeader()
        header.setSectionResizeMode(Columns.Date.value, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Columns.Module.value, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Columns.Level, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Columns.Message.value, QtWidgets.QHeaderView.Stretch)
        header.setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self.setSortingEnabled(True)
        self.sortByColumn(Columns.Date, QtCore.Qt.DescendingOrder)

        header = self.verticalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setDefaultSectionSize(ui.Size.RowHeight(1.0))
        header.setMinimumSectionSize(ui.Size.RowHeight(1.0))
        header.setMaximumSectionSize(ui.Size.RowHeight(2.0))
        header.setHidden(True)

    def _init_actions(self):
        """Initializes actions (stub)."""
        pass

    def _connect_signals(self):
        """Connects signals and slots for model updates."""
        self.model().rowsInserted.connect(self._on_rows_inserted)

    @QtCore.Slot(QtCore.QModelIndex, int, int)
    def _on_rows_inserted(self, parent_index, start, end):
        """Resize rows after insert to accommodate new entries."""
        self.resizeRowsToContents()
        # Determine sort direction for Date column
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
        super().__init__('Log Viewer', parent)
        self.setObjectName('ExpenseTrackerLogDockWidget')
        self.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable |
            QtWidgets.QDockWidget.DockWidgetFloatable
        )

        content = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(content)
        margin = ui.Size.Margin(1.0)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(margin)

        # Toolbar for log controls
        self.toolbar = QtWidgets.QToolBar(content)
        self.toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.toolbar.setMovable(False)
        layout.addWidget(self.toolbar)

        # Log view
        self.view = LogTableView(content)
        self.view.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        layout.addWidget(self.view, 1)

        self.setWidget(content)
        self._init_actions()
        # Pause/resume model updates based on visibility
        self.visibilityChanged.connect(self._on_visibility_changed)

    def _init_actions(self) -> None:
        proxy = self.view.model()

        # Application log level selector
        app_level_action = QtGui.QAction('App Level', self)
        app_menu = QtWidgets.QMenu(self)
        # Exclusive group for app level actions
        self._app_action_group = QtGui.QActionGroup(self)
        self._app_action_group.setExclusive(True)
        for name, lvl in [
            ('Debug', logging.DEBUG),
            ('Info', logging.INFO),
            ('Warning', logging.WARNING),
            ('Error', logging.ERROR),
            ('Critical', logging.CRITICAL),
        ]:
            act = app_menu.addAction(name)
            act.setData(lvl)
            act.setCheckable(True)
            if logging.getLogger().level == lvl:
                act.setChecked(True)
            act.triggered.connect(lambda checked, level=lvl: self._set_app_level(level))
            self._app_action_group.addAction(act)
        app_level_action.setMenu(app_menu)
        app_level_action.setToolTip('Set application logging level')
        # context menu item
        self.view.addAction(app_level_action)
        # toolbar widget with instant popup
        btn_app = QtWidgets.QToolButton(self.toolbar)
        btn_app.setDefaultAction(app_level_action)
        btn_app.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.toolbar.addWidget(btn_app)

        self.toolbar.addSeparator()

        # View filter level selector
        view_filter_action = QtGui.QAction('View Filter', self)
        view_menu = QtWidgets.QMenu(self)
        # Exclusive group for view filter actions
        self._view_filter_group = QtGui.QActionGroup(self)
        self._view_filter_group.setExclusive(True)
        for name, lvl in [
            ('Debug', logging.DEBUG),
            ('Info', logging.INFO),
            ('Warning', logging.WARNING),
            ('Error', logging.ERROR),
            ('Critical', logging.CRITICAL),
        ]:
            act = view_menu.addAction(name)
            act.setData(lvl)
            act.setCheckable(True)
            if proxy._filter_level == lvl:
                act.setChecked(True)
            act.triggered.connect(lambda checked, level=lvl: proxy.setFilterLogLevel(level))
            self._view_filter_group.addAction(act)
        view_filter_action.setMenu(view_menu)
        view_filter_action.setToolTip('Filter view by minimum logging level')
        # context menu item
        self.view.addAction(view_filter_action)
        # toolbar widget with instant popup
        btn_view = QtWidgets.QToolButton(self.toolbar)
        btn_view.setDefaultAction(view_filter_action)
        btn_view.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.toolbar.addWidget(btn_view)

        self.toolbar.addSeparator()

        # Clear logs action
        clear_action = QtGui.QAction('Clear Logs', self)
        clear_action.setIcon(ui.get_icon('btn_delete'))
        clear_action.setToolTip('Clear all log entries')
        clear_action.triggered.connect(self._clear_logs)
        self.toolbar.addAction(clear_action)
        self.view.addAction(clear_action)

    @QtCore.Slot(int)
    def _set_app_level(self, level: int) -> None:
        """Set the root logger's level."""
        logging.getLogger().setLevel(level)

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
    def _on_visibility_changed(self, visible: bool) -> None:
        """Pause or resume log model updates when dock visibility changes."""
        model = self.view.model().sourceModel()
        if visible:
            model.resume()
        else:
            model.pause()
