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
from typing import Optional

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
        self._configure_dock_behavior()
        self.setWindowTitle(app_name)
        self.setObjectName('ExpenseTrackerMainWindow')
        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        # Predeclare UI elements for type clarity
        self.toolbar: QtWidgets.QToolBar
        self.range_selector: RangeSelectorBar
        self.expense_view: ExpenseView
        self.status_indicator: StatusIndicator

        # Placeholders for dock widgets
        self.transactions_view: TransactionsDockWidget
        self.transaction_preview: TransactionDetailsDockWidget
        self.presets_view: PresetsDockWidget
        self.settings_view: SettingsDockWidget
        self.log_view: LogDockWidget
        self.trends_view: TrendDockWidget
        self.piechart_view: PieChartDockWidget
        self.doughnut_view: DoughnutDockWidget

        self._create_ui()
        self._init_actions()
        self._connect_signals()
        self.load_window_settings()

    def _configure_dock_behavior(self) -> None:
        """
        Enable nested and animated docking, and set default tab positions for all dock areas.
        """
        opts = self.dockOptions()
        opts |= QtWidgets.QMainWindow.AllowNestedDocks | QtWidgets.QMainWindow.AnimatedDocks
        self.setDockOptions(opts)

        positions = [
            (QtCore.Qt.LeftDockWidgetArea, QtWidgets.QTabWidget.West),
            (QtCore.Qt.RightDockWidgetArea, QtWidgets.QTabWidget.East),
            (QtCore.Qt.TopDockWidgetArea, QtWidgets.QTabWidget.North),
            (QtCore.Qt.BottomDockWidgetArea, QtWidgets.QTabWidget.South),
        ]
        for area, pos in positions:
            self.setTabPosition(area, pos)
            logging.debug(f'Set tab position for {area} to {pos}')

    def _create_ui(self) -> None:
        """
        Build the main UI: central widget, toolbar, main view and docks based on configuration.
        """
        # Title bar and central layout
        self.setMenuWidget(TitleBar(self))
        central = QtWidgets.QWidget(self)
        central.setProperty('rounded', True)
        layout = QtWidgets.QVBoxLayout(central)
        margin = ui.Size.Margin(1.0)
        layout.setContentsMargins(margin, 0, margin, margin)
        layout.setSpacing(margin * 0.5)
        self.setCentralWidget(central)

        # Toolbar setup
        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.setProperty('transparent', True)
        self.toolbar.setProperty('no_background', True)
        self.toolbar.setObjectName('ExpenseTrackerActionToolBar')
        self.menuWidget().layout().insertWidget(1, self.toolbar, 1)

        # Core widgets
        self.range_selector = RangeSelectorBar(parent=self)
        self.range_selector.setObjectName('ExpenseTrackerRangeSelector')
        self.toolbar.addWidget(self.range_selector)

        self.expense_view = ExpenseView(parent=central)
        self.expense_view.setObjectName('ExpenseTrackerExpenseView')
        layout.addWidget(self.expense_view, 1)

        self.status_indicator = StatusIndicator(parent=self)

        # Dock configuration list including default areas
        dock_configs = [
            {
                'attr': 'transactions_view',
                'class': TransactionsDockWidget,
                'name': 'ExpenseTrackerTransactionsView',
                'area': QtCore.Qt.RightDockWidgetArea},
            {
                'attr': 'transaction_preview',
                'class': TransactionDetailsDockWidget,
                'name': 'ExpenseTrackerTransactionDetailsDockWidget',
                'area': QtCore.Qt.RightDockWidgetArea},
            {
                'attr': 'presets_view',
                'class': PresetsDockWidget,
                'name': 'ExpenseTrackerPresetsDockWidget',
                'area': QtCore.Qt.LeftDockWidgetArea},
            {
                'attr': 'settings_view',
                'class': SettingsDockWidget,
                'name': 'ExpenseTrackerSettingsDockWidget',
                'area': QtCore.Qt.LeftDockWidgetArea},
            {
                'attr': 'log_view',
                'class': LogDockWidget,
                'name': 'ExpenseTrackerLogDockWidget',
                'area': QtCore.Qt.BottomDockWidgetArea},
            {
                'attr': 'trends_view',
                'class': TrendDockWidget,
                'name': 'ExpenseTrackerTrendDockWidget',
                'area': QtCore.Qt.RightDockWidgetArea},
            {
                'attr': 'piechart_view',
                'class': PieChartDockWidget,
                'name': 'ExpenseTrackerPieChartDockWidget',
                'area': QtCore.Qt.RightDockWidgetArea},
            {
                'attr': 'doughnut_view',
                'class': DoughnutDockWidget,
                'name': 'ExpenseTrackerDoughnutDockWidget',
                'area': QtCore.Qt.RightDockWidgetArea},
        ]
        for cfg in dock_configs:
            widget = cfg['class'](parent=self)
            setattr(self, cfg['attr'], widget)
            widget.setObjectName(cfg['name'])
            self.addDockWidget(cfg['area'], widget)
            widget.hide()

            logging.debug(f'Added dock {cfg["name"]} in area {cfg["area"]}')

    def _init_actions(self) -> None:
        """
        Create and register toolbar/menu actions defined by configuration.
        """

        def _make_action(_cfg: dict) -> Optional[QtGui.QAction]:
            if _cfg.get('separator'):
                action = QtGui.QAction(self)
                action.setSeparator(True)
                action.setEnabled(False)
                return action

            if 'widget_action' in _cfg:
                _cfg['widget_action']()
                return None

            action = QtGui.QAction(_cfg['label'], self)
            if 'icon' in _cfg:
                action.setIcon(ui.get_icon(_cfg['icon'], color=ui.Color.DisabledText))
            if 'trigger' in _cfg:
                action.triggered.connect(_cfg['trigger'])

            def toggle_visibility(widget, checked=None):
                checked = checked if checked is not None else widget.isVisible()
                widget.setHidden(checked)

            def set_action_icon(widget, action, icon, checked):
                color = ui.Color.Green if checked else ui.Color.DisabledText
                action.setIcon(ui.get_icon(icon, color=color))

            # Toggle behavior for dock widgets
            if 'widget_attr' in _cfg:
                _widget = getattr(self, _cfg['widget_attr'])
                action.setCheckable(True)
                action.setChecked(_widget.isVisible())

                toggle_visibility_func = functools.partial(toggle_visibility, _widget)
                set_action_icon_func = functools.partial(set_action_icon, _widget, action, cfg['icon'])

                action.triggered.connect(toggle_visibility_func)
                _widget.toggled.connect(set_action_icon_func)

            # Shortcuts
            if 'shortcut' in _cfg:
                action.setShortcut(_cfg['shortcut'])
            if 'shortcuts' in cfg:
                action.setShortcuts(_cfg['shortcuts'])
            if any(k in _cfg for k in ('shortcut', 'shortcuts')):
                action.setShortcutContext(QtCore.Qt.ApplicationShortcut)

            return action

        # Spacer helper for toolbar
        def _spacer() -> QtWidgets.QWidget:
            w = QtWidgets.QWidget(self)
            w.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
            w.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
            w.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Maximum)
            return w

        action_configs = [
            {
                'label': 'Maximize',
                'icon': 'btn_maximize',
                'trigger': self.toggle_maximised,
                'shortcut': 'Ctrl+M',
                'visible': False
            },
            {'widget_action': lambda: self.toolbar.addWidget(_spacer())},
            {
                'label': 'Open Spreadsheet',
                'icon': 'btn_ledger',
                'trigger': signals.openSpreadsheet,
                'shortcut': 'Ctrl+Shift+O'
            },
            {'separator': True},
            {
                'label': 'Presets',
                'widget_attr': 'presets_view',
                'icon': 'btn_presets',
                'shortcut': 'Ctrl+0'
            },
            {
                'label': 'Transactions',
                'widget_attr': 'transactions_view',
                'icon': 'btn_transactions',
                'shortcut': 'Ctrl+1'
            },
            {
                'label': 'Preview',
                'widget_attr': 'transaction_preview',
                'icon': 'btn_TransactionDetails',
                'shortcut': 'Ctrl+2'
            },
            {'separator': True},
            {
                'label': 'Trends',
                'widget_attr': 'trends_view',
                'icon': 'btn_trend',
                'shortcut': 'Ctrl+3'
            },
            {
                'label': 'Pie Chart',
                'widget_attr': 'piechart_view',
                'icon': 'btn_piechart',
                'shortcut': 'Ctrl+4'
            },
            {
                'label': 'Doughnut Chart',
                'widget_attr': 'doughnut_view',
                'icon': 'btn_doughnut',
                'shortcut': 'Ctrl+5'
            },
            {'separator': True},
            {
                'label': 'Logs',
                'widget_attr': 'log_view',
                'icon': 'btn_log',
                'shortcut': 'Ctrl+6'
            },
            {
                'label': 'Settings',
                'widget_attr': 'settings_view',
                'icon': 'btn_settings',
                'shortcut': 'Ctrl+0'
            },
            {'separator': True},
            {
                'label': 'Previous Month',
                'trigger': self.range_selector.previous_month,
                'shortcut': 'Ctrl+Left',
                'visible': False
            },
            {
                'label': 'Next Month',
                'trigger': self.range_selector.next_month,
                'shortcut': 'Ctrl+Right',
                'visible': False
            },
            {
                'label': 'Refresh Data',
                'icon': 'btn_sync',
                'trigger': signals.dataFetchRequested}
        ]

        for cfg in action_configs:
            act = _make_action(cfg)
            if not act:
                continue
            if cfg.get('visible', True):
                self.toolbar.addAction(act)
            self.addAction(act)
            logging.debug(f'Added action: {cfg.get("label", "separator")}')

        # Append status indicator widget
        self.toolbar.addWidget(self.status_indicator)

    def _connect_signals(self) -> None:
        """
        Wire up app-level signals to corresponding dock visibility.
        """
        signals.showTransactions.connect(lambda: (self.transactions_view.show(), self.transactions_view.raise_()))
        signals.showLogs.connect(lambda: (self.log_view.show(), self.log_view.raise_()))
        signals.showSettings.connect(self.settings_view.show)
        signals.showTransactionPreview.connect(self.transaction_preview.show)

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
