from PySide6 import QtWidgets, QtCore, QtGui

from . import ui
from .yearmonth import RangeSelectorBar
from ..data import model
from ..data import view
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


class LoadIndicator(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(5000)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

        self._connect_signals()

    def _connect_signals(self):
        signals.dataAboutToBeFetched.connect(self.show)
        signals.dataAboutToBeFetched.connect(self.set_size)
        signals.dataFetched.connect(self.hide)
        signals.dataFetched.connect(self.set_size)

    @QtCore.Slot()
    def set_size(self):
        r = self.parent().window().geometry()
        self.setGeometry(r)
        QtWidgets.QApplication.instance().processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
        self.repaint()
        self.update()

    def show(self):
        super().show()
        self.timer.start()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)

        r = self.rect()

        o = ui.Size.Margin(2.0)
        r = r.adjusted(o, o, -o, -o)
        r.setHeight(ui.Size.Margin(1.5))
        r.moveCenter(self.rect().center())

        text = 'Fetching data...'
        font, _ = ui.Font.BoldFont(ui.Size.MediumText(1.0))
        painter.setFont(font)
        painter.setPen(ui.Color.SecondaryText())
        painter.drawText(r, QtCore.Qt.AlignCenter, text)

        painter.end()


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

        self._connect_signals()

        QtCore.QTimer.singleShot(0, self.update_status)

    def _connect_signals(self):
        self.clicked.connect(self.action)

        signals.configFileChanged.connect(self.update_status)
        signals.configSectionChanged.connect(self.update_status)
        signals.dataAboutToBeFetched.connect(self.update_status)
        signals.dataFetched.connect(self.update_status)

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
            icon = ui.get_icon('btn_ok', color=ui.Color.Green())
            color = ui.Color.Transparent()
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

        msg = lib.status_user_strings[self._status]

        if self._status == lib.Status.ClientSecretNotFound:
            settings.show_settings_widget(parent=self.window())
            QtWidgets.QMessageBox.critical(self, 'Error', msg)
        elif self._status == lib.Status.ClientSecretInvalid:
            settings.show_settings_widget(parent=self.window())
            QtWidgets.QMessageBox.critical(self, 'Error', msg)
        elif self._status == lib.Status.SpreadsheetIdNotConfigured:
            settings.show_settings_widget(parent=self.window())
            QtWidgets.QMessageBox.critical(self, 'Error', msg)
        elif self._status == lib.Status.SpreadsheetWorksheetNotConfigured:
            settings.show_settings_widget(parent=self.window())
            QtWidgets.QMessageBox.critical(self, 'Error', msg)
        elif self._status == lib.Status.ServiceUnavailable:
            QtWidgets.QMessageBox.critical(self, 'Error', msg)
        elif self._status == lib.Status.NotAuthenticated:
            QtWidgets.QMessageBox.critical(self, 'Error', msg)
            actions.authenticate()
        elif self._status == lib.Status.CacheInvalid:
            QtWidgets.QMessageBox.critical(self, 'Error', msg)
            actions.fetch_data()
        elif self._status == lib.Status.StatusOkay:
            QtWidgets.QMessageBox.information(self, 'Status', msg)


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

        self.load_indicator = LoadIndicator(parent=self)
        self.load_indicator.hide()

        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        ui.set_stylesheet(self)

        self._create_ui()
        self._init_actions()
        self._init_model()
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

        self.expense_view = view.ExpenseView(parent=central)
        self.expense_view.setObjectName('ExpenseTrackerExpenseView')
        central.layout().addWidget(self.expense_view, 1)

        self.status_indicator = StatusIndicator(parent=self)

    def _connect_signals(self):
        pass

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


        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        action = QtGui.QAction('Open Spreadsheet...', self)
        action.setIcon(ui.get_icon('btn_ledger'))
        action.setShortcut('Ctrl+O')
        action.setStatusTip('Open the spreadsheet in the browser')
        action.triggered.connect(actions.open_spreadsheet)
        self.addAction(action)
        self.toolbar.addAction(action)

        action = QtGui.QAction('Fetch Remote Data', self)
        action.setIcon(ui.get_icon('btn_sync'))
        action.setShortcut('Ctrl+R')
        action.setStatusTip('Fetch the data from the remote spreadsheet')
        action.triggered.connect(actions.fetch_data)
        self.addAction(action)
        self.toolbar.addAction(action)

        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)
        self.toolbar.addAction(action)

        action = QtGui.QAction('Open Settings...', self)
        action.setIcon(ui.get_icon('btn_settings'))
        action.setShortcuts(['Ctrl+P', 'Ctrl+.'])
        action.setStatusTip('Open Settings')
        action.triggered.connect(open_settings)
        self.addAction(action)
        self.toolbar.addAction(action)


        action = QtGui.QAction('Quit', self)
        action.setIcon(ui.get_icon('btn_quit', color=ui.Color.Red()))
        action.setShortcut('Ctrl+Q')
        action.setStatusTip('Quit the application')
        action.triggered.connect(QtWidgets.QApplication.instance().quit)
        self.addAction(action)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(self.status_indicator)

    def _init_model(self):
        self.model = model.ExpenseModel(parent=self.expense_view)
        self.expense_view.setModel(self.model)

    def sizeHint(self):
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.6),
            ui.Size.DefaultHeight(1.6)
        )
