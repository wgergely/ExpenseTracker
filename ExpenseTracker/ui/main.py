import enum
import functools

from PySide6 import QtWidgets, QtCore, QtGui

from . import ui
from .yearmonth import RangeSelectorBar
from ..core import database
from ..data.view.expense import ExpenseView
from ..data.view.transaction import TransactionsWidget
from ..data.view.trends import TrendDockWidget
from ..log.view import LogDockWidget
from ..settings.lib import app_name
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


class Edge(enum.Flag):
    NONE = 0
    LEFT = enum.auto()
    TOP = enum.auto()
    RIGHT = enum.auto()
    BOTTOM = enum.auto()
    TOP_LEFT = TOP | LEFT
    TOP_RIGHT = TOP | RIGHT
    BOTTOM_LEFT = BOTTOM | LEFT
    BOTTOM_RIGHT = BOTTOM | RIGHT


CURSOR_MAP: dict[Edge, QtCore.Qt.CursorShape] = {
    Edge.LEFT: QtCore.Qt.SizeHorCursor,
    Edge.RIGHT: QtCore.Qt.SizeHorCursor,
    Edge.TOP: QtCore.Qt.SizeVerCursor,
    Edge.BOTTOM: QtCore.Qt.SizeVerCursor,
    Edge.TOP_LEFT: QtCore.Qt.SizeFDiagCursor,
    Edge.BOTTOM_RIGHT: QtCore.Qt.SizeFDiagCursor,
    Edge.TOP_RIGHT: QtCore.Qt.SizeBDiagCursor,
    Edge.BOTTOM_LEFT: QtCore.Qt.SizeBDiagCursor,
}


class TitleLabel(QtWidgets.QWidget):

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)

        painter.fillRect(self.rect(), ui.Color.VeryDarkBackground())

        font, _ = ui.Font.BoldFont(ui.Size.MediumText(1.2))
        painter.setFont(font)

        color = ui.Color.Text()

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(color)

        path = QtGui.QPainterPath()
        path.addText(0, 0, font, self.window().windowTitle())

        br = path.boundingRect()
        dx = (self.width() - br.width()) * 0.5 - br.left()
        dy = (self.height() - br.height()) * 0.5 - br.top()
        m = QtGui.QTransform().translate(dx, dy)

        painter.drawPath(m.map(path))


