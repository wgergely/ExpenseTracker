import functools

from PySide6 import QtWidgets, QtCore, QtGui

from . import ui
from .yearmonth import RangeSelectorBar
from ..core import database
from ..data.view.expense import ExpenseView
from ..data.view.transaction import TransactionsWidget
from ..data.view.trends import TrendDockWidget
from ..log.view import LogDockWidget
from ..settings.presets.view import PresetsDockWidget
from ..settings.settings import SettingsDockWidget
from ..ui.actions import signals

main_window = None


def show_main_window():
    global main_window
    if main_window is None:
        main_window = MainWindow()
    main_window.show()
    return main_window


class StatusIndicator(QtWidgets.QWidget):
    """Custom status indicator widget.

    """
    clicked = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setObjectName('ExpenseTrackerStatusIndicator')

        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.setFixedSize(
            ui.Size.RowHeight(1.0),
            ui.Size.RowHeight(1.0)
        )

        self._status = database.CacheState.Uninitialized
        self._connect_signals()

        QtCore.QTimer.singleShot(0, self.update_status)

    def _connect_signals(self):
        self.clicked.connect(self.action)

        signals.configFileChanged.connect(self.update_status)
        signals.configSectionChanged.connect(self.update_status)
        signals.dataAboutToBeFetched.connect(self.update_status)
        signals.dataFetched.connect(self.update_status)
        signals.presetsChanged.connect(self.update_status)
        signals.presetActivated.connect(self.update_status)

    def mouseReleaseEvent(self, event):
        if not self.rect().contains(event.pos()):
            super().mouseReleaseEvent(event)
            return

        if event.button() == QtCore.Qt.LeftButton or event.button() == QtCore.Qt.RightButton:
            self.clicked.emit()
            return

        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        option = QtWidgets.QStyleOption()
        option.initFrom(self)

        hover = option.state & QtWidgets.QStyle.State_MouseOver
        pressed = option.state & QtWidgets.QStyle.State_Sunken

        if self._status == database.CacheState.Valid:
            icon = ui.get_icon('btn_ok', color=ui.Color.Green)
            color = ui.Color.Transparent()
        else:
            color = ui.Color.Yellow()
            icon = ui.get_icon('btn_alert', color=ui.Color.Yellow)

        if hover or pressed:
            color = color.lighter(150)

        center = self.rect().center()

        rect = QtCore.QRect(
            0, 0,
            ui.Size.Margin(1.2), ui.Size.Margin(1.2)
        )
        rect.moveCenter(center)

        if hover or pressed:
            painter.setOpacity(0.4)
        else:
            painter.setOpacity(0.3)

        pen = QtGui.QPen(color.lighter(150))
        pen.setWidth(ui.Size.Separator(2.0))
        painter.setPen(pen)
        painter.setBrush(color)
        painter.drawRoundedRect(
            rect,
            rect.height() * 0.5,
            rect.height() * 0.5,
        )

        rect = QtCore.QRect(
            0, 0,
            ui.Size.Margin(1.0), ui.Size.Margin(1.0)
        )
        rect.moveCenter(center)

        painter.setOpacity(1.0)
        icon.paint(painter, rect, QtCore.Qt.AlignCenter)

        painter.end()

    @QtCore.Slot()
    def update_status(self):
        from ..core.database import database as db
        self._status = db.get_state()

    @QtCore.Slot()
    def action(self):
        self.update_status()
        QtWidgets.QMessageBox.information(self, 'Status', self._status.value.capitalize())


