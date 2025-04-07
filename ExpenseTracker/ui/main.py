import enum

from PySide6 import QtWidgets, QtCore, QtGui

from . import ui
from .yearmonth import RangeSelectorBar
from ..auth import auth
from ..auth import service
from ..data import model
from ..data import view
from ..database import database
from ..settings import lib
from ..ui import actions
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

        self._status = lib.Status.UnknownStatus
        self._watcher = QtCore.QFileSystemWatcher(self)

        self._connect_signals()
        self._init_watcher()
        QtCore.QTimer.singleShot(0, self.update_status)

    def _connect_signals(self):
        self.clicked.connect(self.action)
        signals.configSectionChanged.connect(self.update_status)
        signals.dataFetched.connect(self.update_status)

    def _init_watcher(self):
        self._watcher.addPath(str(lib.settings.paths.config_dir))
        self._watcher.addPath(str(lib.settings.paths.presets_dir))
        self._watcher.addPath(str(lib.settings.paths.auth_dir))
        self._watcher.addPath(str(lib.settings.paths.db_dir))

        self._watcher.addPath(str(lib.settings.paths.client_secret_path))
        self._watcher.addPath(str(lib.settings.paths.ledger_path))
        self._watcher.addPath(str(lib.settings.paths.creds_path))
        self._watcher.addPath(str(lib.settings.paths.db_path))

        self._watcher.directoryChanged.connect(self.update_status)
        self._watcher.fileChanged.connect(self.update_status)

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

        if self._status == lib.Status.StatusOkay:
            color = ui.Color.Green()
            icon = ui.get_icon('btn_ok', color=color)
        else:
            color = ui.Color.Yellow()
            icon = ui.get_icon('btn_alert', color=color)

        if hover or pressed:
            color = color.lighter(150)

        rect = self.rect()
        if hover or pressed:
            o = ui.Size.Indicator(0.8)
        else:
            o = ui.Size.Indicator(1.0)

        rect = rect.adjusted(o, o, -o, -o)

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
        rect.moveCenter(self.rect().center())

        painter.setOpacity(1.0)
        icon.paint(painter, rect, QtCore.Qt.AlignCenter)

        painter.end()

    @QtCore.Slot()
    def update_status(self):
        self._status = lib.settings.get_status()

    @QtCore.Slot()
    def action(self):
        from ..settings import settings

        # Update the status before taking action
        self.update_status()

        if self._status == lib.Status.ClientSecretNotFound:
            msg = 'Google authentication information is missing, check the settings.'
            QtWidgets.QMessageBox.critical(self, 'Error', msg)
            settings.show_settings_widget(parent=self)
            return

        if self._status == lib.Status.ClientSecretInvalid:
            settings.show_settings_widget(parent=self.window())
            msg = 'Google Client Secret was not found or is invalid, check the settings.'
            QtWidgets.QMessageBox.critical(self, 'Error', msg)
            return

        if self._status == lib.Status.SpreadsheetIdNotConfigured:
            settings.show_settings_widget(parent=self.window())
            msg = 'Make sure a valid spreadsheet ID is configured in the settings.'
            QtWidgets.QMessageBox.critical(self, 'Error', msg)
            return

        if self._status == lib.Status.SpreadsheetWorksheetNotConfigured:
            settings.show_settings_widget(parent=self.window())
            msg = 'Make sure a valid worksheet name is configured in the settings.'
            QtWidgets.QMessageBox.critical(self, 'Error', msg)
            return

        if self._status == lib.Status.ServiceUnavailable:
            msg = 'The Google Sheets service is unavailable, please check your connection.'
            QtWidgets.QMessageBox.critical(self, 'Error', msg)
            return

        if self._status == lib.Status.NotAuthenticated:
            actions.authenticate()
            return

        if self._status == lib.Status.CacheInvalid:
            msg = 'The remote data needs to be fetched again, please wait...'
            QtWidgets.QMessageBox.critical(self, 'Error', msg)
            actions.fetch_data()
            return


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

        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        ui.set_stylesheet(self)

        self._create_ui()
        self._init_actions()
        self._connect_signals()

        QtCore.QTimer.singleShot(150, self.init_data)

    def _create_ui(self):
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ui.Size.Margin(0.5))

        # Action bar at the top.
        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.setObjectName('ExpenseTrackerActionToolBar')
        layout.addWidget(self.toolbar, 1)

        self.range_selector = RangeSelectorBar(parent=self)
        self.range_selector.setObjectName('ExpenseTrackerRangeSelector')
        self.toolbar.addWidget(self.range_selector)

        self.expense_view = view.ExpenseView(parent=central)
        self.expense_view.setObjectName('ExpenseTrackerExpenseView')
        layout.addWidget(self.expense_view, 1)

        self.status_indicator = StatusIndicator(parent=self)

    def _connect_signals(self):
        pass

    @QtCore.Slot()
    def init_data(self):
        year_month, _ = self.range_selector.get_range()

        span = self.range_selector.get_range_span()
        m = model.ExpenseModel(year_month, span=span)
        m.set_year_month(year_month)
        m.set_span(span)

        self.expense_view.setModel(m)

    def _init_actions(self):
        @QtCore.Slot()
        def open_settings():
            from ..settings import settings
            settings.show_settings_widget(parent=self)

        # Stretchable spacer
        w = QtWidgets.QWidget(self)
        w.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Preferred)
        w.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        w.setStyleSheet('background: transparent;')
        self.toolbar.addWidget(w)

        action = QtGui.QAction('Open Settings...', self)
        action.setIcon(ui.get_icon('btn_settings'))
        action.setShortcuts(['Ctrl+P', 'Ctrl+.'])
        action.setStatusTip('Open Settings')
        action.triggered.connect(open_settings)
        self.addAction(action)
        self.toolbar.addAction(action)

        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        action = QtGui.QAction('Refresh Data', self)
        action.setIcon(ui.get_icon('btn_sync'))
        action.setShortcut('Ctrl+R')
        action.setStatusTip('Refresh Data')
        action.triggered.connect(actions.fetch_data)
        self.addAction(action)
        self.toolbar.addAction(action)

        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        action = QtGui.QAction('Quit', self)
        action.setIcon(ui.get_icon('btn_quit', color=ui.Color.Red()))
        action.setShortcut('Ctrl+Q')
        action.setStatusTip('Quit the application')
        action.triggered.connect(QtWidgets.QApplication.instance().quit)
        self.addAction(action)

        self.toolbar.addWidget(self.status_indicator)

    def sizeHint(self):
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.6),
            ui.Size.DefaultHeight(1.6)
        )
