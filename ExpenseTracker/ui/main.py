"""Main window composition and UI entry points for ExpenseTracker.

This module defines:
    - show(): initialize and display the main window
    - Edge: directional flags for window resizing
    - TitleLabel, TitleBar: custom title components
    - StatusIndicator: widget for cache status display
    - InteractionState and ResizableMainWidget: support window resizing and state changes
"""
import functools
import logging

from PySide6 import QtWidgets, QtCore, QtGui

from . import ui
from .yearmonth import RangeSelectorBar
from ..core import database
from ..data.view.doughnut import DoughnutDockWidget
from ..data.view.expense import ExpenseView
from ..data.view.piechart import PieChartDockWidget
from ..data.view.transaction import TransactionsDockWidget
from ..data.view.transactiondetails import TransactionDetailsDockWidget
from ..data.view.trends import TrendDockWidget
from ..log.view import LogDockWidget
from ..settings.lib import app_name
from ..settings.presets.view import PresetsDockWidget
from ..settings.settings import SettingsDockWidget
from ..ui.actions import signals

widget = None


def show():
    global widget

    if widget is None:
        widget = MainWindow()

    widget.show()


class TitleLabel(QtWidgets.QWidget):
    """Custom title label for the main window."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent=parent)
        self.setObjectName('ExpenseTrackerTitleLabel')

        self._connect_signals()

        QtCore.QTimer.singleShot(100, self.update_title)

    def _connect_signals(self) -> None:
        from ..ui.actions import signals

        @QtCore.Slot(str, object)
        def metadata_changed(key: str, value: object) -> None:
            if key == 'name':
                self.update_title()

        signals.metadataChanged.connect(metadata_changed)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(ui.Color.Text())

        font, metrics = self.get_font()
        x = self.rect().x()
        y = self.rect().center().y() + metrics.height() / 2.0 - metrics.descent()

        path = QtGui.QPainterPath()
        path.addText(
            x,
            y,
            font,
            self.get_title()
        )

        painter.drawPath(path)

    @staticmethod
    def get_font():
        return ui.Font.BlackFont(ui.Size.MediumText(2.0))

    @staticmethod
    def get_title():
        from ..settings import lib
        v = lib.settings['name']
        return v or 'Untitled'

    @QtCore.Slot()
    def update_title(self) -> None:
        """Set the title of the label."""
        font, metrics = self.get_font()
        title = self.get_title()
        self.setFixedWidth(metrics.horizontalAdvance(title) + ui.Size.Margin(1.0))
        self.update()


class TitleBar(QtWidgets.QWidget):
    """A custom title bar with branding and window controls."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent=parent)
        self._drag_pos = None
        self.icon_label = None
        self.title_label = None

        self.setFixedHeight(ui.Size.RowHeight(1.5))

        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Fixed
        )

        self._create_ui()
        self._connect_signals()
        self._init_actions()

    def _create_ui(self) -> None:
        QtWidgets.QHBoxLayout(self)
        self.setObjectName('ExpenseTrackerTitleBar')

        o = ui.Size.Margin(1.0)
        self.layout().setContentsMargins(o, 0, -o, 0)
        self.layout().setSpacing(ui.Size.Indicator(2.0))
        self.layout().setAlignment(QtCore.Qt.AlignCenter)

        # Title
        self.title_label = TitleLabel(parent=self)
        self.layout().addWidget(self.title_label, 0)

    def _init_actions(self) -> None:
        pass

    def _connect_signals(self) -> None:
        pass

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        # only start drag when not maximized
        if event.button() == QtCore.Qt.LeftButton and not self.window().isMaximized():
            self._drag_pos = event.globalPosition().toPoint()
        else:
            self._drag_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if (event.buttons() & QtCore.Qt.LeftButton and
                self._drag_pos is not None and
                not self.window().isMaximized()):
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.window().move(self.window().pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        self.toggle_max_restore()
        super().mouseDoubleClickEvent(event)

    @QtCore.Slot()
    def toggle_max_restore(self) -> None:
        """Toggle between maximized and normal via the ResizableMainWidget API."""
        win = self.window()
        if hasattr(win, 'toggle_maximised'):
            win.toggle_maximised()
        else:
            # fallback
            if win.isMaximized():
                win.showNormal()
            else:
                win.showMaximized()


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

        signals.configSectionChanged.connect(self.update_status)
        signals.dataAboutToBeFetched.connect(self.update_status)
        signals.dataFetched.connect(self.update_status)
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
        try:
            self._status = db.get_state()
        except Exception as e:
            logging.warning(f'Failed to get database state: {e}')
            self._status = database.CacheState.Uninitialized

    @QtCore.Slot()
    def action(self):
        self.update_status()

        from ..core import service
        try:
            service.verify_sheet_access()
            QtWidgets.QMessageBox.information(
                self,
                'Status',
                f'Spreadsheet access verified. \nStatus: {self._status.value.capitalize()}',
                QtWidgets.QMessageBox.Ok
            )
        except Exception as ex:
            QtWidgets.QMessageBox.warning(
                self,
                'Status',
                f'Failed to verify spreadsheet access: {ex} \n\nStatus: {self._status.value.capitalize()}',
                QtWidgets.QMessageBox.Ok
            )


class ResizableMainWidget(QtWidgets.QMainWindow):
    """QMainWindow subclass handling geometry state and maximize/restore behavior."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._previous_geometry = None
        o = ui.Size.Margin(2.0)
        default = (o, int(o * 0.25), o, o)
        # when normal, half of the old frameless margins:
        self._normal_margins = tuple(int(m * 0.5) for m in default)
        # when maximized, no margins:
        self._frameless_margins = (0, 0, 0, 0)
        self.setContentsMargins(*self._normal_margins)

    def showMaximized(self) -> None:
        """Show window maximized without frame and margins."""
        self._previous_geometry = self.geometry()
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint, True)
        self.setContentsMargins(*self._frameless_margins)
        super().showMaximized()

    def showNormal(self) -> None:
        """Restore window to normal state with frame and adjusted margins."""
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint, False)
        self.setContentsMargins(*self._normal_margins)
        super().showNormal()
        if self._previous_geometry is not None:
            self.setGeometry(self._previous_geometry)
            self._previous_geometry = None

    @QtCore.Slot()
    def toggle_maximised(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    @QtCore.Slot()
    def toggle_minimized(self) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.showMinimized()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(ui.Color.VeryDarkBackground())
        painter.drawRect(self.rect())


class MainWindow(ResizableMainWidget):

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        # Enable nested and animated docking behaviors
        opts = self.dockOptions()
        opts |= QtWidgets.QMainWindow.AllowNestedDocks | QtWidgets.QMainWindow.AnimatedDocks
        self.setDockOptions(opts)
        # Position dock-tabs: horizontal at top/bottom, vertical on sides
        self.setTabPosition(QtCore.Qt.LeftDockWidgetArea, QtWidgets.QTabWidget.West)
        self.setTabPosition(QtCore.Qt.RightDockWidgetArea, QtWidgets.QTabWidget.East)
        self.setTabPosition(QtCore.Qt.TopDockWidgetArea, QtWidgets.QTabWidget.North)
        self.setTabPosition(QtCore.Qt.BottomDockWidgetArea, QtWidgets.QTabWidget.South)
        self.setWindowTitle(app_name)

        self.setObjectName('ExpenseTrackerMainWindow')

        self.content_area = None

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
        self.load_window_settings()

    def _create_ui(self):
        self.setMenuWidget(TitleBar(self))

        central = QtWidgets.QWidget(self)
        central.setProperty('rounded', True)
        QtWidgets.QVBoxLayout(central)

        o = ui.Size.Margin(1.0)
        central.layout().setContentsMargins(o, 0, o, o)
        central.layout().setSpacing(o * 0.5)

        self.setCentralWidget(central)

        # Action bar at the top.
        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.setProperty('transparent', True)
        self.toolbar.setProperty('no_background', True)
        self.toolbar.setObjectName('ExpenseTrackerActionToolBar')
        self.menuWidget().layout().insertWidget(1, self.toolbar, 1)

        self.range_selector = RangeSelectorBar(parent=self)
        self.range_selector.setObjectName('ExpenseTrackerRangeSelector')
        self.toolbar.addWidget(self.range_selector)

        self.expense_view = ExpenseView(parent=central)
        self.expense_view.setObjectName('ExpenseTrackerExpenseView')
        central.layout().addWidget(self.expense_view, 1)

        self.status_indicator = StatusIndicator(parent=self)

        # Add transactions dock (right side)
        self.transactions_view = TransactionsDockWidget(parent=self)
        self.transactions_view.setObjectName('ExpenseTrackerTransactionsView')
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.transactions_view)
        self.transactions_view.hide()
        # Add transaction preview dock (right side)
        self.transaction_preview = TransactionDetailsDockWidget(parent=self)
        self.transaction_preview.setObjectName('ExpenseTrackerTransactionDetailsDockWidget')
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.transaction_preview)
        self.transaction_preview.hide()

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

        # Add trend dock (bottom)
        self.trends_view = TrendDockWidget(parent=self)
        self.trends_view.setObjectName('ExpenseTrackerTrendDockWidget')
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.trends_view)
        self.trends_view.hide()

        # Add pie chart dock (right side)
        self.piechart_view = PieChartDockWidget(parent=self)
        self.piechart_view.setObjectName('ExpenseTrackerPieChartDockWidget')
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.piechart_view)
        self.piechart_view.hide()

        # Add doughnut chart dock (right side)
        self.doughnut_view = DoughnutDockWidget(parent=self)
        self.doughnut_view.setObjectName('ExpenseTrackerDoughnutDockWidget')
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.doughnut_view)
        self.doughnut_view.hide()

    def _connect_signals(self):
        signals.showTransactions.connect(
            lambda: self.transactions_view.setHidden(not self.transactions_view.isHidden()))
        signals.showLogs.connect(lambda: (self.log_view.show(), self.log_view.raise_()))

        signals.showSettings.connect(self.settings_view.show)
        signals.showTransactionPreview.connect(self.transaction_preview.show)

    def _init_actions(self):
        action = QtGui.QAction('Maximize', self)
        action.setIcon(ui.get_icon('btn_maximize'))
        action.setToolTip('Maximize')
        action.setStatusTip('Maximize')
        action.setShortcut('Ctrl+M')
        action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        action.triggered.connect(self.toggle_maximised)
        self.addAction(action)

        # Separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        w = QtWidgets.QWidget(self)
        w.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        w.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        w.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Maximum)
        self.toolbar.addWidget(w)

        action = QtGui.QAction('Open Spreadsheet', self)
        action.setShortcut('Ctrl+Shift+O')
        action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        action.setToolTip('Open spreadsheet in browser')
        action.setIcon(ui.get_icon('btn_ledger'))
        action.triggered.connect(signals.openSpreadsheet)
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.toolbar.addAction(action)
        self.addAction(action)

        toggle_func = lambda a, s: a.setIcon(
            ui.get_icon(s, color=ui.Color.Green)) if a.isChecked() else a.setIcon(
            ui.get_icon(s, color=ui.Color.DisabledText))
        toggle_vis = lambda e: e.setHidden(not e.isHidden())

        action = QtGui.QAction('Presets', self)
        action.setCheckable(True)
        action.setChecked(self.presets_view.isVisible())
        action.setIcon(ui.get_icon('btn_presets', color=ui.Color.DisabledText))
        action.setToolTip('Show presets...')
        action.setStatusTip('Show presets...')
        action.setShortcut('Ctrl+Shift+V')
        action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_presets'))
        action.triggered.connect(functools.partial(toggle_vis, self.presets_view))
        self.toolbar.addAction(action)
        self.addAction(action)
        self.presets_view.toggled.connect(action.setChecked)
        action.toggled.connect(lambda checked, a=action: toggle_func(a, 'btn_presets'))

        # Transaction Preview toggle
        action = QtGui.QAction('Preview', self)
        action.setCheckable(True)
        action.setChecked(self.transaction_preview.isVisible())
        action.setIcon(ui.get_icon('btn_TransactionDetails', color=ui.Color.DisabledText))
        action.setToolTip('Show transaction preview...')
        action.setStatusTip('Show transaction preview...')
        action.setShortcut('Ctrl+Shift+V')
        action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        # toggle icon color
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_TransactionDetails'))
        # toggle visibility
        action.triggered.connect(functools.partial(toggle_vis, self.transaction_preview))
        self.toolbar.addAction(action)
        self.addAction(action)
        self.transaction_preview.toggled.connect(action.setChecked)
        action.toggled.connect(lambda checked, a=action: toggle_func(a, 'btn_TransactionDetails'))

        # Separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Transactions', self)
        action.setCheckable(True)
        action.setChecked(self.transactions_view.isVisible())
        action.setIcon(ui.get_icon('btn_transactions', color=ui.Color.DisabledText))
        action.setToolTip('Show transactions...')
        action.setStatusTip('Show transactions...')
        action.setShortcut('Ctrl+Shift+T')
        action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_transactions'))

        self.toolbar.addAction(action)
        self.addAction(action)
        self.transactions_view.toggled.connect(action.setChecked)
        action.toggled.connect(lambda checked, a=action: toggle_func(a, 'btn_transactions'))

        action = QtGui.QAction('Trends', self)
        action.setCheckable(True)
        action.setChecked(self.trends_view.isVisible())
        action.setIcon(ui.get_icon('btn_trend', color=ui.Color.DisabledText))
        action.setToolTip('Show trends chart...')
        action.setStatusTip('Show trends chart...')
        action.setShortcut('Ctrl+Shift+T')
        action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_trend'))
        action.triggered.connect(functools.partial(toggle_vis, self.trends_view))
        self.toolbar.addAction(action)
        self.addAction(action)
        self.trends_view.toggled.connect(action.setChecked)
        action.toggled.connect(lambda checked, a=action: toggle_func(a, 'btn_trend'))

        # Pie Chart toggle
        action = QtGui.QAction('Pie Chart', self)
        action.setCheckable(True)
        action.setChecked(self.piechart_view.isVisible())
        action.setIcon(ui.get_icon('btn_piechart', color=ui.Color.DisabledText))
        action.setToolTip('Show pie chart...')
        action.setStatusTip('Show pie chart...')
        action.triggered.connect(functools.partial(toggle_vis, self.piechart_view))
        self.toolbar.addAction(action)
        self.addAction(action)
        self.piechart_view.toggled.connect(action.setChecked)
        action.toggled.connect(lambda checked, a=action: toggle_func(a, 'btn_piechart'))

        # Doughnut Chart toggle
        action = QtGui.QAction('Doughnut Chart', self)
        action.setCheckable(True)
        action.setChecked(self.doughnut_view.isVisible())
        action.setIcon(ui.get_icon('btn_doughnut', color=ui.Color.DisabledText))
        action.setToolTip('Show doughnut chart...')
        action.setStatusTip('Show doughnut chart...')
        action.triggered.connect(functools.partial(toggle_vis, self.doughnut_view))
        self.toolbar.addAction(action)
        self.addAction(action)
        # sync action checked state when view visibility changes
        self.doughnut_view.toggled.connect(action.setChecked)
        action.toggled.connect(lambda checked, a=action: toggle_func(a, 'btn_doughnut'))

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
        action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_log'))
        action.triggered.connect(functools.partial(toggle_vis, self.log_view))
        self.toolbar.addAction(action)
        self.addAction(action)
        self.log_view.toggled.connect(action.setChecked)
        action.toggled.connect(lambda checked, a=action: toggle_func(a, 'btn_log'))

        action = QtGui.QAction('Settings', self)
        action.setIcon(ui.get_icon('btn_settings', color=ui.Color.DisabledText))
        action.setToolTip('Show settings...')
        action.setStatusTip('Show settings...')
        action.setCheckable(True)
        action.setChecked(self.settings_view.isVisible())
        action.setShortcuts(['Ctrl+,', 'Ctrl+Shift+,', 'Ctrl+.', 'Ctrl+Shift+.', 'Ctrl+Shift+S'])
        action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        action.triggered.connect(functools.partial(toggle_func, action, 'btn_settings'))
        action.triggered.connect(functools.partial(toggle_vis, self.settings_view))
        self.toolbar.addAction(action)
        self.addAction(action)
        self.settings_view.toggled.connect(action.setChecked)
        action.toggled.connect(lambda checked, a=action: toggle_func(a, 'btn_settings'))

        # Separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Previous Month', self)
        action.setShortcuts(['Alt+Left', 'Ctrl+Left'])
        action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        action.triggered.connect(self.range_selector.previous_month)
        self.addAction(action)

        action = QtGui.QAction('Next Month', self)
        action.setShortcuts(['Alt+Right', 'Ctrl+Right'])
        action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        action.triggered.connect(self.range_selector.next_month)
        self.addAction(action)

        action = QtGui.QAction('Refresh Data', self)
        action.setIcon(ui.get_icon('btn_sync'))
        action.setToolTip('Fetch data')
        action.setStatusTip('Fetch data')
        action.triggered.connect(signals.dataFetchRequested)
        self.toolbar.addAction(action)

        self.toolbar.addWidget(self.status_indicator)

    def sizeHint(self):
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.5)
        )

    def closeEvent(self, event) -> None:
        """Persist window geometry and state on close."""
        settings = QtCore.QSettings(app_name, app_name)
        settings.setValue('MainWindow/geometry', self.saveGeometry())
        settings.setValue('MainWindow/windowState', self.saveState())
        settings.setValue('MainWindow/maximized', self.isMaximized())
        super().closeEvent(event)

    @QtCore.Slot(QtCore.QModelIndex)
    def activate_action(self, index: QtCore.QModelIndex) -> None:
        """
        Slot called on double-clicking or pressing Enter on a row.
        Opens a dockable TransactionsDockWidget on the right side.
        """
        if not index.isValid():
            return
        self.window().transactions_view.show()

    def load_window_settings(self) -> None:
        settings = QtCore.QSettings(app_name, app_name)
        geom_data = settings.value('MainWindow/geometry')
        # correctly interpret saved maximized flag (could be bool, string, or numeric)
        raw_max = settings.value('MainWindow/maximized', False)
        if isinstance(raw_max, bool):
            was_maximized = raw_max
        elif isinstance(raw_max, str):
            was_maximized = raw_max.lower() in ('true', '1')
        else:
            try:
                was_maximized = bool(int(raw_max))
            except Exception:
                was_maximized = False
        primary = QtGui.QGuiApplication.primaryScreen()
        avail_primary = primary.availableGeometry()

        if isinstance(geom_data, QtCore.QByteArray) and not was_maximized:
            tmp = QtWidgets.QWidget()
            tmp.restoreGeometry(geom_data)
            rect = tmp.frameGeometry()
            width = min(rect.width(), avail_primary.width())
            height = min(rect.height(), avail_primary.height())

            center = rect.center()
            screen = QtGui.QGuiApplication.screenAt(center) or primary
            avail = screen.availableGeometry()

            x = max(avail.left(), min(rect.x(), avail.right() - width))
            y = max(avail.top(), min(rect.y(), avail.bottom() - height))
            self.setGeometry(x, y, width, height)
        else:
            self.resize(self.sizeHint())
            x = avail_primary.x() + (avail_primary.width() - self.width()) // 2
            y = avail_primary.y() + (avail_primary.height() - self.height()) // 2
            self.move(x, y)

        state = settings.value('MainWindow/windowState')
        if isinstance(state, QtCore.QByteArray):
            self.restoreState(state)

        if was_maximized:
            self.showMaximized()
        else:
            self.clamp_window_to_screens()
        # synchronize toolbar toggle button states with dock visibility
        self._sync_dock_toggle_actions()

    def clamp_window_to_screens(self) -> None:
        frame = self.frameGeometry()
        center = frame.center()
        screen = QtGui.QGuiApplication.screenAt(center) or QtGui.QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()

        width = min(frame.width(), avail.width())
        height = min(frame.height(), avail.height())

        x = max(avail.left(), min(frame.x(), avail.right() - width))
        y = max(avail.top(), min(frame.y(), avail.bottom() - height))

        self.setGeometry(x, y, width, height)

    def _sync_dock_toggle_actions(self) -> None:
        """Ensure toolbar toggle buttons reflect current dock visibility."""
        for view in (
                self.presets_view,
                self.transactions_view,
                self.transaction_preview,
                self.trends_view,
                self.piechart_view,
                self.doughnut_view,
                self.log_view,
                self.settings_view,
        ):
            view.toggled.emit(view.isVisible())