class MainWindow(QtWidgets.QMainWindow):
    """The primary window for the Expense Tracker."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName('ExpenseTrackerMainWindow')
        self.setWindowTitle('Expense Tracker')

        self.toolbar = None
        self.range_selector = None
        self.expense_view = None
        self.transactions_view = None
        self.presets_popup = None
        self.status_indicator = None

        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self._create_ui()
        self._init_actions()
        self._connect_signals()

    def _create_ui(self):
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        central = QtWidgets.QWidget(self)
        QtWidgets.QVBoxLayout(central)

        o = ui.Size.Margin(1.0)
        central.layout().setContentsMargins(o, o, o, o)
        central.layout().setSpacing(ui.Size.Margin(0.5))

        self.setCentralWidget(central)

        # Action bar at the top.
        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.setObjectName('ExpenseTrackerActionToolBar')
        central.layout().addWidget(self.toolbar, 1)

        self.range_selector = RangeSelectorBar(parent=self)
        self.range_selector.setObjectName('ExpenseTrackerRangeSelector')
        self.toolbar.addWidget(self.range_selector)

        self.expense_view = ExpenseView(parent=central)
        self.expense_view.setObjectName('ExpenseTrackerExpenseView')
        central.layout().addWidget(self.expense_view, 1)

        self.status_indicator = StatusIndicator(parent=self)

        self.transactions_view = TransactionsWidget(parent=self)
        self.transactions_view.setObjectName('ExpenseTrackerTransactionsView')

        # Add transactions dock (right side)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.transactions_view)
        self.transactions_view.hide()

        # Add presets dock (left side)
        self.presets_view = PresetsDockWidget(parent=self)
        self.presets_view.setObjectName('ExpenseTrackerPresetsDockWidget')
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.presets_view)
        self.presets_view.hide()

        # Add settings dock (bottom)
        self.settings_view = SettingsDockWidget(parent=self)
        self.settings_view.setObjectName('ExpenseTrackerSettingsDockWidget')
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.settings_view)
        self.settings_view.hide()

        # Add log dock (top)
        self.log_view = LogDockWidget(parent=self)
        self.log_view.setObjectName('ExpenseTrackerLogDockWidget')
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.log_view)
        self.log_view.hide()

        # Add trends dock (bottom)
        self.trends_view = TrendDockWidget(parent=self)
        self.trends_view.setObjectName('ExpenseTrackerTrendDockWidget')
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.trends_view)
        self.trends_view.hide()

    def _connect_signals(self):
        signals.openTransactions.connect(
            lambda: self.transactions_view.setHidden(not self.transactions_view.isHidden()))
        signals.showLogs.connect(lambda: (self.log_view.show(), self.log_view.raise_()))

    def _init_actions(self):
        w = QtWidgets.QWidget(self)
        w.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        w.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        w.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        w.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.toolbar.addWidget(w)

        action = QtGui.QAction('Refresh Data', self)
        action.setIcon(ui.get_icon('btn_fetch'))
        action.setToolTip('Fetch data')
        action.setStatusTip('Fetch data')
        action.triggered.connect(signals.dataFetchRequested)
        self.toolbar.addAction(action)

        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.toolbar.addAction(action)
        self.addAction(action)

        toggle_func = lambda a, s: a.setIcon(
            ui.get_icon(s, color=ui.Color.SelectedText)) if a.isChecked() else a.setIcon(
            ui.get_icon(s, color=ui.Color.DisabledText))
        toggle_vis = lambda e: e.setHidden(not e.isHidden())

        action = QtGui.QAction('Presets', self)
        action.setCheckable(True)
        action.setChecked(self.presets_view.isVisible())
        action.setIcon(ui.get_icon('btn_presets', color=ui.Color.DisabledText))
        action.setToolTip('Show presets...')
        action.setStatusTip('Show presets...')
        action.setShortcut('Ctrl+Shift+P')
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_presets'))
        action.triggered.connect(functools.partial(toggle_vis, self.presets_view))
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Transactions', self)
        action.setCheckable(True)
        action.setChecked(self.transactions_view.isVisible())
        action.setIcon(ui.get_icon('btn_transactions', color=ui.Color.DisabledText))
        action.setToolTip('Show transactions...')
        action.setStatusTip('Show transactions...')
        action.setShortcut('Ctrl+Shift+T')
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_transactions'))
        action.triggered.connect(signals.openTransactions)
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Trends', self)
        action.setCheckable(True)
        action.setChecked(self.trends_view.isVisible())
        action.setIcon(ui.get_icon('btn_trend', color=ui.Color.DisabledText))
        action.setToolTip('Show trends chart...')
        action.setStatusTip('Show trends chart...')
        action.setShortcut('Ctrl+Shift+T')
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_trend'))
        action.triggered.connect(functools.partial(toggle_vis, self.trends_view))
        self.toolbar.addAction(action)
        self.addAction(action)

        # Separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Logs', self)
        action.setCheckable(True)
        action.setChecked(self.log_view.isVisible())
        action.setIcon(ui.get_icon('btn_log', color=ui.Color.DisabledText))
        action.setToolTip('Show logs...')
        action.setStatusTip('Show logs...')
        action.setShortcut('Ctrl+Shift+L')
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_log'))
        action.triggered.connect(functools.partial(toggle_vis, self.log_view))
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Settings', self)
        action.setIcon(ui.get_icon('btn_settings', color=ui.Color.DisabledText))
        action.setToolTip('Show settings...')
        action.setStatusTip('Show settings...')
        action.setCheckable(True)
        action.setChecked(self.settings_view.isVisible())
        action.setShortcuts(['Ctrl+,', 'Ctrl+Shift+,', 'Ctrl+.', 'Ctrl+Shift+.', 'Ctrl+Shift+S'])
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_settings'))
        action.triggered.connect(functools.partial(toggle_vis, self.settings_view))
        self.toolbar.addAction(action)
        self.addAction(action)

        # Separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Previous Month', self)
        action.setShortcuts(['Alt+Left', 'Ctrl+Left'])
        action.setShortcutContext(QtCore.Qt.WindowShortcut)
        action.triggered.connect(self.range_selector.previous_month)
        self.addAction(action)

        action = QtGui.QAction('Next Month', self)
        action.setShortcuts(['Alt+Right', 'Ctrl+Right'])
        action.setShortcutContext(QtCore.Qt.WindowShortcut)
        action.triggered.connect(self.range_selector.next_month)
        self.addAction(action)

        self.toolbar.addWidget(self.status_indicator)

    def sizeHint(self):
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.5)
        )

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