class TitleBar(QtWidgets.QWidget):
    """A custom title bar with branding and window controls."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent=parent)
        self._drag_pos = None
        self.icon_label = None
        self.title_label = None

        h = ui.Size.RowHeight(1.0)
        self.setFixedHeight(h)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Fixed
        )

        self._create_ui()
        self._connect_signals()
        self._init_actions()

    def _create_ui(self) -> None:
        QtWidgets.QHBoxLayout(self)

        o = ui.Size.Margin(1.0)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(ui.Size.Indicator(2.0))

        # Icon
        self.icon_label = QtWidgets.QToolButton(self)
        self.icon_label.setFocusPolicy(QtCore.Qt.NoFocus)

        self.icon_label.setIcon(ui.get_icon('btn_ledger', color=ui.Color.Green))
        self.icon_label.setFixedSize(ui.Size.Margin(1.0), ui.Size.Margin(1.0))
        self.layout().addWidget(self.icon_label, 0)

        # Title
        self.title_label = TitleLabel(parent=self)
        self.layout().addWidget(self.title_label, 1)

        self.layout().addStretch(1)

        # Min button
        self.btn_min = QtWidgets.QToolButton(self)
        self.btn_min.setIcon(ui.get_icon('btn_minimize'))
        self.btn_min.setFocusPolicy(QtCore.Qt.NoFocus)
        self.btn_min.setFixedSize(o, o)
        self.btn_min.setCursor(QtCore.Qt.ArrowCursor)
        self.btn_min.setAutoRaise(True)
        self.layout().addWidget(self.btn_min, 0)

        # Max button
        self.btn_max = QtWidgets.QToolButton(self)
        self.btn_max.setIcon(ui.get_icon('btn_maximize'))
        self.btn_max.setFocusPolicy(QtCore.Qt.NoFocus)
        self.btn_max.setFixedSize(o, o)
        self.btn_max.setCursor(QtCore.Qt.ArrowCursor)
        self.btn_max.setAutoRaise(True)
        self.layout().addWidget(self.btn_max, 0)

        # Close button
        self.btn_close = QtWidgets.QToolButton(self)
        self.btn_close.setIcon(ui.get_icon('btn_close'))
        self.btn_close.setFocusPolicy(QtCore.Qt.NoFocus)
        self.btn_close.setFixedSize(o, o)
        self.btn_close.setCursor(QtCore.Qt.ArrowCursor)
        self.btn_close.setAutoRaise(True)
        self.layout().addWidget(self.btn_close, 0)

    def _init_actions(self) -> None:
        pass

    def _connect_signals(self) -> None:
        self.btn_min.clicked.connect(self.window().showMinimized)
        self.btn_max.clicked.connect(self.toggle_max_restore)
        self.btn_close.clicked.connect(self.window().close)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.buttons() & QtCore.Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.window().move(self.window().pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        self.toggle_max_restore()
        super().mouseDoubleClickEvent(event)

    @QtCore.Slot()
    def toggle_max_restore(self) -> None:
        if self.window().isMaximized():
            self.window().showNormal()
            self.btn_max.setIcon(ui.get_icon('btn_maximize'))
        else:
            self.window().showMaximized()
            self.btn_max.setIcon(ui.get_icon('btn_fullscreen'))


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
        self.setWindowTitle(app_name)

        self.setObjectName('ExpenseTrackerMainWindow')

        self._edge_at_press = None
        self._press_pos = None
        self._press_rect = None

        self.title_bar = None
        self.content_area = None

        self.toolbar = None
        self.range_selector = None
        self.expense_view = None
        self.transactions_view = None
        self.transactions_view = None
        self.presets_popup = None
        self.status_indicator = None

        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # Drop shadow
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(ui.Size.Margin(2.0))
        shadow.setOffset(0, 0)
        shadow.setColor(QtGui.QColor(0, 0, 0, 150))
        self.setGraphicsEffect(shadow)

        self._create_ui()
        self._init_actions()
        self._connect_signals()
        self.load_window_settings()

    def _create_ui(self):
        o = ui.Size.Margin(2.0)
        self.setContentsMargins(o, o, o, o)

        self.title_bar = TitleBar(self)
        self.setMenuWidget(self.title_bar)

        central = QtWidgets.QWidget(self)
        QtWidgets.QVBoxLayout(central)
        o = ui.Size.Margin(1.0)
        central.layout().setContentsMargins(o, 0, o, o)
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

        # Add trend dock (bottom)
        self.trends_view = TrendDockWidget(parent=self)
        self.trends_view.setObjectName('ExpenseTrackerTrendDockWidget')
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.trends_view)
        self.trends_view.hide()

    def _connect_signals(self):
        signals.openTransactions.connect(
            lambda: self.transactions_view.setHidden(not self.transactions_view.isHidden()))
        signals.showLogs.connect(lambda: (self.log_view.show(), self.log_view.raise_()))

    def _init_actions(self):
        # Window action
        action = QtGui.QAction('Toggle Fullscreen', self)
        action.setIcon(ui.get_icon('btn_fullscreen'))
        action.setToolTip('Toggle fullscreen')
        action.setStatusTip('Toggle fullscreen')
        action.setShortcut('F11')
        action.triggered.connect(self.toggle_fullscreen)
        self.addAction(action)

        action = QtGui.QAction('Maximize', self)
        action.setIcon(ui.get_icon('btn_maximize'))
        action.setToolTip('Maximize')
        action.setStatusTip('Maximize')
        action.setShortcut('Ctrl+M')
        action.triggered.connect(self.showMaximized)
        self.addAction(action)

        action = QtGui.QAction('Minimize', self)
        action.setIcon(ui.get_icon('btn_minimize'))
        action.setToolTip('Minimize')
        action.setStatusTip('Minimize')
        action.setShortcut('Ctrl+Shift+M')
        action.triggered.connect(self.showMinimized)
        self.addAction(action)

        # Separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

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

    def _hit_test(self, pos: QtCore.QPoint) -> Edge:
        """Hit test which edge or corner the pointer is over."""
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        b = ui.Size.Indicator(1.0)
        left = x <= b
        right = x >= w - b
        top = y <= b
        bottom = y >= h - b
        if top and left:
            return Edge.TOP_LEFT
        if top and right:
            return Edge.TOP_RIGHT
        if bottom and left:
            return Edge.BOTTOM_LEFT
        if bottom and right:
            return Edge.BOTTOM_RIGHT
        if left:
            return Edge.LEFT
        if right:
            return Edge.RIGHT
        if top:
            return Edge.TOP
        if bottom:
            return Edge.BOTTOM
        return Edge.NONE

    def resize_window(self, edge: Edge, gp: QtCore.QPoint) -> None:
        """Resize the window according to the dragged edge and global pointer."""
        delta = gp - self._press_pos
        geom = QtCore.QRect(self._press_rect)
        if edge & Edge.LEFT:
            geom.setLeft(geom.left() + delta.x())
        if edge & Edge.RIGHT:
            geom.setRight(geom.right() + delta.x())
        if edge & Edge.TOP:
            geom.setTop(geom.top() + delta.y())
        if edge & Edge.BOTTOM:
            geom.setBottom(geom.bottom() + delta.y())

        # enforce minimum size
        min_w, min_h = self.minimumWidth(), self.minimumHeight()
        if geom.width() < min_w:
            geom.setWidth(min_w)
        if geom.height() < min_h:
            geom.setHeight(min_h)
        if not self.isMaximized():
            self.setGeometry(geom)

    def sizeHint(self):
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.5)
        )

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        o = ui.Size.Margin(1.0)
        rect = self.rect().adjusted(
            o, o * 2, -o, -o
        )
        c = ui.Size.Indicator(2.0)

        color = ui.Color.VeryDarkBackground()
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(color)

        painter.drawRoundedRect(
            rect,
            c, c
        )

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self._edge_at_press = self._hit_test(event.pos())
            self._press_rect = self.geometry()
            self._press_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        edge = self._hit_test(event.pos()) if not (event.buttons() & QtCore.Qt.LeftButton) else self._edge_at_press

        cursor = CURSOR_MAP.get(edge, QtCore.Qt.ArrowCursor)
        if self.cursor().shape() != cursor:
            self.setCursor(QtGui.QCursor(cursor))

        if event.buttons() & QtCore.Qt.LeftButton and edge != Edge.NONE:
            self.resize_window(edge, event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._edge_at_press = Edge.NONE
        super().mouseReleaseEvent(event)

    def closeEvent(self, event) -> None:
        """Persist window geometry and state on close."""
        settings = QtCore.QSettings(app_name, app_name)
        settings.setValue('MainWindow/geometry', self.saveGeometry())
        settings.setValue('MainWindow/windowState', self.saveState())
        super().closeEvent(event)

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

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def load_window_settings(self) -> None:
        settings = QtCore.QSettings(app_name, app_name)
        geom = settings.value('MainWindow/geometry')

        if isinstance(geom, QtCore.QByteArray):
            self.restoreGeometry(geom)
        else:
            screen = QtGui.QGuiApplication.primaryScreen()

            self.resize(self.sizeHint())
            avail = screen.availableGeometry()

            x = avail.x() + (avail.width() - self.width()) // 2
            y = avail.y() + (avail.height() - self.height()) // 2
            self.move(x, y)

        state = settings.value('MainWindow/windowState')
        if isinstance(state, QtCore.QByteArray):
            self.restoreState(state)

        self.clamp_window_to_screens()

    def clamp_window_to_screens(self) -> None:
        screen = QtGui.QGuiApplication.screenAt(self.frameGeometry().center()) or QtGui.QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        geom = self.geometry()
        x = max(avail.left(), min(geom.x(), avail.right() - geom.width()))
        y = max(avail.top(), min(geom.y(), avail.bottom() - geom.height()))
        geom.moveTopLeft(QtCore.QPoint(x, y))
        self.setGeometry(geom)
